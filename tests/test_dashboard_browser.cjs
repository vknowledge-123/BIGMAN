const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const output = process.env.SCREENSHOT_DIR || path.join(require('node:os').tmpdir(), 'gapfilter-browser-artifacts');
require('node:fs').mkdirSync(output, { recursive: true });

const daily = {
  previous_date: '2026-09-30', previous_volume: 3000, average: 1000,
  multiplier: 3, percent_change: 2, price_exception: false,
  samples: [{ date: '2026-09-29', volume: 1000 }],
};
const candles = Array.from({ length: 10 }, (_, i) => ({
  start: `2026-10-01T09:${15 + i}:00+05:30`, end: `2026-10-01T09:${16 + i}:00+05:30`,
  color: i % 2 ? 'red' : 'green', volume: 1200 + i * 10, close: 103, turnover: 123600 + i * 1030,
}));
const base = {
  daily_filter: daily, volume_multiplier: 4, opening_volume_average: 100,
  qualifies_scan: true, opening_candles: candles, candidate_reason: 'Daily check passed',
  first_candle_color: 'green', second_candle_color: 'green', first_candle_start: candles[0].start,
  second_candle_start: candles[1].start, ltp: 103, percent_change: 3,
  today_opening_volume: 400, first_candle_volume: 400, first_candle_turnover: 41200,
  candle_volume: 1200, candle_turnover: 123600, previous_close: 100,
  candle_start: candles[9].start, candle_end: candles[9].end, status: 'checked',
  upper_circuit_limit: 104.03, lower_circuit_limit: 92.7,
  upper_circuit_distance_percent: 1, lower_circuit_distance_percent: 10,
  circuit_fetched_at: '2026-10-01T09:25:00+05:30',
};
const stocks = [
  { ...base, symbol: 'COALINDIA', name: 'COAL INDIA LTD', first_candle_color: 'red', second_candle_color: 'green', possible_candidate: true, redwala_gira: true, is_fno: true },
  { ...base, symbol: 'BIRLACABLE', name: 'BIRLA CABLE LIMITED', first_candle_color: 'red', second_candle_color: null, second_candle_start: null, opening_candles: [{ ...candles[0], color: 'red' }], possible_candidate: false, redwala_gira: true },
  { ...base, symbol: 'HIDDEN', qualifies_scan: false },
];

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', route => {
      const pathname = new URL(route.request().url()).pathname;
      let payload = { ok: true, message: 'Test request completed' };
      if (pathname === '/api/config') payload = { client_id: '', symbols_text: 'COALINDIA\nBIRLACABLE', cached_volume_count: 3 };
      if (pathname === '/api/state') payload = { stocks, status: 'Idle', running: false, connected: false, unresolved_symbols: [], updated_at: '2026-10-01T09:25:00+05:30' };
      if (pathname === '/api/backtest') payload = { stocks, target_date: '2026-10-01', tested_count: 3, qualified_count: 2, candidate_count: 1, redwala_count: 2, error_count: 0 };
      return route.fulfill({ json: payload });
    });
    await page.goto(process.env.APP_URL || 'http://127.0.0.1:8011');
    await page.locator('#stockRows .symbol').first().waitFor();
    assert.equal(await page.locator('#stockRows > tr').count(), 4);
    assert.equal(await page.locator('#stockRows > tr').first().locator('td').count(), 19);
    assert.equal(await page.locator('#stockRows > tr').first().locator('.circuit-distance strong').first().innerText(), '1.00%');
    assert.equal(await page.locator('#stockRows > tr').first().locator('.circuit-distance strong').nth(1).innerText(), '10.00%');
    assert.equal(await page.locator('#stockRows .redwala-badge').count(), 2);
    assert.equal(await page.locator('#stockRows > tr').first().locator('.candidate-badge').count(), 2);
    assert.equal(await page.locator('#stockRows').getByText('2: waiting', { exact: true }).count(), 1);
    assert.equal(await page.locator('#stockRows .fno-badge').count(), 1);
    assert.equal(await page.locator('#stockRows').getByText('HIDDEN', { exact: true }).count(), 0);
    await page.locator('#volumeCacheButton').click();
    await page.getByText('Test request completed', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'dashboard-desktop.png'), fullPage: true });
    await page.locator('#liveView .table-wrap').evaluate(el => { el.scrollLeft = el.scrollWidth; });
    await page.screenshot({ path: path.join(output, 'dashboard-badges.png'), fullPage: true });
    await page.locator('#backtestTab').click();
    await page.locator('#backtestDate').fill('2026-09-30');
    await page.locator('#backtestButton').click();
    await page.locator('#backtestRows .symbol').first().waitFor();
    assert.equal(await page.locator('#backtestRows > tr').count(), 2);
    assert.equal(await page.locator('#backtestRows .redwala-badge').count(), 2);
    assert.equal(await page.locator('#backtestRows > tr').first().locator('td').count(), 11);
    await page.screenshot({ path: path.join(output, 'backtest-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#liveTab').click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: path.join(output, 'dashboard-mobile.png'), fullPage: true });
    await page.locator('#backtestTab').click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: path.join(output, 'backtest-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: desktop/mobile live and backtest, badges, filtering, cache button, column counts, no page overflow or JS errors');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
