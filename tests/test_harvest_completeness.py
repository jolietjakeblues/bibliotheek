"""Volledigheid van de oogst: scope uit de OAI, records uit het API, laatste chunk, en alles wat de run moet laten falen."""
import json
import xml.etree.ElementTree as ET

import pytest
import yaml

import adlib_client
import harvest_service
import oai_client
import transform_service
from conftest import ROOT

OAI = 'http://www.openarchives.org/OAI/2.0/'


# --- nepbronnen -----------------------------------------------------------

def _header(db, i, deleted=False):
    status = ' status="deleted"' if deleted else ''
    return f'<header{status}><identifier>{db}:{i}</identifier><datestamp>2026-01-01T00:00:00Z</datestamp></header>'


def _oai_pages(verb, db, ids, announced, page_size=5, deleted=(), article_fields=False):
    pages = []
    ids = list(ids)
    for n, first in enumerate(range(0, len(ids), page_size)):
        chunk = ids[first:first + page_size]
        last = first + page_size >= len(ids)
        rt = f'<resumptionToken completeListSize="{announced}">{"" if last else f"t{n + 1}"}</resumptionToken>'
        if verb == 'ListIdentifiers':
            body = ''.join(_header(db, i, i in deleted) for i in chunk)
        else:
            body = ''.join(
                '<record>' + _header(db, i, i in deleted) + (
                    '' if i in deleted else
                    '<metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    f'<dc:source>journal = {{Tijdschrift ; </dc:source><dc:source>(1990)</dc:source>'
                    f'<dc:source>, {i}-{i + 1}}},</dc:source></oai_dc:dc></metadata>') + '</record>'
                for i in chunk)
        pages.append(f'<OAI-PMH xmlns="{OAI}"><{verb}>{body}{rt}</{verb}></OAI-PMH>')
    return pages


def _api_record(i):
    return ET.fromstring(f'<record priref="{i}" modification="2026-01-01T00:00:00"><priref>{i}</priref>'
                         f'<Title><lead_word/><title>Titel {i}</title></Title></record>')


def _setup(monkeypatch, tmp_path, source, ids, oai_announced=None, api_ids=None, api_hits=None, deleted=(),
           **config_overrides):
    """Zet nepbronnen en een tijdelijke config neer. `ids` = wat de OAI-set bevat, `api_ids` = wat het API kent."""
    with open(ROOT / 'config' / 'config.yml', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    cfg.update({'SRC_API_LIMIT': 10, 'SRC_API_WORKERS': 2, 'SRC_SLEEP': 0, **config_overrides})
    cfg['SOURCES'][source].setdefault('scope', 'oai')
    cfg_path = tmp_path / 'config.yml'
    cfg_path.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    monkeypatch.setenv('CONFIG_PATH', str(cfg_path))
    monkeypatch.setenv('CACHE_PATH', str(tmp_path / 'out'))

    ids = list(ids)
    api_ids = list(api_ids if api_ids is not None else ids)
    announced = len(ids) if oai_announced is None else oai_announced
    db = '1964' if source == 'books' else '1970'
    pages = {'ListIdentifiers': iter(_oai_pages('ListIdentifiers', db, ids, announced, deleted=deleted)),
             'ListRecords': iter(_oai_pages('ListRecords', db, ids, announced, deleted=deleted))}

    def fake_oai(url, *a, **k):
        verb = 'ListIdentifiers' if 'ListIdentifiers' in url else 'ListRecords'
        return ET.fromstring(next(pages[verb]))

    def fake_api(base, database, search, start, limit, retries=5, backoff=2.0):
        hits = len(api_ids) if api_hits is None else api_hits
        records = ''.join(f'<record priref="{i}" modification="2026-01-01T00:00:00"><priref>{i}</priref>'
                          f'<Title><title>Titel {i}</title></Title></record>' for i in api_ids[start - 1:start - 1 + limit])
        return ET.fromstring(f'<adlibXML><recordList>{records}</recordList><diagnostic><hits>{hits}</hits></diagnostic></adlibXML>')

    monkeypatch.setattr(oai_client, 'fetch_and_parse', fake_oai)
    monkeypatch.setattr(adlib_client, 'fetch_page', fake_api)
    monkeypatch.setattr(oai_client.time, 'sleep', lambda s: None)


def manifest(tmp_path, source):
    return json.loads((tmp_path / 'out' / f'manifest-{source}.json').read_text())


def run(source, *extra):
    return harvest_service.main(['--source', source, '--chunks', '10', *extra])


# --- boeken ---------------------------------------------------------------

def test_books_in_scope_only_and_last_chunk_is_written(monkeypatch, tmp_path):
    # OAI publiceert 25 van de 30 API-records: 10 + 10 + 5. Een loop die na de laatste volle chunk stopt, verliest er 5.
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_ids=range(1, 31))
    assert run('books') == 0
    assert sorted(p.name for p in (tmp_path / 'out').glob('*.jsonld')) == ['books-0000.jsonld', 'books-0001.jsonld',
                                                                           'books-0002.jsonld']
    m = manifest(tmp_path, 'books')
    assert m['complete'] is True and m['written'] == 25 and m['out_of_scope'] == 5 and m['api_seen'] == 30


def test_exact_multiple_of_chunk_size(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 21))
    assert run('books') == 0
    assert len(list((tmp_path / 'out').glob('*.jsonld'))) == 2 and manifest(tmp_path, 'books')['written'] == 20


def test_oai_incomplete_fails_the_run(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), oai_announced=30)
    assert run('books') == 1 and manifest(tmp_path, 'books')['complete'] is False


def test_api_incomplete_fails_the_run(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_hits=30)       # API kondigt 30 aan, levert 25
    assert run('books') == 1


def test_record_in_oai_but_not_in_api_fails_and_is_named(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_ids=[i for i in range(1, 26) if i != 7])
    assert run('books') == 1
    m = manifest(tmp_path, 'books')
    assert m['missing_in_api'] == 1 and m['missing_ids'] == ['7'] and m['written'] == 24


def test_missing_in_api_can_be_allowed(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_ids=[i for i in range(1, 26) if i != 7],
           MAX_MISSING_IN_API=1)
    assert run('books') == 0 and manifest(tmp_path, 'books')['written'] == 24


def test_deleted_in_oai_are_not_published(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 11), api_ids=range(1, 11), deleted={3, 4})
    assert run('books') == 0
    m = manifest(tmp_path, 'books')
    assert m['written'] == 8 and m['skipped_reasons'] == {'deleted': 2}


def test_transformation_errors_fail_the_run(monkeypatch, tmp_path):
    real = transform_service.transform_book

    def flaky(graph, config, record, source):
        if record.get('priref') == '2':
            raise ValueError('kapot record')
        return real(graph, config, record, source)

    monkeypatch.setattr(transform_service, 'transform_book', flaky)
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 6))
    assert run('books') == 1
    m = manifest(tmp_path, 'books')
    assert m['errors'] == 1 and m['error_ids'] == ['2'] and m['written'] == 4 and m['complete'] is False


def test_failed_record_leaves_no_partial_triples(monkeypatch, tmp_path):
    real = transform_service.transform_book

    def half_done(graph, config, record, source):
        real(graph, config, record, source)
        if record.get('priref') == '2':
            raise ValueError('na de helft stuk')

    monkeypatch.setattr(transform_service, 'transform_book', half_done)
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 4), MAX_RECORD_ERRORS=1)
    assert run('books') == 0
    data = (tmp_path / 'out' / 'books-0000.jsonld').read_text(encoding='utf-8')
    assert 'Titel 2' not in data and 'Titel 1' in data and 'Titel 3' in data


def test_scope_api_publishes_everything_the_search_returns(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=[], api_ids=range(1, 16), scope='api')
    cfg = yaml.safe_load((tmp_path / 'config.yml').read_text())
    cfg['SOURCES']['books']['scope'] = 'api'
    (tmp_path / 'config.yml').write_text(yaml.safe_dump(cfg))
    assert run('books') == 0 and manifest(tmp_path, 'books')['written'] == 15


def test_limited_run_skips_completeness_check(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), oai_announced=999, api_hits=999)
    assert run('books', '--max-records', '7') == 0


# --- artikelen ------------------------------------------------------------

def test_articles_are_merged_with_api_title(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'article', ids=range(200000001, 200000013))
    assert run('article') == 0
    m = manifest(tmp_path, 'article')
    assert m['written'] == 12 and m['missing_in_api'] == 0
    data = ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'out').glob('article-*.jsonld'))
    assert 'Titel 200000001' in data and 'Tijdschrift' in data           # titel uit het API, tijdschrift uit de OAI


def test_article_missing_in_api_is_written_from_oai_but_fails_the_run(monkeypatch, tmp_path):
    ids = list(range(200000001, 200000011))
    _setup(monkeypatch, tmp_path, 'article', ids=ids, api_ids=[i for i in ids if i != 200000004])
    assert run('article') == 1
    m = manifest(tmp_path, 'article')
    assert m['missing_in_api'] == 1 and m['missing_ids'] == ['200000004'] and m['written'] == 10


def test_article_missing_in_api_can_be_allowed(monkeypatch, tmp_path):
    ids = list(range(200000001, 200000011))
    _setup(monkeypatch, tmp_path, 'article', ids=ids, api_ids=[i for i in ids if i != 200000004], MAX_MISSING_IN_API=1)
    assert run('article') == 0
    data = ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'out').glob('article-*.jsonld'))
    assert 'Titel 200000004' not in data and 'Titel 200000003' in data


def test_unknown_source_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv('CACHE_PATH', str(tmp_path))
    assert harvest_service.main(['--source', 'bestaat-niet']) == 2
