import xml.etree.ElementTree as ET

import pytest

import adlib_client


def page(start, count, hits, error=None):
    if error:
        return ET.fromstring(f'<adlibXML><diagnostic><hits>0</hits><error><message>{error}</message></error></diagnostic></adlibXML>')
    records = ''.join(f'<record priref="{i}"><priref>{i}</priref></record>' for i in range(start + 1, start + count + 1))
    return ET.fromstring(f'<adlibXML><recordList>{records}</recordList><diagnostic><hits>{hits}</hits></diagnostic></adlibXML>')


def run(monkeypatch, total, limit=10, workers=3, **kwargs):
    calls = []

    def fake(base, database, search, start, limit_, retries=5, backoff=2.0):
        calls.append(start)
        offset = start - 1                                       # startfrom telt vanaf 1, net als in het echte API
        return page(offset, max(0, min(limit_, total - offset)), total)

    monkeypatch.setattr(adlib_client, 'fetch_page', fake)
    state = {}
    out = [r.get('priref') for r in adlib_client.iter_records('http://x', 'books', 'all', state, limit=limit,
                                                                workers=workers, **kwargs)]
    return out, state, calls


def test_all_pages_in_order_even_when_fetched_in_parallel(monkeypatch):
    out, state, calls = run(monkeypatch, total=95)
    assert out == [str(i) for i in range(1, 96)]
    assert state == {'seen': 95, 'hits': 95, 'duplicates': 0}
    assert sorted(calls) == list(range(1, 96, 10))            # 1, 11, 21, ... zonder overlap


def test_last_page_with_a_single_record_is_not_lost(monkeypatch):
    out, state, calls = run(monkeypatch, total=31)
    assert len(out) == 31 and calls.count(31) == 1


def test_duplicate_records_are_skipped_and_counted(monkeypatch):
    # een API dat pagina's laat overlappen (zoals met startfrom 0, 500, 1000): het dubbele record wordt niet doorgegeven
    def overlapping(base, database, search, start, limit_, retries=5, backoff=2.0):
        offset = max(0, start - 2)                                # begint één record te vroeg
        return page(offset, min(limit_, 25 - offset), 25)

    monkeypatch.setattr(adlib_client, 'fetch_page', overlapping)
    state = {}
    out = [r.get('priref') for r in adlib_client.iter_records('http://x', 'books', 'all', state, limit=10, workers=1)]
    assert len(out) == len(set(out)) == 25 and state['duplicates'] == 1     # record 10 staat op twee pagina's


def test_exact_multiple_of_page_size(monkeypatch):
    out, state, _ = run(monkeypatch, total=30)
    assert len(out) == 30 and state['hits'] == 30


def test_single_page_and_empty_result(monkeypatch):
    assert run(monkeypatch, total=4)[0] == ['1', '2', '3', '4']
    assert run(monkeypatch, total=0)[0] == []


def test_max_records_stops_early_without_fetching_everything(monkeypatch):
    out, state, calls = run(monkeypatch, total=1000, max_records=15, workers=2)
    assert len(out) == 15 and len(calls) < 20             # niet alle 100 pagina's


def test_syntax_error_with_suggestions_raises_immediately(monkeypatch):
    import urllib.request
    calls = []
    body = (b'<adlibXML><diagnostic><hits>0</hits><error><message>Unexpected token</message>'
            b'<suggestions><suggestion> and </suggestion></suggestions></error></diagnostic></adlibXML>')
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: (calls.append(1), FakeResp(body))[1])
    with pytest.raises(adlib_client.AdlibError, match='Unexpected token'):
        adlib_client.fetch_page('http://x', 'books', 'bad query', 0, 10)
    assert len(calls) == 1                                    # niet opnieuw proberen: dit wordt nooit beter


class FakeResp:
    def __init__(self, body, encoding=''):
        self.body, self.headers = body, {'Content-Encoding': encoding}

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.body


def test_gzip_response_is_decompressed(monkeypatch):
    import gzip
    import urllib.request
    xml = b'<adlibXML><recordList><record priref="1"/></recordList><diagnostic><hits>1</hits></diagnostic></adlibXML>'
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: FakeResp(gzip.compress(xml), 'gzip'))
    root = adlib_client.fetch_page('http://x', 'books', 'all', 0, 10)
    assert root.find('.//record').get('priref') == '1'


def test_broken_xml_is_retried_then_raised(monkeypatch):
    import urllib.request
    import time
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: FakeResp(b'<adlibXML><recordList>'))
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    with pytest.raises(ET.ParseError):
        adlib_client.fetch_page('http://x', 'books', 'all', 0, 10, retries=4)


def test_text_helpers_skip_empty_and_duplicates():
    rec = ET.fromstring('<record><Keyword><keyword.contents> a  b </keyword.contents></Keyword>'
                        '<Keyword><keyword.contents/></Keyword><Keyword><keyword.contents>a b</keyword.contents></Keyword></record>')
    assert adlib_client.texts(rec, 'Keyword/keyword.contents') == ['a b']
    assert adlib_client.first(rec, 'Nope/x') is None


SAME_KEY = (b'<adlibXML><diagnostic><hits>0</hits><error><message>An item with the same key has already been added.'
            b'</message></error></diagnostic></adlibXML>')
GOOD = b'<adlibXML><recordList><record priref="1"/></recordList><diagnostic><hits>1</hits></diagnostic></adlibXML>'


def test_transient_server_error_is_retried_until_it_works(monkeypatch):
    """Het echte geval uit de GitHub Action: de server geeft eenmalig een interne fout zonder suggesties."""
    import time
    import urllib.request
    answers = iter([SAME_KEY, SAME_KEY, GOOD])
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: FakeResp(next(answers)))
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    root = adlib_client.fetch_page('http://x', 'books', 'all', 1, 10, retries=5)
    assert root.find('.//record').get('priref') == '1'


def test_persistent_server_error_is_raised_after_all_attempts(monkeypatch):
    import time
    import urllib.request
    calls = []
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: (calls.append(1), FakeResp(SAME_KEY))[1])
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    with pytest.raises(adlib_client.AdlibError, match='same key'):
        adlib_client.fetch_page('http://x', 'books', 'all', 1, 10, retries=4)
    assert len(calls) == 4
