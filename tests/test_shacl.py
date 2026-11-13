"""De SHACL-shapes: geldige data slaagt, kapotte data wordt afgekeurd (en bekende hiaten zijn alleen waarschuwingen)."""
import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import validate_service
from conftest import ROOT, node_for

SHAPES = Graph().parse(ROOT / 'shacl' / 'bibliotheek.shacl.ttl', format='turtle')


def check(graph):
    return validate_service.validate_graph(graph, SHAPES)


@pytest.fixture
def books(books_graph):
    return books_graph


@pytest.fixture
def articles(build_articles):
    return build_articles()


def test_shapes_file_is_valid_turtle_with_shapes():
    assert len(SHAPES) > 100


def test_real_books_have_no_violations(books):
    assert sum(check(books)['Violation'].values()) == 0


def test_real_articles_have_no_violations(articles):
    result = check(articles)
    assert sum(result['Violation'].values()) == 0
    assert 'Article: schema:name ontbreekt (de bron levert geen artikeltitel).' not in result['Warning']


def test_article_only_in_oai_has_no_title_which_is_a_warning(build_articles):
    result = check(build_articles(with_api=False))
    assert sum(result['Violation'].values()) == 0
    assert result['Warning']['Article: schema:name ontbreekt (de bron levert geen artikeltitel).'] == 6


def test_book_without_title_is_a_violation(books, config):
    book = node_for(config, 'book', '3')
    books.remove((book, SDO.name, None))
    assert check(books)['Violation']['Book: schema:name ontbreekt.'] == 1


def test_internal_link_as_url_is_a_violation(books, config):
    book = node_for(config, 'book', '3')
    books.remove((book, SDO.url, None))
    books.add((book, SDO.url, URIRef('https://proza.ocw.local/otcs/cs.exe/open/?func=doc.Fetch&nodeid=1')))
    assert check(books)['Violation']['Book: schema:url moet een link naar de openbare catalogus zijn.'] == 1


def test_bad_isbn_and_page_count_are_violations(books, config):
    book = node_for(config, 'book', '3')
    books.remove((book, SDO.isbn, None))
    books.add((book, SDO.isbn, Literal('12-34')))
    books.add((book, SDO.numberOfPages, Literal('veel')))
    violations = check(books)['Violation']
    assert violations['Book: schema:isbn moet 10 of 13 tekens zonder streepjes hebben.'] == 1
    assert violations['Book: schema:numberOfPages moet een positief geheel getal zijn.'] >= 1


def test_missing_modification_date_is_a_violation(books, config):
    book = node_for(config, 'book', '3')
    books.remove((book, SDO.sdDatePublished, None))
    assert check(books)['Violation']['Book: schema:sdDatePublished ontbreekt.'] == 1


def test_person_with_two_names_is_a_violation(books, config):
    author = next(a for a in books.objects(node_for(config, 'book', '17'), SDO.author) if (a, RDF.type, SDO.Person) in books)
    books.add((author, SDO.name, Literal('Andere naam', lang='nl')))
    result = check(books)
    assert sum(result['Violation'].values()) >= 1


def test_name_without_language_is_a_violation(books, config):
    book = node_for(config, 'book', '3')
    books.remove((book, SDO.name, None))
    books.add((book, SDO.name, Literal('Zonder taalcode')))
    assert check(books)['Violation']['Book: schema:name moet tekst met taalcode zijn (bv. "..."@nl).'] == 1


def test_volume_without_periodical_is_a_violation(articles, config):
    art = node_for(config, 'article', '200000001')
    volume = next(v for v in articles.objects(art, SDO.isPartOf) if (v, RDF.type, SDO.PublicationVolume) in articles)
    articles.remove((volume, SDO.isPartOf, None))
    assert check(articles)['Violation']['PublicationVolume: schema:isPartOf moet verwijzen naar een schema:Periodical.'] == 1


def test_issue_without_number_is_a_violation(articles, config):
    art = node_for(config, 'article', '200000025')
    issue = next(i for i in articles.objects(art, SDO.isPartOf) if (i, RDF.type, SDO.PublicationIssue) in articles)
    articles.remove((issue, SDO.issueNumber, None))
    assert check(articles)['Violation']['PublicationIssue: schema:issueNumber moet precies één tekstwaarde zijn.'] == 1


def test_article_outside_any_periodical_is_a_warning(articles, config):
    art = node_for(config, 'article', '200000001')
    for parent in list(articles.objects(art, SDO.isPartOf)):
        if not str(parent).endswith('/bibliotheek/'):
            articles.remove((art, SDO.isPartOf, parent))
    result = check(articles)
    assert sum(result['Violation'].values()) == 0
    assert any('geen tijdschrift gevonden' in m for m in result['Warning'])


def test_series_without_name_and_monument_without_number_are_violations(books, config):
    series = next(s for s in books.objects(node_for(config, 'book', '81'), SDO.isPartOf)
                  if (s, RDF.type, SDO.CreativeWorkSeries) in books)
    books.remove((series, SDO.name, None))
    monument = next(m for m in books.objects(node_for(config, 'book', '90'), SDO.about)
                    if (m, RDF.type, SDO.LandmarksOrHistoricalBuildings) in books)
    books.remove((monument, SDO.identifier, None))
    violations = check(books)['Violation']
    assert violations['CreativeWorkSeries: schema:name ontbreekt.'] == 1
    assert violations['LandmarksOrHistoricalBuildings: schema:identifier (rijksmonumentnummer) ontbreekt.'] == 1


def test_validate_main_exit_codes(tmp_path, books, config):
    good = tmp_path / 'good.jsonld'
    books.serialize(destination=str(good), format='json-ld', auto_compact=True)
    assert validate_service.main([str(good), '--shapes', str(ROOT / 'shacl' / 'bibliotheek.shacl.ttl')]) == 0
    books.remove((node_for(config, 'book', '3'), SDO.name, None))
    bad = tmp_path / 'bad.jsonld'
    books.serialize(destination=str(bad), format='json-ld', auto_compact=True)
    assert validate_service.main([str(bad), '--shapes', str(ROOT / 'shacl' / 'bibliotheek.shacl.ttl')]) == 1
