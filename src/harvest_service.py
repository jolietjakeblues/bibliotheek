"""Oogst de bibliotheek en schrijf schema.org JSON-LD in chunks.

Gebruik:
    python src/harvest_service.py --source books --chunks 7000
    python src/harvest_service.py --source all --max-records 50      # snelle test

Bronnen (zie config/config.yml):
  books    volledige records uit het Adlib-API. De OAI-set `books` bepaalt welke records openbaar zijn (scope: oai).
  article  titel en onderwerpen uit het Adlib-API, tijdschrift/jaar/pagina's uit OAI `oai_dc`, samengevoegd op priref.

Per bron ontstaan `{CACHE_PATH}{bron}-0000.jsonld`, `-0001.jsonld`, ... en `{CACHE_PATH}manifest-{bron}.json`.
Controles (de run faalt, zodat er niets gepubliceerd wordt):
  - OAI: opgehaald == completeListSize; API: opgehaald == diagnostic/hits;
  - weggeschreven + fouten == wat we wilden schrijven (niets raakt stilzwijgend kwijt);
  - records die de OAI publiceert maar het API niet kent blijven binnen MAX_MISSING_IN_API;
  - het aantal transformatiefouten blijft binnen MAX_RECORD_ERRORS.
"""
import argparse
import datetime
import json
import logging
import os
import sys
import traceback

import yaml
from rdflib import Graph

import adlib_client
import oai_client
import transform_service
import uris

logger = logging.getLogger(__name__)


def load_config(path: str = None) -> dict:
    path = path or os.getenv('CONFIG_PATH', 'config/config.yml')
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


class ChunkWriter:
    """Verzamelt records in een graph en schrijft elke `chunk_size` records een bestand weg.

    Elke chunk bevat de dataset- en organisatie-node, zodat elk bestand op zichzelf valideerbaar is."""

    def __init__(self, config: dict, cache_path: str, source_name: str, chunk_size: int, state: dict):
        self.config, self.cache_path, self.source_name = config, cache_path, source_name
        self.chunk_size, self.state = chunk_size, state
        self.graph, self.count = uris.get_dataset(config), 0

    def add(self, transform, *args) -> bool:
        """Transformeer één record in de huidige chunk. Een fout telt, en de rest van het record blijft buiten de graph."""
        scratch = Graph()
        try:
            transform(scratch, self.config, *args)
        except Exception as e:  # niet stilzwijgend doorgaan: tel de fout, de run beoordeelt het totaal
            self.state['errors'] += 1
            self.state['error_ids'].append(args[0]['identifier'] if isinstance(args[0], dict) else args[0].get('priref'))
            logger.warning('Fout bij transformatie van %s: %s', self.state['error_ids'][-1],
                           ''.join(traceback.format_exception_only(type(e), e)).strip())
            return False
        self.graph += scratch
        self.count += 1
        if self.count >= self.chunk_size:
            self.flush()
        return True

    def flush(self):
        if self.count == 0:
            return
        path = f"{self.cache_path}{self.source_name}-{self.state['files']:04d}.jsonld"
        self.graph.serialize(format='json-ld', destination=path, encoding='utf-8', auto_compact=True)
        logger.info('Geschreven: %s (%d records, %.0f KB)', path, self.count, os.path.getsize(path) / 1000)
        self.state['files'] += 1
        self.state['written'] += self.count
        self.graph, self.count = uris.get_dataset(self.config), 0


def new_state() -> dict:
    return {'oai_seen': 0, 'oai_expected': None, 'api_seen': 0, 'api_hits': None, 'skipped': 0, 'skipped_reasons': {},
            'errors': 0, 'error_ids': [], 'api_duplicates': 0, 'written': 0, 'files': 0, 'out_of_scope': 0, 'missing_in_api': 0,
            'missing_ids': [], 'intended': 0, 'limited': False}


def _skip(state: dict, reason: str):
    state['skipped'] += 1
    state['skipped_reasons'][reason] = state['skipped_reasons'].get(reason, 0) + 1


def _oai_args(config: dict, source: dict, max_records):
    return dict(sleep_between=float(config.get('SRC_SLEEP', 0.2)), retries=int(config.get('SRC_RETRIES', 5)),
                backoff=float(config.get('SRC_BACKOFF', 2.0)), max_records=max_records)


def _api_iter(config: dict, source: dict, api_state: dict, cap):
    return adlib_client.iter_records(
        config['SRC_API'], config.get('SRC_API_DATABASE', 'books'), source['api_search'], api_state,
        limit=int(config.get('SRC_API_LIMIT', 500)), workers=int(config.get('SRC_API_WORKERS', 3)),
        retries=int(config.get('SRC_RETRIES', 5)), backoff=float(config.get('SRC_BACKOFF', 2.0)), max_records=cap)


def harvest_books(config: dict, source: dict, writer: ChunkWriter, state: dict, max_records=None):
    scope = None
    if source.get('scope', 'oai') == 'oai':
        oai_state = {}
        scope = set()
        logger.info('Selectie ophalen: OAI set=%s (alleen de identifiers)', source['oai']['set'])
        for header in oai_client.iter_headers(config['SRC_URI'], source['oai']['set'], source['oai']['prefix'],
                                              oai_state, **_oai_args(config, source, max_records)):
            if header['deleted']:
                _skip(state, 'deleted')
            else:
                scope.add(transform_service.record_priref(header['identifier']))
        state['oai_seen'], state['oai_expected'] = oai_state['seen'], oai_state.get('complete_list_size')
        state['intended'] = len(scope)
        logger.info('Selectie: %d records', len(scope))

    api_state = {}
    found = set()
    cap = None if max_records is None else max_records * 3 + 500
    for record in _api_iter(config, source, api_state, cap):
        priref = record.get('priref')
        if scope is not None:
            if priref not in scope:
                state['out_of_scope'] += 1
                continue
            found.add(priref)
        else:
            state['intended'] += 1
        writer.add(transform_service.transform_book, record, source)
        if api_state['seen'] % 5000 == 0:
            logger.info('books: %d/%s API-records verwerkt', api_state['seen'], api_state.get('hits'))
    state['api_seen'], state['api_hits'] = api_state['seen'], api_state.get('hits')
    state['api_duplicates'] = api_state.get('duplicates', 0)
    if scope is not None:
        missing = sorted(scope - found, key=int)
        state['missing_in_api'] = len(missing)
        state['missing_ids'] = missing[:200]


def harvest_articles(config: dict, source: dict, writer: ChunkWriter, state: dict, max_records=None):
    oai_state = {}
    oai_records = {}
    logger.info('OAI ophalen: set=%s prefix=%s', source['oai']['set'], source['oai']['prefix'])
    for header, element in oai_client.iter_records(config['SRC_URI'], source['oai']['set'], source['oai']['prefix'],
                                                   oai_state, **_oai_args(config, source, max_records)):
        if header['deleted']:
            _skip(state, 'deleted')
        elif element is None:
            _skip(state, 'geen metadata')
        elif not header['identifier']:
            _skip(state, 'geen identifier')
        else:
            oai_records[transform_service.record_priref(header['identifier'])] = (
                header, transform_service.collect_fields(element))
    state['oai_seen'], state['oai_expected'] = oai_state['seen'], oai_state.get('complete_list_size')
    state['intended'] = len(oai_records)
    logger.info('OAI: %d artikelen', len(oai_records))

    api_state = {}
    done = set()
    cap = None if max_records is None else max_records * 3 + 500
    for record in _api_iter(config, source, api_state, cap):
        priref = record.get('priref')
        if priref not in oai_records:
            state['out_of_scope'] += 1
            continue
        header, fields = oai_records[priref]
        done.add(priref)
        writer.add(transform_service.transform_article, header, fields, source, record)
        if api_state['seen'] % 5000 == 0:
            logger.info('article: %d/%s API-records verwerkt', api_state['seen'], api_state.get('hits'))
    state['api_seen'], state['api_hits'] = api_state['seen'], api_state.get('hits')
    state['api_duplicates'] = api_state.get('duplicates', 0)

    # OAI-artikelen die het API niet kent: wel schrijven (tijdschriftgegevens), maar tellen en bewaken
    leftover = sorted((p for p in oai_records if p not in done), key=int)
    state['missing_in_api'] = len(leftover)
    state['missing_ids'] = leftover[:200]
    for priref in leftover:
        header, fields = oai_records[priref]
        writer.add(transform_service.transform_article, header, fields, source, None)


def harvest_source(config: dict, source_name: str, cache_path: str, chunk_size: int, max_records=None) -> dict:
    """Oogst één bron en geef de state terug (tellers, volledigheid)."""
    source = config['SOURCES'][source_name]
    state = new_state()
    state['limited'] = max_records is not None
    writer = ChunkWriter(config, cache_path, source_name, chunk_size, state)
    logger.info('Start oogst %s (%s)', source_name, source['kind'])
    if source['kind'] == 'book':
        harvest_books(config, source, writer, state, max_records)
    else:
        harvest_articles(config, source, writer, state, max_records)
    writer.flush()                       # ook de LAATSTE (kleinere) chunk moet weggeschreven worden
    return state


def verify_completeness(state: dict, source: dict, max_record_errors: int, max_missing: int) -> bool:
    """Vergelijk wat we gezien en verwerkt hebben met wat de bronnen aankondigen."""
    if state['limited']:
        logger.info('Beperkte run (--max-records): volledigheidscontrole overgeslagen.')
        return True
    ok = True
    uses_oai = source.get('scope', 'oai') == 'oai' or source['kind'] == 'article'
    if uses_oai:
        if state['oai_expected'] is None:
            logger.error('De OAI gaf geen completeListSize; volledigheid kan niet worden gecontroleerd.')
            ok = False
        elif state['oai_seen'] != state['oai_expected']:
            logger.error('ONVOLLEDIG (OAI): bron kondigt %d records aan, %d opgehaald.', state['oai_expected'],
                         state['oai_seen'])
            ok = False
    if state['api_hits'] is None or state['api_seen'] != state['api_hits']:
        logger.error('ONVOLLEDIG (API): bron kondigt %s records aan, %d opgehaald (%d dubbel geleverd).',
                     state['api_hits'], state['api_seen'], state['api_duplicates'])
        ok = False
    # boeken: wat de OAI publiceert maar het API niet kent, wordt niet geschreven; artikelen worden dan alleen uit de OAI geschreven
    not_written = state['missing_in_api'] if source['kind'] == 'book' else 0
    if state['written'] + state['errors'] + not_written != state['intended']:
        logger.error('Rekenfout: weggeschreven (%d) + fouten (%d) + niet in API (%d) != beoogd (%d).',
                     state['written'], state['errors'], not_written, state['intended'])
        ok = False
    if state['missing_in_api'] > max_missing:
        logger.error('%d records staan in de OAI maar niet in het API (toegestaan: %d): %s', state['missing_in_api'],
                     max_missing, ', '.join(state['missing_ids'][:20]))
        ok = False
    if state['errors'] > max_record_errors:
        logger.error('%d records konden niet getransformeerd worden (toegestaan: %d): %s', state['errors'],
                     max_record_errors, ', '.join(map(str, state['error_ids'][:20])))
        ok = False
    logger.info('Controle: OAI %s/%s, API %s/%s, beoogd=%d, weggeschreven=%d, fouten=%d, niet in API=%d -> %s',
                state['oai_seen'], state['oai_expected'], state['api_seen'], state['api_hits'], state['intended'],
                state['written'], state['errors'], state['missing_in_api'], 'OK' if ok else 'MISLUKT')
    return ok


def write_manifest(cache_path: str, source_name: str, state: dict, complete: bool):
    keys = ('oai_seen', 'oai_expected', 'api_seen', 'api_hits', 'api_duplicates', 'intended', 'written', 'files', 'errors', 'skipped',
            'skipped_reasons', 'out_of_scope', 'missing_in_api')
    manifest = {k: state.get(k) for k in keys}
    manifest['source'] = source_name
    manifest['error_ids'] = state.get('error_ids', [])[:200]
    manifest['missing_ids'] = state.get('missing_ids', [])[:200]
    manifest['complete'] = complete
    manifest['finished_at'] = datetime.datetime.now().replace(microsecond=0).isoformat()
    with open(f'{cache_path}manifest-{source_name}.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)


def main(argv=None) -> int:
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO,
                        datefmt='%Y-%m-%d %H:%M:%S')
    parser = argparse.ArgumentParser('Bibliotheek RCE ETL: oogst en transformeer')
    parser.add_argument('--source', default='all', help="Naam van de bron in config (books, article) of 'all'.")
    parser.add_argument('--chunks', type=int, default=7000, help='Aantal records per JSON-LD-bestand.')
    parser.add_argument('--max-records', type=int, default=None, help='Stop na dit aantal records (test).')
    args = parser.parse_args(argv)

    config = load_config()
    cache_path = os.getenv('CACHE_PATH', 'data/')
    if not cache_path.endswith(('/', os.sep)):
        cache_path += '/'
    os.makedirs(cache_path, exist_ok=True)
    names = list(config['SOURCES']) if args.source == 'all' else [args.source]
    unknown = [n for n in names if n not in config['SOURCES']]
    if unknown:
        logger.error('Onbekende bron: %s (beschikbaar: %s)', ', '.join(unknown), ', '.join(config['SOURCES']))
        return 2

    all_ok = True
    for name in names:
        state = harvest_source(config, name, cache_path, args.chunks, args.max_records)
        complete = verify_completeness(state, config['SOURCES'][name], int(config.get('MAX_RECORD_ERRORS', 0)),
                                       int(config.get('MAX_MISSING_IN_API', 0)))
        write_manifest(cache_path, name, state, complete)
        all_ok = all_ok and complete
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
