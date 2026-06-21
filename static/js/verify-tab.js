// ── State ───────────────────────────────────────────────────────
const V = {
  photos:    [],     // [{i, name, path}] full list
  progress:  {},     // path -> 'found'|'missing'|'review'
  matchCache:{},     // globalIndex -> match obj | null
  current:   -1,     // currently displayed global index
  filter:    'all',  // 'all'|'found'|'missing'|'review'
  filtered:  [],     // global indices passing current filter
  scanning:  false,
  abort:     false,
};

const PL_ROW_H = 54; // px — must match CSS .pl-item height

// ── Video detection ─────────────────────────────────────────────
const VIDEO_EXTS = new Set(['mp4','mov','3gp','mkv','avi','m4v','wmv','flv','webm']);
function isVideo(path) {
  return VIDEO_EXTS.has((path.split('.').pop() || '').toLowerCase());
}

// ── Tab lifecycle ───────────────────────────────────────────────
let _vInited = false;
async function vOnTabActivate() {
  await vLoadIndexList();
  await vLoadSessionList();
  if (!_vInited) {
    _vInited = true;
    // Restore any index/source already loaded in the server
    const s = await get('/api/state');
    if (s.active_index) {
      const sel = document.getElementById('v-index-select');
      // Try to match; if not in list (index was deleted) leave blank
      if ([...sel.options].some(o => o.value === s.active_index)) {
        sel.value = s.active_index;
      }
      updateIndexChip(s.active_index_meta);
    }
    if (s.cfg && s.cfg.src) {
      document.getElementById('v-src-input').value = s.cfg.src;
    }
    if (s.src_count > 0) {
      await _vLoadAllPhotos();
      vUpdateFilter();
      vUpdateStats();
    }
  }
}

// ── Index selection ─────────────────────────────────────────────
async function vLoadIndexList() {
  const r   = await get('/api/list_indexes');
  const sel = document.getElementById('v-index-select');
  const prev = sel.value;
  sel.innerHTML = '<option value="">— select an index —</option>';
  (r.indexes || []).forEach(ix => {
    const opt = document.createElement('option');
    opt.value = ix.file;
    opt.textContent = ix.name + '  (' + (ix.total || 0).toLocaleString() + ' files)';
    sel.appendChild(opt);
  });
  if (prev && [...sel.options].some(o => o.value === prev)) sel.value = prev;
}

async function vSelectIndex() {
  const file = document.getElementById('v-index-select').value;
  if (!file) return;
  const r = await post('/api/load_index', {file});
  if (!r.ok) { alert(r.msg); return; }
  updateIndexChip({name: r.name, total: r.total, folder: r.folder});
}

// ── Source loading ──────────────────────────────────────────────
async function vLoadSource() {
  const idxFile = document.getElementById('v-index-select').value;
  const src     = v('v-src-input');
  if (!idxFile) { alert('Select a master index first.'); return; }
  if (!src)     { alert('Enter the source folder path.'); return; }

  const r = await post('/api/new_session', {index_file: idxFile, source: src});
  if (!r.ok) { alert(r.msg); return; }

  V.photos = []; V.progress = {}; V.matchCache = {}; V.current = -1;
  await _vLoadAllPhotos();
  vUpdateFilter();
  vUpdateStats();
  document.getElementById('btn-v-scan').disabled = V.photos.length === 0;
}

async function _vLoadAllPhotos() {
  V.photos = [];
  let page = 0;
  while (true) {
    const r = await get('/api/list?p=' + page);
    if (!r.items) break;
    V.photos.push(...r.items);
    if (page >= r.pages - 1) break;
    page++;
  }
  document.getElementById('v-sidebar-count').textContent =
    V.photos.length.toLocaleString() + ' files';
}

// ── Filtering ───────────────────────────────────────────────────
function vSetFilter(f) {
  V.filter = f;
  document.querySelectorAll('#v-filters .fbtn').forEach(b =>
    b.classList.toggle('on', b.dataset.f === f));
  vUpdateFilter();
}

function vUpdateFilter() {
  if (V.filter === 'all') {
    V.filtered = V.photos.map((_, i) => i);
  } else {
    V.filtered = [];
    V.photos.forEach((p, i) => {
      if (V.progress[p.path] === V.filter) V.filtered.push(i);
    });
  }
  document.getElementById('v-sidebar-count').textContent =
    V.filtered.length.toLocaleString() +
    (V.filter === 'all' ? ' files' : ' of ' + V.photos.length.toLocaleString());
  vRenderSidebar();
  _vUpdateNavButtons();
}

// ── Virtual scroll sidebar ──────────────────────────────────────
function vRenderSidebar() {
  const list  = document.getElementById('v-list');
  const inner = document.getElementById('v-list-inner');
  const total = V.filtered.length;
  inner.style.height = (total * PL_ROW_H) + 'px';

  const scrollTop = list.scrollTop;
  const viewH     = list.clientHeight || 600;
  const first = Math.max(0, Math.floor(scrollTop / PL_ROW_H) - 3);
  const last  = Math.min(total - 1, Math.ceil((scrollTop + viewH) / PL_ROW_H) + 3);

  // Remove rows outside visible range, keep ones inside
  const existing = {};
  inner.querySelectorAll('.pl-item').forEach(el => {
    const fi = +el.dataset.fi;
    if (fi < first || fi > last) { el.remove(); }
    else { existing[fi] = el; }
  });

  for (let fi = first; fi <= last; fi++) {
    if (existing[fi]) {
      // Update active class in place
      const gi = V.filtered[fi];
      existing[fi].classList.toggle('current', gi === V.current);
      continue;
    }
    const gi     = V.filtered[fi];
    if (gi === undefined) continue;
    const photo  = V.photos[gi];
    if (!photo) continue;
    const status = V.progress[photo.path] || 'unknown';
    const active = gi === V.current;

    const div = document.createElement('div');
    div.className = 'pl-item' + (active ? ' current' : '');
    div.dataset.fi = fi;
    div.style.top  = (fi * PL_ROW_H) + 'px';
    div.title = photo.path;

    const thumb = document.createElement('img');
    thumb.className = 'pl-thumb';
    thumb.src = '/thumb/src?i=' + gi;
    thumb.alt = '';
    thumb.onerror = () => { thumb.style.visibility = 'hidden'; };

    const dot  = document.createElement('div');
    dot.className = 'pl-dot dot-' + status;

    const name = document.createElement('div');
    name.className = 'pl-name';
    name.textContent = photo.name;

    div.appendChild(thumb);
    div.appendChild(dot);
    div.appendChild(name);
    div.addEventListener('click', () => vShowPhoto(gi));
    inner.appendChild(div);
  }
}

function vScrollSidebarTo(fi) {
  const list = document.getElementById('v-list');
  const top  = fi * PL_ROW_H;
  if (top < list.scrollTop) {
    list.scrollTop = top - 20;
  } else if (top + PL_ROW_H > list.scrollTop + list.clientHeight) {
    list.scrollTop = top + PL_ROW_H - list.clientHeight + 20;
  }
}

// ── Show a photo ────────────────────────────────────────────────
async function vShowPhoto(gi) {
  V.current = gi;
  const photo = V.photos[gi];
  if (!photo) return;

  vRenderSidebar();
  const fi = V.filtered.indexOf(gi);
  if (fi >= 0) vScrollSidebarTo(fi);
  _vUpdateNavButtons();

  // Load EXIF info for src meta line
  const info = await get('/api/photo?i=' + gi);
  document.getElementById('v-src-meta').textContent =
    photo.name + ' · ' + fmtSize(info.size || 0) + ' · ' + (info.exif_dt || '—');

  // Render source
  _vShowSrc(gi, photo.path);

  // Enable action buttons
  document.getElementById('btn-v-missing').disabled = false;
  document.getElementById('btn-v-review').disabled  = false;

  // Match
  if (V.matchCache.hasOwnProperty(gi)) {
    _vApplyMatch(gi, V.matchCache[gi]);
  } else {
    _vSetDestPlaceholder('⏳', 'Checking…');
    document.getElementById('v-match-chip').className = 'chip chip-muted';
    document.getElementById('v-match-chip').textContent = '—';
    const r = await get('/api/match?i=' + gi);
    V.matchCache[gi] = r.match || null;
    if (r.match) {
      V.progress[photo.path] = 'found';
    } else {
      V.progress[photo.path] = 'missing';
    }
    _vApplyMatch(gi, r.match || null);
    vUpdateStats();
    vRenderSidebar();
  }
}

function _vShowSrc(gi, path) {
  const img = document.getElementById('v-src-img');
  const vid = document.getElementById('v-src-vid');
  const ph  = document.getElementById('v-src-ph');
  if (isVideo(path)) {
    vid.src = '/api/media?path=' + encodeURIComponent(path);
    img.classList.remove('show'); vid.classList.add('show'); ph.style.display = 'none';
  } else {
    img.src = '/thumb/src?i=' + gi;
    img.onclick = () => window.open('/api/media?path=' + encodeURIComponent(path));
    img.classList.add('show'); vid.classList.remove('show'); ph.style.display = 'none';
  }
}

function _vApplyMatch(gi, match) {
  const chip    = document.getElementById('v-match-chip');
  const info    = document.getElementById('v-match-info');
  const deepBtn = document.getElementById('btn-v-deep');
  const photo   = V.photos[gi];
  if (!photo) return;
  const status  = V.progress[photo.path] || 'unknown';

  if (match) {
    chip.textContent = 'FOUND';
    chip.className   = 'chip chip-ok';
    info.textContent = 'via ' + (match.method || '');
    deepBtn.style.display = 'none';
    _vShowDest(match.path, match.method);
    document.getElementById('v-dest-meta').textContent =
      basename(match.path) + '  ·  via ' + match.method + (match.n > 1 ? '  (' + match.n + ' copies)' : '');
  } else {
    chip.textContent = 'MISSING';
    chip.className   = 'chip chip-red';
    info.textContent = '';
    // Deep search only for photos (videos can't be hashed easily)
    deepBtn.style.display = (!isVideo(photo.path)) ? '' : 'none';
    _vSetDestPlaceholder('✗', 'Not found in index');
    document.getElementById('v-dest-meta').textContent = 'No match found';
  }

  // update filter count label
  _vUpdateNavButtons();
}

function _vShowDest(path, method) {
  const img = document.getElementById('v-dest-img');
  const vid = document.getElementById('v-dest-vid');
  const ph  = document.getElementById('v-dest-ph');
  if (!path) { _vSetDestPlaceholder('?', 'Match found but path unknown'); return; }
  if (isVideo(path)) {
    vid.src = '/api/media?path=' + encodeURIComponent(path);
    img.classList.remove('show'); vid.classList.add('show'); ph.style.display = 'none';
  } else {
    img.src = '/thumb/dest?p=' + encodeURIComponent(path);
    img.onclick = () => window.open('/api/media?path=' + encodeURIComponent(path));
    img.classList.add('show'); vid.classList.remove('show'); ph.style.display = 'none';
  }
}

function _vSetDestPlaceholder(icon, msg) {
  const img = document.getElementById('v-dest-img');
  const vid = document.getElementById('v-dest-vid');
  const ph  = document.getElementById('v-dest-ph');
  img.classList.remove('show'); vid.classList.remove('show');
  ph.style.display = '';
  ph.innerHTML = '<div class="icon">' + icon + '</div>' + esc(msg);
}

// ── Navigation ──────────────────────────────────────────────────
function vNavigate(dir) {
  const fi   = V.filtered.indexOf(V.current);
  const next = fi + dir;
  if (next < 0 || next >= V.filtered.length) return;
  vShowPhoto(V.filtered[next]);
}

function _vUpdateNavButtons() {
  const fi = V.filtered.indexOf(V.current);
  document.getElementById('btn-v-prev').disabled = fi <= 0;
  document.getElementById('btn-v-next').disabled = fi < 0 || fi >= V.filtered.length - 1;
  const label = fi >= 0
    ? (fi + 1) + ' / ' + V.filtered.length
    : '— / ' + V.filtered.length;
  document.getElementById('v-nav-counter').textContent = label;
}

// ── Deep search ─────────────────────────────────────────────────
async function vDoDeep() {
  if (V.current < 0) return;
  const btn = document.getElementById('btn-v-deep');
  btn.textContent = '⏳ Searching…'; btn.disabled = true;
  const r = await get('/api/deep_match?i=' + V.current);
  btn.textContent = '🔍 Hash Search'; btn.disabled = false;
  const photo = V.photos[V.current];
  if (r.match) {
    V.matchCache[V.current] = r.match;
    V.progress[photo.path]  = 'found';
    _vApplyMatch(V.current, r.match);
    vUpdateStats();
    vRenderSidebar();
  } else {
    alert('No hash match found — this file is truly missing from the index.');
  }
}

// ── Move actions ────────────────────────────────────────────────
async function vDoMove(type) {
  if (V.current < 0) return;
  const r = await post('/api/move', {i: V.current, type});
  if (!r.ok) { alert(r.result || r.msg || 'Move failed'); return; }
  const photo = V.photos[V.current];
  V.progress[photo.path] = type;
  vUpdateFilter();
  vUpdateStats();
}

async function vSaveAllMissing() {
  const missingDir = v('v-missing-dir');
  if (missingDir) await post('/api/configure', {cfg: {missing_dir: missingDir}});

  const indices = V.photos
    .map((p, i) => ({i, s: V.progress[p.path]}))
    .filter(x => x.s === 'missing')
    .map(x => x.i);

  if (!indices.length) { alert('No missing files to save. Run Scan All first.'); return; }

  const r = await post('/api/bulk_action', {indices, type: 'missing'});
  if (r.ok) {
    alert('Saved ' + r.saved + ' file(s) to:\n' + (r.out_folder || 'output folder'));
  } else {
    alert('Error: ' + (r.msg || 'unknown'));
  }
}

// ── Stats ───────────────────────────────────────────────────────
function vUpdateStats() {
  let found = 0, missing = 0, review = 0;
  V.photos.forEach(p => {
    const s = V.progress[p.path];
    if (s === 'found')   found++;
    else if (s === 'missing') missing++;
    else if (s === 'review')  review++;
  });
  const total   = V.photos.length;
  const checked = found + missing + review;
  document.getElementById('v-st-total').textContent   = total.toLocaleString();
  document.getElementById('v-st-checked').textContent = checked.toLocaleString();
  document.getElementById('v-st-found').textContent   = found.toLocaleString();
  document.getElementById('v-st-missing').textContent = missing.toLocaleString();
  document.getElementById('v-st-review').textContent  = review.toLocaleString();
  document.getElementById('btn-v-save-missing').disabled = (missing === 0);
  document.getElementById('btn-v-scan').disabled =
    (total === 0 || V.scanning);
}

// ── Scan all sources ────────────────────────────────────────────
async function vScanAll() {
  if (!V.photos.length) { alert('Load a source folder first.'); return; }
  V.abort    = false;
  V.scanning = true;
  document.getElementById('btn-v-scan').disabled    = true;
  document.getElementById('btn-v-abort').style.display = '';
  document.getElementById('v-scan-progress').style.display = 'flex';

  const CHUNK = 200;
  const n     = V.photos.length;
  let offset  = 0;

  while (offset < n && !V.abort) {
    const r = await post('/api/batch_match', {start: offset, count: CHUNK});
    if (!r.ok) break;
    for (const res of r.results) {
      V.progress[res.path] = res.status;
      if (res.status === 'found' && !V.matchCache.hasOwnProperty(res.i)) {
        // Store a minimal placeholder so the per-photo view skips the API call
        V.matchCache[res.i] = {method: res.method || '?', path: '', n: 0};
      }
    }
    offset += r.results.length;
    const pct = Math.round(offset / n * 100);
    document.getElementById('v-scan-bar').style.width = pct + '%';
    document.getElementById('v-scan-msg').textContent =
      offset.toLocaleString() + ' / ' + n.toLocaleString() + ' files';
    if (offset % 600 === 0 || offset >= n) {
      vUpdateStats();
      vUpdateFilter();
    }
    if (r.results.length < CHUNK) break;
  }

  V.scanning = false;
  document.getElementById('btn-v-abort').style.display = 'none';
  document.getElementById('v-scan-progress').style.display = 'none';
  vUpdateStats();
  vUpdateFilter();
}

function vAbortScan() {
  V.abort = true;
  document.getElementById('btn-v-abort').style.display = 'none';
}

// ── Session management ──────────────────────────────────────────
async function vLoadSessionList() {
  const r   = await get('/api/list_sessions');
  const sel = document.getElementById('v-session-select');
  sel.innerHTML = '<option value="">— pick session —</option>';
  (r.sessions || []).forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.file;
    const src   = basename(s.source || '');
    const stats = s.stats ? (s.stats.found||0) + '✓ ' + (s.stats.missing||0) + '✗' : '';
    opt.textContent = (s.started || '').slice(0, 10) + '  ·  ' + src + '  ·  ' + stats;
    sel.appendChild(opt);
  });
}

async function vResumeSession() {
  const file = document.getElementById('v-session-select').value;
  if (!file) { alert('Select a session to resume.'); return; }

  const r = await post('/api/load_session', {file});
  if (!r.ok) { alert(r.msg); return; }

  V.photos = []; V.progress = {}; V.matchCache = {}; V.current = -1;

  // Restore index dropdown
  await vLoadIndexList();
  const s = await get('/api/state');
  if (s.active_index) {
    const sel = document.getElementById('v-index-select');
    if ([...sel.options].some(o => o.value === s.active_index)) {
      sel.value = s.active_index;
    }
    updateIndexChip(s.active_index_meta);
  }
  if (r.cfg && r.cfg.src) {
    document.getElementById('v-src-input').value = r.cfg.src;
  }

  // Load photo list
  await _vLoadAllPhotos();

  // Replay cached progress via batch_match (force=false uses server-side cache)
  await vScanAll();

  // Jump to last viewed position
  const last = r.last_idx || 0;
  if (last > 0 && last < V.photos.length) {
    vShowPhoto(last);
  }
}
