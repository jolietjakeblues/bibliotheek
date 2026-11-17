import copy
import xml.etree.ElementTree as ET

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import transform_service as ts
import uris
from conftest import api_records, node_for

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


def article(config, priref):
    return node_for(config, 'article', priref)


def periodical(config, lref):
    return node_for(config, 'periodical', f'periodical/{lref}')


def build_one(config, priref, change=None):
    """Eén fixture-record, eventueel aangepast, getransformeerd."""
    record = copy.deepcopy(api_records('api_articles.xml')[priref])
    if change:
        change(record)
    graph = Graph()
    ts.transform_article(graph, config, record, config['SOURCES']['article'])
    return graph


def test_all_articles_are_transformed(build_articles):
    graph = build_articles()
    articles = set(graph.subjects(RDF.type, SDO.Article))
    assert len(articles) == 6
    assert articles == set(graph.subjects(RDF.type, SDO.CreativeWork))


def test_title_joined_with_leading_word(build_articles, config):
    graph = build_articles()
    assert value(graph, article(config, '200000025'), SDO.name) == Literal(
        'Het buitengedijkte land bij de Schelphoek in 1953', lang='nl')
    assert value(graph, article(config, '200000017'), SDO.name) == Literal('Boerderij De Geer', lang='nl')


def test_without_title_in_the_source_there_is_no_name_and_nothing_is_invented(config):
    graph = build_one(config, '200000001', lambda r: r.remove(r.find('Title')))
    assert list(graph.objects(article(config, '200000001'), SDO.name)) == []
    assert text(graph, article(config, '200000001'), SDO.pageStart) == '1'          # de rest blijft gewoon bestaan


def test_subjects_places_and_cht(build_articles, config):
    graph = build_articles()
    a = article(config, '200000025')
    assert names(graph, a, SDO.about) == {'dijken', 'overstromingen'}
    about = set(graph.objects(a, SDO.about))
    assert URIRef(CHT + 'c615eaa4-85a7-4f2b-9a96-02aa766e8331') in about
    assert names(graph, a, SDO.spatialCoverage) == {'Schelphoek', 'Schouwen-Duiveland', 'Nederland', 'Zeeland',
                                                    'Serooskerke (Schouwen)'}


def test_authors(build_articles, config):
    graph = build_articles()
    assert len(list(graph.objects(article(config, '200000017'), SDO.author))) == 3
    (author,) = graph.objects(article(config, '200000001'), SDO.author)
    assert text(graph, author, SDO.name) == 'Harst, J.J. van der'
    assert (article(config, '200000001'), SDO.creator, author) in graph


def test_notes(build_articles, config):
    graph = build_articles()
    assert [str(o) for o in graph.objects(article(config, '200000090'), SDO.description)] == ['Met literatuur']


def test_modification_date(build_articles, config):
    assert value(build_articles(), article(config, '200000001'), SDO.sdDatePublished) == \
        Literal('2025-05-23', datatype=XSD.date)


def test_internal_fields_are_not_published(config):
    """De testrecords zijn van interne velden ontdaan; zet ze terug en controleer dat de mapping ze niet overneemt."""
    def add_internal(record):
        for tag, value_ in (('shelf_mark', 'GEHEIM-PLANKNUMMER'), ('record_access.owner', '$GEHEIM-EIGENAAR'),
                            ('input.name', 'GEHEIM-INVOERDER'), ('acquisition_date', '2012-01-20')):
            ET.SubElement(record, tag).text = value_
        edit = ET.SubElement(record, 'Edit')
        ET.SubElement(edit, 'edit.name').text = 'GEHEIM-REDACTEUR'
    data = build_one(config, '200000025', add_internal).serialize(format='nt')
    for internal in ('GEHEIM-PLANKNUMMER', 'GEHEIM-EIGENAAR', 'GEHEIM-INVOERDER', 'GEHEIM-REDACTEUR', '2012-01-20'):
        assert internal not in data


def test_issue_volume_year_pages(build_articles, config):
    graph = build_articles()
    art = article(config, '200000001')
    assert text(graph, art, SDO.pageStart) == '1' and text(graph, art, SDO.pageEnd) == '8'
    assert value(graph, art, SDO.datePublished) == Literal('1984', datatype=XSD.gYear)
    assert text(graph, art, SDO.url) == 'https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/200000001'
    issue, volume, journal = chain(graph, art)
    assert (issue, RDF.type, SDO.PublicationIssue) in graph and text(graph, issue, SDO.issueNumber) == '8'
    assert (volume, RDF.type, SDO.PublicationVolume) in graph and text(graph, volume, SDO.volumeNumber) == '1984'
    assert text(graph, journal, SDO.name) == 'Publikatie Stichting Groningen Orgelland'


def test_journal_leading_word_is_joined(build_articles, config):
    graph = build_articles()
    issue, volume, journal = chain(graph, article(config, '200000017'))       # source.title 'Bewaarsman', lead_word 'De'
    assert text(graph, journal, SDO.name) == 'De Bewaarsman'
    assert text(graph, volume, SDO.volumeNumber) == '2' and text(graph, issue, SDO.issueNumber) == '3'
    assert value(graph, volume, SDO.datePublished) == Literal('1996', datatype=XSD.gYear)


def test_periodical_has_the_address_and_catalogue_link_of_its_own_record(build_articles, config):
    graph = build_articles()
    *_, journal = chain(graph, article(config, '200000025'))
    assert journal == periodical(config, '400009141')                         # source.title.lref = priref van het tijdschrift
    assert text(graph, journal, SDO.url) == 'https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/400009141'


def test_two_articles_in_the_same_journal_share_one_periodical(config):
    graph = build_one(config, '200000025')

    def other(record):
        record.set('priref', '299999999')
        record.find('priref').text = '299999999'
    ts.transform_article(graph, config, copy.deepcopy(_with(other, '200000025')), config['SOURCES']['article'])
    assert len(list(graph.subjects(RDF.type, SDO.Periodical))) == 1
    assert len(list(graph.subjects(RDF.type, SDO.Article))) == 2


def _with(change, priref):
    record = copy.deepcopy(api_records('api_articles.xml')[priref])
    change(record)
    return record


def test_without_lref_the_periodical_falls_back_to_its_name(config):
    def drop_lref(record):
        for el in record.iter('source.title.lref'):
            el.text = ''
    graph = build_one(config, '200000025', drop_lref)
    *_, journal = chain(graph, article(config, '200000025'))
    assert journal == node_for(config, 'periodical', 'periodical/Stad en lande : historische bijdragen en mededelingen van de Vereniging Stad en Lande van Schouwen-Duiveland')
    assert value(graph, journal, SDO.url) is None


def test_page_range_with_extra_page_is_pagination(build_articles, config):
    graph = build_articles()
    art = article(config, '200000090')                                        # '8-9, 12'
    assert text(graph, art, SDO.pagination) == '8-9, 12'
    assert value(graph, art, SDO.pageStart) is None
    issue, volume, journal = chain(graph, art)
    assert text(graph, issue, SDO.issueNumber) == '5' and text(graph, volume, SDO.volumeNumber) == '67'


def test_single_page_gives_start_and_end(config):
    def single(record):
        for el in record.iter('source.pagination'):
            el.text = '91'
    graph = build_one(config, '200000025', single)
    art = article(config, '200000025')
    assert text(graph, art, SDO.pageStart) == '91' and text(graph, art, SDO.pageEnd) == '91'


def test_issue_with_slash_and_material_type(build_articles, config):
    graph = build_articles()
    issue, volume, journal = chain(graph, article(config, '200000290'))
    assert text(graph, issue, SDO.issueNumber) == '11/12'
    assert names(graph, journal, SDO.additionalType) == {'jaarverslagen'}


def test_year_only_gives_a_volume_without_issue(build_articles, config):
    graph = build_articles()
    volume, journal = chain(graph, article(config, '200000011'))              # geen jaargang en aflevering, wel 1985
    assert (volume, RDF.type, SDO.PublicationVolume) in graph
    assert value(graph, volume, SDO.volumeNumber) is None
    assert value(graph, volume, SDO.datePublished) == Literal('1985', datatype=XSD.gYear)


def test_article_without_author(build_articles, config):
    graph = build_articles()
    art = article(config, '200000011')
    assert list(graph.objects(art, SDO.author)) == []
    assert text(graph, art, SDO.pageStart) == '16' and text(graph, art, SDO.pageEnd) == '18'


def test_article_without_source_has_no_journal(config):
    graph = build_one(config, '200000025', lambda r: [r.remove(e) for e in r.findall('Source')])
    art = article(config, '200000025')
    assert chain(graph, art) == [] and list(graph.subjects(RDF.type, SDO.Periodical)) == []
    assert value(graph, art, SDO.datePublished) == Literal('1990', datatype=XSD.gYear)    # het jaar komt uit search_year


def test_source_without_a_title_is_ignored_and_the_first_with_a_title_wins(config):
    record = copy.deepcopy(api_records('api_articles.xml')['200000025'])
    assert ts.article_source(record)['lref'] == '400009141'
    empty = copy.deepcopy(record.find('Source'))
    for el in empty.iter('source.title'):
        el.text = ''
    record.insert(0, empty)
    assert ts.article_source(record)['journal'].startswith('Stad en lande')
    record.remove(record.findall('Source')[1])
    assert ts.article_source(record) is None
