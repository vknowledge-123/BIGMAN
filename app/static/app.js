const qs = (selector) => document.querySelector(selector);

const els = {
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
  const colors = [row.first_candle_color, row.second_candle_color];
  if (colors.every((color) => !color)) return `<span class="muted-small">--</span>`;
  return `<div class="opening-pair">${colors.map((color, index) => {
    if (!color) return `<span class="candle-color doji">${index + 1}: waiting</span>`;
    const safeColor = ["green", "red", "doji"].includes(color) ? color : "doji";
    return `<span class="candle-color ${safeColor}">${index + 1}: ${escapeHtml(color)}</span>`;
  }).join("")}</div>`;
}

function fmtOpeningTimeline(row) {
  const candles = (row.opening_candles || []).slice(0, 10);
  const slots = Array(10).fill(null);
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
  const detail = `${daily.previous_date}: ${fmtInt(daily.previous_volume)} / ${fmtNumber(daily.average, 2)}; ${samples}`;
  const exception = daily.price_exception ? ' (price exception)' : '';
  return `<td title="${escapeHtml(detail)}"><strong>${fmtNumber(daily.multiplier, 2)}x</strong></td>
    <td title="${escapeHtml(daily.previous_date + exception)}">${fmtNumber(daily.percent_change, 2)}%</td>`;
}

function fmtSignalBadge(row, reason) {
  const badges = [];
  if (row.possible_candidate) badges.push(`<span class="candidate-badge" title="${reason}">Possible candidate</span>`);
  if (row.redwala_gira) badges.push(`<span class="candidate-badge redwala-badge" title="${reason}">redwala gira</span>`);
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

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || "Request failed");
  }
  return payload;
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

function renderState(state) {
  els.connectionBadge.textContent = state.connected ? "Live Connected" : state.running ? "Connecting" : "Idle";
  els.connectionBadge.className = `badge ${state.connected ? "live" : state.status.toLowerCase().includes("error") ? "error" : "neutral"}`;
  els.updatedAt.textContent = `Updated ${fmtTime(state.updated_at)}`;
  const visibleStocks = state.stocks.filter((row) => row.qualifies_scan === true);
  els.stockCount.textContent = `${visibleStocks.length}/${state.stocks.length}`;
  els.cachedCount.textContent = state.stocks.filter((row) => row.opening_volume_average).length;
  els.unresolved.textContent = state.unresolved_symbols.length ? `Unresolved: ${state.unresolved_symbols.join(", ")}` : "";
  const failedChecks = state.stocks.filter((row) => row.error || /Opening candle check (failed|skipped)/.test(row.candidate_reason || ""));
  els.scanIssues.hidden = failedChecks.length === 0;
  els.scanIssues.textContent = failedChecks.map((row) => `${row.symbol}: ${row.error || row.candidate_reason}`).join("; ");

  const top = visibleStocks[0];
  els.topTurnover.textContent = top ? fmtTurnover(top.candle_turnover) : "--";
  els.topChange.textContent = top && top.percent_change !== null ? `${fmtNumber(top.percent_change, 2)}%` : "--";

  if (!visibleStocks.length) {
    const message = state.stocks.length
      ? "No stocks match both volume checks and candle conditions yet"
      : "No stocks loaded";
    els.rows.innerHTML = `<tr><td colspan="19" class="empty">${message}</td></tr>`;
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
        <td>
          <div class="symbol">
            <strong>${escapeHtml(row.symbol)}</strong>
            <span>${escapeHtml(row.name || row.security_id || "")}</span>
          </div>
        </td>
        <td>${fmtNumber(row.ltp, 2)}</td>
        <td class="${row.percent_change === null ? "" : changeClass}">
          ${row.percent_change === null ? "--" : `${fmtNumber(row.percent_change, 2)}%`}
        </td>
        ${fmtCircuitDistance(row, "upper")}
        ${fmtCircuitDistance(row, "lower")}
        <td>${fmtOpeningPair(row)}</td>
        <td>${fmtInt(row.today_opening_volume)}</td>
        <td title="${escapeHtml(samples)}">${fmtNumber(row.opening_volume_average, 0)}</td>
        <td><strong class="multiplier">${row.volume_multiplier === null ? "--" : `${fmtNumber(row.volume_multiplier, 2)}x`}</strong></td>
        ${fmtDailyFilter(row)}
        <td><strong>${fmtTurnover(row.first_candle_turnover)}</strong></td>
        <td><strong>${fmtTurnover(row.candle_turnover)}</strong></td>
        <td>${fmtInt(row.candle_volume)}</td>
        <td>${fmtCandle(row)}</td>
        <td>${fmtNumber(row.previous_close, 2)}</td>
        <td><div class="badge-stack">${candidateBadge}${fnoBadge}</div></td>
        <td><span class="pill" title="${safeStatus}">${safeStatus}</span></td>
      </tr>
      <tr class="opening-detail-row">
        <td colspan="19">
          <div class="opening-detail-head">
            <span>Opening 10 candles</span>
            <span>${(row.opening_candles || []).length}/10 completed</span>
          </div>
          ${fmtOpeningTimeline(row)}
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
  els.backtestTested.textContent = result.tested_count;
  els.backtestFourX.textContent = result.qualified_count;
  els.backtestCandidates.textContent = result.candidate_count;
  els.backtestErrors.textContent = result.error_count;
  els.backtestMessage.style.color = "";
  const errors = result.stocks.filter((row) => row.error).map((row) => `${row.symbol}: ${row.error}`);
  els.backtestMessage.textContent = `Backtest ${result.target_date}: ${result.candidate_count} possible candidate(s), ${result.redwala_count || 0} redwala gira`;
  if (errors.length) {
    els.backtestMessage.textContent += `; ${errors.join("; ")}`;
    els.backtestMessage.style.color = "#c92a2a";
  }
  const visibleStocks = result.stocks.filter((row) => row.qualifies_scan === true);

  if (!visibleStocks.length) {
    const message = result.stocks.length
      ? "No stocks match both volume checks and candle conditions on this date"
      : "No stocks loaded";
    els.backtestRows.innerHTML = `<tr><td colspan="11" class="empty">${message}</td></tr>`;
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
        <td>
          <div class="symbol">
            <strong>${escapeHtml(row.symbol)}</strong>
            <span>${escapeHtml(row.name || row.security_id || "")}</span>
          </div>
        </td>
        <td>${fmtBacktestCandle(row.first_candle_start, row.first_candle_color)}</td>
        <td>${fmtBacktestCandle(row.second_candle_start, row.second_candle_color)}</td>
        <td>${fmtInt(row.first_candle_volume)}</td>
        <td title="${escapeHtml(samples)}">${fmtNumber(row.opening_volume_average, 0)}</td>
        <td><strong class="multiplier">${row.volume_multiplier === null ? "--" : `${fmtNumber(row.volume_multiplier, 2)}x`}</strong></td>
        ${fmtDailyFilter(row)}
        <td><div class="badge-stack">${candidateBadge}${fnoBadge}</div></td>
        <td><span class="pill" title="${status}">${status}</span></td>
      </tr>
    `;
  }).join("");
}

async function runBacktest() {
  if (!els.backtestDate.value) {
    els.backtestMessage.textContent = "Select a trading date";
    return;
  }
  setBusy(els.backtestButton, true);
  els.backtestMessage.textContent = `Running ${els.backtestDate.value}...`;
  try {
    const result = await api("/api/backtest", {
      method: "POST",
      body: JSON.stringify({ target_date: els.backtestDate.value }),
    });
    renderBacktest(result);
  } catch (error) {
    els.backtestMessage.textContent = error.message;
    els.backtestMessage.style.color = "#c92a2a";
  } finally {
    setBusy(els.backtestButton, false);
  }
}

async function refreshConfig() {
  const config = await api("/api/config");
  els.clientId.value = config.client_id || "";
  if (config.symbols_text) els.symbolsText.value = config.symbols_text;
  els.cachedCount.textContent = config.cached_volume_count;
}

async function refreshState() {
  const state = await api("/api/state");
  renderState(state);
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
    setInterval(refreshState, 2000);
  } catch (error) {
    setMessage(error.message, true);
  }
});
