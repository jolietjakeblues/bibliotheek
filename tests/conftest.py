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
