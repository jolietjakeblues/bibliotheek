"""Transformatie van de bibliotheekrecords van de RCE naar schema.org (RDF).

Bronnen:
  boek      Adlib-API (volledig record): titel, auteurs, uitgever + plaats, reeks, ISBN, onderwerpen met CHT-URI's.
  artikel   Adlib-API, alias `article`: titel, auteurs, onderwerpen en de groep `Source` (tijdschrift, jaargang, aflevering,
            jaar, pagina's, en het priref van het tijdschriftrecord). De OAI bepaalt alleen welke artikelen worden gepubliceerd.

De mapping staat in de docstrings van `transform_book` en `transform_article` en in README.md.
Elk record neemt al zijn eigen nodes mee, zodat een uitvoerbestand (chunk) op zichzelf valideerbaar is.
"""
import re
from typing import Optional

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import adlib_client as adlib
import uris

# Organisatie-achtige namen: de bron maakt geen onderscheid tussen persoon en instelling bij trefwoorden.
_ORG_WORDS = re.compile(
    r'\b(ministerie|gemeente|provincie|stichting|vereniging|rijksdienst|rijksinstituut|instituut|museum|bureau|'
    r'commissie|werkgroep|raad|dienst|universiteit|hogeschool|genootschap|kring|bond|archief|bibliotheek|'
    r'waterschap|projectgroep|adviesbureau|uitgeverij|maatschappij|vof|b\.?v\.?|n\.?v\.?|gmbh|ltd|inc|'
    r'department|ministry|institute|society|council|association|foundation|werkgemeenschap|federatie|'
    r'kamer|college|inspectie|staatsbosbeheer|monumentenzorg|projecten|historische|heemkundige)\b', re.I)
# woorden die ook als eind van een samenstelling een instelling aanduiden (Frans Halsmuseum, Rijksuniversiteit)
_ORG_SUFFIX = re.compile(r'(museum|instituut|universiteit|archief|bibliotheek|vereniging|uitgeverij|genootschap|'
                         r'hogeschool|stichting)\b', re.I)
# 'Achternaam, Initialen' of 'Achternaam, Voornaam': een persoon, ook als de achternaam een organisatiewoord is (Bond, Raad)
_PERSON_NAME = re.compile(r"^[^,]{1,40}, [A-ZÀ-Ý][\w.\-' ]{0,30}$")
_ORG_START = re.compile(r'^(ministerie|gemeente|provincie|stichting|vereniging|rijksdienst|rijksinstituut|instituut|'
                        r'museum|commissie|werkgroep|universiteit|hogeschool|genootschap|waterschap)\b', re.I)
_YEAR = re.compile(r'(?<!\d)(\d{4})(?!\d)')
_PAGES_ONLY = re.compile(r"^\s*(\d+)\s*(?:p\.?|pp\.?|pag\.?|pagina'?s|blz\.?)?\s*$", re.I)
_ISBN_PREFIX = re.compile(r'^\s*ISBN\b:?\s*', re.I)


def clean(value: Optional[str]) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def year_of(value: Optional[str]) -> Optional[str]:
    m = _YEAR.search(value or '')
    return m.group(1) if m else None


def record_priref(identifier: str) -> str:
    """OAI '1970:200000001' -> '200000001' (het deel na de database-prefix is het priref van Adlib)."""
    return identifier.split(':', 1)[1].strip() if ':' in identifier else identifier.strip()


def join_title(lead_word: Optional[str], title: Optional[str]) -> str:
    """Adlib bewaart het voorloop-lidwoord apart: ('De', 'provincie : ...') -> 'De provincie : ...'; ('L'', 'Oeil') -> 'L'Oeil'."""
    lead, rest = clean(lead_word), clean(title)
    if not lead:
        return rest
    return lead + ('' if lead.endswith(("'", '’')) else ' ') + rest


def normalize_isbn(value: str) -> Optional[str]:
    """'90-72033-20-5' of 'ISBN: 90-72033-20-5' -> '9072033205'; None als er geen geldige ISBN-10/13 uit komt."""
    digits = re.sub(r'[\s\-]', '', _ISBN_PREFIX.sub('', value or '')).upper()
    return digits if re.fullmatch(r'\d{9}[\dX]|\d{13}', digits) else None


# ---------------------------------------------------------------------------
# gedeelde bouwstenen
# ---------------------------------------------------------------------------

def _node(config: dict, key: str, kind: str) -> URIRef:
    return uris.get_object_uri(config['BASE_URI'], config['COLLECTION_ID'], key, kind)


def organization_node(config: dict, name: str) -> URIRef:
    """Eén adres per organisatienaam, ongeacht of het als auteur of als uitgever optreedt."""
    return _node(config, f'organization/{name}', 'organization')


def is_organization(name: str) -> bool:
    """Benadering: de bron kent geen onderscheid tussen persoon en instelling bij auteurs en trefwoorden."""
    if _ORG_START.match(name):
        return True
    if _PERSON_NAME.match(name):
        return False
    return bool(_ORG_WORDS.search(name) or _ORG_SUFFIX.search(name))


def _start_record(graph: Graph, config: dict, kind: str, priref: str, types: list, modified: Optional[str]) -> URIRef:
    node = _node(config, priref, kind)
    for t in types:
        graph.add((node, RDF.type, t))
    graph.add((node, SDO.isPartOf, URIRef(config['DATASET_URI'])))
    graph.add((node, SDO.sdPublisher, URIRef(config['ORG_URI'])))
    if modified:
        # datum waarop het record in de bron voor het laatst is gewijzigd (verplicht in het NDE-applicatieprofiel)
        graph.add((node, SDO.sdDatePublished, Literal(modified[:10], datatype=XSD.date)))
    if config.get('LICENSE_URI'):
        graph.add((node, SDO.license, URIRef(config['LICENSE_URI'])))
    # het priref als identifier, zoals in de andere RCE-ETL's
    ident = _node(config, f'{priref}/priref', 'propertyvalue')
    graph.add((ident, RDF.type, SDO.PropertyValue))
    graph.add((ident, SDO.propertyID, Literal('priref')))
    graph.add((ident, SDO.value, Literal(priref, datatype=XSD.string)))
    graph.add((node, SDO.identifier, ident))
    return node


def _add_url(graph: Graph, node: URIRef, template: Optional[str], priref: str):
    if template:
        url = template.format(priref=priref)
        if uris.is_valid_uri(url):
            graph.add((node, SDO.url, URIRef(url)))


def _agent(graph: Graph, config: dict, name: str, force_org: bool = False) -> URIRef:
    """Gedeelde node per naam (persoon of organisatie). Gelijke naam is gelijke persoon: de naam is de
    genormaliseerde ingang uit de catalogus, maar zonder authority-nummer kan een homoniem erbij zitten."""
    if force_org or is_organization(name):
        node = organization_node(config, name)
        graph.add((node, RDF.type, SDO.Organization))
    else:
        node = _node(config, f'person/{name}', 'person')
        graph.add((node, RDF.type, SDO.Person))
    graph.add((node, SDO.name, Literal(name, lang='nl')))
    return node


def _add_authors(graph: Graph, config: dict, work: URIRef, persons: list, corporate: list):
    """schema:author is een subeigenschap van schema:creator; beide staan erop, zodat de shapes op creator kunnen toetsen."""
    seen = set()
    for name, force_org in [(n, False) for n in persons] + [(n, True) for n in corporate]:
        agent = _agent(graph, config, name, force_org)
        if agent in seen:
            continue
        seen.add(agent)
        graph.add((work, SDO.author, agent))
        graph.add((work, SDO.creator, agent))


def _add_named(graph: Graph, config: dict, work: URIRef, predicate: URIRef, name: str, kind: str, types: list):
    """Gedeelde benoemde node (term, plaats): zelfde naam, zelfde adres."""
    node = _node(config, f'{kind}/{name}', kind)
    for t in types:
        graph.add((node, RDF.type, t))
    graph.add((node, SDO.name, Literal(name, lang='nl')))
    graph.add((work, predicate, node))
    return node


def _add_api_description(graph: Graph, config: dict, work: URIRef, record):
    """Velden die boeken en artikelen in het API-record delen: onderwerpen, plaatsen, monumenten, notities."""
    for keyword in adlib.texts(record, 'Keyword/keyword.contents'):
        _add_named(graph, config, work, SDO.about, keyword, 'term', [SDO.DefinedTerm])
    # CHT-term: rechtstreeks de IRI; het label staat in de thesaurus-graph van dezelfde dataset
    for uri in adlib.texts(record, 'Content_subject/RNA_URI'):
        if uri.startswith(('http://', 'https://')) and uris.is_valid_uri(uri):
            graph.add((work, SDO.about, URIRef(uri)))
    for name in adlib.texts(record, 'Person_keyword/person.keyword.name'):
        graph.add((work, SDO.about, _agent(graph, config, name)))

    places = adlib.texts(record, 'geographical_keyword')
    # Het monument is een gedeelde node met alleen het rijksmonumentnummer. De naam staat niet op die node: hetzelfde
    # nummer komt in verschillende records met een andere schrijfwijze voor ('Slot Loevestein', 'Loevestein'), en een
    # gedeelde node mag maar één naam per taal hebben. De naam blijft als plaats bij het boek.
    for number in adlib.texts(record, 'Monumentnumber/monument.number'):
        monument = _node(config, f'rijksmonument/{number}', 'monument')
        graph.add((monument, RDF.type, SDO.LandmarksOrHistoricalBuildings))
        ident = _node(config, f'rijksmonument/{number}/nummer', 'propertyvalue')
        graph.add((ident, RDF.type, SDO.PropertyValue))
        graph.add((ident, SDO.propertyID, Literal('rijksmonumentnummer')))
        graph.add((ident, SDO.value, Literal(number, datatype=XSD.string)))
        graph.add((monument, SDO.identifier, ident))
        graph.add((work, SDO.about, monument))
    places += adlib.texts(record, 'monument.name')
    for tag in ('monument.country', 'monument.province', 'monument.county', 'monument.place'):
        places += adlib.texts(record, tag)
    for place in dict.fromkeys(places):
        _add_named(graph, config, work, SDO.spatialCoverage, place, 'place', [SDO.Place])

    for note in dict.fromkeys(adlib.texts(record, 'notes')):
        graph.add((work, SDO.description, Literal(note, lang='nl')))
    for text in adlib.texts(record, 'abstract'):
        graph.add((work, SDO.abstract, Literal(text, lang='nl')))


def _api_title(record) -> str:
    return join_title(adlib.first(record, 'Title/lead_word'), adlib.first(record, 'Title/title'))


def has_title(record) -> bool:
    """Heeft het API-record een titel? Een boek zonder titel is geen bruikbaar boek: op 20 november waren 18 records van
    de 216.887 leeg (alleen een priref, soms een jaartal) en kregen geen `schema:name`, dat voor een Book verplicht is."""
    return bool(_api_title(record))


# ---------------------------------------------------------------------------
# boeken (Adlib-API)
# ---------------------------------------------------------------------------

def transform_book(graph: Graph, config: dict, record, source: dict) -> URIRef:
    """Adlib-boekrecord -> schema:Book (en schema:CreativeWork, voor het NDE-applicatieprofiel).

    Title/lead_word + title            -> schema:name (@nl)
    Author/author.name                 -> schema:author + schema:creator (Person of Organization, gedeeld per naam)
    Corporate_author                   -> idem, altijd Organization
    Publisher/publisher                -> schema:publisher (Organization, gedeeld per naam)
    Publisher/place_of_publication_2   -> schema:locationCreated (Place)
    Publisher/year_of_publication      -> schema:datePublished (xsd:gYear)
    Series_title                       -> schema:isPartOf (CreativeWorkSeries) en schema:position (deelnummer)
    Isbn/isbn                          -> schema:isbn (genormaliseerd), anders PropertyValue
    pagination, illustrations, dimensions -> schema:size (tekst) en schema:numberOfPages (alleen een los aantal)
    edition                            -> schema:bookEdition
    Keyword/keyword.contents           -> schema:about (DefinedTerm)
    Content_subject/RNA_URI            -> schema:about (CHT-IRI)
    Person_keyword                     -> schema:about (Person/Organization)
    geographical_keyword, monument.*   -> schema:spatialCoverage (Place)
    Monumentnumber                     -> schema:about (LandmarksOrHistoricalBuildings met rijksmonumentnummer)
    notes / abstract                   -> schema:description / schema:abstract (@nl)
    record/@modification               -> schema:sdDatePublished
    Niet overgenomen: comments (interne notities over de collectie), Digital_reference (externe links, deels via een
    proxy), shelf_mark, conference, table_of_contents, accompanying_material.
    """
    priref = record.get('priref') or adlib.first(record, 'priref')
    work = _start_record(graph, config, 'book', priref, [SDO.Book, SDO.CreativeWork], record.get('modification'))

    name = _api_title(record)
    if name:
        graph.add((work, SDO.name, Literal(name, lang='nl')))
    _add_url(graph, work, source.get('catalog_url'), priref)
    _add_authors(graph, config, work, adlib.texts(record, 'Author/author.name'),
                 adlib.texts(record, 'Corporate_author/corporate_author'))

    for group in record.findall('Publisher'):
        publisher, place = adlib.first(group, 'publisher'), adlib.first(group, 'place_of_publication_2')
        if publisher:
            org = organization_node(config, publisher)
            graph.add((org, RDF.type, SDO.Organization))
            graph.add((org, SDO.name, Literal(publisher, lang='nl')))
            graph.add((work, SDO.publisher, org))
        if place:
            _add_named(graph, config, work, SDO.locationCreated, place, 'place', [SDO.Place])
    years = [y for y in (year_of(v) for v in adlib.texts(record, 'Publisher/year_of_publication')) if y]
    if years:
        graph.add((work, SDO.datePublished, Literal(years[0], datatype=XSD.gYear)))

    series_groups = [g for g in record.findall('Series_title') if adlib.first(g, 'series.title')]
    for group in series_groups:
        series_name = join_title(adlib.first(group, 'series.lead_word'), adlib.first(group, 'series.title'))
        series = _node(config, f'series/{series_name}', 'series')
        graph.add((series, RDF.type, SDO.CreativeWorkSeries))
        graph.add((series, SDO.name, Literal(series_name, lang='nl')))
        graph.add((work, SDO.isPartOf, series))
    if len(series_groups) == 1 and adlib.first(series_groups[0], 'series.number'):
        graph.add((work, SDO.position, Literal(adlib.first(series_groups[0], 'series.number'), datatype=XSD.string)))

    for value in adlib.texts(record, 'Isbn/isbn'):
        isbn = normalize_isbn(value)
        if isbn:
            graph.add((work, SDO.isbn, Literal(isbn, datatype=XSD.string)))
        else:
            # ISBN die niet klopt: wel bewaren, maar niet als schema:isbn
            bad = _node(config, f'{priref}/isbn/{value}', 'propertyvalue')
            graph.add((bad, RDF.type, SDO.PropertyValue))
            graph.add((bad, SDO.propertyID, Literal('ISBN (ongeldig)')))
            graph.add((bad, SDO.value, Literal(_ISBN_PREFIX.sub('', value).strip(), datatype=XSD.string)))
            graph.add((work, SDO.identifier, bad))

    extent = adlib.texts(record, 'pagination') + adlib.texts(record, 'illustrations') + adlib.texts(record, 'dimensions')
    if extent:
        graph.add((work, SDO.size, Literal(' ; '.join(extent), datatype=XSD.string)))
        pages = adlib.first(record, 'pagination')
        m = _PAGES_ONLY.match(pages) if pages else None
        if m and int(m.group(1)) > 0:          # '0 p.' (gevonden in een echt boek) is geen aantal; de tekst blijft in schema:size
            graph.add((work, SDO.numberOfPages, Literal(int(m.group(1)), datatype=XSD.integer)))
    for edition in adlib.texts(record, 'edition'):
        graph.add((work, SDO.bookEdition, Literal(edition, lang='nl')))

    _add_api_description(graph, config, work, record)
    return work


# ---------------------------------------------------------------------------
# artikelen (OAI oai_dc + Adlib-API)
# ---------------------------------------------------------------------------

def article_source(record) -> Optional[dict]:
    """Het tijdschrift waarin het artikel staat, uit de groep `Source` van het API-record (alias `article`).

    Geeft None als het record geen `Source` met een titel heeft. Staan er meer groepen, dan telt de eerste met een titel."""
    for src in record.findall('Source'):
        title = adlib.first(src, 'source.title')
        if not title:
            continue
        return {
            'journal': join_title(adlib.first(src, 'source.title.lead_word'), title),
            'lref': adlib.first(src, 'source.title.lref'),            # priref van het tijdschriftrecord
            'volume': adlib.first(src, 'source.volume'),
            'issue': adlib.first(src, 'source.issue'),
            'year': year_of(adlib.first(src, 'source.publication_years')),
            'pages': adlib.first(src, 'source.pagination'),
            'material': adlib.first(src, 'source.material_type'),
        }
    return None


def transform_article(graph: Graph, config: dict, record, source: dict) -> URIRef:
    """Adlib-artikelrecord (alias `article`) -> schema:Article (en schema:CreativeWork).

    Title/lead_word + title        -> schema:name (@nl)
    Author, Corporate_author       -> schema:author + schema:creator
    subjects, places, notes        -> zoals bij boeken (schema:about, schema:spatialCoverage, schema:description)
    Source/source.title (+ lead_word) -> keten schema:isPartOf: PublicationIssue -> PublicationVolume -> Periodical
                                      (alleen de niveaus waarvoor gegevens zijn)
    Source/source.title.lref       -> het adres van de Periodical (het priref van het tijdschriftrecord) en zijn catalogus-url
    Source/source.volume, .issue   -> schema:volumeNumber, schema:issueNumber
    Source/source.pagination       -> schema:pageStart / schema:pageEnd, anders schema:pagination
    Source/source.material_type    -> schema:additionalType (DefinedTerm) op de Periodical
    search_year (anders het jaar van het tijdschrift) -> schema:datePublished (xsd:gYear)

    Niet gepubliceerd: shelf_mark, input.*, Edit (gebruikersnamen), record_access.owner, acquisition_date.
    """
    priref = record.get('priref')
    work = _start_record(graph, config, 'article', priref, [SDO.Article, SDO.CreativeWork], record.get('modification'))
    _add_url(graph, work, source.get('catalog_url'), priref)

    name = _api_title(record)
    if name:                                   # zonder titel in de bron geen schema:name: er wordt niets verzonnen
        graph.add((work, SDO.name, Literal(name, lang='nl')))
    _add_authors(graph, config, work, adlib.texts(record, 'Author/author.name'),
                 adlib.texts(record, 'Corporate_author/corporate_author'))
    _add_api_description(graph, config, work, record)

    src = article_source(record) or {k: None for k in ('journal', 'lref', 'volume', 'issue', 'year', 'pages', 'material')}
    year = year_of(adlib.first(record, 'search_year')) or src['year']
    if year:
        graph.add((work, SDO.datePublished, Literal(year, datatype=XSD.gYear)))

    # pagina's
    pages = src['pages']
    if pages:
        m = re.fullmatch(r'(\d+)\s*-\s*(\d+)', pages)
        if m:
            graph.add((work, SDO.pageStart, Literal(m.group(1), datatype=XSD.string)))
            graph.add((work, SDO.pageEnd, Literal(m.group(2), datatype=XSD.string)))
        elif re.fullmatch(r'\d+', pages):
            graph.add((work, SDO.pageStart, Literal(pages, datatype=XSD.string)))
            graph.add((work, SDO.pageEnd, Literal(pages, datatype=XSD.string)))
        else:
            graph.add((work, SDO.pagination, Literal(pages, datatype=XSD.string)))

    # tijdschrift -> jaargang/deel -> aflevering. Het tijdschrift heeft het adres van zijn eigen record (lref);
    # ontbreekt dat, dan valt het terug op de naam.
    journal = src['journal']
    if journal:
        key = src['lref'] or journal
        periodical = _node(config, f'periodical/{key}', 'periodical')
        graph.add((periodical, RDF.type, SDO.Periodical))
        graph.add((periodical, SDO.name, Literal(journal, lang='nl')))
        if src['lref']:
            _add_url(graph, periodical, source.get('catalog_url'), src['lref'])
        if src['material']:
            _add_named(graph, config, periodical, SDO.additionalType, src['material'], 'term', [SDO.DefinedTerm])
        container = periodical
        if src['volume'] or src['year']:
            volume = _node(config, f"volume/{key}/{src['volume'] or ''}/{src['year'] or ''}", 'publicationvolume')
            graph.add((volume, RDF.type, SDO.PublicationVolume))
            if src['volume']:
                graph.add((volume, SDO.volumeNumber, Literal(src['volume'], datatype=XSD.string)))
            if src['year']:
                graph.add((volume, SDO.datePublished, Literal(src['year'], datatype=XSD.gYear)))
            graph.add((volume, SDO.isPartOf, periodical))
            container = volume
        if src['issue']:
            issue = _node(config, f"issue/{key}/{src['volume'] or ''}/{src['year'] or ''}/{src['issue']}",
                          'publicationissue')
            graph.add((issue, RDF.type, SDO.PublicationIssue))
            graph.add((issue, SDO.issueNumber, Literal(src['issue'], datatype=XSD.string)))
            if src['year']:
                graph.add((issue, SDO.datePublished, Literal(src['year'], datatype=XSD.gYear)))
            graph.add((issue, SDO.isPartOf, container))
            container = issue
        graph.add((work, SDO.isPartOf, container))
    return work
