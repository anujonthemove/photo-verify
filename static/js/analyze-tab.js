/* analyze-tab.js — Folder Analyzer tab logic */

let _azPollTimer = null;

async function azStart() {
  const folder = document.getElementById('az-folder').value.trim();
  if (!folder) return;

  document.getElementById('btn-az-start').disabled = true;
  document.getElementById('az-result').style.display = 'none';
  document.getElementById('az-progress').style.display = '';
  _azSetBar(0, true);
  _azSetMsg('Starting scan…');

  const res = await post('/api/analyze/start', { folder });
  if (!res.ok) {
    _azSetMsg('⚠ ' + (res.msg || 'Error'));
    document.getElementById('btn-az-start').disabled = false;
    _azSetBar(0, false);
    return;
  }

  _azPoll();
}

function _azPoll() {
  clearTimeout(_azPollTimer);
  _azPollTimer = setTimeout(async () => {
    const s = await get('/api/analyze/status');
    _azSetMsg(s.msg || '');

    if (s.phase === 'scanning') {
      _azSetBar(0, true);
      _azPoll();
    } else if (s.phase === 'done') {
      _azSetBar(100, false);
      const sm = s.summary || {};
      document.getElementById('az-summary').textContent =
        `${(sm.total_files || 0).toLocaleString()} files  ·  ` +
        `${sm.total_size || ''}  ·  ` +
        `${sm.ext_count || 0} extensions  ·  ` +
        `${sm.scan_secs || 0}s`;
      document.getElementById('az-result').style.display = '';
      document.getElementById('btn-az-start').disabled = false;
    } else if (s.phase === 'error') {
      _azSetBar(0, false);
      _azSetMsg('⚠ ' + (s.msg || 'Scan failed'));
      document.getElementById('btn-az-start').disabled = false;
    } else {
      _azPoll();
    }
  }, 800);
}

function azOpenReport() {
  window.open('/analyze/report', '_blank');
}

function _azSetMsg(msg) {
  document.getElementById('az-msg').textContent = msg;
}

function _azSetBar(pct, indeterminate) {
  const bar = document.getElementById('az-bar');
  if (indeterminate) {
    bar.style.width = '100%';
    bar.style.animation = 'indeterminate 1.4s ease-in-out infinite';
  } else {
    bar.style.animation = 'none';
    bar.style.width = pct + '%';
  }
}
