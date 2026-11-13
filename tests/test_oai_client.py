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
