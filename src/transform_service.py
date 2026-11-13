"""Transformatie van de bibliotheekrecords van de RCE naar schema.org (RDF).

Bronnen:
  boek      Adlib-API (volledig record): titel, auteurs, uitgever + plaats, reeks, ISBN, onderwerpen met CHT-URI's.
  artikel   Adlib-API (titel, auteurs, onderwerpen) samengevoegd met OAI `oai_dc` (tijdschrift, jaargang, jaar,
            pagina's) op priref. Het OAI-record kent geen titel, het API-record geen tijdschrift.

De mapping staat in de docstrings van `transform_book` en `transform_article` en in README.md.
Elk record neemt al zijn eigen nodes mee, zodat een uitvoerbestand (chunk) op zichzelf valideerbaar is.
"""
import re
from typing import Optional

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import adlib_client as adlib
import uris

NS_PREFIX = {
    'http://purl.org/dc/elements/1.1/': 'dc',
    'http://purl.org/dc/terms/': 'dcterms',
    'http://www.europeana.eu/schemas/edm/': 'edm',
}

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
        # datum waarop het record in de bron voor het laatst is gewijzigd (verplicht in het CN-profiel)
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
    """schema:author is een subeigenschap van schema:creator; het CN-profiel toetst op creator, dus beide."""
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


def _add_api_description(graph: Graph, config: dict, work: URIRef, record, extra_notes=()):
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

    for note in dict.fromkeys(list(adlib.texts(record, 'notes')) + list(extra_notes)):
        graph.add((work, SDO.description, Literal(note, lang='nl')))
    for text in adlib.texts(record, 'abstract'):
        graph.add((work, SDO.abstract, Literal(text, lang='nl')))


def _api_title(record) -> str:
    return join_title(adlib.first(record, 'Title/lead_word'), adlib.first(record, 'Title/title'))


# ---------------------------------------------------------------------------
# boeken (Adlib-API)
# ---------------------------------------------------------------------------

def transform_book(graph: Graph, config: dict, record, source: dict) -> URIRef:
    """Adlib-boekrecord -> schema:Book (en schema:CreativeWork, voor het CN-profiel).

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
        if m:
            graph.add((work, SDO.numberOfPages, Literal(int(m.group(1)), datatype=XSD.integer)))
    for edition in adlib.texts(record, 'edition'):
        graph.add((work, SDO.bookEdition, Literal(edition, lang='nl')))

    _add_api_description(graph, config, work, record)
    return work


# ---------------------------------------------------------------------------
# artikelen (OAI oai_dc + Adlib-API)
# ---------------------------------------------------------------------------

def collect_fields(element) -> dict:
    """OAI Dublin Core: {'dc:source': ['journal = {..', ...], ...}; sleutel is prefix:lokale naam, ongetrimd."""
    fields = {}
    for child in element:
        tag = child.tag
        if not isinstance(tag, str) or '}' not in tag:
            continue
        ns, local = tag[1:].split('}', 1)
        fields.setdefault(f'{NS_PREFIX.get(ns, ns)}:{local}', []).append(''.join(child.itertext()))
    return fields


_BIBTEX = re.compile(r'^\s*(?P<key>\w+)\s*=\s*\{(?P<value>.*?)\}?\s*,?\s*$', re.S)


def bibtex_value(value: str, key: str) -> Optional[str]:
    """'author = {Harst, J.J. van der},' -> 'Harst, J.J. van der' (alleen als de sleutel klopt)."""
    m = _BIBTEX.match(value or '')
    if m and m.group('key').lower() == key:
        return clean(m.group('value')) or None
    return None


def parse_article_source(sources: list) -> dict:
    """Ontleed de dc:source-stukken van een artikel.

    ['journal = {Stad en lande : ... ; ', '27 ', '(1990)', ', 69', ', 198-203},', 'Source.materiaal: tijdschrift']
    -> journal, volume '27', year '1990', issue '69', pages '198-203', material 'tijdschrift'.
    Een journaltitel met voorloop-lidwoord staat in twee stukken ('journal = {De', 'journal = {vrije Fries ; ').
    Velden die niet ontleed kunnen worden blijven leeg; het record blijft bestaan.
    """
    material = None
    pieces = []
    for s in sources:
        s = s or ''
        if s.strip().lower().startswith('source.materiaal:'):
            material = clean(s.split(':', 1)[1]) or None
        else:
            pieces.append(s)
    # lidwoord-split: een tweede stuk dat opnieuw 'journal = {' opent hoort bij het eerste
    joined = ''
    for p in pieces:
        opens = re.match(r'^\s*journal\s*=\s*\{', p, re.I)
        if opens:
            p = p[opens.end():]
            joined = joined + (' ' if joined else '') + p
        else:
            joined += p
    result = {'journal': None, 'volume': None, 'year': None, 'issue': None, 'pages': None, 'material': material}
    if ' ; ' not in joined + ' ':
        result['journal'] = clean(joined.rstrip('}, ')) or None
        return result
    title, _, rest = (joined + ' ').rpartition(' ; ')
    result['journal'] = clean(title) or None
    rest = rest.strip().rstrip(',').rstrip('}').strip().rstrip(',').strip()
    m = re.match(r'^(?P<volume>[^(),]*?)\s*(?:\((?P<year>[^)]*)\))?\s*(?:,\s*(?P<tail>.*))?$', rest)
    if not m:
        return result
    result['volume'] = clean(m.group('volume')) or None
    result['year'] = year_of(m.group('year'))
    tail = clean(m.group('tail'))
    if tail:
        items = [clean(i) for i in tail.split(',') if clean(i)]
        # een bereik als eerste item ('8-9, 12') is een paginering, geen aflevering
        if len(items) > 1 and '-' not in items[0]:
            result['issue'] = items[0]
            result['pages'] = ', '.join(items[1:])
        else:
            result['pages'] = ', '.join(items)
    return result


def transform_article(graph: Graph, config: dict, header: dict, fields: dict, source: dict,
                      record=None) -> URIRef:
    """Artikel -> schema:Article (en schema:CreativeWork). `fields` komt uit de OAI, `record` (optioneel) uit het API.

    API Title                    -> schema:name (@nl); zonder API-record ontbreekt de titel (er wordt niets verzonnen)
    API Author, Corporate_author -> schema:author + schema:creator; zonder API: OAI 'author = {..}'
    API subjects, places, notes  -> zoals bij boeken (schema:about, schema:spatialCoverage, schema:description)
    OAI dc:source 'journal = {..}' -> keten schema:isPartOf: PublicationIssue -> PublicationVolume -> Periodical
                                      (alleen de niveaus waarvoor gegevens zijn)
    OAI pagina's                 -> schema:pageStart / schema:pageEnd, anders schema:pagination
    OAI 'Source.materiaal'       -> schema:additionalType (DefinedTerm) op de Periodical
    OAI 'year = {..}'            -> schema:datePublished (xsd:gYear)
    OAI 'notes = {..}'           -> schema:description (@nl)
    """
    priref = record_priref(header['identifier'])
    modified = (record.get('modification') if record is not None else None) or header['datestamp']
    work = _start_record(graph, config, 'article', priref, [SDO.Article, SDO.CreativeWork], modified)
    _add_url(graph, work, source.get('catalog_url'), priref)

    oai_authors = list(dict.fromkeys(a for a in (bibtex_value(v, 'author') for v in fields.get('dc:creator', [])) if a))
    oai_notes = [n for n in (bibtex_value(v, 'notes') for v in fields.get('dc:notes', [])) if n]
    if record is not None:
        name = _api_title(record)
        if name:
            graph.add((work, SDO.name, Literal(name, lang='nl')))
        persons = adlib.texts(record, 'Author/author.name') or oai_authors
        _add_authors(graph, config, work, persons, adlib.texts(record, 'Corporate_author/corporate_author'))
        _add_api_description(graph, config, work, record, extra_notes=oai_notes)
    else:
        _add_authors(graph, config, work, oai_authors, [])
        for note in dict.fromkeys(oai_notes):
            graph.add((work, SDO.description, Literal(note, lang='nl')))

    src = parse_article_source(fields.get('dc:source', []))
    year = year_of(next((bibtex_value(v, 'year') for v in fields.get('dc:date', []) if bibtex_value(v, 'year')), None)) \
        or src['year']
    if year:
        graph.add((work, SDO.datePublished, Literal(year, datatype=XSD.gYear)))

    # pagina's
    pages = src['pages']
    if pages:
        m = re.fullmatch(r'(\d+)\s*-\s*(\d+)', pages)
        single = re.fullmatch(r'\d+', pages)
        if m:
            graph.add((work, SDO.pageStart, Literal(m.group(1), datatype=XSD.string)))
            graph.add((work, SDO.pageEnd, Literal(m.group(2), datatype=XSD.string)))
        elif single:
            graph.add((work, SDO.pageStart, Literal(pages, datatype=XSD.string)))
            graph.add((work, SDO.pageEnd, Literal(pages, datatype=XSD.string)))
        else:
            graph.add((work, SDO.pagination, Literal(pages, datatype=XSD.string)))

    # tijdschrift -> jaargang/deel -> aflevering
    journal = src['journal']
    if journal:
        periodical = _node(config, f'periodical/{journal}', 'periodical')
        graph.add((periodical, RDF.type, SDO.Periodical))
        graph.add((periodical, SDO.name, Literal(journal, lang='nl')))
        if src['material']:
            _add_named(graph, config, periodical, SDO.additionalType, src['material'], 'term', [SDO.DefinedTerm])
        container = periodical
        if src['volume'] or src['year']:
            volume = _node(config, f"volume/{journal}/{src['volume'] or ''}/{src['year'] or ''}", 'publicationvolume')
            graph.add((volume, RDF.type, SDO.PublicationVolume))
            if src['volume']:
                graph.add((volume, SDO.volumeNumber, Literal(src['volume'], datatype=XSD.string)))
            if src['year']:
                graph.add((volume, SDO.datePublished, Literal(src['year'], datatype=XSD.gYear)))
            graph.add((volume, SDO.isPartOf, periodical))
            container = volume
        if src['issue']:
            issue = _node(config, f"issue/{journal}/{src['volume'] or ''}/{src['year'] or ''}/{src['issue']}",
                          'publicationissue')
            graph.add((issue, RDF.type, SDO.PublicationIssue))
            graph.add((issue, SDO.issueNumber, Literal(src['issue'], datatype=XSD.string)))
            if src['year']:
                graph.add((issue, SDO.datePublished, Literal(src['year'], datatype=XSD.gYear)))
            graph.add((issue, SDO.isPartOf, container))
            container = issue
        graph.add((work, SDO.isPartOf, container))
    return work
