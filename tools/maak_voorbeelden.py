"""Maak de voorbeelden in docs/voorbeelden/ uit de echte fixtures in tests/fixtures/.

    python tools/maak_voorbeelden.py            # schrijft docs/voorbeelden/*.ttl
    python tools/maak_voorbeelden.py --check    # controleert alleen of de bestanden nog kloppen (exitcode 1 zo niet)

De voorbeelden laten zien wat de mapping nu werkelijk oplevert. `tests/test_docs.py` vergelijkt ze met de code, zodat de
documentatie niet ongemerkt achterloopt: verandert de mapping, dan faalt die test tot dit script opnieuw is gedraaid.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from rdflib import Graph, Namespace, URIRef
from rdflib.compare import isomorphic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

import oai_client  # noqa: E402
import transform_service as ts  # noqa: E402
import uris  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures'
OUT = ROOT / 'docs' / 'voorbeelden'

# (bestandsnaam, soort, priref, wat het laat zien)
VOORBEELDEN = [
    ('boek-met-auteurs-en-uitgever', 'book', '17', 'auteurs (persoon en organisatie), uitgever, plaats, ISBN, CHT-term'),
    ('boek-in-reeks', 'book', '81', 'reeks met deelnummer'),
    ('boek-over-monument', 'book', '90', 'rijksmonumentnummer en plaatsen'),
    ('artikel', 'article', '200000025', 'titel uit het API, tijdschrift/jaargang/aflevering en pagina\'s uit de OAI'),
]


def load_config() -> dict:
    with open(ROOT / 'config' / 'config.yml', encoding='utf-8') as f:
        return yaml.safe_load(f)


def api_records(name: str) -> dict:
    return {r.get('priref'): r for r in ET.parse(FIXTURES / name).getroot().iter('record')}


def oai_article(priref: str):
    root = ET.parse(FIXTURES / 'article_page.xml').getroot()
    for rec in root.findall('.//{*}record'):
        header = {'identifier': rec.findtext('.//{*}identifier'), 'datestamp': rec.findtext('.//{*}datestamp'),
                  'deleted': False}
        if ts.record_priref(header['identifier']) == priref:
            return header, ts.collect_fields(rec.find('{*}metadata')[0])
    raise KeyError(priref)


def build(config: dict, kind: str, priref: str) -> Graph:
    """Eén record met alle nodes die het meeneemt, zonder de dataset- en organisatie-node."""
    graph = Graph()
    source = config['SOURCES']['books' if kind == 'book' else 'article']
    if kind == 'book':
        ts.transform_book(graph, config, api_records('api_books.xml')[priref], source)
    else:
        header, fields = oai_article(priref)
        ts.transform_article(graph, config, header, fields, source, api_records('api_articles.xml')[priref])
    return graph


def serialize(graph: Graph, config: dict) -> str:
    bib = Namespace(f"{config['BASE_URI']}{config['COLLECTION_ID']}/id/")
    graph.bind('bib', bib)
    graph.bind('schema', Namespace('https://schema.org/'))
    graph.bind('cht', Namespace('https://data.cultureelerfgoed.nl/term/id/cht/'))
    return graph.serialize(format='turtle')


def bestanden(config: dict) -> dict:
    out = {}
    for naam, kind, priref, omschrijving in VOORBEELDEN:
        kop = (f"# Voorbeeld: {omschrijving}.\n"
               f"# Echt record (priref {priref}) uit tests/fixtures, getransformeerd door src/transform_service.py.\n"
               f"# Gegenereerd door tools/maak_voorbeelden.py; niet met de hand aanpassen.\n\n")
        out[naam] = (kop + serialize(build(config, kind, priref), config), build(config, kind, priref))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='alleen controleren, niets schrijven')
    args = parser.parse_args(argv)
    config = load_config()
    stale = []
    for naam, (tekst, graph) in bestanden(config).items():
        pad = OUT / f'{naam}.ttl'
        if args.check:
            if not pad.exists() or not isomorphic(Graph().parse(pad, format='turtle'), graph):
                stale.append(pad.name)
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            pad.write_text(tekst, encoding='utf-8')
            print('geschreven:', pad.relative_to(ROOT))
    if stale:
        print('Verouderd (draai tools/maak_voorbeelden.py):', ', '.join(stale))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
