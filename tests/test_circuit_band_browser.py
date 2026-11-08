"""Actual FastAPI response-model and browser wiring with synthetic Dhan quotes."""
from urllib.parse import urlsplit
from datetime import timedelta

import pytest

from app.dhan_scanner import Candle, Instrument, StockState
from test_integration_workflows import integration
from test_staged_scan import clock


@pytest.mark.parametrize('width', [1440, 390])
def test_verified_band_filter_from_quote_to_browser_and_reload(integration, monkeypatch, width):
    pw = pytest.importorskip('playwright.sync_api')
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    now = ctx.clock[0]
    definitions = [('POSS20', 20, False), ('RED20', 20, True), ('TEN', 10, False),
                   ('FIVE', 5, True), ('UNKNOWN', None, False), ('RELIANCE', 20, False)]
    ctx.engine._states = {}
    quotes = {}
    for index, (symbol, band, red) in enumerate(definitions):
        sid = str(index+1)
        bar = Candle(now.replace(hour=9, minute=15), 100, 100 if red else 110, 95,
                     95 if red else 110, 500_000 if red else 300_000)
        ctx.engine._states[symbol] = StockState(Instrument(symbol, sid, symbol),
            possible_candidate=not red, redwala_gira=red, qualifies_scan=True,
            confirmation_status='confirmed', signal_session=now.date(), opening_candles=[bar],
            confirmed_opening_candle=bar, today_opening_volume=bar.volume)
        price = 100 if band != 20 else 110
        quotes[sid] = dict(last_price=price, net_change=price-100,
            upper_circuit_limit=100+band if band else None, lower_circuit_limit=100-band if band else None)
    calls = []
    def quote(securities):
        calls.append(securities)
        return dict(status='success', data={'NSE_EQ':quotes})
    monkeypatch.setattr(ctx.broker, 'quote_data', quote, raising=False)
    ctx.engine.refresh_circuit_limits(ctx.broker)
    api = ctx.http.get('/api/state').json()
    rows = {r['symbol']:r for r in api['stocks']}
    assert rows['POSS20']['circuit_band_percent'] == 20
    assert rows['POSS20']['circuit_reference_close'] == 100
    assert rows['RELIANCE']['circuit_band_status'] == 'dynamic'
    assert sum(r['circuit_band_eligible'] for r in rows.values()) == 2
    def route(r):
        url = urlsplit(r.request.url)
        if url.hostname != 'scanner.test':
            r.abort()
            return
        response = ctx.http.request(r.request.method, url.path, content=r.request.post_data,
                                   headers={'content-type':'application/json'})
        r.fulfill(status=response.status_code, body=response.content,
                  content_type=response.headers.get('content-type','text/html'))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width':width, 'height':1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('**/*', route)
            page.goto('http://scanner.test/')
            toggle = page.locator('#dashboardCircuitEnabled')
            pw.expect(toggle).to_be_checked()
            symbols = page.locator('#stockRows .symbol strong')
            pw.expect(symbols).to_have_text(['RED20','POSS20'])
            pw.expect(page.locator('#dashboardCircuitSummary')).to_contain_text('2 below 20%, 2 unverified')
            pw.expect(page.locator('#stockRows .circuit-distance strong').first).to_have_text('9.09%')
            pw.expect(page.locator('#stockRows .circuit-distance strong').nth(1)).to_have_text('27.27%')
            pw.expect(page.locator('#stockRows .algo-row-button')).to_have_count(2)
            assert page.locator('th', has_text='UC Away %').count() == 1
            assert page.locator('th', has_text='LC Away %').count() == 1
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            toggle.uncheck()
            pw.expect(symbols).to_have_count(6)
            page.reload()
            pw.expect(toggle).not_to_be_checked()
            pw.expect(symbols).to_have_count(6)
            toggle.check()
            page.reload()
            pw.expect(toggle).to_be_checked()
            pw.expect(symbols).to_have_count(2)
            # A fresh real API snapshot must remove a now-stale row immediately.
            ctx.engine._states['POSS20'].circuit_fetched_at -= timedelta(seconds=121)
            page.evaluate('(s)=>renderState(s)', ctx.http.get('/api/state').json())
            pw.expect(symbols).to_have_text(['RED20'])
            # Unknown historical circuit data is intentionally not a replay gate.
            replay = dict(stocks=[{**row, 'first_candle_volume':300000} for row in api['stocks']],
                target_date=now.date().isoformat(), tested_count=6, qualified_count=6,
                candidate_count=4, redwala_count=2, error_count=0)
            page.evaluate('(r)=>renderBacktest(r)', replay)
            pw.expect(page.locator('#backtestRows .symbol strong')).to_have_count(6)
            assert len(calls) == 1  # UI toggles/reloads never fetch history/quotes.
            assert not errors
        finally:
            browser.close()
