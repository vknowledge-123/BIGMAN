const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function dashboard() {
  const elements = new Map();
  const context = vm.createContext({
    document: {
      querySelector(selector) {
        if (!elements.has(selector)) elements.set(selector, {
          innerHTML: '', textContent: '', style: {}, hidden: false,
          addEventListener() {}, setAttribute() {}, classList: { toggle() {} },
        });
        return elements.get(selector);
      },
    },
    window: { addEventListener() {} },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8'), context);
  return { context, elements };
}

function fixtures() {
  const daily = {
    previous_date: '2026-09-30', previous_volume: 3000, average: 1000,
    multiplier: 3, percent_change: 2, price_exception: false,
    samples: [{ date: '2026-09-29', volume: 1000 }],
  };
  const base = {
    daily_filter: daily, volume_multiplier: 4, opening_volume_average: 100,
    qualifies_scan: true, opening_candles: [], candidate_reason: 'Daily check passed',
    first_candle_color: 'green', second_candle_color: 'green',
  };
  return [
    { ...base, symbol: 'GREENPAIR', possible_candidate: true, is_fno: true },
    { ...base, symbol: 'REDPAIR', possible_candidate: false, redwala_gira: true },
    { ...base, symbol: 'DAILYFAIL', qualifies_scan: false },
    { ...base, symbol: 'APIERROR', qualifies_scan: false, error: 'Daily history missing' },
  ];
}

test('live table displays only qualified rows with correct badges and daily columns', () => {
  const { context, elements } = dashboard();
  context.state = { stocks: fixtures(), status: 'Idle', unresolved_symbols: [] };
  vm.runInContext('renderState(state)', context);
  const html = elements.get('#stockRows').innerHTML;
  assert.match(html, /GREENPAIR/);
  assert.match(html, /REDPAIR/);
  assert.match(html, /Possible candidate/);
  assert.match(html, /redwala gira/);
  assert.match(html, /F&amp;O/);
  assert.match(html, /3\.00x/);
  assert.doesNotMatch(html, /DAILYFAIL|APIERROR/);
  assert.equal(elements.get('#stockCount').textContent, '2/4');
  assert.match(elements.get('#scanIssues').textContent, /APIERROR: Daily history missing/);
  assert.equal(elements.get('#scanIssues').hidden, false);
  assert.equal((html.match(/<td(?:>| )/g) || []).length, 36); // 17 cells + one detail row per stock
});

test('backtest filtering matches live and preserves failed-check diagnostics', () => {
  const { context, elements } = dashboard();
  context.result = {
    stocks: fixtures(), target_date: '2026-10-01', tested_count: 3,
    qualified_count: 2, candidate_count: 1, redwala_count: 1, error_count: 1,
  };
  vm.runInContext('renderBacktest(result)', context);
  const html = elements.get('#backtestRows').innerHTML;
  assert.match(html, /GREENPAIR/);
  assert.match(html, /REDPAIR/);
  assert.doesNotMatch(html, /DAILYFAIL|APIERROR/);
  assert.equal(elements.get('#backtestFourX').textContent, 2);
  assert.match(elements.get('#backtestMessage').textContent, /1 redwala gira/);
  assert.match(elements.get('#backtestMessage').textContent, /APIERROR: Daily history missing/);
  assert.equal((html.match(/<td(?:>| )/g) || []).length, 22);
});

test('empty results use updated table spans and escape provider errors', () => {
  const { context, elements } = dashboard();
  context.state = { stocks: [], status: 'Idle', unresolved_symbols: [] };
  context.result = { stocks: [], qualified_count: 0, candidate_count: 0, error_count: 0 };
  vm.runInContext('renderState(state); renderBacktest(result)', context);
  assert.match(elements.get('#stockRows').innerHTML, /colspan="17"/);
  assert.match(elements.get('#backtestRows').innerHTML, /colspan="11"/);
  context.state.stocks = [{ ...fixtures()[0], candidate_reason: '<script>alert(1)</script>' }];
  vm.runInContext('renderState(state)', context);
  assert.doesNotMatch(elements.get('#stockRows').innerHTML, /<script>/);
});
