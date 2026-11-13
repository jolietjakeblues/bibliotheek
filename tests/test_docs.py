"""De documentatie moet kloppen met de code: voorbeelden actueel, query's werken, links bestaan, config volledig beschreven."""
import re
import sys

import pytest
import yaml
from rdflib import Graph

from conftest import ROOT

sys.path.insert(0, str(ROOT / 'tools'))
import maak_voorbeelden  # noqa: E402

DOCS = ROOT / 'docs'
MARKDOWN = [ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'CHANGELOG.md', *sorted(DOCS.glob('*.md'))]


def test_voorbeelden_zijn_actueel():
    """Verandert de mapping, dan moeten docs/voorbeelden/*.ttl opnieuw worden gemaakt: python tools/maak_voorbeelden.py"""
    assert maak_voorbeelden.main(['--check']) == 0


# --- SPARQL ---------------------------------------------------------------

def sparql_blokken():
    tekst = (DOCS / 'sparql.md').read_text(encoding='utf-8')
    return [b.strip() for b in re.findall(r'```sparql\n(.*?)```', tekst, re.S) if 'SELECT' in b]


@pytest.fixture
def voorbeeldgraph(books_graph, build_articles):
    g = Graph()
    g += books_graph
    g += build_articles()
    return g


def test_elke_query_is_gemarkeerd():
    for blok in sparql_blokken():
        assert blok.startswith(('# test: lokaal', '# test: overslaan')), f'markeer de query:\n{blok[:120]}'


@pytest.mark.parametrize('blok', [b for b in sparql_blokken() if b.startswith('# test: lokaal')],
                         ids=lambda b: re.search(r'SELECT (.*?) WHERE', b, re.S).group(1)[:40].replace('\n', ' '))
def test_lokale_query_levert_rijen_op_de_voorbeeldrecords(voorbeeldgraph, blok):
    rijen = list(voorbeeldgraph.query(blok))
    assert rijen, f'de query geeft geen rijen op de voorbeeldrecords:\n{blok}'


# --- links en volledigheid ------------------------------------------------

@pytest.mark.parametrize('bestand', MARKDOWN, ids=lambda p: str(p.relative_to(ROOT)))
def test_relatieve_links_bestaan(bestand):
    for doel in re.findall(r'\]\(([^)\s]+)\)', bestand.read_text(encoding='utf-8')):
        if doel.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        pad = (bestand.parent / doel.split('#')[0]).resolve()
        assert pad.exists(), f'{bestand.relative_to(ROOT)}: link naar {doel} bestaat niet'


def test_readme_verwijst_naar_elk_document_in_docs():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    for doc in DOCS.glob('*.md'):
        assert f'docs/{doc.name}' in readme, f'README verwijst niet naar docs/{doc.name}'


def test_elke_configuratiesleutel_is_beschreven():
    config = yaml.safe_load((ROOT / 'config' / 'config.yml').read_text(encoding='utf-8'))
    tekst = (DOCS / 'configuratie.md').read_text(encoding='utf-8')
    sleutels = set(config)
    for bron in config['SOURCES'].values():
        sleutels |= set(bron)
    sleutels |= set(config['SOURCES'])
    ontbrekend = [s for s in sorted(sleutels) if f'`{s}`' not in tekst]
    assert not ontbrekend, f'niet beschreven in docs/configuratie.md: {ontbrekend}'


def test_workflow_invoervelden_staan_in_het_beheerdocument():
    workflow = yaml.safe_load((ROOT / '.github' / 'workflows' / 'harvest_bibliotheek.yml').read_text(encoding='utf-8'))
    invoer = workflow[True]['workflow_dispatch']['inputs']          # YAML leest 'on' als True
    tekst = (DOCS / 'beheer.md').read_text(encoding='utf-8')
    for naam in invoer:
        assert f'`{naam}`' in tekst, f'invoerveld {naam} staat niet in docs/beheer.md'
