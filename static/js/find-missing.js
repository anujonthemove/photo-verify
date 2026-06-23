// ────────────────────────────────────────────────────────────────────────────
// Find Missing tab
// ────────────────────────────────────────────────────────────────────────────
let _fmLoadedIndex  = null;   // {file, name, total, folder}
let _fmScanAbort    = false;
let _fmSourceCount  = 0;

async function fmRefreshIndexSelect() {
  const sel = document.getElementById('fm-index-select');
  const cur = sel.value;
  const r   = await get('/api/list_indexes');
  sel.innerHTML = '<option value="">— select an index —</option>';
  (r.indexes || []).forEach(ix => {
    const opt = document.createElement('option');
    opt.value       = ix.file;
    opt.textContent = ix.name + ' (' + (ix.total || 0).toLocaleString() + ' files' +
                      (ix.built ? ', ' + ix.built.slice(0,10) : '') + ')';
    sel.appendChild(opt);
  });
  if (cur) sel.value = cur;
  // Re-trigger auto-load if a value is already selected
  if (sel.value) await fmLoadIndex();
  if (!_fmSourceCount) fmAddSource();
}

async function fmLoadIndex() {
  const file = document.getElementById('fm-index-select').value;
  if (!file) {
    _fmLoadedIndex = null;
    document.getElementById('fm-index-badge').textContent = '';
    document.getElementById('btn-fm-scan').disabled = true;
    return;
  }
  const r = await post('/api/load_index', {file});
  if (!r.ok) {
    document.getElementById('fm-index-badge').textContent = 'Error: ' + r.msg;
    return;
  }
  _fmLoadedIndex = {file, name: r.name, total: r.total, folder: r.folder};
  document.getElementById('fm-index-badge').textContent =
    '✓ ' + r.name + ' — ' + (r.total || 0).toLocaleString() + ' files indexed';
  document.getElementById('btn-fm-scan').disabled = false;
  updateActiveIndexChip({name: r.name, total: r.total, folder: r.folder});
}

function fmAddSource() {
  _fmSourceCount++;
  const wrap = document.createElement('div');
  wrap.className = 'fm-src-row';
  wrap.dataset.sid = _fmSourceCount;
  wrap.innerHTML = `<input class="fm-src-input" type="text" placeholder="E:\\\\Backups\\\\YourFolder" autocomplete="off">
    <button class="fm-src-del" onclick="this.parentNode.remove()" title="Remove">✕</button>`;
  document.getElementById('fm-sources').appendChild(wrap);
}

async function fmScanAll() {
  if (!_fmLoadedIndex) { alert('Select and load a master index first.'); return; }
  const sources = [...document.querySelectorAll('.fm-src-input')]
    .map(i => i.value.trim()).filter(Boolean);
  if (!sources.length) { alert('Add at least one source folder.'); return; }

  const outDir = document.getElementById('fm-missing-dir').value.trim();
  // Push output dir to backend config before scanning
  if (outDir) await post('/api/configure', {cfg: {missing_dir: outDir}});

  document.getElementById('btn-fm-scan').disabled = true;
  document.getElementById('fm-results').innerHTML = '';
  _fmScanAbort = false;

  for (const src of sources) {
    if (_fmScanAbort) break;
    await fmScanSource(src, outDir);
  }
  document.getElementById('btn-fm-scan').disabled = false;
}

async function fmScanSource(source, outDir) {
  const resultsEl = document.getElementById('fm-results');
  const blockId   = 'fm-block-' + source.replace(/[^a-z0-9]/gi, '_');

  resultsEl.insertAdjacentHTML('beforeend', `
    <div class="fm-result-block" id="${blockId}">
      <div class="fm-result-header">
        <div class="fm-result-title">${esc(source)}</div>
      </div>
      <div class="fm-progress-wrap"><div class="fm-progress-bar" id="${blockId}-bar"></div></div>
      <div class="fm-scan-msg" id="${blockId}-msg">Starting session…</div>
      <div class="fm-stats" style="display:none" id="${blockId}-stats"></div>
      <div class="fm-result-actions" style="display:none" id="${blockId}-actions"></div>
    </div>`);

  const setMsg = m => { const el = document.getElementById(blockId + '-msg'); if(el) el.textContent = m; };
  const setBar = p => { const el = document.getElementById(blockId + '-bar'); if(el) el.style.width = p + '%'; };

  // Create session (also loads index + scans source into _state['src_photos'])
  const sr = await post('/api/new_session', {index_file: _fmLoadedIndex.file, source});
  if (!sr.ok) { setMsg('Error: ' + sr.msg); return; }

  const nSrc = sr.n_src;
  setMsg(`Scanning ${nSrc.toLocaleString()} files…`);

  // Chunked scan — CHUNK size balances UI responsiveness vs round-trips
  const CHUNK = 200;
  let offset  = 0;
  let found = 0, missing = 0, review = 0;
  const missingIndices = [];  // collect indices of missing files for bulk save

  while (offset < nSrc && !_fmScanAbort) {
    const r = await post('/api/batch_match', {start: offset, count: CHUNK});
    if (!r || !r.results) break;

    for (const res of r.results) {
      if (res.status === 'found')        found++;
      else if (res.status === 'missing') { missing++; missingIndices.push(res.i); }
      else                               review++;
    }

    offset += r.results.length;
    const pct = nSrc > 0 ? Math.round(offset / nSrc * 100) : 0;
    setBar(pct);
    setMsg(`${offset.toLocaleString()} / ${nSrc.toLocaleString()} checked…`);

    const statsEl = document.getElementById(blockId + '-stats');
    if (statsEl) {
      statsEl.style.display = 'flex';
      statsEl.innerHTML =
        `<span class="fm-stat-found">Found: ${found.toLocaleString()}</span>` +
        `<span class="fm-stat-missing">Missing: ${missing.toLocaleString()}</span>` +
        `<span class="fm-stat-unchecked">Remaining: ${(nSrc - offset).toLocaleString()}</span>`;
    }

    if (r.results.length < CHUNK) break;
  }

  setBar(100);
  setMsg('Scan complete.');
  _save_session_state();

  const actEl = document.getElementById(blockId + '-actions');
  if (actEl && missing > 0) {
    actEl.style.display = 'flex';
    // Store indices on the button so they survive across multiple source scans
    const btn = document.createElement('button');
    btn.className = 'fm-btn-sm danger';
    btn.textContent = 'Save All Missing (' + missing.toLocaleString() + ')';
    btn._missingIndices = missingIndices;
    btn._outDir = outDir;
    btn.onclick = () => fmSaveAllMissing(btn._missingIndices, btn._outDir);
    actEl.appendChild(btn);
  }
}

async function _save_session_state() {
  // Persist current session progress to disk
  await post('/api/save_progress_bulk', {idx_map: {}, last_idx: 0});
}

async function fmSaveAllMissing(indices, outDir) {
  if (!indices || !indices.length) { alert('No missing files to save.'); return; }
  const r = await post('/api/bulk_action', {indices, type: 'missing'});
  if (r && r.saved !== undefined) {
    alert('Saved ' + r.saved + ' files to:\n' + (r.out_dir || outDir || 'output folder'));
  } else {
    alert(r && r.msg ? r.msg : 'Error saving files.');
  }
}
