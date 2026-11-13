from rdflib import Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import transform_service as ts
from conftest import node_for

CHT = 'https://data.cultureelerfgoed.nl/term/id/cht/'


def value(graph, subject, predicate):
    return graph.value(subject, predicate)


def text(graph, subject, predicate):
    v = graph.value(subject, predicate)
    return None if v is None else str(v)


def names(graph, subject, predicate):
    return {str(graph.value(o, SDO.name)) for o in graph.objects(subject, predicate) if graph.value(o, SDO.name)}


def chain(graph, article):
    """Alle nodes boven het artikel: aflevering -> jaargang -> tijdschrift."""
    out, current = [], article
    while True:
        parents = [p for p in graph.objects(current, SDO.isPartOf) if not str(p).endswith('/bibliotheek/')]
        if not parents:
            return out
        current = parents[0]
        out.append(current)


def article(config, priref):
    return node_for(config, 'article', priref)


def test_all_articles_are_transformed(build_articles):
    graph = build_articles()
    articles = set(graph.subjects(RDF.type, SDO.Article))
    assert len(articles) == 6
    assert articles == set(graph.subjects(RDF.type, SDO.CreativeWork))


def test_title_from_api_joined_with_leading_word(build_articles, config):
    graph = build_articles()
    assert value(graph, article(config, '200000025'), SDO.name) == Literal(
        'Het buitengedijkte land bij de Schelphoek in 1953', lang='nl')
    assert value(graph, article(config, '200000017'), SDO.name) == Literal('Boerderij De Geer', lang='nl')


def test_without_api_record_there_is_no_title_and_nothing_is_invented(build_articles, config):
    graph = build_articles(with_api=False)
    assert list(graph.objects(article(config, '200000001'), SDO.name)) == []
    # tijdschrift, jaar en pagina's komen uit de OAI en blijven dus gewoon bestaan
    assert text(graph, article(config, '200000001'), SDO.pageStart) == '1'
    (author,) = graph.objects(article(config, '200000001'), SDO.author)
    assert text(graph, author, SDO.name) == 'Harst, J.J. van der'


def test_subjects_places_and_cht_from_api(build_articles, config):
    graph = build_articles()
    a = article(config, '200000025')
    assert names(graph, a, SDO.about) == {'dijken', 'overstromingen'}
    about = set(graph.objects(a, SDO.about))
    assert URIRef(CHT + 'c615eaa4-85a7-4f2b-9a96-02aa766e8331') in about
    assert names(graph, a, SDO.spatialCoverage) == {'Schelphoek', 'Schouwen-Duiveland', 'Nederland', 'Zeeland',
                                                    'Serooskerke (Schouwen)'}


def test_authors_are_not_duplicated_between_api_and_oai(build_articles, config):
    graph = build_articles()
    assert len(list(graph.objects(article(config, '200000017'), SDO.author))) == 3
    (author,) = graph.objects(article(config, '200000001'), SDO.author)
    assert text(graph, author, SDO.name) == 'Harst, J.J. van der'


def test_notes_from_api_and_oai_are_deduplicated(build_articles, config):
    graph = build_articles()
    descriptions = [str(o) for o in graph.objects(article(config, '200000090'), SDO.description)]
    assert descriptions == ['Met literatuur']                  # staat in beide bronnen, maar is één beschrijving


def test_modification_date_comes_from_api_when_available(build_articles, config):
    assert value(build_articles(), article(config, '200000001'), SDO.sdDatePublished) == \
        Literal('2025-05-23', datatype=XSD.date)


def test_volume_year_pages(build_articles, config):
    graph = build_articles()
    art = article(config, '200000001')
    assert text(graph, art, SDO.pageStart) == '1' and text(graph, art, SDO.pageEnd) == '8'
    assert value(graph, art, SDO.datePublished) == Literal('1984', datatype=XSD.gYear)
    assert text(graph, art, SDO.url) == 'https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/200000001'
    volume, periodical = chain(graph, art)
    assert (volume, RDF.type, SDO.PublicationVolume) in graph
    assert text(graph, volume, SDO.volumeNumber) == '1984'
    assert text(graph, periodical, SDO.name) == 'Publikatie Stichting Groningen Orgelland'


def test_journal_title_split_over_two_fields_is_joined(build_articles, config):
    graph = build_articles()
    art = article(config, '200000017')                         # 'journal = {De' + 'journal = {Bewaarsman ; '
    volume, periodical = chain(graph, art)
    assert text(graph, periodical, SDO.name) == 'De Bewaarsman'
    assert value(graph, volume, SDO.volumeNumber) is None       # alleen een jaartal, geen volumenummer
    assert value(graph, volume, SDO.datePublished) == Literal('1996', datatype=XSD.gYear)


def test_issue_volume_year_chain(build_articles, config):
    graph = build_articles()
    art = article(config, '200000025')
    issue, volume, periodical = chain(graph, art)
    assert (issue, RDF.type, SDO.PublicationIssue) in graph
    assert text(graph, issue, SDO.issueNumber) == '69'
    assert text(graph, volume, SDO.volumeNumber) == '27'
    assert text(graph, periodical, SDO.name).startswith('Stad en lande')
    assert text(graph, art, SDO.pageStart) == '198' and text(graph, art, SDO.pageEnd) == '203'


def test_page_range_first_is_pagination_not_issue(build_articles, config):
    graph = build_articles()
    art = article(config, '200000090')                          # ', 8-9, 12'
    assert text(graph, art, SDO.pagination) == '8-9, 12'
    assert not list(graph.subjects(RDF.type, SDO.PublicationIssue)) or \
        all((i, SDO.issueNumber, Literal('8-9', datatype=XSD.string)) not in graph
            for i in graph.subjects(RDF.type, SDO.PublicationIssue))


def test_issue_with_slash_and_material_type(build_articles, config):
    graph = build_articles()
    issue, volume, periodical = chain(graph, article(config, '200000290'))
    assert text(graph, issue, SDO.issueNumber) == '11/12'
    assert names(graph, periodical, SDO.additionalType) == {'jaarverslagen'}


def test_article_without_author(build_articles, config):
    graph = build_articles()
    art = article(config, '200000011')
    assert list(graph.objects(art, SDO.author)) == []
    assert text(graph, art, SDO.pageStart) == '16'


# --- parse_article_source -------------------------------------------------

def test_parse_source_full():
    r = ts.parse_article_source(['journal = {Stad en lande ; ', '27 ', '(1990)', ', 69', ', 198-203},',
                                 'Source.materiaal: tijdschrift'])
    assert r == {'journal': 'Stad en lande', 'volume': '27', 'year': '1990', 'issue': '69',
                 'pages': '198-203', 'material': 'tijdschrift'}


def test_parse_source_year_and_pages_only():
    r = ts.parse_article_source(['journal = {Jaarboek / Oud-Utrecht ; ', '(1943)', ', 94-118},',
                                 'Source.materiaal: jaarboek'])
    assert (r['journal'], r['volume'], r['year'], r['issue'], r['pages']) == \
        ('Jaarboek / Oud-Utrecht', None, '1943', None, '94-118')


def test_parse_source_without_pages():
    r = ts.parse_article_source(['journal = {Historische Kring Eemnes ; ', '12 ', '(1990)',
                                 'Source.materiaal: tijdschrift'])
    assert (r['journal'], r['volume'], r['year'], r['pages']) == ('Historische Kring Eemnes', '12', '1990', None)


def test_parse_source_single_page_and_unparseable():
    r = ts.parse_article_source(['journal = {Oud Hoorn ; ', '12 ', '(1990)', ', 91},'])
    assert r['pages'] == '91' and r['issue'] is None
    # geen scheidingsteken ' ; ': alleen een titel, rest blijft leeg, geen fout
    r = ts.parse_article_source(['journal = {Alleen een titel},'])
    assert r['journal'] == 'Alleen een titel' and r['year'] is None
    assert ts.parse_article_source([])['journal'] is None


def test_bibtex_value():
    assert ts.bibtex_value('author = {Harst, J.J. van der},', 'author') == 'Harst, J.J. van der'
    assert ts.bibtex_value('year = {1984},', 'year') == '1984'
    assert ts.bibtex_value('year = {1984},', 'author') is None
    assert ts.bibtex_value('niets', 'author') is None
