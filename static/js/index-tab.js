let _idxPollTimer = null;

// ── Path Mappings ─────────────────────────────────────────────────────────────

let _pmMappings = [];

async function pmLoad() {
  const r = await get('/api/settings');
  _pmMappings = (r.path_mappings || []).slice();
  _pmRender();
}

function _pmRender() {
  const el = document.getElementById('pm-list');
  if (!_pmMappings.length) {
    el.innerHTML = '<div class="idx-empty" style="margin-bottom:0;font-size:.82rem">No mappings — indexes use their stored paths.</div>';
    return;
  }
  el.innerHTML = `<table class="pm-table">
    <thead><tr><th>From (stored)</th><th>To (current)</th><th></th></tr></thead>
    <tbody>${_pmMappings.map((m, i) => `
      <tr>
        <td class="pm-cell">${esc(m.from)}</td>
        <td class="pm-cell">${esc(m.to)}</td>
        <td><button class="pm-del-btn" onclick="pmRemove(${i})">✕</button></td>
      </tr>`).join('')}
    </tbody></table>`;
}

function pmAdd() {
  const f = document.getElementById('pm-from').value.trim();
  const t = document.getElementById('pm-to').value.trim();
  if (!f) { alert('Enter a "From" prefix.'); return; }
  _pmMappings.push({ from: f, to: t });
  document.getElementById('pm-from').value = '';
  document.getElementById('pm-to').value   = '';
  _pmRender();
  pmSave();
}

function pmRemove(i) {
  _pmMappings.splice(i, 1);
  _pmRender();
  pmSave();
}

async function pmSave() {
  const r = await post('/api/settings/path_mappings', { mappings: _pmMappings });
  if (!r.ok) { alert('Failed to save mappings: ' + r.msg); }
}

// ── Index list ────────────────────────────────────────────────────────────────

async function idxRefreshList() {
  const r = await get('/api/list_indexes');
  const el = document.getElementById('idx-list');
  if (!r.indexes || !r.indexes.length) {
    el.innerHTML = '<div class="idx-empty">No indexes yet. Build one above.</div>';
    return;
  }
  el.innerHTML = '';
  r.indexes.forEach(ix => {
    const row = document.createElement('div');
    row.className = 'idx-row';
    row.innerHTML = `
      <div class="idx-row-name" title="${esc(ix.folder)}">${esc(ix.name)}</div>
      <div class="idx-row-meta">${(ix.total || 0).toLocaleString()} files</div>
      <div class="idx-row-meta">${(ix.built || '').slice(0, 10)}</div>
      <div class="idx-row-folder" title="${esc(ix.folder)}">${esc(ix.folder)}</div>
      <div class="idx-row-btns">
        <button class="idx-row-btn btn-props">&#128269; Properties</button>
        <button class="idx-row-btn danger btn-del">&#10005; Delete</button>
      </div>`;
    row.querySelector('.btn-props').addEventListener('click', () => idxViewProps(ix.file));
    row.querySelector('.btn-del').addEventListener('click',   () => idxDelete(ix.file));
    el.appendChild(row);
  });
}

async function idxViewProps(file) {
  const r = await get('/api/index_info?file=' + encodeURIComponent(file));
  if (!r.ok) { alert('Could not load index info:\n' + r.msg); return; }
  const rows = [
    ['Name',              r.name   || '—'],
    ['Folder',            r.folder || '—'],
    ['Built',             r.built  || '—'],
    ['Total files',       (r.total   || 0).toLocaleString()],
    ['Photo keys (EXIF)', (r.n_exif  || 0).toLocaleString()],
    ['Video keys',        (r.n_video || 0).toLocaleString()],
    ['Filename keys',     (r.n_fname || 0).toLocaleString()],
    ['Index file size',   (r.size_mb || 0) + ' MB'],
    ['File path',         r.file   || '—'],
  ];
  document.getElementById('idx-props-table').innerHTML =
    rows.map(([k, val]) => `<tr><td>${esc(k)}</td><td>${esc(String(val))}</td></tr>`).join('');
  document.getElementById('idx-props-overlay').classList.add('open');
}

function closeIdxProps() {
  document.getElementById('idx-props-overlay').classList.remove('open');
}

async function idxDelete(file) {
  if (!confirm('Delete this index file?\n\n' + file + '\n\nThis cannot be undone.')) return;
  const r = await post('/api/delete_index', {file});
  if (!r.ok) { alert('Delete failed: ' + r.msg); return; }
  idxRefreshList();
}

async function buildIndex() {
  const folder = v('idx-folder');
  const name   = v('idx-name');
  if (!folder) { alert('Enter the folder path to index.'); return; }
  const r = await post('/api/build_index', {folder, name});
  if (!r.ok) { alert(r.msg); return; }
  document.getElementById('btn-build-index').disabled = true;
  document.getElementById('btn-abort-index').style.display = '';
  document.getElementById('idx-build-progress').style.display = 'block';
  document.getElementById('idx-build-bar').style.width = '0%';
  document.getElementById('idx-build-msg').textContent = 'Starting…';
  _idxPollTimer = setInterval(idxPollProgress, 800);
}

async function abortIndex() {
  if (!confirm('Stop the index build? Progress will be lost.')) return;
  await post('/api/abort_index', {});
  document.getElementById('btn-abort-index').style.display = 'none';
}

async function idxPollProgress() {
  const s = await get('/api/idx_status');
  if (!s) return;
  const pct = s.total > 0 ? Math.round(s.current / s.total * 100) : 0;
  document.getElementById('idx-build-bar').style.width = pct + '%';
  document.getElementById('idx-build-msg').textContent = s.msg || '';
  const countEl = document.getElementById('idx-build-count');
  if (countEl) {
    countEl.textContent = (s.phase === 'building' && s.total > 0)
      ? `${s.current.toLocaleString()} / ${s.total.toLocaleString()} files`
      : '';
  }
  if (s.phase === 'done' || s.phase === 'error') {
    clearInterval(_idxPollTimer);
    _idxPollTimer = null;
    document.getElementById('btn-build-index').disabled = false;
    document.getElementById('btn-abort-index').style.display = 'none';
    if (s.phase === 'done') {
      const s2 = await get('/api/state');
      updateIndexChip(s2.active_index_meta);
    }
    idxRefreshList();
    vLoadIndexList(); // keep Verify tab dropdown in sync
  }
}
