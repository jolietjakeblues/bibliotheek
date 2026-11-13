import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'tests' / 'fixtures'
sys.path.insert(0, str(ROOT / 'src'))

import oai_client  # noqa: E402
import transform_service  # noqa: E402
import uris  # noqa: E402


@pytest.fixture(scope='session')
def config():
    with open(ROOT / 'config' / 'config.yml', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(autouse=True)
def config_path(monkeypatch):
    monkeypatch.setenv('CONFIG_PATH', str(ROOT / 'config' / 'config.yml'))


def api_records(name: str) -> dict:
    """{priref: <record>} uit een API-fixture (echte records van het Adlib-API)."""
    root = ET.parse(FIXTURES / name).getroot()
    return {r.get('priref'): r for r in root.iter('record')}


@pytest.fixture
def books_graph(config):
    """Alle echte boekrecords uit tests/fixtures/api_books.xml, getransformeerd."""
    graph = uris.get_dataset(config)
    for record in api_records('api_books.xml').values():
        transform_service.transform_book(graph, config, record, config['SOURCES']['books'])
    return graph


@pytest.fixture
def build_articles(config, monkeypatch):
    """Artikelen: OAI-fixture (tijdschrift, pagina's) en optioneel de API-fixture (titel, onderwerpen)."""
    def _build(with_api: bool = True):
        root = ET.fromstring((FIXTURES / 'article_page.xml').read_text(encoding='utf-8'))
        monkeypatch.setattr(oai_client, 'fetch_and_parse', lambda *a, **k: root)
        source = config['SOURCES']['article']
        api = api_records('api_articles.xml') if with_api else {}
        graph = uris.get_dataset(config)
        for header, element in oai_client.iter_records('http://example.org/oai', 'article', 'oai_dc', {},
                                                       sleep_between=0):
            priref = transform_service.record_priref(header['identifier'])
            transform_service.transform_article(graph, config, header, transform_service.collect_fields(element),
                                                source, api.get(priref))
        return graph
    return _build


def node_for(config, kind: str, priref: str):
    return uris.get_object_uri(config['BASE_URI'], config['COLLECTION_ID'], priref, kind)


# ---------------------------------------------------------------------------
# nagebootste OAI-server met tijdvakken
# ---------------------------------------------------------------------------

class FakeOai:
    """Een OAI-server met `from`/`until` zoals de echte: beide op hele seconden en inclusief, terwijl de datestamps
    fracties van een seconde hebben (de header toont ze afgekapt). Pagina's van `page_size` records met een resumptionToken."""

    NS = 'http://www.openarchives.org/OAI/2.0/'

    def __init__(self, stamps: dict, page_size: int = 5, db: str = '1964'):
        import datetime
        self.dt = datetime
        self.stamps = dict(stamps)                 # identifier-nummer -> datetime (met microseconden)
        self.page_size, self.db = page_size, db
        self.requests, self.tokens = [], {}
        self.lock = __import__('threading').Lock()

    def _parse(self, text):
        return self.dt.datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ')

    def _list(self, params):
        lo = self._parse(params['from']) if 'from' in params else None
        hi = self._parse(params['until']) if 'until' in params else None
        return [i for i, t in sorted(self.stamps.items())
                if (lo is None or t >= lo) and (hi is None or t <= hi)]

    def fetch(self, url, retries=5, backoff=2.0):
        import urllib.parse
        import xml.etree.ElementTree as ET
        params = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}
        verb = params['verb']
        with self.lock:
            self.requests.append(params)
            if 'resumptionToken' in params:
                ident, offset = params['resumptionToken'].rsplit('@', 1)
                query, offset = self.tokens[ident], int(offset)
            else:
                query, offset = {k: v for k, v in params.items() if k in ('from', 'until')}, 0
                ident = str(len(self.tokens))
                self.tokens[ident] = query
        ids = self._list(query)
        if not ids:
            return ET.fromstring(f'<OAI-PMH xmlns="{self.NS}"><error code="noRecordsMatch">geen</error></OAI-PMH>')
        more = offset + self.page_size < len(ids)
        size = f'completeListSize="{len(ids)}" cursor="{offset}"'
        token = f'<resumptionToken {size}>{ident}@{offset + self.page_size}</resumptionToken>' if more             else f'<resumptionToken {size}/>'
        items = ''
        for i in ids[offset:offset + self.page_size]:
            header = (f'<header><identifier>{self.db}:{i}</identifier>'
                      f'<datestamp>{self.stamps[i].strftime("%Y-%m-%dT%H:%M:%SZ")}</datestamp></header>')
            if verb == 'ListRecords':
                items += (f'<record>{header}<metadata><oai_dc:dc xmlns:oai_dc="x" xmlns:dc="y"><dc:source>bron {i}</dc:source>'
                          f'</oai_dc:dc></metadata></record>')
            else:
                items += header
        return ET.fromstring(f'<OAI-PMH xmlns="{self.NS}"><{verb}>{items}{token}</{verb}></OAI-PMH>')
