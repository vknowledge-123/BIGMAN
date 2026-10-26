const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function dashboard() {
  const elements = new Map();
  const context = vm.createContext({
    AbortController, setTimeout, clearTimeout,
    document: {
      querySelector(selector) {
        if (!elements.has(selector)) elements.set(selector, {
          innerHTML: '', textContent: '', value: '', style: {}, hidden: false,
          listeners: {}, addEventListener(name, handler) { this.listeners[name] = handler; },
          setAttribute() {}, classList: { toggle() {} },
        });
        return elements.get(selector);
      },
    },
    window: { addEventListener() {} },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8'), context);
  elements.get('#dailyVolumeMax').value = '4';
  elements.get('#minuteVolumeMin').value = '4';
  elements.get('#firstCandleTurnoverMin').value = '3';
  elements.get('#redwalaOpenGapMax').value = '1';
  elements.get('#pdhlMax').value = '4';
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

test('API validation errors show the field and reason instead of object Object', async () => {
  const {context} = dashboard();
  context.fetch = async () => ({ok: false, json: async () => ({detail: [
    {loc: ['body', 'settings', 'stop_pct'], msg: 'Input should be less than 100'}
  ]})});
  await assert.rejects(vm.runInContext("api('/api/algo/start')", context),
    /settings.stop_pct: Input should be less than 100/);
});

test('daily history warnings label Redwala as partial and preserve all failure details', () => {
  const { context, elements } = dashboard();
  const stocks = [{ ...fixtures()[1], status: 'Partial: daily history unavailable',
    data_warning: 'Daily history for REDPAIR: DH-905', daily_filter: null },
    ...Array.from({length: 6}, (_, i) => ({symbol: `FAIL${i}`, error: 'Daily history DH-905', qualifies_scan: false}))];
  context.result = {stocks, tested_count: 1, error_count: 6, warning_count: 1,
    redwala_count: 1, candidate_count: 0, qualified_count: 1};
  vm.runInContext('renderBacktest(result)', context);
  assert.match(elements.get('#backtestMessage').textContent, /Incomplete backtest: 7 stock/);
  assert.match(elements.get('#backtestRows').innerHTML, /redwala gira/);
  assert.match(elements.get('#backtestRows').innerHTML, /Partial: daily history unavailable/);
  assert.match(elements.get('#backtestIssueList').innerHTML, /FAIL5/);
  assert.doesNotMatch(elements.get('#backtestMessage').textContent, /FAIL5/);
  assert.equal(elements.get('#backtestIssues').hidden, false);
  elements.get('#setupFilter').value = 'possible';
  vm.runInContext('renderBacktest(result)', context);
  assert.match(elements.get('#backtestRows').innerHTML, /could not be fully checked/);
});

test('Redwala low-break badges appear only on Redwala in live and backtest', () => {
  const { context, elements } = dashboard();
  const stocks = [
    { ...fixtures()[1], first_candle_low_break: true, previous_day_low_cross: true },
    { ...fixtures()[0], first_candle_low_break: true, previous_day_low_cross: true },
  ];
  context.state = { stocks, status: 'Live', unresolved_symbols: [] };
  context.result = { stocks, target_date: '2026-10-01', tested_count: 2,
    qualified_count: 2, candidate_count: 1, redwala_count: 1, error_count: 0 };
  vm.runInContext('renderState(state); renderBacktest(result)', context);
  for (const id of ['#stockRows', '#backtestRows']) {
    const html = elements.get(id).innerHTML;
    assert.equal((html.match(/>First Candle Low Break</g) || []).length, 1);
    assert.equal((html.match(/>First Candle PDL Cross</g) || []).length, 1);
  }
});

test('PDL badge requires first-candle cross regardless of later breaks in live and backtest', () => {
  for (const [cross, broken] of [[false, false], [true, false], [false, true], [true, true]]) {
    const { context, elements } = dashboard();
    const stocks = [{ ...fixtures()[1], previous_day_low_cross: cross, previous_day_low_break: broken }];
    context.state = { stocks, status: 'Live', unresolved_symbols: [] };
    context.result = { stocks, target_date: '2026-10-01', tested_count: 1,
      qualified_count: 1, candidate_count: 0, redwala_count: 1, error_count: 0 };
    vm.runInContext('renderState(state); renderBacktest(result)', context);
    for (const id of ['#stockRows', '#backtestRows']) {
      const html = elements.get(id).innerHTML;
      assert.equal((html.match(/>First Candle PDL Cross</g) || []).length, cross ? 1 : 0);
      assert.doesNotMatch(html, />Previous Day Low Break</);
    }
  }
});

test('second-candle PDL badge appears only on Redwala in both views', () => {
  const { context, elements } = dashboard();
  const stocks = [
    { ...fixtures()[1], previous_day_low_cross: true, previous_day_low_cross_second_candle: true },
    { ...fixtures()[0], previous_day_low_cross_second_candle: true },
  ];
  context.state = { stocks, status: 'Live', unresolved_symbols: [] };
  context.result = { stocks, target_date: '2026-10-01', tested_count: 2,
    qualified_count: 2, candidate_count: 1, redwala_count: 1, error_count: 0 };
  vm.runInContext('renderState(state); renderBacktest(result)', context);
  for (const id of ['#stockRows', '#backtestRows']) {
    const html = elements.get(id).innerHTML;
    assert.equal((html.match(/>PDL Cross on 2nd Candle</g) || []).length, 1);
    assert.equal((html.match(/>First Candle PDL Cross</g) || []).length, 1);
  }
});

test('live breakout badges sort first, preserve other matches, and update as badges arrive', () => {
  const { context, elements } = dashboard();
  const stocks = [
    { ...fixtures()[0], symbol: 'PLAIN', first_open_equals_low: true },
    { ...fixtures()[1], symbol: 'RED_PDL', previous_day_low_cross: true },
    { ...fixtures()[0], symbol: 'HIGH_BREAK', first_candle_high_break: true },
    { ...fixtures()[1], symbol: 'PLAIN_RED' },
  ];
  context.state = { stocks, status: 'Live', unresolved_symbols: [] };
  const symbols = () => [...elements.get('#stockRows').innerHTML.matchAll(/<strong>(PLAIN|RED_PDL|HIGH_BREAK|PLAIN_RED)<\/strong>/g)].map(match => match[1]);
  vm.runInContext('renderState(state)', context);
  assert.deepEqual(symbols(), ['RED_PDL', 'HIGH_BREAK', 'PLAIN', 'PLAIN_RED']);
  assert.deepEqual(stocks.map(row => row.symbol), ['PLAIN', 'RED_PDL', 'HIGH_BREAK', 'PLAIN_RED']);
  stocks[0].previous_day_high_cross = true;
  vm.runInContext('renderState(state)', context);
  assert.deepEqual(symbols(), ['PLAIN', 'RED_PDL', 'HIGH_BREAK', 'PLAIN_RED']);
  elements.get('#setupFilter').value = 'redwala';
  stocks[1].previous_day_low_cross = false;
  stocks[3].previous_day_low_cross_second_candle = true;
  vm.runInContext('renderState(state)', context);
  assert.deepEqual(symbols(), ['PLAIN_RED', 'RED_PDL']);
  assert.equal(vm.runInContext('hasBreakoutBadge({redwala_gira:true,first_candle_low_break:true})', context), true);
  assert.equal(vm.runInContext('hasBreakoutBadge({possible_candidate:true,first_candle_high_break:true,awaiting_confirmation:true})', context), false);
});

test('backtest sends opening scan mode', async () => {
  const { context, elements } = dashboard();
  elements.get('#setupFilter').value = 'redwala';
  elements.get('#backtestDate').value = '2026-10-01';
  let backtests = 0;
  context.fetch = async (url, options) => {
    if (url === '/api/volume-filters') return {ok: true, json: async () => ({message: 'Saved'})};
    if (url === '/api/state') return {ok: true, json: async () => ({stocks: [], unresolved_symbols: []})};
    assert.equal(url, '/api/backtest');
    backtests++;
    assert.deepEqual(JSON.parse(options.body), { target_date: '2026-10-01', scan_type: 'opening' });
    return { ok: true, json: async () => ({ scan_type: 'opening', stocks: [], tested_count: 0,
      qualified_count: 0, candidate_count: 0, error_count: 0 }) };
  };
  await vm.runInContext('runBacktest()', context);
  assert.equal(backtests, 1);
  assert.equal(elements.get('#backtestButton').disabled, false);
});

test('backtest waits for selected monthly and two-day filters to save before running', async () => {
  const {context, elements} = dashboard();
  elements.get('#backtestDate').value = '2026-10-09';
  elements.get('#monthlyFilter').checked = true;
  elements.get('#lastTwoDaysFilter').checked = true;
  elements.get('#volumeFiltersForm').listeners.change();
  assert.match(elements.get('#filterChangesStatus').textContent, /Unapplied changes/);
  let finishSave;
  let sentSettings;
  let backtests = 0;
  context.fetch = async (url, options) => {
    if (url === '/api/volume-filters') {
      sentSettings = JSON.parse(options.body);
      return new Promise(resolve => { finishSave = resolve; });
    }
    if (url === '/api/state') return {ok: true, json: async () => ({stocks: [], unresolved_symbols: []})};
    assert.equal(url, '/api/backtest');
    backtests++;
    return {ok: true, json: async () => ({stocks: [], volume_filters: sentSettings,
      target_date: '2026-10-09', tested_count: 0, qualified_count: 0, candidate_count: 0, error_count: 0})};
  };
  const pending = vm.runInContext('runBacktest()', context);
  assert.equal(backtests, 0);
  assert.equal(sentSettings.monthly_filter, true);
  assert.equal(sentSettings.last_two_days_filter, true);
  assert.equal(elements.get('#monthlyFilter').disabled, true);
  await vm.runInContext('runBacktest()', context); // Ignore double clicks.
  finishSave({ok: true, json: async () => ({message: 'Saved'})});
  await pending;
  assert.equal(backtests, 1);
  assert.equal(elements.get('#monthlyFilter').disabled, false);
  assert.match(elements.get('#filterChangesStatus').textContent, /Selected filters are saved/);
  assert.match(elements.get('#backtestMessage').textContent, /Monthly Filter ON/);
  assert.match(elements.get('#backtestMessage').textContent, /Last 2 Days Filter ON/);
});

test('failed or timed-out filter save never starts a backtest', async () => {
  for (const timeout of [false, true]) {
    const {context, elements} = dashboard();
    elements.get('#backtestDate').value = '2026-10-09';
    elements.get('#monthlyFilter').checked = true;
    let backtests = 0;
    context.fetch = async url => {
      if (url === '/api/backtest') backtests++;
      throw Object.assign(new Error('Save failed'), {name: timeout ? 'AbortError' : 'Error'});
    };
    await vm.runInContext('runBacktest()', context);
    assert.equal(backtests, 0);
    assert.match(elements.get('#backtestMessage').textContent, /Backtest not started/);
    assert.equal(elements.get('#monthlyFilter').checked, true);
    assert.equal(elements.get('#monthlyFilter').disabled, false);
    assert.equal(elements.get('#backtestButton').disabled, false);
  }
});

test('invalid settings and an in-progress save block backtests', async () => {
  const {context, elements} = dashboard();
  elements.get('#backtestDate').value = '2026-10-09';
  let requests = 0;
  context.fetch = async () => { requests++; throw new Error('Unexpected request'); };
  elements.get('#minuteVolumeMin').value = '0';
  await vm.runInContext('runBacktest()', context);
  assert.match(elements.get('#backtestMessage').textContent, /greater than zero/);
  elements.get('#minuteVolumeMin').value = '4';
  elements.get('#saveVolumeFilters').disabled = true;
  await vm.runInContext('runBacktest()', context);
  assert.match(elements.get('#backtestMessage').textContent, /still saving/);
  assert.equal(requests, 0);
});

test('turnover column, high-break badge and Retest Break scan render in both views', () => {
  const { context, elements } = dashboard();
  const rows = [
    { ...fixtures()[0], first_candle_turnover: 35000000, first_candle_high_break: true },
    { ...fixtures()[0], symbol: 'RETEST', possible_candidate: false, retest_break: true,
      retest_break_at: '2026-10-01T09:22:00+05:30', retest_reason: 'All green; high broken', first_candle_turnover: 45000000 },
  ];
  context.state = { stocks: rows, status: 'Live', unresolved_symbols: [] };
  context.result = { stocks: rows, target_date: '2026-10-01', tested_count: 2,
    qualified_count: 2, candidate_count: 1, error_count: 0, retest_count: 1 };
  vm.runInContext('renderState(state); renderBacktest(result)', context);
  for (const key of ['#stockRows', '#backtestRows']) {
    assert.match(elements.get(key).innerHTML, /First Candle High Break/);
    assert.match(elements.get(key).innerHTML, /Retest Break/);
    assert.match(elements.get(key).innerHTML, /4\.50 Cr/);
  }
  elements.get('#setupFilter').value = 'retest';
  vm.runInContext('renderState(state); renderBacktest(result)', context);
  for (const key of ['#stockRows', '#backtestRows']) {
    assert.match(elements.get(key).innerHTML, /RETEST/);
    assert.doesNotMatch(elements.get(key).innerHTML, /GREENPAIR|First Candle High Break/);
  }
  assert.equal((elements.get('#backtestRows').innerHTML.match(/<td(?:>| )/g) || []).length, 10);
});

test('filter summary reports the open-cross toggle and exact comparison', () => {
  const { context } = dashboard();
  assert.match(vm.runInContext('filterDescription()', context), /Today Open Cross OFF/);
  assert.match(vm.runInContext('filterDescription({today_open_cross: true})', context), /Today Open Cross ON \(Candidates and Retest Break: open > highest close of prior 5 sessions\)/);
});

test('new opening filters show exact rules in live summaries', () => {
  const { context } = dashboard();
  assert.match(vm.runInContext('filterDescription()', context), /Monthly Filter OFF; Last 2 Days Filter OFF/);
  context.settings = {monthly_filter: true, last_two_days_filter: true};
  for (const fn of ['filterDescription']) {
    const description = vm.runInContext(`${fn}(settings)`, context);
    assert.match(description, /Monthly Filter ON \(open > highest close of prior 20 trading sessions\)/);
    assert.match(description, /both green: no extra condition; red\/doji: open > both prior closes/);
    assert.match(description, /Redwala: turnover plus a red first candle with open = high; volume filters do not apply/);
  }
});

test('filter form submits both toggles and restores saved selections', async () => {
  const { context, elements } = dashboard();
  context.fetch = async (url) => ({ok: true, json: async () => ({
    volume_filters: {monthly_filter: true, last_two_days_filter: true},
  })});
  await vm.runInContext('refreshConfig()', context);
  assert.equal(elements.get('#monthlyFilter').checked, true);
  assert.equal(elements.get('#lastTwoDaysFilter').checked, true);
  elements.get('#monthlyFilter').checked = false;
  vm.runInContext('saveFilterSettings = settings => { globalThis.submitted = settings; }', context);
  elements.get('#volumeFiltersForm').listeners.submit({preventDefault() {}});
  assert.equal(context.submitted.monthly_filter, false);
  assert.equal(context.submitted.last_two_days_filter, true);
});

test('background config refresh preserves toggle drafts and typed credentials', async () => {
  const {context, elements} = dashboard();
  context.fetch = async () => ({ok: true, json: async () => ({client_id: 'SAVED', has_credentials: true,
    symbols_text: 'AAA', volume_filters: {monthly_filter: true}})});
  await vm.runInContext('refreshConfig()', context);
  assert.equal(elements.get('#clientId').value, 'SAVED');
  assert.equal(elements.get('#accessToken').value, '');
  assert.equal(elements.get('#accessToken').required, false);
  assert.match(elements.get('#credentialsStatus').textContent, /Credentials saved/);
  elements.get('#monthlyFilter').checked = false;
  elements.get('#pdhlFilter').checked = true;
  elements.get('#pdhlMax').value = '2.75';
  elements.get('#clientId').value = 'EDITED';
  elements.get('#accessToken').value = 'NEW_TOKEN';
  elements.get('#symbolsText').value = 'NEW_SYMBOL';
  await vm.runInContext('refreshConfig()', context);
  assert.equal(elements.get('#monthlyFilter').checked, false);
  assert.equal(elements.get('#pdhlFilter').checked, true);
  assert.equal(elements.get('#pdhlMax').value, '2.75');
  assert.equal(elements.get('#clientId').value, 'EDITED');
  assert.equal(elements.get('#accessToken').value, 'NEW_TOKEN');
  assert.equal(elements.get('#accessToken').required, true);
  assert.equal(elements.get('#symbolsText').value, 'NEW_SYMBOL');
  assert.match(elements.get('#filterChangesStatus').textContent, /Unapplied/);
});

test('initial slow config load preserves fields edited while it runs', async () => {
  const {context, elements} = dashboard();
  let finish;
  context.fetch = () => new Promise(resolve => { finish = resolve; });
  const request = vm.runInContext('refreshConfig()', context);
  elements.get('#pdhlFilter').checked = true;
  elements.get('#volumeFiltersForm').listeners.change({target: {id: 'pdhlFilter'}});
  elements.get('#clientId').value = 'TYPED';
  finish({ok: true, json: async () => ({client_id: 'SAVED', has_credentials: true,
    volume_filters: {monthly_filter: true, pdhl_filter: false, pdhl_max: 3.25}})});
  await request;
  assert.equal(elements.get('#pdhlFilter').checked, true);
  assert.equal(elements.get('#monthlyFilter').checked, true);
  assert.equal(elements.get('#pdhlMax').value, 3.25);
  assert.equal(elements.get('#clientId').value, 'TYPED');
});

test('late initial algo state and later polls preserve edited algo toggles', () => {
  const {context, elements} = dashboard();
  elements.get('#algoSessions').querySelectorAll = () => [];
  vm.runInContext("qs('#algoTrailing').checked = true; qs('#algoLadder').checked = true", context);
  elements.get('#algoSettingsForm').listeners.change();
  vm.runInContext('renderAlgo({settings: {trailing: false, ladder: false}, sessions: []})', context);
  vm.runInContext('renderAlgo({settings: {trailing: false, ladder: false}, sessions: []})', context);
  assert.equal(elements.get('#algoTrailing').checked, true);
  assert.equal(elements.get('#algoLadder').checked, true);
});

test('stale config response cannot replace newly saved filter state', async () => {
  const {context, elements} = dashboard();
  context.fetch = async () => ({ok: true, json: async () => ({volume_filters: {pdhl_filter: false}})});
  await vm.runInContext('refreshConfig()', context);
  let finish;
  context.fetch = (url) => url === '/api/config' ? new Promise(resolve => { finish = resolve; })
    : Promise.resolve({ok: true, json: async () => ({stocks: [], unresolved_symbols: [], message: 'Saved'})});
  const stale = vm.runInContext('refreshConfig()', context);
  elements.get('#pdhlFilter').checked = true;
  await vm.runInContext('saveFilterSettings(readFilterSettings())', context);
  finish({ok: true, json: async () => ({volume_filters: {pdhl_filter: false}})});
  await stale;
  assert.equal(elements.get('#pdhlFilter').checked, true);
  assert.match(elements.get('#activeVolumeFilters').textContent, /PDHL ON/);
  assert.match(elements.get('#filterChangesStatus').textContent, /Selected filters are saved/);
});

test('setup-specific price controls round trip decimals and reject invalid percentages', async () => {
  const {context, elements} = dashboard();
  context.fetch = async () => ({ok: true, json: async () => ({volume_filters: {
    redwala_open_previous_close: true, redwala_open_gap_max: 1.25, pdhl_filter: true, pdhl_max: 3.75
  }})});
  await vm.runInContext('refreshConfig()', context);
  assert.equal(elements.get('#redwalaOpenPreviousClose').checked, true);
  assert.equal(elements.get('#pdhlFilter').checked, true);
  const settings = vm.runInContext('readFilterSettings()', context);
  assert.equal(settings.redwala_open_gap_max, 1.25);
  assert.equal(settings.pdhl_max, 3.75);
  const summary = vm.runInContext('filterDescription(readFilterSettings())', context);
  assert.match(summary, /Possible Candidates only/);
  assert.match(summary, /first open > previous close > first close/);
  for (const id of ['#redwalaOpenGapMax', '#pdhlMax']) {
    for (const value of ['', '-1', 'NaN', 'Infinity']) {
      elements.get(id).value = value;
      assert.throws(() => vm.runInContext('readFilterSettings()', context), /percentages/);
    }
    elements.get(id).value = '0';
    assert.doesNotThrow(() => vm.runInContext('readFilterSettings()', context));
  }
});

test('turnover captions use live settings and preserve each backtest threshold', () => {
  const { context, elements } = dashboard();
  context.state = { stocks: [fixtures()[2]], status: 'Idle', unresolved_symbols: [],
    volume_filters: { first_candle_turnover_min: 12500000 } };
  vm.runInContext('renderState(state)', context);
  assert.match(elements.get('#liveTurnoverSummary').textContent, /₹1\.25 crore/);
  assert.match(elements.get('#stockRows').innerHTML, /₹1\.25 crore/);
  context.result = { stocks: [fixtures()[2]], target_date: '2026-10-01', tested_count: 1,
    qualified_count: 0, candidate_count: 0, error_count: 0,
    volume_filters: { first_candle_turnover_min: 50000000 } };
  vm.runInContext('renderBacktest(result)', context);
  assert.match(elements.get('#backtestTurnoverSummary').textContent, /₹5 crore/);
  assert.match(elements.get('#backtestMessage').textContent, /₹5 crore/);
  assert.match(elements.get('#backtestRows').innerHTML, /₹5 crore/);
});

test('save completes without waiting for state polling or overwriting newer edits', async () => {
  const { context, elements } = dashboard();
  let resolveState;
  let stateCalls = 0;
  context.fetch = async (url) => {
    if (url === '/api/volume-filters') return { ok: true, json: async () => ({ message: 'Applied' }) };
    assert.equal(url, '/api/state');
    stateCalls++;
    return new Promise((resolve) => { resolveState = resolve; });
  };
  elements.get('#minuteVolumeMin').value = '8';
  await vm.runInContext('saveFilterSettings({daily_volume_max: 4, minute_volume_min: 2, first_candle_turnover_min: 30000000})', context);
  assert.equal(elements.get('#saveVolumeFilters').disabled, false);
  assert.equal(elements.get('#saveVolumeFilters').textContent, 'Save & Apply');
  assert.equal(elements.get('#minuteVolumeMin').value, '8');
  assert.match(elements.get('#activeVolumeFilters').textContent, /first minute ≥ 2×/);
  const firstPoll = vm.runInContext('refreshState()', context);
  assert.equal(firstPoll, vm.runInContext('refreshState()', context));
  assert.equal(stateCalls, 1);
  resolveState({ ok: true, json: async () => ({ stocks: [], status: 'Idle', unresolved_symbols: [] }) });
  await firstPoll;
});

test('save timeout unlocks controls and explains uncertain persistence', async () => {
  const { context, elements } = dashboard();
  context.setTimeout = (callback) => setTimeout(callback, 1);
  context.fetch = (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(Object.assign(new Error('Timed out'), { name: 'AbortError' })));
  });
  await vm.runInContext('saveFilterSettings({daily_volume_max: 4, minute_volume_min: 4, first_candle_turnover_min: 30000000})', context);
  assert.equal(elements.get('#saveVolumeFilters').disabled, false);
  assert.match(elements.get('#message').textContent, /Settings may have been saved/);
});

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
  assert.equal((html.match(/<td(?:>| )/g) || []).length, 38); // 18 cells + one detail row per stock
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
  assert.equal((html.match(/<td(?:>| )/g) || []).length, 20);
});

test('empty results use updated table spans and escape provider errors', () => {
  const { context, elements } = dashboard();
  context.state = { stocks: [], status: 'Idle', unresolved_symbols: [] };
  context.result = { stocks: [], qualified_count: 0, candidate_count: 0, error_count: 0 };
  vm.runInContext('renderState(state); renderBacktest(result)', context);
  assert.match(elements.get('#stockRows').innerHTML, /colspan="18"/);
  assert.match(elements.get('#backtestRows').innerHTML, /colspan="10"/);
  context.state.stocks = [{ ...fixtures()[0], candidate_reason: '<script>alert(1)</script>' }];
  vm.runInContext('renderState(state)', context);
  assert.doesNotMatch(elements.get('#stockRows').innerHTML, /<script>/);
});

test('first-candle setup and crossing badges appear in live and backtest without a second candle', () => {
  const { context, elements } = dashboard();
  const green = { ...fixtures()[0], second_candle_color: null, first_open_equals_low: true, previous_day_high_cross: true };
  const red = { ...fixtures()[1], second_candle_color: null, first_candle_color: 'red', previous_day_low_cross: true };
  context.state = { stocks: [green, red], status: 'Idle', unresolved_symbols: [] };
  context.result = { stocks: [green, red], qualified_count: 2, candidate_count: 1, redwala_count: 1, error_count: 0 };
  vm.runInContext('renderState(state); renderBacktest(result)', context);
  for (const id of ['#stockRows', '#backtestRows']) {
    assert.match(elements.get(id).innerHTML, /Possible candidate/);
    assert.match(elements.get(id).innerHTML, /redwala gira/);
    assert.match(elements.get(id).innerHTML, /F&amp;O/);
    assert.match(elements.get(id).innerHTML, /open ==low/);
    assert.match(elements.get(id).innerHTML, /previous day high cross/);
    assert.match(elements.get(id).innerHTML, /First Candle PDL Cross/);
    assert.doesNotMatch(elements.get(id).innerHTML, /2: waiting/);
  }
  context.state.stocks = [{ ...red, first_open_equals_low: true, previous_day_high_cross: true }];
  vm.runInContext('renderState(state)', context);
  assert.match(elements.get('#stockRows').innerHTML, /redwala gira/);
  assert.doesNotMatch(elements.get('#stockRows').innerHTML, /Possible candidate|open ==low|previous day high cross/);
});

test('circuit distances display percentage, zero at the limit and missing states', () => {
  const { context } = dashboard();
  context.row = { upper_circuit_distance_percent: 1, lower_circuit_distance_percent: 10,
    upper_circuit_limit: 101, lower_circuit_limit: 90, circuit_fetched_at: '2026-10-01T10:00:00+05:30' };
  assert.match(vm.runInContext('fmtCircuitDistance(row, "upper")', context), /1\.00%/);
  assert.match(vm.runInContext('fmtCircuitDistance(row, "lower")', context), /10\.00%/);
  context.row.upper_circuit_distance_percent = 0;
  assert.match(vm.runInContext('fmtCircuitDistance(row, "upper")', context), /0\.00%/);
  context.row.upper_circuit_distance_percent = null;
  context.row.circuit_error = '<script>Bad quote</script>';
  const missing = vm.runInContext('fmtCircuitDistance(row, "upper")', context);
  assert.match(missing, /<strong>--<\/strong>/);
  assert.doesNotMatch(missing, /<script>/);
});

test('live matches are visible as awaiting confirmation without final badges or confirmed counts', () => {
  const { context, elements } = dashboard();
  context.state = { stocks: [{ ...fixtures()[0], qualifies_scan: false, possible_candidate: false,
    preparation_status: 'ready', confirmation_status: 'awaiting_confirmation', awaiting_confirmation: true,
    provisional_setup: 'Possible candidate', first_open_equals_low: true, previous_day_high_cross: true,
  }], status: 'Live', unresolved_symbols: [] };
  vm.runInContext('renderState(state)', context);
  assert.match(elements.get('#stockRows').innerHTML, /Possible candidate - Awaiting confirmation/);
  assert.doesNotMatch(elements.get('#stockRows').innerHTML, /open ==low|previous day high cross/);
  assert.equal(elements.get('#stockCount').textContent, '0/1');
  assert.match(elements.get('#scanSummary').textContent, /Awaiting confirmation 1/);
  Object.assign(context.state.stocks[0], { qualifies_scan: true, possible_candidate: true,
    confirmation_status: 'confirmed', awaiting_confirmation: false });
  vm.runInContext('renderState(state)', context);
  assert.doesNotMatch(elements.get('#stockRows').innerHTML, /Awaiting confirmation/);
  assert.match(elements.get('#stockRows').innerHTML, /previous day high cross/);
  assert.equal(elements.get('#stockCount').textContent, '1/1');
});


test('opening setups and algo start controls remain visible after 13:30 IST', () => {
  const { context, elements } = dashboard();
  const stocks = fixtures().map(row => ({...row, confirmation_status: 'confirmed'}));
  context.state = {stocks, status: 'Live', unresolved_symbols: [], updated_at: '2026-10-16T14:00:00+05:30'};
  vm.runInContext('renderState(state)', context);
  const html = elements.get('#stockRows').innerHTML;
  assert.match(html, /GREENPAIR/);
  assert.match(html, /REDPAIR/);
  assert.equal((html.match(/data-algo-action="start"/g) || []).length, 2);
  assert.equal(elements.has('#afternoonStartButton'), false);
  assert.doesNotMatch(fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8'), /afternoon/i);
});


test('badge stocks sort by first-candle turnover across both setups', () => {
  const { context, elements } = dashboard();
  const stocks = [
    {...fixtures()[0],symbol:'PLAIN',first_candle_turnover:990000000},
    {...fixtures()[1],symbol:'RED19',previous_day_low_cross:true,first_candle_turnover:190000000,candle_turnover:900000000},
    {...fixtures()[0],symbol:'GREEN20',first_candle_high_break:true,first_candle_turnover:200000000,candle_turnover:1},
    {...fixtures()[0],symbol:'TIE20',previous_day_high_cross:true,first_candle_turnover:200000000},
    {...fixtures()[1],symbol:'MISSING',first_candle_low_break:true,first_candle_turnover:null},
    {...fixtures()[0],symbol:'PROVISIONAL',first_candle_high_break:true,first_candle_turnover:500000000,awaiting_confirmation:true},
  ];
  context.state={stocks,status:'Live',unresolved_symbols:[]};
  vm.runInContext('renderState(state)', context);
  const symbols=()=>[...elements.get('#stockRows').innerHTML.matchAll(/<strong>(PLAIN|RED19|GREEN20|TIE20|MISSING|PROVISIONAL)<\/strong>/g)].map(m=>m[1]);
  assert.deepEqual(symbols(),['GREEN20','TIE20','RED19','MISSING','PLAIN','PROVISIONAL']);
  stocks[0].previous_day_high_cross=true;
  vm.runInContext('renderState(state)', context);
  assert.deepEqual(symbols(),['PLAIN','GREEN20','TIE20','RED19','MISSING','PROVISIONAL']);
  elements.get('#setupFilter').value='redwala';
  vm.runInContext('renderState(state)', context);
  assert.deepEqual(symbols(),['RED19','MISSING']);
  assert.equal(stocks[0].symbol,'PLAIN');
});

test('explicit first direction overrides setup direction in the live confirmation', () => {
  const {context}=dashboard();
  assert.equal(vm.runInContext("algoFirstSide({first_direction:'short'}, 'possible')",context),'SELL');
  assert.equal(vm.runInContext("algoFirstSide({first_direction:'long'}, 'redwala')",context),'BUY');
  assert.equal(vm.runInContext("algoFirstSide({}, 'possible')",context),'BUY');
  assert.equal(vm.runInContext("algoFirstSide({}, 'redwala')",context),'SELL');
});
