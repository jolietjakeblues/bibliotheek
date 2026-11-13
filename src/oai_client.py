"""Minimale OAI-PMH-client voor ListRecords (alleen standaardbibliotheek).

Afgeleid van oai_harvester.py (cultureelerfgoed/oai_harvester-voor-Collectie-Nederland), zonder het interactieve
deel: retries met backoff, Retry-After, timeout, opschonen van ongeldige XML-tekens en bijhouden van
completeListSize zodat de aanroeper de volledigheid kan controleren.
"""
import gzip
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from typing import Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

NS = {'oai': 'http://www.openarchives.org/OAI/2.0/'}

# ongeldige XML control chars (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F)
INVALID_XML_CHARS = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
# losse & die geen geldige entity openen: "A&B" -> "A&amp;B"
AMP_FIX = re.compile(r'&(?![A-Za-z#][A-Za-z0-9]*;)')

HEADERS = {
    'User-Agent': 'RCE-bibliotheek-ETL (OAI-PMH harvester)',
    'Accept': 'application/xml, text/xml;q=0.9, */*;q=0.1',
    'Accept-Encoding': 'identity, gzip, deflate',
}


class OaiError(Exception):
    """De bron antwoordde met een OAI-fout (bijv. cannotDisseminateFormat)."""


def build_url(base: str, params: dict) -> str:
    return f"{base.rstrip('?')}?{urllib.parse.urlencode(params)}"


def _open(url: str, retries: int, backoff: float) -> bytes:
    """HTTP GET met retries; respecteert Retry-After bij 429/503."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            # timeout: een hangende verbinding mag de hele GitHub Action niet blokkeren
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                encoding = resp.headers.get('Content-Encoding', '').lower()
            if encoding == 'gzip':
                raw = gzip.decompress(raw)
            elif encoding in ('deflate', 'zlib'):
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            return raw
        except urllib.error.HTTPError as e:
            wait = backoff * (attempt + 1)
            retry_after = (e.headers or {}).get('Retry-After')
            if e.code in (429, 503) and retry_after:
                try:
                    wait = max(wait, float(retry_after))
                except ValueError:
                    pass
            if attempt == retries - 1:
                raise
            logger.warning('HTTP %s bij %s; %.1fs wachten en opnieuw proberen', e.code, url, wait)
            time.sleep(wait)
        except Exception as e:  # netwerkfout, timeout
            if attempt == retries - 1:
                raise
            wait = backoff * (attempt + 1)
            logger.warning('Netwerkfout (%s); %.1fs wachten en opnieuw proberen', e, wait)
            time.sleep(wait)
    raise RuntimeError('onbereikbaar')


def fetch_and_parse(url: str, retries: int = 5, backoff: float = 2.0) -> ET.Element:
    """Ophalen, schonen en parsen. Bij een parsefout één reparatiepoging voor losse '&'."""
    text = _open(url, retries, backoff).decode('utf-8', errors='replace')
    text = INVALID_XML_CHARS.sub('', text)
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return ET.fromstring(AMP_FIX.sub('&amp;', text))


def _header_of(rec) -> dict:
    header_el = rec.find('oai:header', NS)
    return {
        'identifier': (header_el.findtext('oai:identifier', '', NS) if header_el is not None else '').strip(),
        'datestamp': (header_el.findtext('oai:datestamp', '', NS) if header_el is not None else '').strip(),
        'deleted': header_el is not None and header_el.get('status') == 'deleted',
    }


def _iter_pages(base_url: str, verb: str, set_spec: str, metadata_prefix: str, state: dict,
                sleep_between: float, retries: int, backoff: float) -> Iterator[ET.Element]:
    """Geeft per OAI-pagina het <verb>-element; houdt completeListSize bij in `state`."""
    params = {'verb': verb, 'metadataPrefix': metadata_prefix, 'set': set_spec}
    while True:
        root = fetch_and_parse(build_url(base_url, params), retries, backoff)

        error = root.find('oai:error', NS)
        if error is not None:
            if error.get('code') == 'noRecordsMatch':
                return
            raise OaiError(f"{error.get('code')}: {(error.text or '').strip()}")

        container = root.find(f'oai:{verb}', NS)
        yield container

        token_el = container.find('oai:resumptionToken', NS) if container is not None else None
        if token_el is not None and token_el.get('completeListSize'):
            state['complete_list_size'] = int(token_el.get('completeListSize'))
        token = (token_el.text or '').strip() if token_el is not None else ''
        if not token:
            return
        # per OAI-PMH hoort een vervolgverzoek alleen verb en resumptionToken te bevatten
        params = {'verb': verb, 'resumptionToken': token}
        time.sleep(sleep_between)


def iter_records(base_url: str, set_spec: str, metadata_prefix: str, state: dict,
                 sleep_between: float = 0.2, retries: int = 5, backoff: float = 2.0,
                 max_records: Optional[int] = None) -> Iterator[Tuple[dict, Optional[ET.Element]]]:
    """Geeft per record (header, metadata-element); metadata is None bij een verwijderd of leeg record.

    header = {'identifier', 'datestamp', 'deleted'}. In `state` worden `seen` en `complete_list_size`
    bijgehouden. Fouten bij het ophalen laten we bewust doorlopen: een run die stilzwijgend een deel mist
    is erger dan een run die faalt (de publicatiestap wordt dan niet uitgevoerd).
    """
    state.setdefault('seen', 0)
    for container in _iter_pages(base_url, 'ListRecords', set_spec, metadata_prefix, state,
                                 sleep_between, retries, backoff):
        for rec in container.findall('oai:record', NS):
            metadata = rec.find('oai:metadata', NS)
            element = metadata[0] if metadata is not None and len(metadata) else None
            state['seen'] += 1
            yield _header_of(rec), element
            if max_records is not None and state['seen'] >= max_records:
                return


def iter_headers(base_url: str, set_spec: str, metadata_prefix: str, state: dict,
                 sleep_between: float = 0.2, retries: int = 5, backoff: float = 2.0,
                 max_records: Optional[int] = None) -> Iterator[dict]:
    """Zoals iter_records, maar met ListIdentifiers: alleen de headers (identifier, datestamp, deleted)."""
    state.setdefault('seen', 0)
    for container in _iter_pages(base_url, 'ListIdentifiers', set_spec, metadata_prefix, state,
                                 sleep_between, retries, backoff):
        for header in container.findall('oai:header', NS):
            state['seen'] += 1
            yield {
                'identifier': header.findtext('oai:identifier', '', NS).strip(),
                'datestamp': header.findtext('oai:datestamp', '', NS).strip(),
                'deleted': header.get('status') == 'deleted',
            }
            if max_records is not None and state['seen'] >= max_records:
                return
