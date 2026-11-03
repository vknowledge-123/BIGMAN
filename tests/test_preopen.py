import csv
import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.preopen import PreopenRequest, PreopenSettings, filter_csv
from test_integration_workflows import integration
from test_staged_scan import clock


CSV = '''SYMBOL,INDICATIVE EQUILIBRIUM PRICE,FINAL PRICE,CHANGE,%CHANGE,VALUE (₹ Crores)
HDFCBANK,-,689.70,1.65,0.24,75.68
ICICIBANK,-,1400.90,-2.10,-0.15,41.37
STLTECH,-,900,32.45,3.74,12.34
E2E,-,580,-14.35,-2.41,10.68
M&M,-,3000,30,1,9
APOLLO,-,415.8,4.9,1.19,2.91
ITCHOTELS,-,169,4.7,2.85,2.89
ZERO,100,100,0,0,1
INVALID,-,100,0,-,2
'''


def request(**settings):
    return PreopenRequest(csv_text=CSV, filename="NSE-preopen-27-Oct-2026.csv", settings=settings)


@pytest.mark.parametrize("mode,direction,minimum,maximum,expected", [
    ("cash", "gainers", 0, None, ["STLTECH", "APOLLO", "ITCHOTELS", "ZERO"]),
    ("fno", "gainers", 0, None, ["HDFCBANK", "M&M"]),
    ("cash", "losers", -5, -1, ["E2E"]),
    ("fno", "losers", -5, 0, ["ICICIBANK"]),
    ("cash", "both", -5, 5, ["STLTECH", "E2E", "APOLLO", "ITCHOTELS", "ZERO"]),
])
def test_script_direction_and_universe_rules(mode, direction, minimum, maximum, expected):
    result = filter_csv(request(universe=mode, direction=direction, min_change=minimum, max_change=maximum))
    assert result["symbols"] == expected
    assert result["total_rows"] == 9 and result["invalid_rows"] == 1
    assert all(row["is_fno"] == (mode == "fno") for row in result["rows"])


def test_limits_inclusive_top_n_after_membership_price_fallback_and_stable_sort():
    result = filter_csv(request(universe="cash", min_turnover=2.89, max_turnover=12.34,
                                min_change=1.19, max_change=3.74, top_n=2))
    assert result["symbols"] == ["STLTECH", "APOLLO"]
    assert result["matched_count"] == 3
    assert result["rows"][0]["price"] == 900
    tied = PreopenRequest(csv_text="Symbol,Change %,Turnover CR\nZZZ,1,5\nAAA,1,5\n", settings={"top_n": 1})
    assert filter_csv(tied)["symbols"] == ["ZZZ"]


def test_bom_multiline_headers_numeric_formats_duplicates_and_missing_values():
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([" symbol \n", " %change\n", "VALUE (₹\u00a0Crores)", "IEP"])
    writer.writerows([[" NSE : STLTECH ", "+2%", "₹1,234.50 Cr", "900"],
                      ["STLTECH", "2", "99", "900"], ["BAD", "NaN", "5", "100"],
                      ["BAD2", "1", "Infinity", "100"], ["BAD3", "1", "-1", "100"]])
    result = filter_csv(PreopenRequest(csv_text="\ufeff" + stream.getvalue()))
    assert result["symbols"] == ["STLTECH"]
    assert result["rows"][0]["turnover_crore"] == 1234.5
    assert result["duplicate_rows"] == 1 and result["invalid_rows"] == 3


@pytest.mark.parametrize("text", ["", "Symbol,CHANGE,Value\nABC,1,2", "Symbol,%CHANGE\nABC,1",
                                    'Symbol,%CHANGE,VALUE\n"broken,1,2', 'Symbol,Symbol,%CHANGE,VALUE\nABC,ABC,1,2'])
def test_bad_csv_never_becomes_a_stock_list(text):
    with pytest.raises((ValueError, ValidationError)):
        filter_csv(PreopenRequest(csv_text=text))


@pytest.mark.parametrize("settings", [{"min_turnover": -1}, {"min_turnover": 4, "max_turnover": 3},
    {"min_change": 3, "max_change": 2}, {"top_n": 0}, {"top_n": 1.5}, {"min_change": float('nan')},
    {"universe": "all"}, {"direction": "losers"}, {"direction": "both"},
    {"direction": "gainers", "min_change": -1}])
def test_invalid_settings(settings):
    with pytest.raises(ValidationError):
        PreopenSettings(**settings)


def test_preview_is_read_only_apply_replaces_universe_and_survives_reload(integration):
    ctx = integration
    old = ctx.store.load()
    payload = request(universe="fno", min_turnover=1).model_dump()
    response = ctx.http.post('/api/preopen/preview', json=payload)
    assert response.status_code == 200
    assert ctx.store.load().symbols == old.symbols
    assert ctx.store.load_preopen_import() is None
    response = ctx.http.post('/api/preopen/apply', json=payload)
    assert response.status_code == 200, response.text
    assert ctx.store.load().symbols == ['HDFCBANK', 'M&M']
    assert list(ctx.engine._states) == ['HDFCBANK', 'M&M']
    assert ctx.store.load().access_token == old.access_token
    assert ctx.store.load().volume_filters == old.volume_filters
    restored = ctx.http.get('/api/preopen').json()['saved']
    assert restored == payload
    assert not ctx.broker.minute_calls and not ctx.broker.daily_calls
    before = ctx.store.load().symbols
    payload['settings']['min_turnover'] = 99999
    assert ctx.http.post('/api/preopen/apply', json=payload).status_code == 400
    assert ctx.store.load().symbols == before


def test_resolution_failure_preserves_existing_list(integration, monkeypatch):
    ctx = integration
    old = ctx.store.load().symbols
    def fail(*_): raise RuntimeError('Instrument master unavailable')
    monkeypatch.setattr(ctx.engine.resolver, 'resolve', fail)
    response = ctx.http.post('/api/preopen/apply', json=request().model_dump())
    assert response.status_code == 500
    assert ctx.store.load().symbols == old
    assert ctx.store.load_preopen_import() is None


def test_csv_import_browser_workflow(integration):
    pw = pytest.importorskip('playwright.sync_api')
    ctx = integration
    def route(r):
        from urllib.parse import urlsplit
        url = urlsplit(r.request.url)
        if url.hostname != 'scanner.test':
            return r.abort()
        response = ctx.http.request(r.request.method, url.path + ('?' + url.query if url.query else ''),
                                    content=r.request.post_data, headers={'content-type': 'application/json'})
        r.fulfill(status=response.status_code, body=response.content,
                  content_type=response.headers.get('content-type', 'text/html'))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('**/*', route)
            page.goto('http://scanner.test/')
            page.locator('#preopenFile').set_input_files({'name': 'NSE-27-Oct-2026.csv', 'mimeType': 'text/csv', 'buffer': CSV.encode()})
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 4 stocks in scanner')
            pw.expect(page.locator('#preopenRows')).to_contain_text('STLTECH')
            assert ctx.store.load().symbols == ['RED', 'GREEN']
            page.locator('#preopenFno').check()
            pw.expect(page.locator('#preopenCash')).not_to_be_checked()
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 2 stocks in scanner')
            page.locator('#preopenTopN').fill('1')
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 1 stock in scanner')
            page.locator('#preopenApply').click()
            pw.expect(page.locator('#preopenStatus')).to_contain_text('Loaded 1 F&O')
            pw.expect(page.locator('#symbolsText')).to_have_value('HDFCBANK')
            page.reload()
            pw.expect(page.locator('#preopenFno')).to_be_checked()
            pw.expect(page.locator('#preopenTopN')).to_have_value('1')
            pw.expect(page.locator('#preopenRows')).to_contain_text('HDFCBANK')
            page.locator('#preopenCash').check()
            page.locator('#preopenMinTurnover').fill('9999')
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 0 stocks in scanner')
            pw.expect(page.locator('#preopenApply')).to_be_disabled()
            assert ctx.store.load().symbols == ['HDFCBANK']
            page.locator('#preopenMinTurnover').fill('1')
            page.locator('#preopenDirection').select_option('losers')
            page.locator('#preopenMinChange').fill('-5')
            page.locator('#preopenMaxChange').fill('-1')
            pw.expect(page.locator('#preopenRows')).to_contain_text('E2E')
            page.locator('#preopenApply').click()
            pw.expect(page.locator('#symbolsText')).to_have_value('E2E')
            assert ctx.store.load().symbols == ['E2E']
            assert not errors
            artifacts = Path('docs/algo-test-artifacts')
            artifacts.mkdir(exist_ok=True)
            page.locator('#preopenPanel').screenshot(path=str(artifacts / 'preopen-import-desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.locator('#preopenPanel').screenshot(path=str(artifacts / 'preopen-import-mobile.png'))
            page.locator('#preopenFile').set_input_files({'name': 'bad.csv', 'mimeType': 'text/csv', 'buffer': b'SYMBOL,CHANGE,VALUE\nBAD,1,2'})
            pw.expect(page.locator('#preopenStatus')).to_contain_text('percentage change')
            pw.expect(page.locator('#preopenApply')).to_be_disabled()
            assert ctx.store.load().symbols == ['E2E']
        finally:
            browser.close()


RAW_NSE_CSV = """SYMBOL,%CHANGE,FINAL PRICE,FINAL VOLUME,VALUE
RAWLOW,1,100,24000,"24,00,000.00"
RAWEDGE,1,100,25000,"25,00,000.00"
RAWTHREE,1,100,300000,"3,00,00,000.00"
RAWHIGH,1,100,350000,"3,50,00,000.00"
HDFCBANK,1,100,400000,"4,00,00,000.00"
"""


@pytest.mark.parametrize("minimum,maximum,expected", [
    (.25, None, ['RAWHIGH','RAWTHREE','RAWEDGE']),
    (3, None, ['RAWHIGH','RAWTHREE']),
    (3, 3, ['RAWTHREE']),
    (3.01, None, ['RAWHIGH']),
])
def test_detailed_nse_value_in_rupees_normalized_before_filtering(minimum, maximum, expected):
    result = filter_csv(PreopenRequest(csv_text=RAW_NSE_CSV,
        settings={'min_turnover':minimum, 'max_turnover':maximum}))
    assert result['symbols'] == expected
    assert result['turnover_source_column'] == 'VALUE'
    assert result['turnover_source_unit'] == 'rupees'
    assert all(minimum <= row['turnover_crore'] <= (maximum if maximum is not None else 999) for row in result['rows'])


def test_crore_header_takes_precedence_and_is_not_converted_twice():
    text='SYMBOL,%CHANGE,FINAL PRICE,FINAL VOLUME,VALUE,VALUE (Crores)\nRAWTHREE,1,100,300000,30000000,3\n'
    result=filter_csv(PreopenRequest(csv_text=text, settings={'min_turnover':3,'max_turnover':3}))
    assert result['symbols'] == ['RAWTHREE']
    assert result['rows'][0]['turnover_crore'] == 3
    assert result['turnover_source_unit'] == 'crore'


@pytest.mark.parametrize('header', ['VALUE (INR)', 'VALUE (RS)', 'VALUE (RUPEES)'])
def test_explicit_rupee_units(header):
    text=f'SYMBOL,%CHANGE,{header}\nRAWTHREE,1,30000000\n'
    result=filter_csv(PreopenRequest(csv_text=text,settings={'min_turnover':3,'max_turnover':3}))
    assert result['symbols'] == ['RAWTHREE']
    assert result['rows'][0]['turnover_crore'] == 3


def test_raw_nse_turnover_preview_apply_and_reload_in_browser(integration):
    pw = pytest.importorskip('playwright.sync_api')
    ctx=integration
    def route(r):
        from urllib.parse import urlsplit
        url=urlsplit(r.request.url)
        if url.hostname != 'scanner.test': return r.abort()
        result=ctx.http.request(r.request.method,url.path,content=r.request.post_data,
                               headers={'content-type':'application/json'})
        r.fulfill(status=result.status_code,body=result.content,content_type=result.headers.get('content-type','text/html'))
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page()
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('**/*',route)
            page.goto('http://scanner.test/')
            page.locator('#preopenFile').set_input_files({'name':'NSE-03-Nov-2026.csv','mimeType':'text/csv','buffer':RAW_NSE_CSV.encode()})
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 4 stocks in scanner')
            page.locator('#preopenMinTurnover').fill('0.25')
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 3 stocks in scanner')
            pw.expect(page.locator('#preopenStatus')).to_contain_text('converted to crore')
            pw.expect(page.locator('#preopenStatus')).to_contain_text('minimum 0.25 crore')
            page.locator('#preopenMinTurnover').fill('3')
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 2 stocks in scanner')
            pw.expect(page.locator('#preopenStatus')).to_contain_text('minimum 3 crore')
            assert ctx.store.load().symbols == ['RED','GREEN']
            page.locator('#preopenApply').click()
            pw.expect(page.locator('#symbolsText')).to_have_value('RAWHIGH\nRAWTHREE')
            assert ctx.store.load_preopen_import()['settings']['min_turnover'] == 3
            page.reload()
            pw.expect(page.locator('#preopenMinTurnover')).to_have_value('3')
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 2 stocks in scanner')
            page.locator('#preopenMaxTurnover').fill('3')
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 1 stock in scanner')
            pw.expect(page.locator('#preopenRows')).to_contain_text('RAWTHREE')
            page.locator('#preopenFno').check()
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 0 stocks in scanner')
            page.locator('#preopenMaxTurnover').fill('')
            pw.expect(page.locator('#preopenApply')).to_have_text('Use 1 stock in scanner')
            pw.expect(page.locator('#preopenRows')).to_contain_text('HDFCBANK')
            assert not errors
            assert not ctx.broker.daily_calls and not ctx.broker.minute_calls
        finally:
            browser.close()
