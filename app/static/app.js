const qs = (selector) => document.querySelector(selector);

const els = {
  volumeFiltersForm: qs("#volumeFiltersForm"),
  dailyVolumeMax: qs("#dailyVolumeMax"),
  minuteVolumeMin: qs("#minuteVolumeMin"),
  firstCandleTurnoverMin: qs("#firstCandleTurnoverMin"),
  todayOpenCross: qs("#todayOpenCross"),
  monthlyFilter: qs("#monthlyFilter"),
  lastTwoDaysFilter: qs("#lastTwoDaysFilter"),
  setupFilter: qs("#setupFilter"),
  liveTurnoverSummary: qs("#liveTurnoverSummary"),
  backtestTurnoverSummary: qs("#backtestTurnoverSummary"),
  saveVolumeFilters: qs("#saveVolumeFilters"),
  activeVolumeFilters: qs("#activeVolumeFilters"),
  filterChangesStatus: qs("#filterChangesStatus"),
  credentialsForm: qs("#credentialsForm"),
  symbolsForm: qs("#symbolsForm"),
  clientId: qs("#clientId"),
  accessToken: qs("#accessToken"),
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
  return `Monthly Filter ${settings.monthly_filter ? "ON (open > highest close of prior 20 trading sessions)" : "OFF"}; Last 2 Days Filter ${settings.last_two_days_filter ? "ON (both green: no extra condition; red/doji: open > both prior closes)" : "OFF"}; Redwala uses only turnover plus a red first candle with open = high; volume and opening filters do not apply`;
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

function fmtDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
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
      headers: { "Content-Type": "application/json" },
      ...options,
      ...(controller ? { signal: controller.signal } : {}),
    });
    const payload = await response.json().catch((error) => {
      if (error.name === "AbortError") throw error;
      return {};
    });
    if (!response.ok) {
      throw new Error(payload.detail || payload.message || "Request failed");
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
let lastBacktestResult = null;

function matchesSetup(row) {
  const selected = els.setupFilter.value || "all";
  if (selected === "possible") return row.possible_candidate || row.provisional_setup === "Possible candidate";
  if (selected === "redwala") return row.redwala_gira || row.provisional_setup === "redwala gira";
  if (selected === "retest") return row.retest_break;
  return true;
}

// Stable sort preserves the scanner order within each priority group.
function hasBreakoutBadge(row) {
  if (row.awaiting_confirmation) return false;
  return Boolean((row.possible_candidate && (row.first_candle_high_break || row.previous_day_high_cross))
    || (row.redwala_gira && (row.first_candle_low_break || row.previous_day_low_cross
      || row.previous_day_low_cross_second_candle)));
}

function renderState(state) {
  lastLiveState = state;
  els.liveTurnoverSummary.textContent = `Showing setups with ${turnoverDescription(state.volume_filters)} (volume × close).`;
  els.connectionBadge.textContent = state.connected ? "Live Connected" : state.running ? "Connecting" : "Idle";
  els.connectionBadge.className = `badge ${state.connected ? "live" : state.status.toLowerCase().includes("error") ? "error" : "neutral"}`;
  els.updatedAt.textContent = `Updated ${fmtTime(state.updated_at)}`;
  const visibleStocks = state.stocks.filter((row) => (row.qualifies_scan === true || row.awaiting_confirmation) && matchesSetup(row))
    .sort((a, b) => Number(hasBreakoutBadge(b)) - Number(hasBreakoutBadge(a)));
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
    const message = state.stocks.length
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
  const visibleStocks = result.stocks.filter((row) => row.qualifies_scan === true && matchesSetup(row));

  if (!visibleStocks.length) {
    const message = dataIssues.length ? 'No confirmed matches for this view. Some stocks could not be fully checked; see Backtest data issues.' : result.stocks.length
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
        </td>
        <td>${fmtBacktestCandle(row.first_candle_start, row.first_candle_color)}</td>
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
    els.todayOpenCross, els.monthlyFilter, els.lastTwoDaysFilter];
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
      body: JSON.stringify({ target_date: els.backtestDate.value, scan_type: 'opening' }),
    });
    renderBacktest(result);
  } catch (error) {
    els.backtestMessage.textContent = error.message;
    els.backtestMessage.style.color = "#c92a2a";
  } finally {
    controls.forEach(control => { control.disabled = false; });
    setBusy(els.backtestButton, false);
  }
}

async function refreshConfig() {
  const config = await api("/api/config");
  els.clientId.value = config.client_id || "";
  if (config.symbols_text) els.symbolsText.value = config.symbols_text;
  els.cachedCount.textContent = config.cached_volume_count;
  els.dailyVolumeMax.value = config.volume_filters?.daily_volume_max ?? 4;
  els.minuteVolumeMin.value = config.volume_filters?.minute_volume_min ?? 4;
  els.firstCandleTurnoverMin.value = (config.volume_filters?.first_candle_turnover_min ?? 30000000) / 10000000;
  els.todayOpenCross.checked = config.volume_filters?.today_open_cross ?? false;
  els.monthlyFilter.checked = config.volume_filters?.monthly_filter ?? false;
  els.lastTwoDaysFilter.checked = config.volume_filters?.last_two_days_filter ?? false;
  els.activeVolumeFilters.textContent = `Saved: ${filterDescription(config.volume_filters)}`;
  savedFilterSettings = readFilterSettings();
  updateFilterChangesStatus();
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
  return settings;
}

function updateFilterChangesStatus() {
  let changed = true;
  try {
    const selected = readFilterSettings();
    changed = !savedFilterSettings || Object.keys(selected).some(key => selected[key] !== savedFilterSettings[key]);
  } catch (_) { /* Invalid input is also an unapplied change. */ }
  els.filterChangesStatus.textContent = changed
    ? "Unapplied changes. Run Backtest will save these selections first. Use Save & Apply to update Live. Existing backtest results are unchanged."
    : "Selected filters are saved. Run Backtest to generate results with these settings.";
}

els.volumeFiltersForm.addEventListener("input", updateFilterChangesStatus);
els.volumeFiltersForm.addEventListener("change", updateFilterChangesStatus);

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
  runAction(els.credentialsForm.querySelector("button"), () => api("/api/credentials", {
    method: "POST",
    body: JSON.stringify({
      client_id: els.clientId.value,
      access_token: els.accessToken.value,
    }),
  }));
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
  const earliest = new Date(today);
  earliest.setDate(earliest.getDate() - 60);
  const defaultDate = new Date(today);
  defaultDate.setDate(defaultDate.getDate() - 1);
  els.backtestDate.max = fmtDateInput(today);
  els.backtestDate.min = fmtDateInput(earliest);
  els.backtestDate.value = fmtDateInput(defaultDate);
  setActiveView(window.location.hash === "#backtest" ? "backtest" : "live");
  try {
    await refreshConfig();
    await refreshState();
  } catch (error) {
    setMessage(error.message, true);
  }
  setInterval(() => refreshState().catch(() => {}), 2000);
});
