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

async function appShutdown() {
  if (!confirm('Stop the PhotoVerify server?')) return;
  const btn = document.getElementById('btn-shutdown');
  if (btn) btn.disabled = true;
  try { await post('/api/shutdown', {}); } catch (_) {}
  document.body.innerHTML =
    '<div style="display:flex;height:100vh;align-items:center;justify-content:center;' +
    'flex-direction:column;gap:16px;font-family:sans-serif;background:#0f172a;color:#94a3b8">' +
    '<div style="font-size:2.5rem;color:#e2e8f0">⏻</div>' +
    '<div style="font-size:1.1rem;color:#e2e8f0">Server stopped</div>' +
    '<div style="font-size:.85rem">You can close this tab.</div></div>';
}
