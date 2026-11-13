import xml.etree.ElementTree as ET

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import transform_service as ts
from conftest import node_for

CHT = 'https://data.cultureelerfgoed.nl/term/id/cht/'


def names(graph, subject, predicate):
    return {str(graph.value(o, SDO.name)) for o in graph.objects(subject, predicate) if graph.value(o, SDO.name)}


def book(config, priref):
    return node_for(config, 'book', priref)


def test_all_real_records_become_books(books_graph):
    books = set(books_graph.subjects(RDF.type, SDO.Book))
    assert len(books) == 11
    assert books == set(books_graph.subjects(RDF.type, SDO.CreativeWork))   # CN-profiel toetst op CreativeWork


def test_leading_word_is_joined_to_title(books_graph, config):
    assert books_graph.value(book(config, '17'), SDO.name) == Literal(
        'De provincie : partner in cultuurbeleid : naar een gebiedsgewijze en integrale aanpak', lang='nl')
    # lidwoord met apostrof krijgt geen spatie: L' + Hospice -> L'Hospice
    assert str(books_graph.value(book(config, '624'), SDO.name)).startswith("L'Hospice de Charenton")


def test_persons_and_corporate_author(books_graph, config):
    b = book(config, '17')
    assert names(books_graph, b, SDO.author) == {'Deijck-Hofmeester, Carla van', 'Raijmakers, Willem-Jan',
                                                 'R&H, projecten en adviezen'}
    assert names(books_graph, b, SDO.creator) == names(books_graph, b, SDO.author)
    (corp,) = [a for a in books_graph.objects(b, SDO.author) if str(books_graph.value(a, SDO.name)).startswith('R&H')]
    assert (corp, RDF.type, SDO.Organization) in books_graph                  # Corporate_author is altijd een organisatie
    persons = [a for a in books_graph.objects(b, SDO.author) if (a, RDF.type, SDO.Person) in books_graph]
    assert len(persons) == 2


def test_publisher_place_year_isbn_pages(books_graph, config):
    b = book(config, '17')
    assert names(books_graph, b, SDO.publisher) == {'Interprovinciaal Overleg'}
    assert names(books_graph, b, SDO.locationCreated) == {'Den Haag'}
    assert books_graph.value(b, SDO.datePublished) == Literal('1996', datatype=XSD.gYear)
    assert books_graph.value(b, SDO.isbn) == Literal('9080257222', datatype=XSD.string)
    assert books_graph.value(b, SDO.numberOfPages) == Literal(52, datatype=XSD.integer)
    assert str(books_graph.value(b, SDO.size)) == '52 ; ill. fot. ; 25'
    assert str(books_graph.value(b, SDO.url)) == 'https://catalogus.cultureelerfgoed.nl/Details/fullCatalogue/17'
    assert books_graph.value(b, SDO.sdDatePublished) == Literal('2024-10-16', datatype=XSD.date)


def test_place_without_publisher(books_graph, config):
    b = book(config, '3')                                                  # publisher leeg, plaats Tilburg
    assert list(books_graph.objects(b, SDO.publisher)) == []
    assert names(books_graph, b, SDO.locationCreated) == {'Tilburg'}
    assert books_graph.value(b, SDO.numberOfPages) == Literal(96, datatype=XSD.integer)   # '96 p'


def test_two_publisher_groups(books_graph, config):
    b = book(config, '281')
    assert names(books_graph, b, SDO.publisher) == {'Riksantikvaren', 'Gyldendal Norsk Forlag'}
    assert names(books_graph, b, SDO.locationCreated) == {'Oslo'}


def test_series_with_number(books_graph, config):
    for priref, series_name, number in [('81', 'Advies Vromraad', '003'), ('50', 'Publicatie RLG', '97/3'),
                                        ('1523', 'Leidse Historische Reeks', '13')]:
        b = book(config, priref)
        (series,) = [s for s in books_graph.objects(b, SDO.isPartOf) if (s, RDF.type, SDO.CreativeWorkSeries) in books_graph]
        assert str(books_graph.value(series, SDO.name)) == series_name
        assert books_graph.value(b, SDO.position) == Literal(number, datatype=XSD.string)
        assert (b, SDO.isPartOf, URIRef('https://linkeddata.cultureelerfgoed.nl/rce/bibliotheek/')) in books_graph


def test_series_without_number_and_shared_series_node(books_graph, config):
    assert books_graph.value(book(config, '281'), SDO.position) is None
    # dezelfde reeksnaam in twee records is één node
    g = Graph()
    cfg = config
    for p in ('1', '2'):
        rec = ET.fromstring(f'<record priref="{p}" modification="2026-01-01T00:00:00"><Title><title>T{p}</title></Title>'
                            f'<Series_title><series.title>Reeks X</series.title><series.number>{p}</series.number></Series_title></record>')
        ts.transform_book(g, cfg, rec, cfg['SOURCES']['books'])
    assert len(list(g.subjects(RDF.type, SDO.CreativeWorkSeries))) == 1


def test_pages_that_are_not_a_plain_count(books_graph, config):
    assert books_graph.value(book(config, '1523'), SDO.numberOfPages) is None      # '120 ; 131'
    assert books_graph.value(book(config, '51'), SDO.numberOfPages) == Literal(57, datatype=XSD.integer)  # "57 pagina's"


def test_edition_and_abstract(books_graph, config):
    assert books_graph.value(book(config, '114'), SDO.bookEdition) == Literal('4e herz. dr.', lang='nl')
    assert books_graph.value(book(config, '51'), SDO.abstract) == Literal('496 E. Monumentenzorg en cultuurbeleid', lang='nl')


def test_cht_terms_are_linked_directly_and_empty_ones_ignored(books_graph, config):
    about = set(books_graph.objects(book(config, '90'), SDO.about))
    assert URIRef(CHT + '1130e375-3469-4e63-a8d4-5fcb339f7536') in about
    assert URIRef(CHT + '20ee0f42-6390-4d87-9442-131fc94ce14b') in about
    # record 3 heeft alleen een lege RNA_URI: geen about-IRI, wel het trefwoord als term
    assert names(books_graph, book(config, '3'), SDO.about) == {'architectuurbeleid'}
    assert not any(str(o).startswith(CHT) for o in books_graph.objects(book(config, '3'), SDO.about))


def test_monument_number_name_and_places(books_graph, config):
    b = book(config, '90')
    (monument,) = [m for m in books_graph.objects(b, SDO.about) if (m, RDF.type, SDO.LandmarksOrHistoricalBuildings) in books_graph]
    assert books_graph.value(monument, SDO.name) is None       # de naam staat niet op de gedeelde node
    (ident,) = books_graph.objects(monument, SDO.identifier)
    assert str(books_graph.value(ident, SDO.propertyID)) == 'rijksmonumentnummer'
    assert str(books_graph.value(ident, SDO.value)) == '10081'
    # de monumentnaam blijft bij het boek als plaats, naast land, provincie en plaats
    assert names(books_graph, b, SDO.spatialCoverage) == {'Nederland', 'Gelderland', 'Poederoijen', 'Slot Loevestein'}


def test_same_monument_number_with_different_names_is_one_node_without_conflict(config):
    g = Graph()
    for p, name in (('1', 'Slot Loevestein'), ('2', 'Loevestein')):
        rec = ET.fromstring(f'<record priref="{p}" modification="2026-01-01T00:00:00"><Title><title>T{p}</title></Title>'
                            f'<Monumentnumber><monument.number>10081</monument.number></Monumentnumber>'
                            f'<monument.name>{name}</monument.name></record>')
        ts.transform_book(g, config, rec, config['SOURCES']['books'])
    monuments = list(g.subjects(RDF.type, SDO.LandmarksOrHistoricalBuildings))
    assert len(monuments) == 1 and list(g.objects(monuments[0], SDO.name)) == []
    assert {str(g.value(o, SDO.name)) for o in g.objects(book(config, '1'), SDO.spatialCoverage)} == {'Slot Loevestein'}


def test_person_keyword_organization_and_geographical_keyword(books_graph, config):
    b = book(config, '91')
    org = [o for o in books_graph.objects(b, SDO.about) if (o, RDF.type, SDO.Organization) in books_graph]
    assert [str(books_graph.value(o, SDO.name)) for o in org] == ['Rijksmuseum Muiderslot']
    assert 'Charenton' in names(books_graph, book(config, '624'), SDO.spatialCoverage)


def test_notes_become_descriptions(books_graph, config):
    descriptions = {str(o) for o in books_graph.objects(book(config, '624'), SDO.description)}
    assert 'Met noten, bronnen, bibliografie en register' in descriptions and len(descriptions) == 2


def test_internal_and_unmapped_fields_are_not_published(books_graph):
    everything = books_graph.serialize(format='nt')
    for forbidden in ('.local', 'proza', 'nX2.9', 'shelf', 'openathens'):
        assert forbidden not in everything


def test_addresses_are_stable(config):
    a, b = Graph(), Graph()
    from conftest import api_records
    for graph in (a, b):
        for record in api_records('api_books.xml').values():
            ts.transform_book(graph, config, record, config['SOURCES']['books'])
    assert set(a) == set(b)                                   # zelfde adressen bij een tweede run


def test_every_record_points_to_dataset_and_publisher(books_graph, config):
    for b in books_graph.subjects(RDF.type, SDO.Book):
        assert (b, SDO.isPartOf, URIRef(config['DATASET_URI'])) in books_graph
        assert (b, SDO.sdPublisher, URIRef(config['ORG_URI'])) in books_graph


# --- gedeelde auteurs en uitgevers ---------------------------------------

def _rec(priref, authors=(), corporate=(), publishers=()):
    xml = f'<record priref="{priref}" modification="2026-01-01T00:00:00"><Title><title>Boek {priref}</title></Title>'
    xml += ''.join(f'<Author><author.name>{a}</author.name></Author>' for a in authors)
    xml += ''.join(f'<Corporate_author><corporate_author>{c}</corporate_author></Corporate_author>' for c in corporate)
    xml += ''.join(f'<Publisher><place_of_publication_2>{p}</place_of_publication_2><publisher>{n}</publisher></Publisher>'
                   for p, n in publishers)
    return ET.fromstring(xml + '</record>')


def test_same_author_in_two_records_is_one_node(config):
    g = Graph()
    for p in ('1', '2'):
        ts.transform_book(g, config, _rec(p, authors=['Meijer, Jaap'], publishers=[('Utrecht', 'Kosmos')]),
                          config['SOURCES']['books'])
    a, b = book(config, '1'), book(config, '2')
    assert set(g.objects(a, SDO.author)) == set(g.objects(b, SDO.author))
    assert set(g.objects(a, SDO.publisher)) == set(g.objects(b, SDO.publisher))


def test_organization_as_author_and_publisher_is_one_node(config):
    g = Graph()
    ts.transform_book(g, config, _rec('1', corporate=['Frans Halsmuseum'], publishers=[('Haarlem', 'Frans Halsmuseum')]),
                      config['SOURCES']['books'])
    (author,) = g.objects(book(config, '1'), SDO.author)
    (publisher,) = g.objects(book(config, '1'), SDO.publisher)
    assert author == publisher                                # 'alle boeken van/uitgegeven door Frans Halsmuseum'
    assert (author, RDF.type, SDO.Organization) in g and len(list(g.objects(author, SDO.name))) == 1


def test_different_names_stay_different_nodes(config):
    g = Graph()
    ts.transform_book(g, config, _rec('1', authors=['Smit, J.']), config['SOURCES']['books'])
    ts.transform_book(g, config, _rec('2', authors=['Smit, K.']), config['SOURCES']['books'])
    assert set(g.objects(book(config, '1'), SDO.author)).isdisjoint(set(g.objects(book(config, '2'), SDO.author)))


# --- losse hulpfuncties ---------------------------------------------------

def test_join_title():
    assert ts.join_title('De', 'provincie') == 'De provincie'
    assert ts.join_title("L'", 'Oeil') == "L'Oeil"
    assert ts.join_title(None, 'Titel') == 'Titel'
    assert ts.join_title('', '') == ''


def test_normalize_isbn():
    assert ts.normalize_isbn('90-72033-20-5') == '9072033205'
    assert ts.normalize_isbn('ISBN: 978-90-12345-67-8') == '9789012345678'
    assert ts.normalize_isbn('90 7203 320 x') == '907203320X'
    assert ts.normalize_isbn('123') is None


def test_invalid_isbn_is_kept_as_property_value(config):
    g = Graph()
    rec = ET.fromstring('<record priref="9" modification="2026-01-01T00:00:00"><Title><title>T</title></Title>'
                        '<Isbn><isbn>12-34</isbn></Isbn></record>')
    work = ts.transform_book(g, config, rec, config['SOURCES']['books'])
    assert g.value(work, SDO.isbn) is None
    assert 'ISBN (ongeldig)' in {str(g.value(i, SDO.propertyID)) for i in g.objects(work, SDO.identifier)}


def test_is_organization():
    assert ts.is_organization('Stichting Oude Kerken')
    assert ts.is_organization('Ministerie van Volkshuisvesting, Ruimtelijke Ordening en Milieubeheer')
    assert ts.is_organization('R&H, projecten en adviezen')
    assert ts.is_organization('Frans Halsmuseum')
    assert ts.is_organization('Rijksmuseum Muiderslot')
    assert not ts.is_organization('Wallis de Vries, G.C.')
    assert not ts.is_organization('Bond, J.')              # achternaam die ook een organisatiewoord is
    assert not ts.is_organization('Hugo Kingmans')
