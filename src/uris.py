"""Vaste adressen en de basis-nodes (organisatie, dataset).

Het adres van een node hangt alleen af van een sleutel (priref, positie, naam). Een tweede run levert dus
dezelfde adressen op. Het patroon is hetzelfde als in de andere RCE-ETL's: uuid3 over de sleutel.
"""
import uuid
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

_INVALID_URI_CHARS = '<>" {}|\\^`'


def get_object_uri(base_uri: str, collection_id: str, key: str, kind: str) -> URIRef:
    """{base}{collection}/id/{kind}/{uuid3(url, key)}; kind is een korte klassenaam in kleine letters."""
    obj_uuid = uuid.uuid3(uuid.NAMESPACE_URL, str(key))
    return URIRef(f"{base_uri.rstrip('/')}/{collection_id.strip('/')}/id/{kind}/{obj_uuid}")


def is_valid_uri(uri: str) -> bool:
    return bool(uri) and not any(c in uri for c in _INVALID_URI_CHARS)


def get_organization(config: dict) -> Graph:
    """Graph met de organisatie die de dataset publiceert."""
    graph = Graph()
    org = URIRef(config['ORG_URI'])
    graph.add((org, RDF.type, SDO.Organization))
    graph.add((org, SDO.name, Literal(config['ORG_NAME'], lang='nl')))
    graph.add((org, SDO.sameAs, URIRef(config['ORG_SAME_AS'])))
    graph.add((org, SDO.identifier, Literal(config['ORG_ISIL'], datatype=XSD.string)))
    graph.add((org, SDO.alternateName, Literal(config['ORG_ALTNAME'], lang='en')))
    contact = get_object_uri('https://linkeddata.cultureelerfgoed.nl/', 'rce/datacatalog',
                             config['ORG_CONTACT_EMAIL'], 'contactpoint')
    graph.add((contact, RDF.type, SDO.ContactPoint))
    graph.add((contact, SDO.name, Literal(config['ORG_CONTACT_NAME'], lang='nl')))
    graph.add((contact, SDO.email, Literal(config['ORG_CONTACT_EMAIL'], datatype=XSD.string)))
    graph.add((org, SDO.contactPoint, contact))
    return graph


def get_dataset(config: dict) -> Graph:
    """Graph met de dataset-node waar elk record naar verwijst (schema:isPartOf) plus de organisatie."""
    graph = get_organization(config)
    dataset = URIRef(config['DATASET_URI'])
    graph.add((dataset, RDF.type, SDO.Dataset))
    graph.add((dataset, SDO.name, Literal(config['DATASET_NAME'], lang='nl')))
    if config.get('DATASET_DESCRIPTION'):
        graph.add((dataset, SDO.description, Literal(config['DATASET_DESCRIPTION'], lang='nl')))
    graph.add((dataset, SDO.publisher, URIRef(config['ORG_URI'])))
    if config.get('LICENSE_URI'):
        graph.add((dataset, SDO.license, URIRef(config['LICENSE_URI'])))
    return graph
