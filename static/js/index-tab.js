let _idxPollTimer = null;

async function idxRefreshList() {
  const r = await get('/api/list_indexes');
  const el = document.getElementById('idx-list');
  if (!r.indexes || !r.indexes.length) {
    el.innerHTML = '<div class="idx-empty">No indexes yet. Build one above.</div>';
    return;
  }
  el.innerHTML = r.indexes.map(ix => `
    <div class="idx-row">
      <div class="idx-row-name" title="${esc(ix.folder)}">${esc(ix.name)}</div>
      <div class="idx-row-meta">${(ix.total || 0).toLocaleString()} files</div>
      <div class="idx-row-meta">${(ix.built || '').slice(0, 10)}</div>
      <div class="idx-row-folder" title="${esc(ix.folder)}">${esc(ix.folder)}</div>
      <div class="idx-row-btns">
        <button class="idx-row-btn" onclick="idxViewProps(${JSON.stringify(esc(ix.file))})">&#128269; Properties</button>
        <button class="idx-row-btn danger" onclick="idxDelete(${JSON.stringify(esc(ix.file))})">&#10005; Delete</button>
      </div>
    </div>`).join('');
}

async function idxViewProps(escapedFile) {
  const file = escapedFile
    .replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"');
  const r = await get('/api/index_info?file=' + encodeURIComponent(file));
  if (!r.ok) { alert('Could not load index info:\n' + r.msg); return; }
  const rows = [
    ['Name',       r.name || '—'],
    ['Folder',     r.folder || '—'],
    ['Built',      r.built || '—'],
    ['Total files', (r.total || 0).toLocaleString()],
    ['Photo keys (EXIF)', (r.n_exif || 0).toLocaleString()],
    ['Video keys', (r.n_video || 0).toLocaleString()],
    ['Filename keys', (r.n_fname || 0).toLocaleString()],
    ['Index file size', (r.size_mb || 0) + ' MB'],
    ['File path', r.file || '—'],
  ];
  document.getElementById('idx-props-table').innerHTML =
    rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(String(v))}</td></tr>`).join('');
  document.getElementById('idx-props-overlay').classList.add('open');
}

function closeIdxProps() {
  document.getElementById('idx-props-overlay').classList.remove('open');
}

async function idxDelete(escapedFile) {
  const file = escapedFile
    .replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"');
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
  document.getElementById('idx-build-progress').style.display = 'block';
  document.getElementById('idx-build-bar').style.width = '0%';
  document.getElementById('idx-build-msg').textContent = 'Starting…';
  _idxPollTimer = setInterval(idxPollProgress, 800);
}

async function idxPollProgress() {
  const s = await get('/api/idx_status');
  if (!s) return;
  const pct = s.total > 0 ? Math.round(s.current / s.total * 100) : 0;
  document.getElementById('idx-build-bar').style.width = pct + '%';
  document.getElementById('idx-build-msg').textContent = s.msg || '';
  if (s.phase === 'done' || s.phase === 'error') {
    clearInterval(_idxPollTimer);
    _idxPollTimer = null;
    document.getElementById('btn-build-index').disabled = false;
    if (s.phase === 'done') {
      const s2 = await get('/api/state');
      updateIndexChip(s2.active_index_meta);
    }
    idxRefreshList();
  }
}
