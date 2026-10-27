(() => {
  const get = id => document.getElementById(id);
  let source = null, revision = 0, fileRead = 0, timer, preview = null, applying = false;
  const status = text => { get('preopenStatus').textContent = text; };
  const number = (id, optional = false) => {
    const raw = get(id).value.trim();
    if (optional && !raw) return null;
    if (!raw || !Number.isFinite(Number(raw))) throw new Error('Enter valid CSV filter numbers. Optional maximums and Top N may be blank.');
    return Number(raw);
  };
  const fields = [['preopenMinTurnover', 'min_turnover'], ['preopenMaxTurnover', 'max_turnover'],
    ['preopenMinChange', 'min_change'], ['preopenMaxChange', 'max_change'], ['preopenTopN', 'top_n']];
  function settings() {
    const result = {universe: get('preopenFno').checked ? 'fno' : 'cash', direction: get('preopenDirection').value};
    for (const [id, key] of fields) result[key] = number(id, ['max_turnover', 'max_change', 'top_n'].includes(key));
    if (result.top_n !== null && (!Number.isInteger(result.top_n) || result.top_n < 1)) throw new Error('Top N must be a positive whole number or blank for all.');
    return result;
  }
  function invalidate() {
    ++revision;
    preview = null;
    get('preopenApply').disabled = true;
    get('preopenTable').hidden = true;
    clearTimeout(timer);
  }
  function show(result) {
    preview = result;
    get('preopenRows').innerHTML = result.rows.map((row, i) => `<tr><td>${i + 1}</td><td>${escapeHtml(row.symbol)}</td><td>${fmtNumber(row.price)}</td><td>${fmtNumber(row.change_percent)}</td><td>${fmtNumber(row.turnover_crore)}</td></tr>`).join('');
    get('preopenTable').hidden = !result.selected_count;
    get('preopenApply').disabled = !result.selected_count || applying;
    get('preopenApply').textContent = `Use ${result.selected_count} ${result.selected_count === 1 ? 'stock' : 'stocks'} in scanner`;
    status(`${result.filename}: ${result.selected_count} selected from ${result.matched_count} matches (${result.settings.universe === 'fno' ? 'F&O' : 'Cash / non-F&O'}). ${result.total_rows} rows; ${result.invalid_rows} missing or invalid rows skipped; ${result.duplicate_rows} duplicates skipped. Uses the app's ${result.fno_list_count}-symbol F&O list from your scripts. Preview only until you use these stocks.`);
  }
  async function runPreview() {
    clearTimeout(timer);
    if (!source || applying) return;
    const current = ++revision;
    get('preopenApply').disabled = true;
    preview = null;
    get('preopenTable').hidden = true;
    try {
      const payload = {...source, settings: settings()};
      status('Filtering CSV…');
      const result = await api('/api/preopen/preview', {method: 'POST', body: JSON.stringify(payload)});
      if (current === revision) show(result);
    } catch (error) {
      if (current === revision) status(error.message);
    }
  }
  get('preopenForm').addEventListener('submit', event => {
    event.preventDefault();
    if (!source) status('Choose an NSE pre-open CSV first.');
    else runPreview();
  });
  get('preopenForm').addEventListener('input', event => {
    if (event.target.id === 'preopenFile' || applying) return;
    invalidate();
    if (source) timer = setTimeout(runPreview, 300);
  });
  get('preopenFile').addEventListener('change', async () => {
    const sequence = ++fileRead;
    invalidate();
    source = null;
    get('preopenSource').textContent = 'No CSV loaded.';
    const file = get('preopenFile').files[0];
    if (!file) return status('Choose an NSE pre-open CSV first.');
    try {
      if (!file.name.toLowerCase().endsWith('.csv') || file.size > 2000000) throw new Error('Choose a CSV file no larger than 2 MB.');
      status('Reading CSV…');
      const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      if (sequence !== fileRead) return;
      source = {csv_text: text, filename: file.name};
      get('preopenSource').textContent = `Loaded CSV: ${file.name}`;
      await runPreview();
    } catch (error) {
      if (sequence === fileRead) status(`Could not read CSV: ${error.message}`);
    }
  });
  get('preopenApply').addEventListener('click', async () => {
    if (!source || !preview || applying) return;
    const payload = {...source, settings: preview.settings};
    applying = true;
    invalidate();
    const controls = [...get('preopenForm').querySelectorAll('input, select, button')];
    controls.forEach(control => { control.disabled = true; });
    status('Loading filtered stocks into the scanner…');
    try {
      const result = await api('/api/preopen/apply', {method: 'POST', body: JSON.stringify(payload)}, 120000);
      els.symbolsText.value = result.symbols.join('\n');
      show(result);
      status(result.message + (result.unresolved_symbols.length ? ` Unresolved: ${result.unresolved_symbols.join(', ')}` : ''));
      await refreshState();
    } catch (error) {
      status(error.name === 'AbortError' ? 'Loading timed out. Check the Stocks list before retrying; the server may still be applying it.' : error.message);
    } finally {
      applying = false;
      controls.forEach(control => { control.disabled = false; });
      get('preopenApply').disabled = !preview?.selected_count;
    }
  });
  window.addEventListener('load', async () => {
    const initial = revision;
    try {
      const {saved} = await api('/api/preopen');
      if (!saved || revision !== initial) return;
      source = {csv_text: saved.csv_text, filename: saved.filename};
      get('preopenSource').textContent = `Saved CSV: ${saved.filename}`;
      const s = saved.settings;
      get('preopenCash').checked = s.universe === 'cash';
      get('preopenFno').checked = s.universe === 'fno';
      get('preopenDirection').value = s.direction;
      for (const [id, key] of fields) get(id).value = s[key] ?? '';
      await runPreview();
    } catch (error) {
      if (revision === initial) status(`Could not load the saved CSV: ${error.message}. You can upload it again.`);
    }
  });
})();
