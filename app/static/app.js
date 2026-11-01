const qs = (selector) => document.querySelector(selector);

const els = {
  volumeFiltersForm: qs("#volumeFiltersForm"),
  dailyVolumeMax: qs("#dailyVolumeMax"),
  minuteVolumeMin: qs("#minuteVolumeMin"),
  firstCandleTurnoverMin: qs("#firstCandleTurnoverMin"),
  todayOpenCross: qs("#todayOpenCross"),
  monthlyFilter: qs("#monthlyFilter"),
  lastTwoDaysFilter: qs("#lastTwoDaysFilter"),
  redwalaOpenPreviousClose: qs("#redwalaOpenPreviousClose"),
  redwalaOpenGapMax: qs("#redwalaOpenGapMax"),
  redwalaOpenTolerance: qs("#redwalaOpenTolerance"),
  redwalaOpenToleranceMax: qs("#redwalaOpenToleranceMax"),
  pdhlFilter: qs("#pdhlFilter"),
  pdhlMax: qs("#pdhlMax"),
  possibleOpenPreClose: qs("#possibleOpenPreClose"),
  possibleOpenPreCloseMax: qs("#possibleOpenPreCloseMax"),
  setupFilter: qs("#setupFilter"),
  dashboardVolumeEnabled: qs("#dashboardVolumeEnabled"),
  dashboardVolumeMin: qs("#dashboardVolumeMin"),
  dashboardVolumeError: qs("#dashboardVolumeError"),
  dashboardVolumeSummary: qs("#dashboardVolumeSummary"),
  dashboardPriceEnabled: qs("#dashboardPriceEnabled"),
  dashboardPriceMax: qs("#dashboardPriceMax"),
  dashboardPriceError: qs("#dashboardPriceError"),
  liveTurnoverSummary: qs("#liveTurnoverSummary"),
  backtestTurnoverSummary: qs("#backtestTurnoverSummary"),
  saveVolumeFilters: qs("#saveVolumeFilters"),
  activeVolumeFilters: qs("#activeVolumeFilters"),
  filterChangesStatus: qs("#filterChangesStatus"),
  credentialsForm: qs("#credentialsForm"),
  symbolsForm: qs("#symbolsForm"),
  clientId: qs("#clientId"),
  accessToken: qs("#accessToken"),
  credentialsStatus: qs("#credentialsStatus"),
  symbolsText: qs("#symbolsText"),
  cacheButton: qs("#cacheButton"),
  volumeCacheButton: qs("#volumeCacheButton"),
  startButton: qs("#startButton"),
  stopButton: qs("#stopButton"),
  repairButton: qs("#repairButton"),
  message: qs("#message"),
  unresolved: qs("#unresolved"),
  scanIssues: qs("#scanIssues"),
  rows: qs("#stockRows"),
  connectionBadge: qs("#connectionBadge"),
  updatedAt: qs("#updatedAt"),
  stockCount: qs("#stockCount"),
  cachedCount: qs("#cachedCount"),
  topTurnover: qs("#topTurnover"),
  topChange: qs("#topChange"),
  liveTab: qs("#liveTab"),
  backtestTab: qs("#backtestTab"),
  liveView: qs("#liveView"),
  backtestView: qs("#backtestView"),
  backtestDate: qs("#backtestDate"),
  backtestButton: qs("#backtestButton"),
  backtestMessage: qs("#backtestMessage"),
  backtestRows: qs("#backtestRows"),
  backtestTested: qs("#backtestTested"),
  backtestFourX: qs("#backtestFourX"),
  backtestCandidates: qs("#backtestCandidates"),
  backtestErrors: qs("#backtestErrors"),
};

function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function filterDescription(settings = {}) {
  return `Day ≤ ${settings.daily_volume_max ?? 4}× (or price change ≤ +1%); first minute ≥ ${settings.minute_volume_min ?? 4}×; ${turnoverDescription(settings)}; Today Open Cross ${settings.today_open_cross ? "ON (Candidates and Retest Break: open > highest close of prior 5 sessions)" : "OFF"}; ${additionalOpeningDescription(settings)}`;
}

function additionalOpeningDescription(settings = {}) {
  const redwalaOpeningRule = settings.redwala_open_tolerance
    ? `opening tolerance ON (open at/above previous close or up to ${settings.redwala_open_tolerance_max ?? 0.5}% below); first close < previous close`
    : "opening tolerance OFF; first open > previous close > first close";
  return `Monthly Filter ${settings.monthly_filter ? "ON (open > highest close of prior 20 trading sessions)" : "OFF"}; Last 2 Days Filter ${settings.last_two_days_filter ? "ON (both green: no extra condition; red/doji: open > both prior closes)" : "OFF"}; PDHL ${settings.pdhl_filter ? `ON (Possible Candidates only: (previous high - low) / low ≤ ${settings.pdhl_max ?? 4}%)` : "OFF"}; Possible Candidates Open / Previous Close ${settings.possible_open_pre_close ? `ON (absolute opening difference ≤ ${settings.possible_open_pre_close_max ?? 1}%)` : "OFF"}; Redwala: turnover plus a red first candle with open = high; volume filters do not apply; Redwala Open or Close / Previous Close ${settings.redwala_open_previous_close ? `ON (open or close absolute distance ≤ ${settings.redwala_open_gap_max ?? 1}%; ${redwalaOpeningRule})` : "OFF"}`;
}

function turnoverDescription(settings = {}) {
  return `first-candle turnover > ₹${(settings.first_candle_turnover_min ?? 30000000) / 10000000} crore`;
}

function fmtInt(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function fmtTurnover(value) {
  if (!value) return "--";
  const amount = Number(value);
  if (amount >= 10000000) return `${fmtNumber(amount / 10000000, 2)} Cr`;
  if (amount >= 100000) return `${fmtNumber(amount / 100000, 2)} L`;
  return fmtNumber(amount, 0);
}

function fmtTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[char]);
}

function fmtCandle(row) {
  if (!row.candle_start || !row.candle_end) return "--";
  const start = fmtTime(row.candle_start).slice(0, 5);
  const end = fmtTime(row.candle_end).slice(0, 5);
  return `${start} - ${end}`;
}

function fmtDateInput(date, offsetDays = 0) {
  const shifted = new Date(date.getTime() + offsetDays * 86400000);
  const parts = new Intl.DateTimeFormat("en-GB", {timeZone: "Asia/Kolkata",
    year: "numeric", month: "2-digit", day: "2-digit"}).formatToParts(shifted);
  const part = type => parts.find(item => item.type === type).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function fmtBacktestCandle(start, color) {
  if (!start || !color) return `<span class="muted-small">--</span>`;
  const safeColor = ["green", "red", "doji"].includes(color) ? color : "doji";
  return `<span class="candle-color ${safeColor}">${fmtTime(start).slice(0, 5)} ${escapeHtml(color)}</span>`;
}

function fmtOpeningPair(row) {
  const colors = [row.first_candle_color];
  if (colors.every((color) => !color)) return `<span class="muted-small">--</span>`;
  return `<div class="opening-pair">${colors.map((color, index) => {
    if (!color) return `<span class="candle-color doji">${index + 1}: waiting</span>`;
    const safeColor = ["green", "red", "doji"].includes(color) ? color : "doji";
    return `<span class="candle-color ${safeColor}">${index + 1}: ${escapeHtml(color)}</span>`;
  }).join("")}</div>`;
}

function fmtOpeningTimeline(row) {
  const candles = (row.opening_candles || []).slice(0, 5);
  const slots = Array(5).fill(null);
  if (candles.length) {
    const firstStart = new Date(candles[0].start).getTime();
    candles.forEach((candle) => {
      const slot = Math.round((new Date(candle.start).getTime() - firstStart) / 60000);
      if (slot >= 0 && slot < slots.length) slots[slot] = candle;
    });
  }
  return `<div class="opening-timeline">${slots.map((candle, index) => {
    if (!candle) {
      return `<div class="opening-candle waiting"><span>#${index + 1}</span><strong>Waiting</strong></div>`;
    }
    const safeColor = ["green", "red", "doji"].includes(candle.color) ? candle.color : "doji";
    return `
      <div class="opening-candle ${safeColor}">
        <div><span>${fmtTime(candle.start).slice(0, 5)}</span><span>${escapeHtml(candle.color)}</span></div>
        <strong>${fmtTurnover(candle.turnover)}</strong>
        <small>Vol ${fmtInt(candle.volume)}</small>
        <small>Close ${fmtNumber(candle.close, 2)}</small>
      </div>
    `;
  }).join("")}</div>`;
}

function setMessage(text, isError = false) {
  els.message.textContent = text;
  els.message.style.color = isError ? "#c92a2a" : "#697386";
}

function fmtDailyFilter(row) {
  const daily = row.daily_filter;
  if (!daily) return '<td>--</td><td>--</td>';
  const samples = daily.samples.map((sample) => `${sample.date}: ${fmtInt(sample.volume)}`).join(' | ');
  const detail = `${daily.previous_date}: ${fmtInt(daily.previous_volume)} / ${fmtNumber(daily.average, 2)}; High ${fmtNumber(daily.previous_high, 2)}, Low ${fmtNumber(daily.previous_low, 2)}; ${samples}`;
  const exception = daily.price_exception ? ' (price exception)' : '';
  return `<td title="${escapeHtml(detail)}"><strong>${fmtNumber(daily.multiplier, 2)}x</strong></td>
    <td title="${escapeHtml(daily.previous_date + exception)}">${fmtNumber(daily.percent_change, 2)}%</td>`;
}

function fmtSignalBadge(row, reason) {
  const badges = [];
  if (row.awaiting_confirmation) return badges.join('') + `<span class="candidate-badge pending-badge" title="${reason}">${escapeHtml(row.provisional_setup || "Live match")} - Awaiting confirmation</span>`;
  if (row.possible_candidate) badges.push(`<span class="candidate-badge" title="${reason}">Possible candidate</span>`);
  if (row.possible_candidate && row.first_candle_high_break) badges.push(`<span class="candidate-badge" title="A later trade exceeded the first candle's high; this badge remains after the break">First Candle High Break</span>`);
  if (row.retest_break) badges.push(`<span class="candidate-badge retest-badge" title="${escapeHtml(row.retest_reason || '')}">Retest Break${row.retest_break_at ? ` · ${fmtTime(row.retest_break_at).slice(0, 5)}` : ''}</span>`);
  if (row.possible_candidate && row.first_open_equals_low) badges.push(`<span class="candidate-badge" title="First candle open equals its low">open ==low</span>`);
  if (row.possible_candidate && row.previous_day_high_cross) badges.push(`<span class="candidate-badge" title="First candle opens below and closes above previous day high (${fmtNumber(row.daily_filter?.previous_high, 2)})">previous day high cross</span>`);
  if (row.redwala_gira) badges.push(`<span class="candidate-badge redwala-badge" title="${reason}">redwala gira</span>`);
  if (row.redwala_gira && row.first_candle_low_break) badges.push(`<span class="candidate-badge redwala-badge" title="A later price traded strictly below the first candle low; retained after a rebound">First Candle Low Break</span>`);
  if (row.redwala_gira && row.previous_day_low_cross) badges.push(`<span class="candidate-badge redwala-badge" title="First candle opens strictly above and closes strictly below the previous trading day's low (${fmtNumber(row.daily_filter?.previous_low, 2)})">First Candle PDL Cross</span>`);
  if (row.redwala_gira && row.previous_day_low_cross_second_candle) badges.push(`<span class="candidate-badge redwala-badge" title="Second candle opens strictly above and closes strictly below the previous trading day's low (${fmtNumber(row.daily_filter?.previous_low, 2)})">PDL Cross on 2nd Candle</span>`);
  return badges.join("") || `<span class="muted-small" title="${reason}">--</span>`;
}

function fmtCircuitDistance(row, side) {
  const distance = row[`${side}_circuit_distance_percent`];
  const limit = row[`${side}_circuit_limit`];
  const available = distance !== null && distance !== undefined && Number.isFinite(Number(distance));
  const title = available
    ? `${side === "upper" ? "Upper" : "Lower"} circuit ${fmtNumber(limit)}; quote ${fmtTime(row.circuit_fetched_at)}; distance as % of LTP`
    : (row.circuit_error || "Circuit limit unavailable");
  return `<td class="circuit-distance" title="${escapeHtml(title)}"><strong>${available ? `${fmtNumber(distance)}%` : "--"}</strong>
    <small>${limit === null || limit === undefined ? "" : `Limit ${fmtNumber(limit)}`}</small></td>`;
}

async function api(path, options = {}, timeoutMs = 0) {
  const controller = timeoutMs ? new AbortController() : null;
  const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(path, {
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      ...options,
      ...(controller ? { signal: controller.signal } : {}),
    });
    const payload = await response.json().catch((error) => {
      if (error.name === "AbortError") throw error;
      return {};
    });
    if (!response.ok) {
      const detail = payload.detail || payload.message;
      const message = Array.isArray(detail)
        ? detail.map(item => `${(item.loc || []).filter(part => part !== 'body').join('.')}: ${item.msg || 'Invalid value'}`).join('; ')
        : typeof detail === 'string' ? detail : 'Request failed';
      throw new Error(message);
    }
    return payload;
  } finally {
    if (timeout !== null) clearTimeout(timeout);
  }
}

function setBusy(button, busy) {
  button.disabled = busy;
}

async function runAction(button, fn) {
  setBusy(button, true);
  try {
    const result = await fn();
    setMessage(result.message || "Done");
    await refreshState();
    await refreshConfig();
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

let lastLiveState = null;
const dashboardVolumeStorageKey = "scanner.dashboardVolume.v1";
let dashboardVolumeFilter = {enabled: false, minimum: 100000};

function restoreDashboardVolumeFilter() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(dashboardVolumeStorageKey));
    if (saved && typeof saved.enabled === "boolean" && Number.isSafeInteger(saved.minimum) && saved.minimum >= 0) {
      dashboardVolumeFilter = {enabled: saved.enabled, minimum: saved.minimum};
    }
  } catch (_) { /* Unavailable storage or invalid saved data: use defaults. */ }
  els.dashboardVolumeEnabled.checked = dashboardVolumeFilter.enabled;
  els.dashboardVolumeMin.value = dashboardVolumeFilter.minimum;
}

function matchesDashboardVolume(row, backtest = false) {
  const volume = backtest ? row.first_candle_volume : row.today_opening_volume;
  return !dashboardVolumeFilter.enabled || (Number.isFinite(volume) && volume > dashboardVolumeFilter.minimum);
}

function applyDashboardVolumeFilter() {
  const raw = String(els.dashboardVolumeMin.value).trim();
  const minimum = Number(raw);
  const valid = raw !== "" && Number.isSafeInteger(minimum) && minimum >= 0;
  const enabled = Boolean(els.dashboardVolumeEnabled.checked);
  els.dashboardVolumeError.hidden = valid;
  els.dashboardVolumeError.textContent = valid ? "" : "Enter a whole number of shares, zero or higher. The last valid threshold remains applied.";
  if (!valid && enabled) {
    els.dashboardVolumeEnabled.checked = dashboardVolumeFilter.enabled;
    return;
  }
  dashboardVolumeFilter = {enabled, minimum: valid ? minimum : dashboardVolumeFilter.minimum};
  try { window.localStorage.setItem(dashboardVolumeStorageKey, JSON.stringify(dashboardVolumeFilter)); }
  catch (_) { /* Filtering still works without browser storage. */ }
  if (lastLiveState) renderState(lastLiveState);
  if (lastBacktestResult) renderBacktest(lastBacktestResult);
}

restoreDashboardVolumeFilter();
els.dashboardVolumeEnabled.addEventListener("change", applyDashboardVolumeFilter);
els.dashboardVolumeMin.addEventListener("input", applyDashboardVolumeFilter);
let lastBacktestResult = null;
const dashboardPriceStorageKey = "scanner.dashboardPrice.v1";
let dashboardPriceFilter = {enabled: false, maximum: 250};
try {
  const saved = JSON.parse(window.localStorage.getItem(dashboardPriceStorageKey));
  // Preserve the entered value from the former minimum-price control.
  const maximum = saved?.maximum ?? saved?.minimum;
  if (saved && typeof saved.enabled === "boolean" && Number.isFinite(maximum) && maximum >= 0) {
    dashboardPriceFilter = {enabled: saved.enabled, maximum};
  }
} catch (_) { /* Use defaults when storage is unavailable or malformed. */ }
els.dashboardPriceEnabled.checked = dashboardPriceFilter.enabled;
els.dashboardPriceMax.value = dashboardPriceFilter.maximum;

function matchesDashboardPrice(row, backtest = false) {
  const price = backtest ? row.first_candle_close : row.ltp;
  return !dashboardPriceFilter.enabled || (Number.isFinite(price) && price > 0 && price <= dashboardPriceFilter.maximum);
}

function applyDashboardPriceFilter() {
  const raw = String(els.dashboardPriceMax.value).trim();
  const maximum = Number(raw);
  const valid = raw !== "" && Number.isFinite(maximum) && maximum >= 0;
  const enabled = Boolean(els.dashboardPriceEnabled.checked);
  els.dashboardPriceError.hidden = valid;
  els.dashboardPriceError.textContent = valid ? "" : "Enter a finite price, zero or higher. The last valid maximum remains applied.";
  if (!valid && enabled) {
    els.dashboardPriceEnabled.checked = dashboardPriceFilter.enabled;
    return;
  }
  dashboardPriceFilter = {enabled, maximum: valid ? maximum : dashboardPriceFilter.maximum};
  try { window.localStorage.setItem(dashboardPriceStorageKey, JSON.stringify(dashboardPriceFilter)); } catch (_) {}
  if (lastLiveState) renderState(lastLiveState);
  if (lastBacktestResult) renderBacktest(lastBacktestResult);
}
els.dashboardPriceEnabled.addEventListener("change", applyDashboardPriceFilter);
els.dashboardPriceMax.addEventListener("input", applyDashboardPriceFilter);

function displayFilterDescription(backtest = false) {
  const filters = [];
  if (dashboardVolumeFilter.enabled) filters.push(`first-candle volume > ${fmtInt(dashboardVolumeFilter.minimum)} shares`);
  if (dashboardPriceFilter.enabled) filters.push(`${backtest ? "first-candle close" : "LTP"} <= Rs ${fmtNumber(dashboardPriceFilter.maximum)}`);
  return filters.length ? filters.join("; ") : "display filters OFF";
}

function matchesSetup(row) {
  const selected = els.setupFilter.value || "all";
  if (selected === "possible") return row.possible_candidate || row.provisional_setup === "Possible candidate";
  if (selected === "redwala") return row.redwala_gira || row.provisional_setup === "redwala gira";
  if (selected === "retest") return row.retest_break;
  return true;
}

// Preserve existing breakout-badge priority; ties keep the scanner order.
function hasBreakoutBadge(row) {
  if (row.awaiting_confirmation) return false;
  return Boolean((row.possible_candidate && (row.first_candle_high_break || row.previous_day_high_cross))
    || (row.redwala_gira && (row.first_candle_low_break || row.previous_day_low_cross
      || row.previous_day_low_cross_second_candle)));
}

function compareLiveStocks(a, b) {
  const priority = Number(hasBreakoutBadge(b)) - Number(hasBreakoutBadge(a));
  if (priority) return priority;
  if (!hasBreakoutBadge(a) && !dashboardVolumeFilter.enabled && !dashboardPriceFilter.enabled) return 0;
  const turnover = row => Number.isFinite(row.first_candle_turnover) && row.first_candle_turnover >= 0
    ? row.first_candle_turnover : -1;
  return turnover(b) - turnover(a);
}

function renderState(state) {
  lastLiveState = state;
  updateAlgoBacktestStale();
  renderAlgo(state.algo);
  els.liveTurnoverSummary.textContent = `Showing setups with ${turnoverDescription(state.volume_filters)} (volume × close).`;
  els.connectionBadge.textContent = state.connected ? "Live Connected" : state.running ? "Connecting" : "Idle";
  els.connectionBadge.className = `badge ${state.connected ? "live" : state.status.toLowerCase().includes("error") ? "error" : "neutral"}`;
  els.updatedAt.textContent = `Updated ${fmtTime(state.updated_at)}`;
  const setupStocks = state.stocks.filter((row) => (row.qualifies_scan === true || row.awaiting_confirmation) && matchesSetup(row));
  const visibleStocks = setupStocks.filter(row => matchesDashboardVolume(row) && matchesDashboardPrice(row)).sort(compareLiveStocks);
  els.dashboardVolumeSummary.textContent = dashboardVolumeFilter.enabled || dashboardPriceFilter.enabled
    ? `Showing ${visibleStocks.length} of ${setupStocks.length} matching setups: ${displayFilterDescription()}. ${setupStocks.length - visibleStocks.length} hidden by display filters. Qualified Stocks counts all scanner matches.`
    : `Dashboard volume filter OFF. Showing ${visibleStocks.length} matching setups.`;
  const confirmedCount = state.stocks.filter((row) => row.qualifies_scan === true).length;
  const awaitingCount = state.stocks.filter((row) => row.awaiting_confirmation).length;
  els.stockCount.textContent = `${confirmedCount}/${state.stocks.length}`;
  qs("#scanSummary").textContent = `Prepared ${state.stocks.filter((row) => row.preparation_status === "ready").length} | Daily-filter failures (still scanned for Redwala) ${state.stocks.filter((row) => row.preparation_status === "excluded").length} | Unresolved ${state.stocks.filter((row) => row.error || row.preparation_status === "unresolved" || row.confirmation_status === "unresolved").length} | Awaiting confirmation ${awaitingCount} | Confirmed setups ${confirmedCount} | Retest Break ${state.stocks.filter((row) => row.retest_break).length}`;
  els.cachedCount.textContent = state.stocks.filter((row) => row.preparation_status === "ready").length;
  els.unresolved.textContent = state.unresolved_symbols.length ? `Unresolved: ${state.unresolved_symbols.join(", ")}` : "";
  const failedChecks = state.stocks.filter((row) => row.error || /Opening candle check (failed|skipped)/.test(row.candidate_reason || ""));
  const retestIssues = state.stocks.filter((row) => row.retest_status === "unresolved")
    .map((row) => `${row.symbol}: ${row.retest_reason || "Retest check unresolved"}`);
  const issues = [...failedChecks.map((row) => `${row.symbol}: ${row.error || row.candidate_reason}`), ...retestIssues];
  els.scanIssues.hidden = issues.length === 0;
  els.scanIssues.textContent = issues.join("; ");

  const top = visibleStocks[0];
  els.topTurnover.textContent = top ? fmtTurnover(top.candle_turnover) : "--";
  els.topChange.textContent = top && top.percent_change !== null ? `${fmtNumber(top.percent_change, 2)}%` : "--";

  if (!visibleStocks.length) {
    const message = dashboardPriceFilter.enabled && setupStocks.length
      ? `No setups match the display filters: ${displayFilterDescription()}. Adjust the limits or turn the display filters OFF.`
      : dashboardVolumeFilter.enabled && setupStocks.length
      ? `No setups have first-candle volume strictly above ${fmtInt(dashboardVolumeFilter.minimum)} shares. Lower the dashboard threshold or turn this display filter OFF.`
      : state.stocks.length
      ? `No matching setups yet: ${turnoverDescription(state.volume_filters)}; Redwala requires a red first candle with open = high, without volume filters`
      : "No stocks loaded";
    els.rows.innerHTML = `<tr><td colspan="18" class="empty">${message}</td></tr>`;
    return;
  }

  els.rows.innerHTML = visibleStocks.map((row, index) => {
    const changeClass = row.percent_change >= 0 ? "positive" : "negative";
    const statusText = row.error || row.status || "waiting";
    const safeStatus = escapeHtml(statusText);
    const candidateReason = escapeHtml(row.candidate_reason || "Opening candles not checked");
    const candidateBadge = fmtSignalBadge(row, candidateReason);
    const fnoBadge = row.is_fno ? `<span class="fno-badge">F&amp;O</span>` : "";
    const samples = (row.opening_volume_samples || [])
      .map((sample) => `${sample.date}: ${fmtInt(sample.volume)}`)
      .join(" | ");
    return `
      <tr class="${row.possible_candidate ? "candidate-row" : ""}">
        <td>${index + 1}</td>
        <td class="symbol-cell">
          <div class="symbol">
            <strong>${escapeHtml(row.symbol)}</strong>
            <span>${escapeHtml(row.name || row.security_id || "")}</span>
          </div>
          <div class="badge-stack">${candidateBadge}${fnoBadge}</div>
          ${algoRowButton(row, false)}
        </td>
        <td class="first-turnover-cell"><strong>${fmtTurnover(row.first_candle_turnover)}</strong></td>
        <td><strong class="multiplier">${row.volume_multiplier === null ? "--" : `${fmtNumber(row.volume_multiplier, 2)}x`}</strong></td>
        <td>${fmtNumber(row.ltp, 2)}</td>
        <td class="${row.percent_change === null ? "" : changeClass}">
          ${row.percent_change === null ? "--" : `${fmtNumber(row.percent_change, 2)}%`}
        </td>
        ${fmtCircuitDistance(row, "upper")}
        ${fmtCircuitDistance(row, "lower")}
        <td>${fmtOpeningPair(row)}</td>
        <td>${fmtInt(row.today_opening_volume)}</td>
        <td title="${escapeHtml(samples)}">${fmtNumber(row.opening_volume_average, 0)}</td>
        ${fmtDailyFilter(row)}
        <td><strong>${fmtTurnover(row.candle_turnover)}</strong></td>
        <td>${fmtInt(row.candle_volume)}</td>
        <td>${fmtCandle(row)}</td>
        <td>${fmtNumber(row.previous_close, 2)}</td>
        <td><span class="pill" title="${safeStatus}">${safeStatus}</span></td>
      </tr>
      <tr class="opening-detail-row">
        <td colspan="18">
          <div class="opening-summary">
            <div class="opening-detail-head">
              <span>First 5 candles - Turnover</span>
              <span>${Math.min((row.opening_candles || []).length, 5)}/5 completed</span>
            </div>
            ${fmtOpeningTimeline(row)}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function setActiveView(view) {
  const showBacktest = view === "backtest";
  els.liveView.hidden = showBacktest;
  els.backtestView.hidden = !showBacktest;
  els.liveTab.classList.toggle("active", !showBacktest);
  els.backtestTab.classList.toggle("active", showBacktest);
  els.liveTab.setAttribute("aria-selected", String(!showBacktest));
  els.backtestTab.setAttribute("aria-selected", String(showBacktest));
  window.history.replaceState(null, "", showBacktest ? "#backtest" : "#live");
}

function renderBacktest(result) {
  qs('#openingBacktestResults').hidden = false;
  lastBacktestResult = result;
  const dataIssues = result.stocks.filter(row => row.error || row.data_warning)
    .map(row => `${row.symbol}: ${row.error || row.data_warning}`);
  const partialNotice = dataIssues.length ? `Incomplete backtest: ${dataIssues.length} stock(s) have missing data; totals are partial. ` : '';
  qs('#backtestIssues').hidden = !dataIssues.length;
  qs('#backtestIssueList').innerHTML = dataIssues.map(issue => `<p>${escapeHtml(issue)}</p>`).join('');
  els.backtestTurnoverSummary.textContent = `This run requires ${turnoverDescription(result.volume_filters)} (volume × close).`;
  els.backtestTested.textContent = result.tested_count;
  els.backtestFourX.textContent = result.qualified_count;
  els.backtestCandidates.textContent = result.candidate_count;
  els.backtestErrors.textContent = result.warning_count ? `${result.error_count} + ${result.warning_count} partial` : result.error_count;
  els.backtestMessage.style.color = "";
  const errors = [...dataIssues];
  errors.push(...result.stocks.filter((row) => row.retest_status === "unresolved")
    .map((row) => `${row.symbol}: ${row.retest_reason}`));
  els.backtestMessage.textContent = `Backtest ${result.target_date}: ${result.candidate_count} possible candidate(s), ${result.redwala_count || 0} redwala gira, ${result.retest_count || 0} Retest Break. Filters used: ${filterDescription(result.volume_filters)}`;
  if (errors.length) {
    els.backtestMessage.textContent = partialNotice + els.backtestMessage.textContent + `; ${errors.slice(0, 3).join("; ")}${errors.length > 3 ? '; see Backtest data issues for all failures.' : ''}`;
    els.backtestMessage.style.color = "#c92a2a";
  }
  const setupStocks = result.stocks.filter((row) => row.qualifies_scan === true && matchesSetup(row));
  const visibleStocks = setupStocks.filter(row => matchesDashboardVolume(row, true) && matchesDashboardPrice(row, true));
  if (dashboardVolumeFilter.enabled || dashboardPriceFilter.enabled) visibleStocks.sort(compareLiveStocks);
  qs('#backtestDisplaySummary').textContent = `Showing ${visibleStocks.length} of ${setupStocks.length} matching setups: ${displayFilterDescription(true)}. ${setupStocks.length - visibleStocks.length} hidden. Backtest totals above count all scanner matches.`;
  updateBacktestFiltersStatus();

  if (!visibleStocks.length) {
    const message = setupStocks.length && (dashboardVolumeFilter.enabled || dashboardPriceFilter.enabled)
      ? `No setups match the display filters: ${displayFilterDescription(true)}. Missing volume or close is excluded; rerun older backtests if needed.`
      : dataIssues.length ? 'No confirmed matches for this view. Some stocks could not be fully checked; see Backtest data issues.' : result.stocks.length
      ? `No matching setups on this date: ${turnoverDescription(result.volume_filters)}; Redwala requires a red first candle with open = high, without volume filters`
      : "No stocks loaded";
    els.backtestRows.innerHTML = `<tr><td colspan="10" class="empty">${message}</td></tr>`;
    return;
  }

  els.backtestRows.innerHTML = visibleStocks.map((row, index) => {
    const reason = escapeHtml(row.candidate_reason || row.error || "No candidate setup");
    const candidateBadge = fmtSignalBadge(row, reason);
    const fnoBadge = row.is_fno ? `<span class="fno-badge">F&amp;O</span>` : "";
    const samples = (row.opening_volume_samples || [])
      .map((sample) => `${sample.date}: ${fmtInt(sample.volume)}`)
      .join(" | ");
    const status = escapeHtml(row.error || row.status || "checked");
    return `
      <tr class="${row.possible_candidate ? "candidate-row" : ""}">
        <td>${index + 1}</td>
        <td class="symbol-cell">
          <div class="symbol">
            <strong>${escapeHtml(row.symbol)}</strong>
            <span>${escapeHtml(row.name || row.security_id || "")}</span>
          </div>
          <div class="badge-stack">${candidateBadge}${fnoBadge}</div>
          ${algoRowButton(row, true)}
        </td>
        <td>${fmtBacktestCandle(row.first_candle_start, row.first_candle_color)}${backtestOpeningPrices(row)}</td>
        <td title="First-candle turnover: ${fmtTurnover(row.first_candle_turnover)}">${fmtInt(row.first_candle_volume)}</td>
        <td title="${escapeHtml(samples)}">${fmtNumber(row.opening_volume_average, 0)}</td>
        <td><strong class="multiplier">${row.volume_multiplier === null ? "--" : `${fmtNumber(row.volume_multiplier, 2)}x`}</strong></td>
        ${fmtDailyFilter(row)}
        <td><strong>${fmtTurnover(row.first_candle_turnover)}</strong></td>
        <td><span class="pill" title="${status}">${status}</span></td>
      </tr>
    `;
  }).join("");
}

function backtestOpeningPrices(row) {
  const previous = row.daily_filter?.previous_close;
  const gap = Number.isFinite(previous) && previous > 0 && Number.isFinite(row.first_candle_open)
    ? Math.abs(row.first_candle_open - previous) / previous * 100 : null;
  return `<div class="muted-small">Open ${fmtNumber(row.first_candle_open)} · Close ${fmtNumber(row.first_candle_close)}<br>Prev close ${fmtNumber(previous)} · Open gap ${fmtNumber(gap, 3)}%</div>`;
}

function updateBacktestFiltersStatus() {
  const status = qs('#backtestFiltersStatus');
  if (!lastBacktestResult) { status.hidden = true; return; }
  let changed = true;
  try {
    const selected = readFilterSettings();
    const used = normalizedFilterSettings(lastBacktestResult.volume_filters);
    changed = Object.keys(selected).some(key => selected[key] !== used[key]);
  } catch (_) {}
  status.hidden = !changed;
  status.textContent = changed ? "Scanner filters changed since this backtest. These are previous results; rerun the backtest to apply your selected scanner settings. Display volume and price filters apply immediately." : "";
}

async function runBacktest() {
  if (els.backtestButton.disabled) return;
  if (!els.backtestDate.value) {
    els.backtestMessage.textContent = "Select a trading date";
    return;
  }
  if (els.saveVolumeFilters.disabled) {
    els.backtestMessage.textContent = "Filters are still saving. Run Backtest after the save completes.";
    return;
  }
  setBusy(els.backtestButton, true);
  const controls = [els.dailyVolumeMax, els.minuteVolumeMin, els.firstCandleTurnoverMin,
    els.todayOpenCross, els.monthlyFilter, els.lastTwoDaysFilter, els.possibleOpenPreClose,
    els.possibleOpenPreCloseMax, els.redwalaOpenPreviousClose, els.redwalaOpenGapMax,
    els.redwalaOpenTolerance, els.redwalaOpenToleranceMax, els.pdhlFilter, els.pdhlMax];
  try {
    const settings = readFilterSettings();
    controls.forEach(control => { control.disabled = true; });
    els.backtestMessage.textContent = "Applying selected filters before backtest…";
    if (!await saveFilterSettings(settings)) {
      throw new Error("Backtest not started: filters could not be saved. Check the save error and retry.");
    }
    els.backtestMessage.textContent = `Running ${els.backtestDate.value}...`;
    const result = await api("/api/backtest", {
      method: "POST",
      body: JSON.stringify({ target_date: els.backtestDate.value, scan_type: 'opening', volume_filters: settings }),
    });
    if (settings.possible_open_pre_close && (result.volume_filters?.possible_open_pre_close !== true
      || result.volume_filters?.possible_open_pre_close_max !== settings.possible_open_pre_close_max)) {
      throw new Error("Backtest returned different Open / Previous Close settings. Results were not displayed. Check that the updated server is running and rerun the backtest.");
    }
    renderBacktest(result);
  } catch (error) {
    els.backtestMessage.textContent = error.message;
    els.backtestMessage.style.color = "#c92a2a";
  } finally {
    controls.forEach(control => { control.disabled = false; });
    setBusy(els.backtestButton, false);
  }
}

let configRequest = 0;
let filterWriteRevision = 0;
const editedFilterFields = new Set();
let credentialsRevision = 0;
let loadedCredentials = {client_id: "", has_credentials: false};
let configLoaded = false;

function renderCredentialsStatus() {
  const reusable = loadedCredentials.has_credentials && els.clientId.value.trim() === loadedCredentials.client_id;
  els.accessToken.required = !reusable;
  els.accessToken.placeholder = reusable ? "Saved token — leave blank to keep" : "Enter access token";
  els.credentialsStatus.textContent = reusable
    ? "Credentials saved on this server and reused after refresh. Token hidden; enter a new token only to replace it."
    : "Enter Client ID and access token, then Save. Credentials are kept on this server.";
}
els.clientId.addEventListener("input", renderCredentialsStatus);

async function refreshConfig() {
  const request = ++configRequest;
  const revision = filterWriteRevision;
  const credentialRevision = credentialsRevision;
  const clientBefore = els.clientId.value;
  const symbolsBefore = els.symbolsText.value;
  const config = await api("/api/config");
  if (request !== configRequest) return;
  if (credentialRevision === credentialsRevision) {
    loadedCredentials = {client_id: config.client_id || "", has_credentials: Boolean(config.has_credentials)};
    if (!configLoaded && els.clientId.value === clientBefore) els.clientId.value = loadedCredentials.client_id;
    renderCredentialsStatus();
  }
  if (!configLoaded && els.symbolsText.value === symbolsBefore) els.symbolsText.value = config.symbols_text || "";
  els.cachedCount.textContent = config.cached_volume_count;
  // Only hydrate once. Background actions must never replace the user's draft.
  if (revision === filterWriteRevision && !configLoaded) {
    const s = normalizedFilterSettings(config.volume_filters);
    for (const [id, value] of Object.entries({dailyVolumeMax: s.daily_volume_max,
      minuteVolumeMin: s.minute_volume_min, firstCandleTurnoverMin: s.first_candle_turnover_min / 10000000,
      todayOpenCross: s.today_open_cross, monthlyFilter: s.monthly_filter,
      lastTwoDaysFilter: s.last_two_days_filter, redwalaOpenPreviousClose: s.redwala_open_previous_close,
      redwalaOpenTolerance: s.redwala_open_tolerance, redwalaOpenToleranceMax: s.redwala_open_tolerance_max,
      possibleOpenPreClose: s.possible_open_pre_close, possibleOpenPreCloseMax: s.possible_open_pre_close_max,
      redwalaOpenGapMax: s.redwala_open_gap_max, pdhlFilter: s.pdhl_filter, pdhlMax: s.pdhl_max})) {
      if (!editedFilterFields.has(id) && !editedFilterFields.has('*')) {
        els[id][typeof value === 'boolean' ? 'checked' : 'value'] = value;
      }
    }
  }
  if (revision === filterWriteRevision) {
    els.activeVolumeFilters.textContent = `Saved: ${filterDescription(config.volume_filters)}`;
    savedFilterSettings = normalizedFilterSettings(config.volume_filters);
  }
  if (!configLoaded) {
    els.saveVolumeFilters.disabled = false;
    els.saveVolumeFilters.textContent = "Save & Apply";
  }
  configLoaded = true;
  updateFilterChangesStatus();
}

function normalizedFilterSettings(settings = {}) {
  return {daily_volume_max: 4, minute_volume_min: 4, first_candle_turnover_min: 30000000,
    today_open_cross: false, monthly_filter: false, last_two_days_filter: false,
    redwala_open_previous_close: false, redwala_open_gap_max: 1, pdhl_filter: false, pdhl_max: 4,
    redwala_open_tolerance: false, redwala_open_tolerance_max: 0.5,
    possible_open_pre_close: false, possible_open_pre_close_max: 1,
    ...settings};
}

let savedFilterSettings = null;

function readFilterSettings() {
  const settings = {
    daily_volume_max: Number(els.dailyVolumeMax.value),
    minute_volume_min: Number(els.minuteVolumeMin.value),
    first_candle_turnover_min: Number(els.firstCandleTurnoverMin.value) * 10000000,
  };
  if (Object.values(settings).some(value => !Number.isFinite(value) || value <= 0)) {
    throw new Error("Volume multipliers and turnover must be finite numbers greater than zero.");
  }
  settings.today_open_cross = Boolean(els.todayOpenCross.checked);
  settings.monthly_filter = Boolean(els.monthlyFilter.checked);
  settings.last_two_days_filter = Boolean(els.lastTwoDaysFilter.checked);
  settings.redwala_open_previous_close = Boolean(els.redwalaOpenPreviousClose.checked);
  settings.redwala_open_tolerance = Boolean(els.redwalaOpenTolerance.checked);
  settings.pdhl_filter = Boolean(els.pdhlFilter.checked);
  settings.possible_open_pre_close = Boolean(els.possibleOpenPreClose.checked);
  for (const [key, control] of [["redwala_open_gap_max", els.redwalaOpenGapMax], ["redwala_open_tolerance_max", els.redwalaOpenToleranceMax], ["pdhl_max", els.pdhlMax], ["possible_open_pre_close_max", els.possibleOpenPreCloseMax]]) {
    const value = Number(control.value);
    if (String(control.value).trim() === "" || !Number.isFinite(value) || value < 0) {
      throw new Error("Open-or-close distance, opening tolerance and PDHL percentages must be finite numbers greater than or equal to zero.");
    }
    settings[key] = value;
  }
  return settings;
}

function updateFilterChangesStatus() {
  updateBacktestFiltersStatus();
  let changed = true;
  try {
    const selected = readFilterSettings();
    changed = !savedFilterSettings || Object.keys(selected).some(key => selected[key] !== savedFilterSettings[key]);
  } catch (_) { /* Invalid input is also an unapplied change. */ }
  els.filterChangesStatus.textContent = changed
    ? "Unapplied changes. Run Backtest will save these selections first. Use Save & Apply to update Live. Existing backtest results are unchanged."
    : "Selected filters are saved. Run Backtest to generate results with these settings.";
}

function filterFormChanged(event) {
  editedFilterFields.add(event?.target?.id || '*');
  updateFilterChangesStatus();
}
els.volumeFiltersForm.addEventListener("input", filterFormChanged);
els.volumeFiltersForm.addEventListener("change", filterFormChanged);

let stateRefresh = null;
function refreshState() {
  // At most one poll in flight, even when an action also requests a refresh.
  if (!stateRefresh) {
    stateRefresh = api("/api/state", {}, 8000).then(renderState).finally(() => { stateRefresh = null; });
  }
  return stateRefresh;
}

async function saveFilterSettings(settings) {
  if (els.saveVolumeFilters.disabled) return false;
  ++filterWriteRevision;
  setBusy(els.saveVolumeFilters, true);
  els.saveVolumeFilters.textContent = "Applying…";
  els.saveVolumeFilters.setAttribute("aria-busy", "true");
  setMessage("Saving settings and updating cached results…");
  try {
    const result = await api("/api/volume-filters", {
      method: "POST", body: JSON.stringify(settings),
    }, 10000);
    els.activeVolumeFilters.textContent = `Saved: ${filterDescription(settings)}`;
    savedFilterSettings = { ...settings };
    ++filterWriteRevision; // Ignore reads started before this save completed.
    updateFilterChangesStatus();
    setMessage(result.message || "Filters applied");
    // Refresh results separately. A delayed poll cannot keep the Save button busy,
    // and config reloads must not overwrite edits made while this request ran.
    refreshState().catch(() => {});
    return true;
  } catch (error) {
    setMessage(error.name === "AbortError"
      ? "Save response timed out. Settings may have been saved; reload to check before retrying."
      : error.message, true);
    return false;
  } finally {
    setBusy(els.saveVolumeFilters, false);
    els.saveVolumeFilters.textContent = "Save & Apply";
    els.saveVolumeFilters.setAttribute("aria-busy", "false");
  }
}

els.credentialsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const clientId = els.clientId.value.trim();
  const token = els.accessToken.value;
  ++credentialsRevision;
  runAction(els.credentialsForm.querySelector("button"), async () => {
    const result = await api("/api/credentials", {
      method: "POST", body: JSON.stringify({client_id: clientId, access_token: token}),
    });
    ++credentialsRevision;
    loadedCredentials = {client_id: clientId, has_credentials: true};
    if (els.accessToken.value === token) els.accessToken.value = "";
    renderCredentialsStatus();
    return result;
  });
});

els.volumeFiltersForm.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    saveFilterSettings(readFilterSettings());
  } catch (error) {
    setMessage(error.message, true);
  }
});

els.symbolsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runAction(els.symbolsForm.querySelector("button"), () => api("/api/symbols", {
    method: "POST",
    body: JSON.stringify({ symbols_text: els.symbolsText.value }),
  }));
});

els.cacheButton.addEventListener("click", () => {
  runAction(els.cacheButton, () => api("/api/cache", { method: "POST" }));
});

els.volumeCacheButton.addEventListener("click", () => {
  runAction(els.volumeCacheButton, () => api("/api/cache-volume", { method: "POST" }));
});



els.startButton.addEventListener("click", () => {
  runAction(els.startButton, () => api("/api/start", { method: "POST" }));
});

els.stopButton.addEventListener("click", () => {
  runAction(els.stopButton, () => api("/api/stop", { method: "POST" }));
});

els.repairButton.addEventListener("click", () => {
  runAction(els.repairButton, () => api("/api/repair", { method: "POST" }));
});

els.liveTab.addEventListener("click", () => setActiveView("live"));
els.backtestTab.addEventListener("click", () => setActiveView("backtest"));
els.backtestButton.addEventListener("click", runBacktest);
els.setupFilter.addEventListener("change", () => {
  if (lastLiveState) renderState(lastLiveState);
  if (lastBacktestResult) renderBacktest(lastBacktestResult);
});

window.addEventListener("load", async () => {
  if (window.lucide) window.lucide.createIcons();
  const today = new Date();
  els.backtestDate.max = fmtDateInput(today);
  els.backtestDate.min = fmtDateInput(today, -60);
  els.backtestDate.value = fmtDateInput(today, -1);
  setActiveView(window.location.hash === "#backtest" ? "backtest" : "live");
  try {
    await refreshConfig();
    await refreshState();
  } catch (error) {
    setMessage(error.message, true);
  }
  let configRetryPending = false;
  setInterval(() => {
    if (!configLoaded && !configRetryPending) {
      configRetryPending = true;
      refreshConfig().catch(() => {}).finally(() => { configRetryPending = false; });
    }
    refreshState().catch(() => {});
  }, 2000);
});


const algoFields = {
  capital: 'algoCapital', target_pct: 'algoTarget', stop_pct: 'algoStop',
  trailing_pct: 'algoTrailPct', max_adds: 'algoMaxAdds', max_reversals: 'algoMaxReversals',
  max_loss: 'algoMaxLoss', slippage_bps: 'algoSlippage', fee_per_order: 'algoFee',
};
let algoLoaded = false;
let algoFormEdited = false;
let algoActionBusy = false;
let algoBacktestBusy = false;
let lastAlgoBacktestInputs = null;
let lastAlgoBacktestFilters = null;
function algoBacktestPayload() {
  return {symbol: qs('#algoBacktestSymbol').value.trim().toUpperCase(),
    setup: qs('#algoBacktestSetup').value, target_date: qs('#algoBacktestDate').value,
    start_time: qs('#algoBacktestTime').value, settings: {...readAlgoSettings(), mode: 'paper'}};
}
function updateAlgoBacktestStale() {
  if (!lastAlgoBacktestInputs) return;
  let changed = true;
  try {
    changed = JSON.stringify(algoBacktestPayload()) !== lastAlgoBacktestInputs
      || (lastLiveState?.volume_filters && filterDescription(lastLiveState.volume_filters) !== lastAlgoBacktestFilters);
  } catch (_) { /* Invalid edited inputs also require a new run. */ }
  qs('#algoBacktestStale').hidden = !changed;
  qs('#algoBacktestStale').textContent = changed
    ? 'Settings changed. This result uses the earlier settings; rerun the algo backtest to update P&L.' : '';
}
for (const form of ['#algoSettingsForm', '#algoBacktestForm']) {
  const onEdit = () => {
    if (form === '#algoSettingsForm') algoFormEdited = true;
    updateAlgoBacktestStale();
  };
  qs(form).addEventListener('input', onEdit);
  qs(form).addEventListener('change', onEdit);
}
function readAlgoSettings() {
  const settings = {mode: qs('#algoMode').value, sizing: 'capital', reference: 'original',
    first_direction: qs('#algoFirstDirection').value || 'setup',
    reversal_size: 'initial', square_off: qs('#algoSquareOff').value,
    trailing: Boolean(qs('#algoTrailing').checked), ladder: Boolean(qs('#algoLadder').checked),
    pyramiding: Boolean(qs('#algoPyramid').checked)};
  for (const [key, id] of Object.entries(algoFields)) {
    const raw = qs('#' + id).value;
    settings[key] = Number(raw);
    if (raw === '' || !Number.isFinite(settings[key])) throw new Error('Enter valid algo settings before starting.');
  }
  if (settings.capital <= 0 || settings.target_pct <= 0 || settings.stop_pct <= 0 || settings.max_loss <= 0)
    throw new Error('Capital, target, stop and maximum loss must be greater than zero.');
  return settings;
}
function algoRowButton(row, backtest) {
  const setup = row.possible_candidate ? 'possible' : row.redwala_gira ? 'redwala' : null;
  if (!setup || row.awaiting_confirmation || (!backtest && row.confirmation_status !== 'confirmed')) return '';
  return `<button type="button" class="algo-row-button" data-algo-symbol="${escapeHtml(row.symbol)}" data-algo-setup="${setup}" data-algo-action="${backtest ? 'backtest' : 'start'}">${backtest ? 'Algo Backtest' : 'Start Algo'}</button>`;
}

function algoFirstSide(settings, setup) {
  return settings.first_direction === 'long' ? 'BUY' : settings.first_direction === 'short' ? 'SELL'
    : setup === 'possible' ? 'BUY' : 'SELL';
}
function algoFills(fills) {
  return `<div class="algo-fills"><table><thead><tr><th>Time (IST)</th><th>Buy / Sell</th><th>Shares</th><th>Fill price</th><th>Net shares</th><th>Cumulative gross P&amp;L</th></tr></thead><tbody>${fills.map(f => `<tr><td>${escapeHtml(f.time)}${f.execution === 'candle_close' ? `<br><small>${fmtTime(f.candle_start)} candle close</small>` : ''}</td><td>${f.qty > 0 ? 'BUY' : 'SELL'}</td><td>${Math.abs(f.qty)}</td><td>${fmtNumber(f.price)}</td><td>${f.net_qty}</td><td>${fmtNumber(f.realized)}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderAlgo(data) {
  if (!data) return;
  qs('#algoFeedStatus').textContent = `Market websocket: ${data.market_socket_connected ? 'connected' : 'idle / reconnecting'} · Order updates: ${data.order_socket_connected ? 'connected' : 'idle / reconnecting'}. Session messages show REST fallback or missing data.`;
  const openDetails = new Set(Array.from(qs('#algoSessions').querySelectorAll('details[open]')).map(el => el.dataset.session));
  if (!algoLoaded && !algoFormEdited) {
    const s = data.settings || {};
    for (const [key, id] of Object.entries(algoFields)) if (s[key] != null) qs('#' + id).value = s[key];
    // Every new browser session defaults to paper; switching to live is explicit.
    qs('#algoMode').value = 'paper';
    qs('#algoFirstDirection').value = s.first_direction || 'setup';
    qs('#algoSquareOff').value = s.square_off || '15:15';
    qs('#algoTrailing').checked = Boolean(s.trailing);
    qs('#algoLadder').checked = Boolean(s.ladder);
    qs('#algoPyramid').checked = Boolean(s.pyramiding);
    qs('#algoBacktestDate').value = els.backtestDate.value;
    algoLoaded = true;
  }
  qs('#algoSessions').innerHTML = (data.sessions || []).map(row => {
    const s = row.strategy, c = s.settings, pending = row.pending;
    const side = Math.sign(s.net_qty), reference = c.reference === 'average' ? s.average : s.original;
    const target = side ? reference * (1 + side * c.target_pct / 100) : null;
    return `<article class="algo-session" data-mode="${escapeHtml(row.mode)}">
      <strong>${escapeHtml(row.symbol)} &middot; ${escapeHtml(row.mode.toUpperCase())} &middot; ${escapeHtml(row.status)} &middot; ${escapeHtml(row.session_date)}</strong>
      <p>App quantity ${s.net_qty} &middot; Broker quantity ${row.broker_qty ?? '--'} &middot; Initial quantity ${s.base_qty} &middot; Original entry ${fmtNumber(s.original)} &middot; Average ${fmtNumber(s.average)} &middot; Target ${fmtNumber(target)} &middot; Stop ${fmtNumber(s.stop)} &middot; Adds ${s.adds}/${c.max_adds} &middot; Reversals ${s.reversals}/${c.max_reversals} &middot; P&amp;L &#8377;${fmtNumber(row.pnl ?? s.realized - s.fees)}</p>
      <p>${escapeHtml(row.message || '')}${pending ? ` &middot; Order ${escapeHtml(pending.order_id || pending.correlation)}: ${escapeHtml(pending.state)}, ${pending.filled_qty}/${Math.abs(pending.delta)} filled` : ''}</p>
      ${row.status !== 'done' ? `<button type="button" data-algo-session="${row.id}" data-algo-action="exit">Exit &amp; Stop</button>${row.status === 'paused' ? `<button type="button" data-algo-session="${row.id}" data-algo-action="resume">Reconcile &amp; Resume</button>` : ''}` : ''}
      <details data-session="${row.id}" ${openDetails.has(row.id) ? 'open' : ''}><summary>Fills &amp; session settings</summary><p>First ladder ${s.initial_side > 0 ? 'Long' : 'Short'} &middot; Capital &#8377;${fmtNumber(c.capital)} &middot; TG ${c.target_pct}% &middot; SL ${c.stop_pct}% &middot; TSL ${c.trailing ? c.trailing_pct + '%' : 'off'} &middot; Ladder ${c.ladder ? 'on' : 'off'} &middot; Pyramiding ${c.pyramiding ? 'on' : 'off'} &middot; Square-off ${escapeHtml(c.square_off)} IST</p>${algoFills(s.fills || [])}</details>
    </article>`;
  }).join('') || '<p>No algo sessions. Select a stock from the scanner results.</p>';
}
async function handleAlgoClick(event) {
  const button = event.target.closest('[data-algo-action]');
  if (!button || algoActionBusy) return;
  const action = button.dataset.algoAction;
  try {
    if (action === 'backtest') {
      qs('#algoBacktestSymbol').value = button.dataset.algoSymbol;
      qs('#algoBacktestSetup').value = button.dataset.algoSetup;
      qs('#algoBacktestDate').value = lastBacktestResult?.target_date || els.backtestDate.value;
      qs('#algoPanel').scrollIntoView({behavior: 'smooth'});
      qs('#algoMessage').textContent = 'Stock selected. Review entry time and settings, then Run Stock Algo Backtest.';
      return;
    }
    const settings = action === 'start' ? readAlgoSettings() : null;
    if (settings?.mode === 'live' && !window.confirm(`Place REAL intraday orders for ${button.dataset.algoSymbol}? Initial direction: ${algoFirstSide(settings, button.dataset.algoSetup)}. Capital per entry/add INR ${settings.capital}. Target ${settings.target_pct}%, SL ${settings.stop_pct}%, ladder ${settings.ladder ? 'ON' : 'OFF'}, pyramiding ${settings.pyramiding ? 'ON' : 'OFF'}. Exits require this server and fresh data.`)) return;
    algoActionBusy = true;
    button.disabled = true;
    const url = action === 'start' ? '/api/algo/start' : `/api/algo/${encodeURIComponent(button.dataset.algoSession)}/${action}`;
    const body = action === 'start' ? {symbol: button.dataset.algoSymbol, setup: button.dataset.algoSetup, settings} : {};
    const result = await api(url, {method: 'POST', body: JSON.stringify(body)}, 15000);
    qs('#algoMessage').textContent = result.message;
    await refreshState();
  } catch (error) {
    qs('#algoMessage').textContent = error.name === 'AbortError' ? 'Response timed out. Check algo sessions before retrying; the request may have succeeded.' : error.message;
  } finally {
    algoActionBusy = false;
    button.disabled = false;
  }
}
qs('#stockRows').addEventListener('click', handleAlgoClick);
qs('#backtestRows').addEventListener('click', handleAlgoClick);
qs('#algoSessions').addEventListener('click', handleAlgoClick);
qs('#algoSettingsForm').addEventListener('submit', async event => {
  event.preventDefault();
  const button = qs('#algoSave');
  if (button.disabled) return;
  button.disabled = true;
  try {
    const result = await api('/api/algo/settings', {method: 'POST', body: JSON.stringify(readAlgoSettings())}, 10000);
    qs('#algoMessage').textContent = result.message;
  } catch (error) { qs('#algoMessage').textContent = error.message; }
  finally { button.disabled = false; }
});
qs('#algoMode').addEventListener('change', () => {
  qs('#algoMessage').textContent = qs('#algoMode').value === 'live'
    ? 'LIVE selected. Start Algo will request real Dhan orders for the selected stock.'
    : 'Paper selected. New sessions simulate fills; existing live sessions remain active.';
});
qs('#algoBacktestForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (algoBacktestBusy) return;
  algoBacktestBusy = true;
  qs('#algoBacktestRun').disabled = true;
  lastAlgoBacktestInputs = null;
  qs('#algoBacktestStale').hidden = true;
  qs('#algoBacktestResult').textContent = 'Fetching history and replaying the selected stock...';
  try {
    const inputs = JSON.stringify(algoBacktestPayload());
    const result = await api('/api/algo/backtest', {method: 'POST', body: inputs});
    qs('#algoBacktestResult').innerHTML = `<h3>${escapeHtml(result.symbol)} &middot; ${escapeHtml(result.target_date)} &middot; P&amp;L &#8377;${fmtNumber(result.pnl)}</h3>
      <p>Gross P&amp;L &#8377;${fmtNumber(result.strategy.realized)} &minus; costs &#8377;${fmtNumber(result.strategy.fees)} = net P&amp;L &#8377;${fmtNumber(result.pnl)}. Slippage is included in fill prices.</p>
      <p>First ladder: ${result.strategy.initial_side > 0 ? 'Long' : 'Short'} &middot; Entry time: ${escapeHtml(result.start_time)}</p>
      <p>${escapeHtml(result.model)}${result.truncated ? ' INCOMPLETE SESSION: closed at the last available candle; not a full-day result.' : ''}</p>
      <p>Filters used: ${escapeHtml(filterDescription(result.volume_filters))}</p>
      ${algoFills(result.strategy.fills)}<details><summary>Strategy actions</summary>${result.actions.map(a => `<p>${escapeHtml(a.time)} &middot; ${escapeHtml(a.reason)} &middot; intended net ${a.desired}</p>`).join('')}</details>`;
    lastAlgoBacktestInputs = inputs;
    lastAlgoBacktestFilters = filterDescription(result.volume_filters);
    updateAlgoBacktestStale();
  } catch (error) { qs('#algoBacktestResult').textContent = error.message; }
  finally { algoBacktestBusy = false; qs('#algoBacktestRun').disabled = false; }
});
