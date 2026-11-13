"""Minimale OAI-PMH-client voor ListRecords (alleen standaardbibliotheek).

Afgeleid van oai_harvester.py (cultureelerfgoed/oai_harvester-voor-Collectie-Nederland), zonder het interactieve
deel: retries met backoff, Retry-After, timeout, opschonen van ongeldige XML-tekens en bijhouden van
completeListSize zodat de aanroeper de volledigheid kan controleren.
"""
import concurrent.futures
import datetime
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
                sleep_between: float, retries: int, backoff: float, window=None) -> Iterator[ET.Element]:
    """Geeft per OAI-pagina het <verb>-element; houdt completeListSize bij in `state`.

    `window` = (van, tot) beperkt de lijst tot records met een datestamp in dat tijdvak (zie `iter_windowed`);
    `tot` mag None zijn (open einde)."""
    params = {'verb': verb, 'metadataPrefix': metadata_prefix, 'set': set_spec}
    if window:
        params['from'] = window[0]
        if window[1]:
            params['until'] = window[1]
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
                 max_records: Optional[int] = None, window=None) -> Iterator[Tuple[dict, Optional[ET.Element]]]:
    """Geeft per record (header, metadata-element); metadata is None bij een verwijderd of leeg record.

    header = {'identifier', 'datestamp', 'deleted'}. In `state` worden `seen` en `complete_list_size`
    bijgehouden. Fouten bij het ophalen laten we bewust doorlopen: een run die stilzwijgend een deel mist
    is erger dan een run die faalt (de publicatiestap wordt dan niet uitgevoerd).
    """
    state.setdefault('seen', 0)
    for container in _iter_pages(base_url, 'ListRecords', set_spec, metadata_prefix, state,
                                 sleep_between, retries, backoff, window):
        for rec in container.findall('oai:record', NS):
            metadata = rec.find('oai:metadata', NS)
            element = metadata[0] if metadata is not None and len(metadata) else None
            state['seen'] += 1
            yield _header_of(rec), element
            if max_records is not None and state['seen'] >= max_records:
                return


def iter_headers(base_url: str, set_spec: str, metadata_prefix: str, state: dict,
                 sleep_between: float = 0.2, retries: int = 5, backoff: float = 2.0,
                 max_records: Optional[int] = None, window=None) -> Iterator[dict]:
    """Zoals iter_records, maar met ListIdentifiers: alleen de headers (identifier, datestamp, deleted)."""
    state.setdefault('seen', 0)
    for container in _iter_pages(base_url, 'ListIdentifiers', set_spec, metadata_prefix, state,
                                 sleep_between, retries, backoff, window):
        for header in container.findall('oai:header', NS):
            state['seen'] += 1
            yield {
                'identifier': header.findtext('oai:identifier', '', NS).strip(),
                'datestamp': header.findtext('oai:datestamp', '', NS).strip(),
                'deleted': header.get('status') == 'deleted',
            }
            if max_records is not None and state['seen'] >= max_records:
                return


# ---------------------------------------------------------------------------
# parallel ophalen in tijdvakken
# ---------------------------------------------------------------------------
# Eén OAI-lijst is niet te parallelliseren: elke pagina (10 records) wijst met een resumptionToken naar de volgende. De OAI
# kan de lijst wel beperken tot een tijdvak (`from`/`until`, op de seconde). Verdeel de lijst in tijdvakken die elk een eigen
# lijst vormen en haal die tegelijk op. Een boekenlijst van 182.000 records duurt zo niet drie uur maar een fractie daarvan.
# Elk tijdvak moet precies zoveel records opleveren als de OAI vooraf meldde, en de tijdvakken samen precies de hele lijst.

STAMP = '%Y-%m-%dT%H:%M:%SZ'
EARLIEST = datetime.datetime(1900, 1, 1)
ONE_SECOND = datetime.timedelta(seconds=1)


def count_window(base_url: str, set_spec: str, metadata_prefix: str, window, retries: int = 5,
                 backoff: float = 2.0) -> int:
    """Aantal records in een tijdvak (of in de hele lijst bij window=None), volgens de eerste pagina van de lijst."""
    pages = _iter_pages(base_url, 'ListIdentifiers', set_spec, metadata_prefix, {}, 0, retries, backoff, window)
    for container in pages:                                  # alleen de eerste pagina: de rest hoeft niet
        token = container.find('oai:resumptionToken', NS)
        if token is not None and token.get('completeListSize'):
            return int(token.get('completeListSize'))
        return len(container.findall('oai:header', NS))      # korte lijst zonder token: alles staat op deze pagina
    return 0                                                  # noRecordsMatch


def plan_windows(base_url: str, set_spec: str, metadata_prefix: str, max_window: int = 5000, retries: int = 5,
                 backoff: float = 2.0, now: Optional[datetime.datetime] = None):
    """Verdeel de lijst in tijdvakken van hooguit `max_window` records. Geeft (totaal, [(van, tot, aantal), ...]).

    Het laatste tijdvak heeft geen einddatum (als het records bevat). Elk tijdvak wordt
    gehalveerd tot het klein genoeg is (of niet verder te splitsen is: een seconde).

    LET OP: de datestamps in de bron hebben fracties van een seconde, `from` en `until` rekenen op hele seconden. Laat je
    twee tijdvakken met een seconde aansluiten ([lo, mid] en [mid+1s, hi]), dan valt een record op mid+0,5s in geen van
    beide (gevonden: 9 van 63.259 records). Daarom overlappen de helften op één tijdstip ([lo, mid] en [mid, hi]). Een record
    precies op `mid` komt dan in beide voor; de aanroeper ontdubbelt, en hier wordt hun aantal van de som afgetrokken. De
    tellingen moeten sluiten, anders wordt er niets opgehaald."""
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)

    def fmt(d):
        return d.strftime(STAMP) if d else None

    def count(lo, hi):
        return count_window(base_url, set_spec, metadata_prefix, (fmt(lo), fmt(hi)), retries, backoff)

    total = count_window(base_url, set_spec, metadata_prefix, None, retries, backoff)
    whole = count(EARLIEST, None)
    if whole != total:
        raise OaiError(f'De lijst heeft {total} records, maar vanaf {fmt(EARLIEST)} zijn het er {whole}: '
                       f'er zijn records met een datestamp die buiten de tijdvakken valt.')
    windows, overlap = [], [0]

    def split(lo, hi, n):
        if n == 0:
            return
        top = hi or now
        if n <= max_window or top - lo < 2 * ONE_SECOND:
            windows.append((fmt(lo), fmt(hi), n))
            return
        mid = (lo + (top - lo) / 2).replace(microsecond=0)
        left, right, on_mid = count(lo, mid), count(mid, hi), count(mid, mid)
        if left + right - on_mid != n:
            raise OaiError(f'Tijdvak {fmt(lo)} .. {fmt(hi)} heeft {n} records, de twee helften samen {left + right - on_mid} '
                           f'(waarvan {on_mid} op {fmt(mid)}): de bron veranderde tijdens het plannen.')
        overlap[0] += on_mid
        split(lo, mid, left)
        split(mid, hi, right)

    split(EARLIEST, None, whole)
    planned = sum(w[2] for w in windows) - overlap[0]
    if planned != total:
        raise OaiError(f'De tijdvakken bevatten samen {planned} records (na aftrek van {overlap[0]} dubbele), de lijst {total}.')
    return total, windows


def iter_windowed(base_url: str, set_spec: str, metadata_prefix: str, state: dict, verb: str = 'ListIdentifiers',
                  workers: int = 4, max_window: int = 5000, sleep_between: float = 0.2, retries: int = 5,
                  backoff: float = 2.0) -> Iterator:
    """Zoals `iter_headers` (verb ListIdentifiers) of `iter_records` (ListRecords), maar de lijst wordt in tijdvakken
    parallel opgehaald. `state['complete_list_size']` is het totaal volgens de OAI; een tijdvak dat een ander aantal
    oplevert dan vooraf gemeld, laat de run falen."""
    state.setdefault('seen', 0)
    state.setdefault('overlap', 0)
    total, windows = plan_windows(base_url, set_spec, metadata_prefix, max_window, retries, backoff)
    state['complete_list_size'] = total
    state['windows'] = len(windows)
    logger.info('OAI: %d records in %d tijdvakken, %d tegelijk', total, len(windows), workers)
    fetch = iter_headers if verb == 'ListIdentifiers' else iter_records
    done = []

    def harvest(window):
        sub = {}
        items = list(fetch(base_url, set_spec, metadata_prefix, sub, sleep_between, retries, backoff,
                           window=(window[0], window[1])))
        if len(items) != window[2] or sub.get('complete_list_size', window[2]) != window[2]:
            raise OaiError(f'Tijdvak {window[0]} .. {window[1]}: {len(items)} records opgehaald, {window[2]} verwacht '
                           f'(de OAI meldt nu {sub.get("complete_list_size")}); de bron veranderde tijdens de run.')
        done.append(window)
        logger.info('OAI: tijdvak %d/%d klaar (%d records)', len(done), len(windows), len(items))
        return items

    seen_ids = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(harvest, w) for w in windows]
        try:
            for future in futures:
                for item in future.result():
                    identifier = (item[0] if isinstance(item, tuple) else item)['identifier']
                    if identifier in seen_ids:                  # een record precies op de grens van twee tijdvakken
                        state['overlap'] += 1
                        continue
                    seen_ids.add(identifier)
                    state['seen'] += 1
                    yield item
        finally:
            for future in futures:
                future.cancel()
