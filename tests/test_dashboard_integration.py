"""Browser controls -> real HTTP handlers -> cache/filter/scanner/backtest code."""
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from test_integration_workflows import integration
from test_staged_scan import clock


def test_scanner_controls_cache_filters_and_backtest_in_browser(integration):
    pw = pytest.importorskip('playwright.sync_api')
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    requests = []
    def route(r):
        url = urlsplit(r.request.url)
        if url.hostname != 'scanner.test':
            r.abort()
            return
        path = url.path + ('?' + url.query if url.query else '')
        result = ctx.http.request(r.request.method, path, content=r.request.post_data,
                                  headers={'content-type': 'application/json'})
        requests.append((path, result.status_code))
        r.fulfill(status=result.status_code, body=result.content,
                  content_type=result.headers.get('content-type', 'text/html'))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('**/*', route)
            page.goto('http://scanner.test/')
            pw.expect(page.locator('#symbolsText')).to_have_value('RED\nGREEN')
            pw.expect(page.locator('#clientId')).to_have_value('test')
            pw.expect(page.locator('#credentialsStatus')).to_contain_text('Credentials saved')
            pw.expect(page.locator('#accessToken')).to_have_value('')
            assert page.locator('#accessToken').get_attribute('required') is None
            page.locator('#credentialsForm button').click()
            pw.expect(page.locator('#message')).to_contain_text('Credentials saved')
            assert ctx.store.load().access_token == 'fake'
            # Actions refresh server metadata but must not replace a filter draft.
            page.locator('#pdhlFilter').check()
            page.locator('#pdhlMax').fill('2.75')
            page.locator('#stopButton').click()
            pw.expect(page.locator('#stopButton')).to_be_enabled()
            pw.expect(page.locator('#pdhlFilter')).to_be_checked()
            pw.expect(page.locator('#pdhlMax')).to_have_value('2.75')
            pw.expect(page.locator('#filterChangesStatus')).to_contain_text('Unapplied changes')
            page.locator('#pdhlFilter').uncheck()
            page.locator('#pdhlMax').fill('4')
            page.locator('#volumeCacheButton').click()
            pw.expect(page.locator('#message')).to_contain_text('Cached opening volume')
            page.locator('#repairButton').click()
            pw.expect(page.locator('#message')).to_contain_text('Repaired')
            pw.expect(page.locator('#stockRows')).to_contain_text('redwala gira')
            calls_before = len(ctx.broker.minute_calls) + len(ctx.broker.daily_calls)
            page.locator('#dailyVolumeMax').fill('2.5')
            page.locator('#minuteVolumeMin').fill('6.5')
            page.locator('#firstCandleTurnoverMin').fill('1.5')
            for control in ('#todayOpenCross', '#monthlyFilter', '#lastTwoDaysFilter'):
                page.locator(control).check()
            page.locator('#saveVolumeFilters').click()
            pw.expect(page.locator('#activeVolumeFilters')).to_contain_text('2.5')
            pw.expect(page.locator('#saveVolumeFilters')).to_be_enabled()
            settings = ctx.store.load().volume_filters
            assert (settings.daily_volume_max, settings.minute_volume_min, settings.first_candle_turnover_min) == (2.5, 6.5, 15000000)
            assert settings.today_open_cross and settings.monthly_filter and settings.last_two_days_filter
            assert len(ctx.broker.minute_calls) + len(ctx.broker.daily_calls) == calls_before
            pw.expect(page.locator('#stockRows')).to_contain_text('redwala gira')
            page.locator('#setupFilter').select_option('possible')
            pw.expect(page.locator('#stockRows .redwala-badge')).to_have_count(0)
            page.locator('#setupFilter').select_option('redwala')
            pw.expect(page.locator('#stockRows')).to_contain_text('redwala gira')
            page.locator('#backtestTab').click()
            page.locator('#backtestDate').fill(ctx.clock[0].date().isoformat())
            page.locator('#backtestButton').click()
            pw.expect(page.locator('#backtestRows')).to_contain_text('redwala gira')
            pw.expect(page.locator('#backtestButton')).to_be_enabled()
            page.locator('#pdhlFilter').check()
            page.locator('#pdhlMax').fill('0')
            page.locator('#saveVolumeFilters').click()
            pw.expect(page.locator('#activeVolumeFilters')).to_contain_text('PDHL ON')
            pw.expect(page.locator('#activeVolumeFilters')).to_contain_text('Possible Candidates only')
            page.locator('#backtestButton').click()
            pw.expect(page.locator('#backtestButton')).to_be_enabled()
            pw.expect(page.locator('#backtestRows')).to_contain_text('redwala gira')
            page.locator('#redwalaOpenPreviousClose').check()
            page.locator('#redwalaOpenGapMax').fill('0.25')
            page.locator('#saveVolumeFilters').click()
            pw.expect(page.locator('#activeVolumeFilters')).to_contain_text('open or close absolute distance \u2264 0.25%')
            page.locator('#backtestButton').click()
            pw.expect(page.locator('#backtestButton')).to_be_enabled()
            pw.expect(page.locator('#backtestRows .redwala-badge')).to_have_count(0)
            page.reload()
            pw.expect(page.locator('#clientId')).to_have_value('test')
            pw.expect(page.locator('#credentialsStatus')).to_contain_text('Credentials saved')
            pw.expect(page.locator('#accessToken')).to_have_value('')
            pw.expect(page.locator('#redwalaOpenPreviousClose')).to_be_checked()
            pw.expect(page.locator('#redwalaOpenGapMax')).to_have_value('0.25')
            pw.expect(page.locator('#pdhlFilter')).to_be_checked()
            pw.expect(page.locator('#pdhlMax')).to_have_value('0')
            assert not errors
            assert all(status < 400 for _, status in requests)
            artifacts = Path('docs/algo-test-artifacts')
            artifacts.mkdir(exist_ok=True)
            page.screenshot(path=str(artifacts/'scanner-integration-desktop.png'), full_page=True)
            page.set_viewport_size({'width':390, 'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(artifacts/'scanner-integration-mobile.png'), full_page=True)
        finally:
            browser.close()


def test_dashboard_volume_display_filter_in_browser(integration):
    pw = pytest.importorskip('playwright.sync_api')
    ctx = integration
    ctx.clock[0] = ctx.clock[0].replace(hour=10)
    assert ctx.http.post('/api/cache-volume').status_code == 200
    assert ctx.http.post('/api/repair').status_code == 200
    stocks = ctx.http.get('/api/state').json()['stocks']
    threshold = max(row['today_opening_volume'] for row in stocks)
    qualified = sum(row['qualifies_scan'] for row in stocks)
    assert qualified > 0
    writes = []
    def route(r):
        url = urlsplit(r.request.url)
        if url.hostname != 'scanner.test':
            r.abort()
            return
        if r.request.method != 'GET':
            writes.append(url.path)
        result = ctx.http.request(r.request.method, url.path, content=r.request.post_data,
                                  headers={'content-type': 'application/json'})
        r.fulfill(status=result.status_code, body=result.content,
                  content_type=result.headers.get('content-type', 'text/html'))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', route)
            page.goto('http://scanner.test/')
            pw.expect(page.locator('#stockRows')).to_contain_text('redwala gira')
            pw.expect(page.locator('#dashboardVolumeMin')).to_have_value('100000')
            page.locator('#dashboardVolumeMin').fill(str(int(threshold)))
            page.locator('#dashboardVolumeEnabled').check()
            pw.expect(page.locator('#stockRows')).to_contain_text('No setups have first-candle volume strictly above')
            page.reload()
            pw.expect(page.locator('#dashboardVolumeEnabled')).to_be_checked()
            pw.expect(page.locator('#dashboardVolumeMin')).to_have_value(str(int(threshold)))
            pw.expect(page.locator('#stockRows')).to_contain_text('No setups have first-candle volume strictly above')
            page.locator('#dashboardVolumeMin').fill(str(int(threshold) - 1))
            pw.expect(page.locator('#stockRows')).to_contain_text('redwala gira')
            page.locator('#dashboardVolumeEnabled').uncheck()
            pw.expect(page.locator('#dashboardVolumeSummary')).to_contain_text('filter OFF')
            replay = ctx.http.post('/api/backtest', json={'target_date':ctx.clock[0].date().isoformat()}).json()
            page.evaluate('(result) => renderBacktest(result)', replay)
            page.locator('#backtestTab').click()
            pw.expect(page.locator('#dashboardVolumeEnabled')).to_be_visible()
            page.locator('#dashboardVolumeMin').fill(str(int(threshold)))
            page.locator('#dashboardVolumeEnabled').check()
            pw.expect(page.locator('#backtestRows')).to_contain_text('No setups match the display filters')
            page.locator('#dashboardVolumeEnabled').uncheck()
            pw.expect(page.locator('#backtestRows')).to_contain_text('redwala gira')
            close = max(row['first_candle_close'] for row in replay['stocks'])
            page.locator('#dashboardPriceMax').fill(str(close))
            page.locator('#dashboardPriceEnabled').check()
            pw.expect(page.locator('#backtestRows')).to_contain_text('redwala gira')
            page.locator('#dashboardPriceMax').fill(str(close-0.01))
            pw.expect(page.locator('#backtestRows')).to_contain_text('No setups match the display filters')
            page.reload()
            pw.expect(page.locator('#dashboardPriceEnabled')).to_be_checked()
            pw.expect(page.locator('#dashboardPriceMax')).to_have_value(str(close-0.01))
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert sum(row['qualifies_scan'] for row in ctx.http.get('/api/state').json()['stocks']) == qualified
            assert not writes and not errors
        finally:
            browser.close()
