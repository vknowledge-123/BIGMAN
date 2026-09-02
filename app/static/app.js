const qs = (selector) => document.querySelector(selector);

const els = {
  credentialsForm: qs("#credentialsForm"),
  symbolsForm: qs("#symbolsForm"),
  clientId: qs("#clientId"),
  accessToken: qs("#accessToken"),
  symbolsText: qs("#symbolsText"),
  cacheButton: qs("#cacheButton"),
  startButton: qs("#startButton"),
  stopButton: qs("#stopButton"),
  repairButton: qs("#repairButton"),
  message: qs("#message"),
  unresolved: qs("#unresolved"),
  rows: qs("#stockRows"),
  connectionBadge: qs("#connectionBadge"),
  updatedAt: qs("#updatedAt"),
  stockCount: qs("#stockCount"),
  cachedCount: qs("#cachedCount"),
  topTurnover: qs("#topTurnover"),
  topChange: qs("#topChange"),
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

function setMessage(text, isError = false) {
  els.message.textContent = text;
  els.message.style.color = isError ? "#c92a2a" : "#697386";
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
  els.stockCount.textContent = state.stocks.length;
  els.cachedCount.textContent = state.stocks.filter((row) => row.previous_close).length;
  els.unresolved.textContent = state.unresolved_symbols.length ? `Unresolved: ${state.unresolved_symbols.join(", ")}` : "";

  const top = state.stocks[0];
  els.topTurnover.textContent = top ? fmtTurnover(top.candle_turnover) : "--";
  els.topChange.textContent = top && top.percent_change !== null ? `${fmtNumber(top.percent_change, 2)}%` : "--";

  if (!state.stocks.length) {
    els.rows.innerHTML = `<tr><td colspan="9" class="empty">No stocks loaded</td></tr>`;
    return;
  }

  els.rows.innerHTML = state.stocks.map((row, index) => {
    const changeClass = row.percent_change >= 0 ? "positive" : "negative";
    const statusText = row.error || row.status || "waiting";
    const safeStatus = escapeHtml(statusText);
    return `
      <tr>
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
        <td><strong>${fmtTurnover(row.candle_turnover)}</strong></td>
        <td>${fmtInt(row.candle_volume)}</td>
        <td>${fmtCandle(row)}</td>
        <td>${fmtNumber(row.previous_close, 2)}</td>
        <td><span class="pill" title="${safeStatus}">${safeStatus}</span></td>
      </tr>
    `;
  }).join("");
}

async function refreshConfig() {
  const config = await api("/api/config");
  els.clientId.value = config.client_id || "";
  if (config.symbols_text) els.symbolsText.value = config.symbols_text;
  els.cachedCount.textContent = config.cached_close_count;
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

els.startButton.addEventListener("click", () => {
  runAction(els.startButton, () => api("/api/start", { method: "POST" }));
});

els.stopButton.addEventListener("click", () => {
  runAction(els.stopButton, () => api("/api/stop", { method: "POST" }));
});

els.repairButton.addEventListener("click", () => {
  runAction(els.repairButton, () => api("/api/repair", { method: "POST" }));
});

window.addEventListener("load", async () => {
  if (window.lucide) window.lucide.createIcons();
  try {
    await refreshConfig();
    await refreshState();
    setInterval(refreshState, 2000);
  } catch (error) {
    setMessage(error.message, true);
  }
});
