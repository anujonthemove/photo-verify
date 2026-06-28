/* compare-tab.js — Master vs backup folder comparison */

let _czCount     = 1;   // number of backup inputs currently shown
let _czPollTimer = null;

function czAddFolder() {
  _czCount++;
  const row = document.createElement('div');
  row.className = 'idx-form-row cz-row';
  row.id = `cz-row-${_czCount}`;
  row.innerHTML =
    `<label>Backup ${_czCount}</label>` +
    `<input id="cz-f-${_czCount}" type="text" placeholder="D:\\Backup_..." autocomplete="off">` +
    `<button class="cz-remove-btn" onclick="czRemoveFolder(${_czCount})" title="Remove">✕</button>`;
  document.getElementById('cz-folder-list').appendChild(row);
}

function czRemoveFolder(n) {
  const row = document.getElementById(`cz-row-${n}`);
  if (row) row.remove();
}

function _czBackups() {
  return Array.from(document.querySelectorAll('.cz-row input'))
    .map(el => el.value.trim())
    .filter(v => v);
}

async function czStart() {
  const master  = document.getElementById('cz-master').value.trim();
  const backups = _czBackups();

  if (!master) {
    alert('Enter the master folder path.');
    return;
  }
  if (backups.length < 1) {
    alert('Enter at least one backup folder path.');
    return;
  }

  document.getElementById('btn-cz-start').disabled = true;
  document.getElementById('btn-cz-add').disabled   = true;
  document.getElementById('cz-result').style.display   = 'none';
  document.getElementById('cz-save-msg').textContent   = '';
  document.getElementById('cz-progress').style.display = '';
  _czSetBar(0, true);
  _czSetMsg('Starting…');

  const res = await post('/api/compare/start', { master, backups });
  if (!res.ok) {
    _czSetMsg('⚠ ' + (res.msg || 'Error'));
    _czDone();
    return;
  }
  _czPoll();
}

function _czPoll() {
  clearTimeout(_czPollTimer);
  _czPollTimer = setTimeout(async () => {
    const s = await get('/api/compare/status');
    _czSetMsg(s.msg || '');

    if (s.phase === 'scanning') {
      const pct = s.total > 0 ? (s.current / s.total) * 90 : 0;
      _czSetBar(pct, pct === 0);
      _czPoll();
    } else if (s.phase === 'done') {
      _czSetBar(100, false);
      const sm = s.summary || {};
      const n  = (sm.n_missing || 0).toLocaleString();
      const sz = sm.missing_size || '';
      const ex = sm.n_exts || 0;
      let line = `${n} file${sm.n_missing !== 1 ? 's' : ''} missing from master`;
      if (ex)  line += ` · ${ex} extension${ex !== 1 ? 's' : ''}`;
      if (sz)  line += ` · ${sz}`;
      if ((sm.top_exts || []).length) {
        line += `\n${sm.top_exts.join('  ·  ')}`;
      }
      document.getElementById('cz-summary').textContent = line;
      document.getElementById('btn-cz-save').disabled =
        !sm.n_missing || sm.n_missing === 0;
      document.getElementById('cz-result').style.display = '';
      _czDone();
    } else if (s.phase === 'error') {
      _czSetBar(0, false);
      _czSetMsg('⚠ ' + (s.msg || 'Scan failed'));
      _czDone();
    } else {
      _czPoll();
    }
  }, 900);
}

function czOpenReport() {
  window.open('/compare/report', '_blank');
}

async function czSaveMissing() {
  const btn = document.getElementById('btn-cz-save');
  const msg = document.getElementById('cz-save-msg');
  btn.disabled = true;
  msg.textContent = 'Saving…';

  const res = await post('/api/compare/save_missing', {});
  if (res.ok) {
    const by = res.by_ext || {};
    const extSummary = Object.entries(by)
      .sort((a, b) => b[1] - a[1])
      .map(([e, n]) => `${e}×${n}`)
      .join('  ');
    msg.textContent =
      `✓ Saved ${(res.total || 0).toLocaleString()} files` +
      (extSummary ? ` (${extSummary})` : '') +
      ` → ${res.saved_dir}` +
      (res.errors ? `  ⚠ ${res.errors} error(s)` : '');
  } else {
    msg.textContent = '⚠ ' + (res.msg || 'Save failed');
    btn.disabled = false;
  }
}

function _czDone() {
  document.getElementById('btn-cz-start').disabled = false;
  document.getElementById('btn-cz-add').disabled   = false;
}

function _czSetMsg(msg) {
  document.getElementById('cz-msg').textContent = msg;
}

function _czSetBar(pct, indeterminate) {
  const bar = document.getElementById('cz-bar');
  if (indeterminate) {
    bar.style.width     = '100%';
    bar.style.animation = 'indeterminate 1.4s ease-in-out infinite';
  } else {
    bar.style.animation = 'none';
    bar.style.width     = pct + '%';
  }
}
