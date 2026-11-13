"""Client voor het Adlib-API (wwwopac.ashx), het volledige-recordkanaal van de RCE-bibliotheek.

    {SRC_API}?database=books&search=all&XMLtype=grouped&limit=500&startfrom=0

Het API pagineert met `startfrom` (zonder token), dus pagina's kunnen parallel worden opgehaald. LET OP: `startfrom`
telt vanaf 1 (`first_item` in het antwoord). Met stappen van 0, 500, 1000 overlapt elke pagina de vorige met één record;
de juiste stappen zijn 1, 501, 1001. Een pagina duurt
5 tot 17 seconden; `workers` pagina's tegelijk houdt de totale looptijd binnen redelijke grenzen.
`diagnostic/hits` geeft het totaal aantal treffers van de zoekopdracht; de aanroeper vergelijkt dat met `state['seen']`.
"""
import collections
import concurrent.futures
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterator, Optional, Tuple

import oai_client

logger = logging.getLogger(__name__)


class AdlibError(Exception):
    """Het API antwoordde met een foutmelding (bijv. een ongeldige zoekopdracht)."""


def build_url(base: str, database: str, search: str, start: int, limit: int) -> str:
    params = {'database': database, 'search': search, 'XMLtype': 'grouped', 'limit': limit, 'startfrom': start}
    return f"{base.rstrip('?')}?{urllib.parse.urlencode(params)}"


def fetch_page(base: str, database: str, search: str, start: int, limit: int,
               retries: int = 5, backoff: float = 2.0) -> ET.Element:
    """Eén pagina ophalen en parsen.

    Het ophalen zelf (retries, Retry-After, gzip/deflate, timeout) doet dezelfde functie als de OAI-client. Daarbovenop
    worden twee soorten fouten opnieuw geprobeerd: een beschadigd antwoord, en een foutmelding van de server zonder
    suggesties. Een echte syntaxisfout in de zoekopdracht komt met `suggestions` terug en is dus niet tijdelijk; die
    geeft meteen een AdlibError. Voorbeeld van een tijdelijke serverfout (gezien in een GitHub Action, lokaal niet te
    reproduceren): 'An item with the same key has already been added.'"""
    url = build_url(base, database, search, start, limit)
    attempts = max(1, retries)
    last = None
    for attempt in range(attempts):
        raw = oai_client._open(url, retries, backoff)
        text = oai_client.INVALID_XML_CHARS.sub('', raw.decode('utf-8', errors='replace'))
        try:
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                root = ET.fromstring(oai_client.AMP_FIX.sub('&amp;', text))
        except ET.ParseError as e:                # afgekapt of beschadigd antwoord: nog een keer proberen
            last = e
            logger.warning('Pagina startfrom=%d is geen geldige XML (%s); opnieuw proberen', start, e)
            time.sleep(backoff * (attempt + 1))
            continue
        error = root.find('.//diagnostic/error')
        if error is None:
            return root
        message = f"{error.findtext('message')} (search={search!r}, startfrom={start})"
        last = AdlibError(message)
        if error.find('suggestions') is not None:          # syntaxisfout in de zoekopdracht: niet tijdelijk
            raise last
        logger.warning('Serverfout van het API (poging %d/%d): %s', attempt + 1, attempts, message)
        time.sleep(backoff * (attempt + 1))
    raise last


RECORD_ERROR = re.compile(r'record number (\d+)', re.IGNORECASE)


def fetch_readable(base: str, database: str, search: str, start: int, limit: int, retries: int = 5,
                   backoff: float = 2.0, hits: Optional[int] = None) -> Tuple[ET.Element, list]:
    """Zoals `fetch_page`, maar een record dat de server zelf niet kan uitleveren stopt de pagina niet.

    Een foutmelding die een record noemt ("Invalid integer value '76, 85' for Field 't3' ..., record number 450004680")
    is geen tijdelijke storing: het record staat in de bron fout en elke pagina die het bevat, faalt. Zo'n pagina wordt
    in tweeën gedeeld, steeds verder, tot het ene kapotte record overblijft. De rest van de pagina komt gewoon binnen.
    Geeft (pagina, [priref's die niet te lezen waren]). Een andere fout (zonder record) wordt niet verholpen maar doorgegeven."""
    try:
        return fetch_page(base, database, search, start, limit, retries, backoff), []
    except AdlibError as e:
        named = RECORD_ERROR.search(str(e))
        if named is None:
            raise                                                          # geen record genoemd: niet te omzeilen
        if limit < 2:                                                      # één record per pagina: dit is het kapotte
            logger.warning('Record %s is onleesbaar in het API en wordt overgeslagen: %s', named.group(1), e)
            return _empty_page(hits), [named.group(1)]
        logger.warning('Pagina startfrom=%d bevat een record dat de server niet kan leveren; de pagina wordt gesplitst: %s',
                       start, e)
    records, unreadable, total = [], [], hits
    half = limit // 2
    for s, n in ((start, half), (start + half, limit - half)):
        if total is not None:
            n = min(n, total - s + 1)                                      # niet voorbij het einde van de resultaten vragen
        if n < 1:
            continue
        page, bad = fetch_readable(base, database, search, s, n, min(retries, 2), backoff, total)
        records.extend(page.findall('.//recordList/record'))
        unreadable.extend(bad)
        found = page.findtext('.//diagnostic/hits')
        if total is None and found and int(found) > 0:
            total = int(found)
    if total is None:                                                      # niets leesbaar: de oorspronkelijke fout blijft staan
        raise AdlibError(f"Geen enkel record van pagina startfrom={start} was te lezen (onleesbaar: {', '.join(unreadable)})")
    return _empty_page(total, records), unreadable


def _empty_page(hits: Optional[int], records: Optional[list] = None) -> ET.Element:
    root = ET.Element('adlibXML')
    record_list = ET.SubElement(root, 'recordList')
    record_list.extend(records or [])
    ET.SubElement(ET.SubElement(root, 'diagnostic'), 'hits').text = str(hits or 0)
    return root


def iter_records(base: str, database: str, search: str, state: dict, limit: int = 500, workers: int = 3,
                 retries: int = 5, backoff: float = 2.0, max_records: Optional[int] = None) -> Iterator[ET.Element]:
    """Geeft alle <record>-elementen van de zoekopdracht, in volgorde van pagina.

    Houdt `state['hits']` (aantal treffers volgens het API), `state['seen']` (aantal opgehaalde records) en
    `state['unreadable']` (priref's die het API zelf niet kon uitleveren, zie `fetch_readable`) bij.
    """
    state.setdefault('seen', 0)
    state.setdefault('duplicates', 0)
    state.setdefault('unreadable', [])
    first, bad = fetch_readable(base, database, search, 1, limit, retries, backoff)
    state['hits'] = int(first.findtext('.//diagnostic/hits') or 0)
    state['unreadable'].extend(bad)
    pending = collections.deque()
    starts = iter(range(limit + 1, state['hits'] + 1, limit))
    seen_ids = set()

    def fetch(s):
        return fetch_readable(base, database, search, s, limit, retries, backoff, state['hits'])

    def pages():
        yield first
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            try:
                for _ in range(workers * 2):                      # begrensd vooruitlezen, geen 700 futures tegelijk
                    s = next(starts, None)
                    if s is None:
                        break
                    pending.append(pool.submit(fetch, s))
                while pending:
                    page, unreadable = pending.popleft().result()
                    state['unreadable'].extend(unreadable)
                    yield page
                    s = next(starts, None)
                    if s is not None:
                        pending.append(pool.submit(fetch, s))
            finally:
                for f in pending:
                    f.cancel()

    for page in pages():
        for record in page.findall('.//recordList/record'):
            priref = record.get('priref')
            if priref in seen_ids:
                # een record dat twee keer geleverd wordt betekent dat de paginering niet klopt; het wordt niet
                # nogmaals doorgegeven en `seen` blijft dan achter bij `hits`, waardoor de run faalt
                state['duplicates'] += 1
                logger.warning('Record %s is dubbel geleverd door het API', priref)
                continue
            seen_ids.add(priref)
            state['seen'] += 1
            yield record
            if max_records is not None and state['seen'] >= max_records:
                return


# ---------------------------------------------------------------------------
# hulpjes om records te lezen
# ---------------------------------------------------------------------------

def texts(record: ET.Element, path: str) -> list:
    """Alle niet-lege teksten onder `path` (bijv. 'Author/author.name'), in volgorde, zonder dubbelen."""
    out = []
    for el in record.findall(path):
        value = ' '.join((el.text or '').split())
        if value and value not in out:
            out.append(value)
    return out


def first(record: ET.Element, path: str) -> Optional[str]:
    values = texts(record, path)
    return values[0] if values else None
