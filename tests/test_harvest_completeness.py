"""Volledigheid van de oogst: scope uit de OAI, records uit het API, laatste chunk, en alles wat de run moet laten falen."""
import json
import xml.etree.ElementTree as ET

import pytest
import yaml

import adlib_client
import harvest_service
import oai_client
import transform_service
from conftest import ROOT

OAI = 'http://www.openarchives.org/OAI/2.0/'


# --- nepbronnen -----------------------------------------------------------

def _header(db, i, deleted=False):
    status = ' status="deleted"' if deleted else ''
    return f'<header{status}><identifier>{db}:{i}</identifier><datestamp>2026-01-01T00:00:00Z</datestamp></header>'


def _oai_pages(verb, db, ids, announced, page_size=5, deleted=(), article_fields=False):
    pages = []
    ids = list(ids)
    for n, first in enumerate(range(0, len(ids), page_size)):
        chunk = ids[first:first + page_size]
        last = first + page_size >= len(ids)
        rt = f'<resumptionToken completeListSize="{announced}">{"" if last else f"t{n + 1}"}</resumptionToken>'
        if verb == 'ListIdentifiers':
            body = ''.join(_header(db, i, i in deleted) for i in chunk)
        else:
            body = ''.join(
                '<record>' + _header(db, i, i in deleted) + (
                    '' if i in deleted else
                    '<metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    f'<dc:source>journal = {{Tijdschrift ; </dc:source><dc:source>(1990)</dc:source>'
                    f'<dc:source>, {i}-{i + 1}}},</dc:source></oai_dc:dc></metadata>') + '</record>'
                for i in chunk)
        pages.append(f'<OAI-PMH xmlns="{OAI}"><{verb}>{body}{rt}</{verb}></OAI-PMH>')
    return pages


def _api_record(i):
    return ET.fromstring(f'<record priref="{i}" modification="2026-01-01T00:00:00"><priref>{i}</priref>'
                         f'<Title><lead_word/><title>Titel {i}</title></Title></record>')


def _setup(monkeypatch, tmp_path, source, ids, oai_announced=None, api_ids=None, api_hits=None, deleted=(),
           **config_overrides):
    """Zet nepbronnen en een tijdelijke config neer. `ids` = wat de OAI-set bevat, `api_ids` = wat het API kent."""
    with open(ROOT / 'config' / 'config.yml', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    cfg.update({'SRC_API_LIMIT': 10, 'SRC_API_WORKERS': 2, 'SRC_SLEEP': 0, 'SRC_OAI_WORKERS': 1, **config_overrides})
    cfg['SOURCES'][source].setdefault('scope', 'oai')
    cfg_path = tmp_path / 'config.yml'
    cfg_path.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    monkeypatch.setenv('CONFIG_PATH', str(cfg_path))
    monkeypatch.setenv('CACHE_PATH', str(tmp_path / 'out'))

    ids = list(ids)
    api_ids = list(api_ids if api_ids is not None else ids)
    announced = len(ids) if oai_announced is None else oai_announced
    db = '1964' if source == 'books' else '1970'
    pages = {'ListIdentifiers': iter(_oai_pages('ListIdentifiers', db, ids, announced, deleted=deleted)),
             'ListRecords': iter(_oai_pages('ListRecords', db, ids, announced, deleted=deleted))}

    def fake_oai(url, *a, **k):
        verb = 'ListIdentifiers' if 'ListIdentifiers' in url else 'ListRecords'
        return ET.fromstring(next(pages[verb]))

    def fake_api(base, database, search, start, limit, retries=5, backoff=2.0):
        hits = len(api_ids) if api_hits is None else api_hits
        records = ''.join(f'<record priref="{i}" modification="2026-01-01T00:00:00"><priref>{i}</priref>'
                          f'<Title><title>Titel {i}</title></Title></record>' for i in api_ids[start - 1:start - 1 + limit])
        return ET.fromstring(f'<adlibXML><recordList>{records}</recordList><diagnostic><hits>{hits}</hits></diagnostic></adlibXML>')

    monkeypatch.setattr(oai_client, 'fetch_and_parse', fake_oai)
    monkeypatch.setattr(adlib_client, 'fetch_page', fake_api)
    monkeypatch.setattr(oai_client.time, 'sleep', lambda s: None)


def manifest(tmp_path, source):
    return json.loads((tmp_path / 'out' / f'manifest-{source}.json').read_text())


def run(source, *extra):
    return harvest_service.main(['--source', source, '--chunks', '10', *extra])


# --- boeken ---------------------------------------------------------------

def test_books_in_scope_only_and_last_chunk_is_written(monkeypatch, tmp_path):
    # OAI publiceert 25 van de 30 API-records: 10 + 10 + 5. Een loop die na de laatste volle chunk stopt, verliest er 5.
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_ids=range(1, 31))
    assert run('books') == 0
    assert sorted(p.name for p in (tmp_path / 'out').glob('*.jsonld')) == ['books-0000.jsonld', 'books-0001.jsonld',
                                                                           'books-0002.jsonld']
    m = manifest(tmp_path, 'books')
    assert m['complete'] is True and m['written'] == 25 and m['out_of_scope'] == 5 and m['api_seen'] == 30


def test_exact_multiple_of_chunk_size(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 21))
    assert run('books') == 0
    assert len(list((tmp_path / 'out').glob('*.jsonld'))) == 2 and manifest(tmp_path, 'books')['written'] == 20


def test_oai_incomplete_fails_the_run(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), oai_announced=30)
    assert run('books') == 1 and manifest(tmp_path, 'books')['complete'] is False


def test_api_incomplete_fails_the_run(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_hits=30)       # API kondigt 30 aan, levert 25
    assert run('books') == 1


def test_record_in_oai_but_not_in_api_fails_and_is_named(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_ids=[i for i in range(1, 26) if i != 7])
    assert run('books') == 1
    m = manifest(tmp_path, 'books')
    assert m['missing_in_api'] == 1 and m['missing_ids'] == ['7'] and m['written'] == 24


def test_missing_in_api_can_be_allowed(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_ids=[i for i in range(1, 26) if i != 7],
           MAX_MISSING_IN_API=1)
    assert run('books') == 0 and manifest(tmp_path, 'books')['written'] == 24


def _unreadable(monkeypatch, bad):
    """Laat het API-record(s) `bad` niet leveren, zoals de echte server bij priref 450004680 (daarna splitst de client de pagina)."""
    fake = adlib_client.fetch_page

    def picky(base, database, search, start, limit, retries=5, backoff=2.0):
        page = fake(base, database, search, start, limit, retries, backoff)
        hit = [r.get('priref') for r in page.findall('.//record') if int(r.get('priref')) in bad]
        if hit:
            raise adlib_client.AdlibError(f"Invalid integer value '76, 85' for Field 't3', record number {hit[0]}")
        return page

    monkeypatch.setattr(adlib_client, 'fetch_page', picky)


def test_unreadable_book_is_named_skipped_and_fails_the_run_by_default(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), MAX_UNREADABLE_IN_API=0)
    _unreadable(monkeypatch, {7})
    assert run('books') == 1
    m = manifest(tmp_path, 'books')
    assert m['unreadable_ids'] == ['7'] and m['unreadable_in_scope'] == 1 and m['api_unreadable'] == 1
    assert m['missing_in_api'] == 0 and m['written'] == 24 and m['api_seen'] == 24 and m['api_hits'] == 25


def test_unreadable_book_within_the_allowance_passes_and_is_not_published(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), MAX_UNREADABLE_IN_API=1)
    _unreadable(monkeypatch, {7})
    assert run('books') == 0
    m = manifest(tmp_path, 'books')
    assert m['complete'] is True and m['written'] == 24 and m['unreadable_ids'] == ['7']
    data = ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'out').glob('books-*.jsonld'))
    assert 'Titel 7"' not in data and 'Titel 8' in data


def test_unreadable_book_with_scope_api_balances(monkeypatch, tmp_path):
    # gevonden in een droge run op het echte API: bij scope 'api' telde het onleesbare record niet mee in 'beoogd'
    _setup(monkeypatch, tmp_path, 'books', ids=[], api_ids=range(1, 16), scope='api', MAX_UNREADABLE_IN_API=1)
    cfg = yaml.safe_load((tmp_path / 'config.yml').read_text())
    cfg['SOURCES']['books']['scope'] = 'api'
    (tmp_path / 'config.yml').write_text(yaml.safe_dump(cfg))
    _unreadable(monkeypatch, {7})
    assert run('books') == 0
    m = manifest(tmp_path, 'books')
    assert m['written'] == 14 and m['intended'] == 15 and m['unreadable_ids'] == ['7']


def test_unreadable_record_outside_the_selection_is_harmless(monkeypatch, tmp_path):
    # het API heeft 30 records, de OAI publiceert er 25; record 28 is kapot maar wordt toch niet gepubliceerd
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), api_ids=range(1, 31), MAX_UNREADABLE_IN_API=0)
    _unreadable(monkeypatch, {28})
    assert run('books') == 0
    m = manifest(tmp_path, 'books')
    assert m['api_unreadable'] == 1 and m['unreadable_in_scope'] == 0 and m['written'] == 25


def test_unreadable_without_record_in_the_error_is_not_swallowed(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26))

    def broken(base, database, search, start, limit, retries=5, backoff=2.0):
        raise adlib_client.AdlibError('Er ging iets mis')

    monkeypatch.setattr(adlib_client, 'fetch_page', broken)
    with pytest.raises(adlib_client.AdlibError):
        run('books')


def test_deleted_in_oai_are_not_published(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 11), api_ids=range(1, 11), deleted={3, 4})
    assert run('books') == 0
    m = manifest(tmp_path, 'books')
    assert m['written'] == 8 and m['skipped_reasons'] == {'deleted': 2}


def test_transformation_errors_fail_the_run(monkeypatch, tmp_path):
    real = transform_service.transform_book

    def flaky(graph, config, record, source):
        if record.get('priref') == '2':
            raise ValueError('kapot record')
        return real(graph, config, record, source)

    monkeypatch.setattr(transform_service, 'transform_book', flaky)
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 6))
    assert run('books') == 1
    m = manifest(tmp_path, 'books')
    assert m['errors'] == 1 and m['error_ids'] == ['2'] and m['written'] == 4 and m['complete'] is False


def test_failed_record_leaves_no_partial_triples(monkeypatch, tmp_path):
    real = transform_service.transform_book

    def half_done(graph, config, record, source):
        real(graph, config, record, source)
        if record.get('priref') == '2':
            raise ValueError('na de helft stuk')

    monkeypatch.setattr(transform_service, 'transform_book', half_done)
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 4), MAX_RECORD_ERRORS=1)
    assert run('books') == 0
    data = (tmp_path / 'out' / 'books-0000.jsonld').read_text(encoding='utf-8')
    assert 'Titel 2' not in data and 'Titel 1' in data and 'Titel 3' in data


def test_scope_api_publishes_everything_the_search_returns(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=[], api_ids=range(1, 16), scope='api')
    cfg = yaml.safe_load((tmp_path / 'config.yml').read_text())
    cfg['SOURCES']['books']['scope'] = 'api'
    (tmp_path / 'config.yml').write_text(yaml.safe_dump(cfg))
    assert run('books') == 0 and manifest(tmp_path, 'books')['written'] == 15


def test_limited_run_skips_completeness_check(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), oai_announced=999, api_hits=999)
    assert run('books', '--max-records', '7') == 0


# --- artikelen ------------------------------------------------------------

def test_articles_are_merged_with_api_title(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'article', ids=range(200000001, 200000013))
    assert run('article') == 0
    m = manifest(tmp_path, 'article')
    assert m['written'] == 12 and m['missing_in_api'] == 0
    data = ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'out').glob('article-*.jsonld'))
    assert 'Titel 200000001' in data and 'Tijdschrift' in data           # titel uit het API, tijdschrift uit de OAI


def test_article_missing_in_api_is_written_from_oai_but_fails_the_run(monkeypatch, tmp_path):
    ids = list(range(200000001, 200000011))
    _setup(monkeypatch, tmp_path, 'article', ids=ids, api_ids=[i for i in ids if i != 200000004])
    assert run('article') == 1
    m = manifest(tmp_path, 'article')
    assert m['missing_in_api'] == 1 and m['missing_ids'] == ['200000004'] and m['written'] == 10


def test_article_missing_in_api_can_be_allowed(monkeypatch, tmp_path):
    ids = list(range(200000001, 200000011))
    _setup(monkeypatch, tmp_path, 'article', ids=ids, api_ids=[i for i in ids if i != 200000004], MAX_MISSING_IN_API=1)
    assert run('article') == 0
    data = ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'out').glob('article-*.jsonld'))
    assert 'Titel 200000004' not in data and 'Titel 200000003' in data


def test_unreadable_article_is_still_written_from_the_oai(monkeypatch, tmp_path):
    ids = list(range(200000001, 200000011))
    _setup(monkeypatch, tmp_path, 'article', ids=ids, MAX_UNREADABLE_IN_API=1)
    _unreadable(monkeypatch, {200000004})
    assert run('article') == 0
    m = manifest(tmp_path, 'article')
    assert m['unreadable_ids'] == ['200000004'] and m['missing_in_api'] == 0 and m['written'] == 10
    data = ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'out').glob('article-*.jsonld'))
    assert 'Titel 200000004' not in data and 'Tijdschrift' in data       # geen titel, wel het tijdschriftgegeven uit de OAI


def test_unknown_source_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv('CACHE_PATH', str(tmp_path))
    assert harvest_service.main(['--source', 'bestaat-niet']) == 2


def test_books_harvested_in_parallel_windows_are_complete(monkeypatch, tmp_path):
    from conftest import FakeOai
    import datetime
    ids = list(range(1, 26))
    _setup(monkeypatch, tmp_path, 'books', ids=ids, SRC_OAI_WORKERS=3, SRC_OAI_WINDOW=6)
    fake = FakeOai({i: datetime.datetime(2026, 3, 1, 12, 0, 0) + datetime.timedelta(seconds=0.5 * i) for i in ids})
    monkeypatch.setattr(oai_client, 'fetch_and_parse', fake.fetch)
    assert run('books') == 0
    m = manifest(tmp_path, 'books')
    assert m['complete'] is True and m['written'] == 25 and m['oai_seen'] == m['oai_expected'] == 25
    assert m['oai_windows'] > 1


def test_limited_run_does_not_use_windows(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, 'books', ids=range(1, 26), SRC_OAI_WORKERS=3)
    assert run('books', '--max-records', '7') == 0
    assert manifest(tmp_path, 'books')['oai_windows'] is None
