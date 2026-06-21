async function get(url) {
  return (await fetch(url)).json();
}
async function post(url, body) {
  return (await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  })).json();
}
function v(id)   { return document.getElementById(id)?.value?.trim() || ''; }
function esc(s)  { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function fmtSize(b) {
  if (b < 1024)    return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(1) + ' MB';
}
function basename(p) { return p.replace(/\\/g, '/').split('/').pop() || p; }
