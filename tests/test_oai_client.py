import xml.etree.ElementTree as ET

import pytest

import oai_client

OAI = 'http://www.openarchives.org/OAI/2.0/'


def page(records='', token=None, size=None, error=None):
    rt = ''
    if token is not None:
        attrs = f' completeListSize="{size}"' if size else ''
        rt = f'<resumptionToken{attrs}>{token}</resumptionToken>'
    body = f'<error code="{error[0]}">{error[1]}</error>' if error else f'<ListRecords>{records}{rt}</ListRecords>'
    return ET.fromstring(f'<OAI-PMH xmlns="{OAI}">{body}</OAI-PMH>')


def rec(i, status=''):
    meta = '' if status else '<metadata><oai_dc:dc xmlns:oai_dc="x"><a>1</a></oai_dc:dc></metadata>'
    return (f'<record><header{" status=%r" % status if status else ""}><identifier>db:{i}</identifier>'
            f'<datestamp>2026-01-0{i}T00:00:00Z</datestamp></header>{meta}</record>').replace("'", '"')


def run(monkeypatch, pages, **kwargs):
    urls = []
    it = iter(pages)

    def fake(url, *a, **k):
        urls.append(url)
        return next(it)

    monkeypatch.setattr(oai_client, 'fetch_and_parse', fake)
    state = {}
    out = list(oai_client.iter_records('http://example.org/oai', 'books', 'oai_dc_book', state,
                                       sleep_between=0, **kwargs))
    return out, state, urls


def test_follows_resumption_token_with_only_verb_and_token(monkeypatch):
    out, state, urls = run(monkeypatch, [page(rec(1) + rec(2), token='abc', size=3), page(rec(3), token='')])
    assert [h['identifier'] for h, _ in out] == ['db:1', 'db:2', 'db:3']
    assert state['seen'] == 3 and state['complete_list_size'] == 3
    assert 'set=books' in urls[0] and 'metadataPrefix=oai_dc_book' in urls[0]
    assert 'resumptionToken=abc' in urls[1] and 'set=' not in urls[1] and 'metadataPrefix' not in urls[1]


def test_deleted_and_empty_records_are_reported(monkeypatch):
    out, _, _ = run(monkeypatch, [page(rec(1, status='deleted'))])
    (header, element), = out
    assert header['deleted'] is True and element is None


def test_no_records_match_is_empty_not_an_error(monkeypatch):
    out, state, _ = run(monkeypatch, [page(error=('noRecordsMatch', 'niets'))])
    assert out == [] and state['seen'] == 0


def test_other_oai_errors_raise(monkeypatch):
    with pytest.raises(oai_client.OaiError, match='cannotDisseminateFormat'):
        run(monkeypatch, [page(error=('cannotDisseminateFormat', "Meta data prefix 'x' not found"))])


def test_max_records_stops_early(monkeypatch):
    out, state, urls = run(monkeypatch, [page(rec(1) + rec(2) + rec(3), token='abc', size=9)], max_records=2)
    assert len(out) == 2 and len(urls) == 1


def test_fetch_repairs_loose_ampersand_and_control_chars(monkeypatch):
    raw = ('<OAI-PMH xmlns="%s"><ListRecords><record><header><identifier>d:1</identifier><datestamp>2026-01-01T00:00:00Z'
           '</datestamp></header><metadata><x>A&B \x01 ok</x></metadata></record></ListRecords></OAI-PMH>' % OAI)
    monkeypatch.setattr(oai_client, '_open', lambda *a, **k: raw.encode('utf-8'))
    root = oai_client.fetch_and_parse('http://example.org')
    assert root.find('.//{*}x').text == 'A&B  ok'


def test_iter_headers_uses_list_identifiers(monkeypatch):
    def hdr(i, status=''):
        return f'<header{" status=%s" % chr(34) + status + chr(34) if status else ""}><identifier>db:{i}</identifier><datestamp>2026-01-01T00:00:00Z</datestamp></header>'

    def page(headers, token, size=None):
        attrs = f' completeListSize="{size}"' if size else ''
        return ET.fromstring(f'<OAI-PMH xmlns="{OAI}"><ListIdentifiers>{headers}'
                             f'<resumptionToken{attrs}>{token}</resumptionToken></ListIdentifiers></OAI-PMH>')

    pages = iter([page(hdr(1) + hdr(2, 'deleted'), 'abc', 3), page(hdr(3), '')])
    urls = []
    monkeypatch.setattr(oai_client, 'fetch_and_parse', lambda url, *a, **k: (urls.append(url), next(pages))[1])
    state = {}
    out = list(oai_client.iter_headers('http://example.org/oai', 'books', 'oai_dc_book', state, sleep_between=0))
    assert [(h['identifier'], h['deleted']) for h in out] == [('db:1', False), ('db:2', True), ('db:3', False)]
    assert state['seen'] == 3 and state['complete_list_size'] == 3
    assert 'verb=ListIdentifiers' in urls[0] and 'resumptionToken=abc' in urls[1]


# --- tijdvakken (parallel ophalen) -------------------------------------------------------------------------------

import datetime  # noqa: E402

from conftest import FakeOai  # noqa: E402

START = datetime.datetime(2026, 3, 1, 12, 0, 0)
NOW = datetime.datetime(2026, 3, 1, 13, 0, 0)


def dense(n=300):
    """Records om de halve seconde: de helft heeft een fractie, en elke hele seconde bevat een record. Zo valt er altijd
    een record precies op en vlak na de grens waar een tijdvak gehalveerd wordt."""
    return {i: START + datetime.timedelta(seconds=0.5 * i) for i in range(1, n + 1)}


def served(monkeypatch, fake):
    monkeypatch.setattr(oai_client, 'fetch_and_parse', fake.fetch)
    monkeypatch.setattr(oai_client.time, 'sleep', lambda s: None)
    return fake


def window_ids(fake, window):
    query = {'from': window[0]}
    if window[1]:
        query['until'] = window[1]
    return set(fake._list(query))


def test_naive_adjacent_windows_lose_records_with_fractional_seconds(monkeypatch):
    """Waarom de tijdvakken overlappen: [lo, mid] en [mid+1s, hi] laten records tussen mid en mid+1s vallen."""
    fake = FakeOai(dense())
    mid = START + datetime.timedelta(seconds=60)
    f = lambda d: d.strftime(oai_client.STAMP)  # noqa: E731
    left = set(fake._list({'from': f(START), 'until': f(mid)}))
    right = set(fake._list({'from': f(mid + datetime.timedelta(seconds=1))}))
    assert len(left | right) < 300                                      # het record op mid+0,5s zit in geen van beide


def test_windows_cover_every_record(monkeypatch):
    fake = served(monkeypatch, FakeOai(dense()))
    total, windows = oai_client.plan_windows('http://x', 'books', 'oai_dc_book', max_window=40, now=NOW)
    assert total == 300 and len(windows) > 5
    assert set().union(*(window_ids(fake, w) for w in windows)) == set(range(1, 301))    # niets valt ertussen
    assert all(n <= 40 for _, _, n in windows)
    assert all(n > 0 for _, _, n in windows)                             # lege tijdvakken worden niet opgehaald


def test_windowed_iteration_yields_each_record_once(monkeypatch):
    fake = served(monkeypatch, FakeOai(dense()))
    state = {}
    out = list(oai_client.iter_windowed('http://x', 'books', 'oai_dc_book', state, workers=3, max_window=40,
                                        sleep_between=0))
    ids = [h['identifier'] for h in out]
    assert sorted(ids) == sorted(f'1964:{i}' for i in range(1, 301)) and len(set(ids)) == 300
    assert state['seen'] == 300 == state['complete_list_size'] and state['windows'] > 5
    assert state['overlap'] >= 1                                         # records precies op een grens kwamen twee keer binnen
    assert any('from' in r for r in fake.requests)


def test_windowed_list_records_returns_header_and_metadata(monkeypatch):
    served(monkeypatch, FakeOai(dense(60), db='1970'))
    out = list(oai_client.iter_windowed('http://x', 'article', 'oai_dc', {}, verb='ListRecords', workers=2,
                                        max_window=15, sleep_between=0))
    assert len(out) == 60
    header, element = out[0]
    assert header['identifier'].startswith('1970:') and element is not None


def test_window_that_changes_after_planning_fails_the_run(monkeypatch):
    served(monkeypatch, FakeOai(dense(100)))
    real = oai_client.plan_windows

    def stale(*a, **k):                                                  # de bron veranderde na het plannen
        total, windows = real(*a, **k)
        return total, [(a_, b_, n + 1) for a_, b_, n in windows]

    monkeypatch.setattr(oai_client, 'plan_windows', stale)
    with pytest.raises(oai_client.OaiError, match='verwacht'):
        list(oai_client.iter_windowed('http://x', 'books', 'oai_dc_book', {}, workers=2, max_window=20, sleep_between=0))


def test_record_outside_the_windows_stops_the_planning(monkeypatch):
    stamps = dense(20)
    stamps[99] = datetime.datetime(1850, 1, 1)                           # ouder dan het vroegste tijdvak
    served(monkeypatch, FakeOai(stamps))
    with pytest.raises(oai_client.OaiError, match='buiten de tijdvakken'):
        oai_client.plan_windows('http://x', 'books', 'oai_dc_book', max_window=5, now=NOW)


def test_count_of_a_short_list_without_complete_list_size(monkeypatch):
    body = (f'<OAI-PMH xmlns="{OAI}"><ListIdentifiers><header><identifier>db:1</identifier></header>'
            f'<header><identifier>db:2</identifier></header></ListIdentifiers></OAI-PMH>')
    monkeypatch.setattr(oai_client, 'fetch_and_parse', lambda *a, **k: ET.fromstring(body))
    assert oai_client.count_window('http://x', 'books', 'oai_dc_book', ('2026-01-01T00:00:00Z', None)) == 2
