// ────────────────────────────────────────────────────────────────────────────
// Browse state
// ────────────────────────────────────────────────────────────────────────────
const B = {
  rootLoaded:  false,
  currentPath: '',
  allFiles:    [],
  mediaFilter: 'all',
  sortMode:    'date',
  _sorted:     [],
  _nodeId:     0,
  _nodeMap:    {},
};

function _browseNodeId(path) {
  if (!B._nodeMap[path]) B._nodeMap[path] = 'tn_' + (++B._nodeId);
  return B._nodeMap[path];
}

// ────────────────────────────────────────────────────────────────────────────
// Folder tree
// ────────────────────────────────────────────────────────────────────────────
async function setBrowseRoot() {
  const input = document.getElementById('browse-root-input');
  const root  = input.value.trim();
  if (root) {
    const r = await post('/api/set_browse_root', {root});
    if (!r.ok) { alert(r.msg); return; }
  }
  B.rootLoaded = false;
  B._nodeId  = 0;
  B._nodeMap = {};
  document.getElementById('browse-tree').innerHTML = '';
  document.getElementById('browse-grid').innerHTML = '';
  B.allFiles = [];
  B._sorted  = [];
  await loadBrowseRoot();
}

async function loadBrowseRoot() {
  const tree = document.getElementById('browse-tree');
  B.rootLoaded = true;
  const data = await get('/api/browse_tree');
  if (!data.ok) {
    tree.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:11px;">No folder available. Enter a path above or load an index first.</div>';
    return;
  }
  // Show the resolved root in the input
  const inp = document.getElementById('browse-root-input');
  if (inp && !inp.value) inp.placeholder = data.path;
  tree.innerHTML = '';
  _renderTreeNodes(data.dirs, tree, 0, data.path);
  _loadFolderFiles(data.path, data.files);
}

function _renderTreeNodes(dirs, container, depth, parentPath) {
  dirs.forEach(d => {
    const nid = _browseNodeId(d.path);
    const row = document.createElement('div');
    row.className = 'tree-node';
    row.style.paddingLeft = (10 + depth * 14) + 'px';
    row.dataset.path = d.path;
    row.dataset.depth = depth;
    row.innerHTML = `<span class="tree-arrow" id="arr-${nid}">▶</span>📁 <span>${esc(d.name)}</span>`;
    row.onclick = () => toggleTreeNode(d.path, nid, depth);

    const children = document.createElement('div');
    children.className = 'tree-children';
    children.id = 'ch-' + nid;

    container.appendChild(row);
    container.appendChild(children);
  });
}

async function toggleTreeNode(path, nid, depth) {
  // Highlight selected
  document.querySelectorAll('.tree-node').forEach(n => n.classList.remove('selected'));
  const row = document.querySelector(`.tree-node[data-path="${CSS.escape(path)}"]`);
  if (row) row.classList.add('selected');

  const arrow    = document.getElementById('arr-' + nid);
  const children = document.getElementById('ch-'  + nid);
  const isOpen   = arrow && arrow.classList.contains('open');

  // Always reload folder files on click
  const data = await get('/api/browse_tree?path=' + encodeURIComponent(path));
  if (data.ok) _loadFolderFiles(path, data.files);

  if (isOpen) {
    if (arrow) arrow.classList.remove('open');
    if (children) children.classList.remove('open');
  } else {
    if (arrow) arrow.classList.add('open');
    if (children) {
      children.classList.add('open');
      if (!children.dataset.loaded) {
        _renderTreeNodes(data.dirs || [], children, depth + 1, path);
        children.dataset.loaded = '1';
      }
    }
  }
}

// ────────────────────────────────────────────────────────────────────────────
// Media grid
// ────────────────────────────────────────────────────────────────────────────
function _loadFolderFiles(path, files) {
  B.currentPath = path;
  B.allFiles    = files || [];
  document.getElementById('browse-path-label').textContent = path;
  sortAndRenderGrid();
}

function setBrowseFilter(f) {
  B.mediaFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.mf === f));
  sortAndRenderGrid();
}

function sortAndRenderGrid() {
  B.sortMode = document.getElementById('browse-sort').value;
  let files = B.allFiles.slice();
  if (B.mediaFilter === 'photo') files = files.filter(f => !f.is_video);
  if (B.mediaFilter === 'video') files = files.filter(f =>  f.is_video);
  if (B.sortMode === 'date') files.sort((a, b) => b.mtime - a.mtime);
  else                       files.sort((a, b) => a.name.localeCompare(b.name));
  B._sorted = files;

  const grid = document.getElementById('browse-grid');
  document.getElementById('browse-count').textContent = files.length + ' item' + (files.length !== 1 ? 's' : '');

  if (!files.length) {
    grid.innerHTML = '<div id="browse-empty">No media files in this folder.</div>';
    return;
  }
  grid.innerHTML = files.map((f, i) => {
    const thumb = '/thumb/dest?p=' + encodeURIComponent(f.path) + '&_=' + Math.floor(f.mtime);
    const badge = f.is_video ? '<div class="video-badge">▶</div>' : '';
    return `<div class="media-cell" onclick="openLightbox(${i})">
      <img src="${thumb}" loading="lazy" onerror="this.style.opacity='.15'">
      ${badge}
      <div class="cell-name">${esc(f.name)}</div>
    </div>`;
  }).join('');
}

// ────────────────────────────────────────────────────────────────────────────
// Lightbox
// ────────────────────────────────────────────────────────────────────────────
function openLightbox(idx) {
  const f = B._sorted[idx];
  if (!f) return;
  const lb  = document.getElementById('browse-lightbox');
  const img = document.getElementById('lb-img');
  const vid = document.getElementById('lb-video');
  img.classList.remove('show');
  vid.classList.remove('show');
  if (vid.src) { vid.pause(); vid.removeAttribute('src'); vid.load(); }

  const url = '/api/media?path=' + encodeURIComponent(f.path);
  document.getElementById('lb-caption').textContent = f.name;
  if (f.is_video) {
    vid.src = url;
    vid.classList.add('show');
  } else {
    img.src = url;
    img.classList.add('show');
  }
  lb.classList.add('open');
}

function closeLightbox() {
  const vid = document.getElementById('lb-video');
  if (vid.src) { vid.pause(); vid.removeAttribute('src'); vid.load(); }
  document.getElementById('browse-lightbox').classList.remove('open');
}
