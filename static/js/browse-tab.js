/* browse-tab.js — Live Photo Browse tab */

let _brItems  = [];   // [{i, type, name, path, video_path}, ...]
let _brTotal  = 0;
let _brCur    = -1;   // currently displayed index
let _brLiveTimer = null;

// ── Virtual scroll constants (match verify-tab pattern) ──────────────────────
const BR_ITEM_H = 56;   // px per sidebar row

// ── Load ─────────────────────────────────────────────────────────────────────

async function brLoad() {
  const folder = document.getElementById('br-folder').value.trim();
  if (!folder) { alert('Enter a folder path.'); return; }

  document.getElementById('btn-br-load').disabled = true;
  document.getElementById('br-count-chip').textContent = 'Scanning…';
  _brItems = [];
  _brTotal = 0;
  _brCur   = -1;
  _brResetViewer();
  document.getElementById('br-list-inner').style.height = '0';
  document.getElementById('br-list-inner').innerHTML    = '';

  const res = await post('/api/browse/load', { folder });
  document.getElementById('btn-br-load').disabled = false;

  if (!res.ok) {
    document.getElementById('br-count-chip').textContent = '⚠ ' + (res.msg || 'Error');
    return;
  }

  const { total, live, static: stat, video: vid } = res;
  _brTotal = total;
  document.getElementById('br-count-chip').textContent =
    `${total.toLocaleString()} item${total !== 1 ? 's' : ''}` +
    (live  ? `  ·  ${live.toLocaleString()} live`   : '') +
    (stat  ? `  ·  ${stat.toLocaleString()} static` : '') +
    (vid   ? `  ·  ${vid.toLocaleString()} video`   : '');

  await _brFetchAllItems();
  _brRenderSidebar();
  if (_brItems.length) brNavigate(0, true);
}

async function _brFetchAllItems() {
  let page = 0;
  while (true) {
    const d = await get(`/api/browse/list?p=${page}`);
    _brItems = _brItems.concat(d.items || []);
    if (page >= (d.pages || 1) - 1) break;
    page++;
  }
}

// ── Sidebar virtual scroll ────────────────────────────────────────────────────

function _brRenderSidebar() {
  const list  = document.getElementById('br-list');
  const inner = document.getElementById('br-list-inner');
  inner.style.height = (_brItems.length * BR_ITEM_H) + 'px';

  const top    = list.scrollTop;
  const vis    = list.clientHeight;
  const start  = Math.max(0, Math.floor(top / BR_ITEM_H) - 5);
  const end    = Math.min(_brItems.length, Math.ceil((top + vis) / BR_ITEM_H) + 5);

  // Remove rows outside visible range
  Array.from(inner.children).forEach(el => {
    const idx = parseInt(el.dataset.i, 10);
    if (idx < start || idx >= end) el.remove();
  });

  const existing = new Set(
    Array.from(inner.children).map(el => parseInt(el.dataset.i, 10))
  );

  for (let i = start; i < end; i++) {
    if (existing.has(i)) continue;
    const it  = _brItems[i];
    const row = document.createElement('div');
    row.className = 'br-row' + (i === _brCur ? ' active' : '');
    row.dataset.i = i;
    row.style.top = (i * BR_ITEM_H) + 'px';
    row.onclick   = () => brNavigate(i, true);

    const liveHtml = it.type === 'live'
      ? '<span class="br-live-dot" title="Live Photo"></span>'
      : '';
    const metaLabel = it.type === 'live'   ? 'Live Photo'
                    : it.type === 'video'  ? 'Video'
                    : 'Photo';

    row.innerHTML =
      `<img class="br-thumb" src="/thumb/browse?i=${i}" loading="lazy" alt="">` +
      `<div class="br-row-info">` +
      `<div class="br-row-name">${_esc(it.name)}</div>` +
      `<div class="br-row-meta">${metaLabel}</div>` +
      `</div>${liveHtml}`;

    inner.appendChild(row);
  }
}

function _esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Navigation ────────────────────────────────────────────────────────────────

function brNavigate(targetOrDelta, absolute = false) {
  if (!_brItems.length) return;
  let next = absolute ? targetOrDelta : _brCur + targetOrDelta;
  next = Math.max(0, Math.min(_brItems.length - 1, next));
  if (next === _brCur && absolute === false) return;
  _brCur = next;

  // Update sidebar active state
  document.querySelectorAll('.br-row').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.i, 10) === _brCur);
  });

  // Scroll sidebar to keep active row visible
  const list = document.getElementById('br-list');
  const rowTop    = _brCur * BR_ITEM_H;
  const rowBottom = rowTop + BR_ITEM_H;
  if (rowTop < list.scrollTop) list.scrollTop = rowTop - BR_ITEM_H;
  else if (rowBottom > list.scrollTop + list.clientHeight)
    list.scrollTop = rowBottom - list.clientHeight + BR_ITEM_H;

  _brShowItem(_brCur);
}

// ── Viewer ────────────────────────────────────────────────────────────────────

async function _brShowItem(i) {
  _brStopLive();
  const it = _brItems[i];

  document.getElementById('br-nav-counter').textContent =
    `${i + 1} / ${_brItems.length}`;
  document.getElementById('btn-br-prev').disabled = (i === 0);
  document.getElementById('btn-br-next').disabled = (i === _brItems.length - 1);

  const img   = document.getElementById('br-img');
  const vid   = document.getElementById('br-vid');
  const ph    = document.getElementById('br-ph');
  const badge = document.getElementById('br-live-badge');
  const meta  = document.getElementById('br-viewer-meta');

  ph.style.display  = 'none';
  vid.style.display = 'none';
  img.style.display = '';
  img.src = '';   // clear first to avoid flicker of old image

  meta.textContent = it.name;
  badge.style.display = it.type === 'live' ? '' : 'none';

  if (it.type === 'video') {
    // Standalone video — no still image, play with audio and loop
    img.style.display = 'none';
    _brPlayLive(it.video_path, { muted: false, loop: true });
  } else {
    img.src = `/api/media?path=${encodeURIComponent(it.path)}`;
    if (it.type === 'live') {
      // Small delay so the still loads first, then play muted once
      _brLiveTimer = setTimeout(() => _brPlayLive(it.video_path, { muted: true, loop: false }), 600);
    }
  }
}

function _brPlayLive(videoPath, { muted = true, loop = false } = {}) {
  const img = document.getElementById('br-img');
  const vid = document.getElementById('br-vid');

  vid.src   = `/api/media?path=${encodeURIComponent(videoPath)}`;
  vid.muted = muted;
  vid.loop  = loop;

  // Live photo: restore still after playback. Standalone video: loops, no restore needed.
  vid.onended = loop ? null : () => {
    vid.style.display = 'none';
    img.style.display = '';
    vid.src = '';
  };

  img.style.display = 'none';
  vid.style.display = '';
  vid.play().catch(() => {
    vid.style.display = 'none';
    img.style.display = '';
  });
}

function brReplayLive() {
  if (_brCur < 0 || !_brItems[_brCur]) return;
  const it = _brItems[_brCur];
  if (it.type !== 'live' && it.type !== 'video') return;
  _brStopLive();
  if (it.type === 'video') {
    _brPlayLive(it.video_path, { muted: false, loop: true });
  } else {
    _brPlayLive(it.video_path, { muted: true, loop: false });
  }
}

function _brStopLive() {
  clearTimeout(_brLiveTimer);
  _brLiveTimer = null;
  const vid = document.getElementById('br-vid');
  vid.pause();
  vid.src           = '';
  vid.style.display = 'none';
  document.getElementById('br-img').style.display = '';
}

function _brResetViewer() {
  _brStopLive();
  document.getElementById('br-img').src         = '';
  document.getElementById('br-viewer-meta').textContent = '';
  document.getElementById('br-live-badge').style.display = 'none';
  document.getElementById('br-ph').style.display = '';
  document.getElementById('br-nav-counter').textContent = '— / —';
  document.getElementById('btn-br-prev').disabled = true;
  document.getElementById('btn-br-next').disabled = true;
}

// ── Keyboard ──────────────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (!document.getElementById('browse-panel').classList.contains('active')) return;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); brNavigate(1); }
  if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   { e.preventDefault(); brNavigate(-1); }
  if (e.key === ' ') { e.preventDefault(); brReplayLive(); }
});
