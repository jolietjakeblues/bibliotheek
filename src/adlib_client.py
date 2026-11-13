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
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterator, Optional

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


def iter_records(base: str, database: str, search: str, state: dict, limit: int = 500, workers: int = 3,
                 retries: int = 5, backoff: float = 2.0, max_records: Optional[int] = None) -> Iterator[ET.Element]:
    """Geeft alle <record>-elementen van de zoekopdracht, in volgorde van pagina.

    Houdt `state['hits']` (aantal treffers volgens het API) en `state['seen']` (aantal opgehaalde records) bij.
    """
    state.setdefault('seen', 0)
    state.setdefault('duplicates', 0)
    first = fetch_page(base, database, search, 1, limit, retries, backoff)
    state['hits'] = int(first.findtext('.//diagnostic/hits') or 0)
    pending = collections.deque()
    starts = iter(range(limit + 1, state['hits'] + 1, limit))
    seen_ids = set()

    def pages():
        yield first
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            try:
                for _ in range(workers * 2):                      # begrensd vooruitlezen, geen 700 futures tegelijk
                    s = next(starts, None)
                    if s is None:
                        break
                    pending.append(pool.submit(fetch_page, base, database, search, s, limit, retries, backoff))
                while pending:
                    yield pending.popleft().result()
                    s = next(starts, None)
                    if s is not None:
                        pending.append(pool.submit(fetch_page, base, database, search, s, limit, retries, backoff))
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
