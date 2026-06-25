function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(name + '-panel').classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'index')   { idxRefreshList(); }
  if (name === 'verify')  { vOnTabActivate(); }
}

function updateIndexChip(meta) {
  const chip = document.getElementById('active-index-chip');
  if (meta && meta.name) {
    chip.style.display = '';
    chip.className = 'chip chip-ok';
    chip.textContent = meta.name + ' · ' + (meta.total || 0).toLocaleString() + ' files';
    chip.title = meta.folder || '';
  } else {
    chip.style.display = 'none';
  }
}

async function init() {
  const s = await get('/api/state');
  updateIndexChip(s.active_index_meta);
  switchTab('index');
}

window.addEventListener('load', init);
