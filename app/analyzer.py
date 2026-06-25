"""Core folder-analysis logic shared by analyze.py (CLI) and the web server."""

import os, heapq, time, datetime, html as _html
from collections import defaultdict
from dataclasses import dataclass, field

from app.constants import PHOTO_EXT, VIDEO_EXT, REPORTS_DIR

AUDIO_EXT   = {'.mp3','.aac','.flac','.wav','.ogg','.m4a','.opus','.wma','.amr',
               '.3ga','.aiff','.au','.mid','.midi','.caf','.mka'}
APP_EXT     = {'.apk','.xapk','.obb'}
DOC_EXT     = {'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.txt','.rtf',
               '.odt','.csv','.epub','.mobi','.pages','.numbers','.key','.md',
               '.html','.htm'}
ARCHIVE_EXT = {'.zip','.tar','.gz','.bz2','.xz','.rar','.7z','.jar','.tgz','.zst'}
DATA_EXT    = {'.db','.sqlite','.sqlite3','.json','.xml','.yaml','.yml','.proto',
               '.pb','.realm','.parquet','.ndjson'}
SYSTEM_EXT  = {'.so','.dex','.odex','.vdex','.art','.oat','.bin','.img','.dat',
               '.bak','.prop','.cfg','.conf','.ini','.log','.tmp','.cache',
               '.nomedia','.classpath','.policy'}


def _build_category_map():
    m = {}
    for ext in SYSTEM_EXT:   m[ext] = 'System'
    for ext in DATA_EXT:     m[ext] = 'Data/DB'
    for ext in ARCHIVE_EXT:  m[ext] = 'Archive'
    for ext in DOC_EXT:      m[ext] = 'Document'
    for ext in APP_EXT:      m[ext] = 'App'
    for ext in AUDIO_EXT:    m[ext] = 'Audio'
    for ext in VIDEO_EXT:    m[ext] = 'Video'
    for ext in PHOTO_EXT:    m[ext] = 'Photo'
    return m


CATEGORY_MAP = _build_category_map()

CAT_ORDER = ['Photo', 'Video', 'Audio', 'App', 'Document', 'Archive', 'Data/DB', 'System', 'Other']
CAT_COLOR = {
    'Photo':    '#3b82f6',
    'Video':    '#8b5cf6',
    'Audio':    '#10b981',
    'App':      '#f59e0b',
    'Document': '#6366f1',
    'Archive':  '#ec4899',
    'Data/DB':  '#14b8a6',
    'System':   '#94a3b8',
    'Other':    '#64748b',
}


def _cat(ext: str) -> str:
    return CATEGORY_MAP.get(ext, 'Other')


# ── Stats & scan ─────────────────────────────────────────────────────────────

TOP_N_FILES   = 20
TOP_N_FOLDERS = 15
TOP_N_DUPS    = 50


@dataclass
class Stats:
    folder: str
    total_files: int = 0
    total_size: int = 0
    ext_count: dict = field(default_factory=lambda: defaultdict(int))
    ext_size:  dict = field(default_factory=lambda: defaultdict(int))
    cat_count: dict = field(default_factory=lambda: defaultdict(int))
    cat_size:  dict = field(default_factory=lambda: defaultdict(int))
    top_files: list = field(default_factory=list)
    folder_count: dict = field(default_factory=lambda: defaultdict(int))
    basename_map: dict = field(default_factory=lambda: defaultdict(list))
    mtime_min: float = float('inf')
    mtime_max: float = 0.0
    scan_secs: float = 0.0
    errors: int = 0


def scan(folder: str, on_progress=None) -> Stats:
    st = Stats(folder=folder)
    t0 = time.perf_counter()
    heap: list = []

    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                size  = os.path.getsize(fpath)
                mtime = os.path.getmtime(fpath)
            except OSError:
                st.errors += 1
                continue

            ext = os.path.splitext(fname)[1].lower()
            cat = _cat(ext)

            st.total_files += 1
            st.total_size  += size
            st.ext_count[ext] += 1
            st.ext_size[ext]  += size
            st.cat_count[cat] += 1
            st.cat_size[cat]  += size
            st.folder_count[dirpath] += 1
            st.basename_map[fname.lower()].append(fpath)

            if mtime < st.mtime_min: st.mtime_min = mtime
            if mtime > st.mtime_max: st.mtime_max = mtime

            if len(heap) < TOP_N_FILES:
                heapq.heappush(heap, (size, fpath))
            elif size > heap[0][0]:
                heapq.heapreplace(heap, (size, fpath))

            if on_progress and st.total_files % 5_000 == 0:
                on_progress(st.total_files)

    st.top_files = sorted(heap, reverse=True)
    st.scan_secs = time.perf_counter() - t0
    return st


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_ts(ts: float) -> str:
    if ts == float('inf') or ts == 0.0:
        return '—'
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')


def esc(s) -> str:
    return _html.escape(str(s))


# ── HTML rendering ────────────────────────────────────────────────────────────

def _card(label: str, value: str, sub: str = '') -> str:
    sub_html = f'<div class="card-sub">{esc(sub)}</div>' if sub else ''
    return (f'<div class="card">'
            f'<div class="card-label">{esc(label)}</div>'
            f'<div class="card-value">{value}</div>'
            f'{sub_html}</div>')


def _badge(cat: str) -> str:
    color = CAT_COLOR.get(cat, '#64748b')
    return f'<span class="badge" style="background:{color}22;color:{color}">{esc(cat)}</span>'


def _table(table_id: str, headers: list, rows_html: str) -> str:
    ths = ''.join(
        f'<th onclick="sortTable(this,\'{table_id}\',{i},{str(num).lower()})"'
        f'{" class=\"sorted-desc\"" if default_sort else ""}>{esc(label)}</th>'
        for i, (label, num, default_sort) in enumerate(headers)
    )
    return (f'<table id="{table_id}"><thead><tr>{ths}</tr></thead>'
            f'<tbody>{rows_html}</tbody></table>')


def render_html(st: Stats) -> str:
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    date_range = f"{fmt_ts(st.mtime_min)} → {fmt_ts(st.mtime_max)}" if st.total_files else '—'
    cats_found = sum(1 for c in CAT_ORDER if st.cat_count.get(c, 0) > 0)
    err_sub    = f"{st.errors:,} unreadable" if st.errors else ''

    cards_html = (
        _card('Total Files',       f"{st.total_files:,}",     err_sub) +
        _card('Total Size',        fmt_size(st.total_size),   '') +
        _card('Unique Extensions', f"{len(st.ext_count)}",    '') +
        _card('Categories',        f"{cats_found}",           '') +
        _card('Date Range',        date_range,                'file mod times') +
        _card('Scan Time',         f"{st.scan_secs:.2f}s",    '')
    )

    max_cat  = max((st.cat_count.get(c, 0) for c in CAT_ORDER), default=1) or 1
    cat_rows = []
    for cat in CAT_ORDER:
        cnt = st.cat_count.get(cat, 0)
        if not cnt:
            continue
        size  = st.cat_size.get(cat, 0)
        pct   = cnt / st.total_files * 100 if st.total_files else 0
        w_pct = cnt / max_cat * 100
        color = CAT_COLOR[cat]
        cat_rows.append(
            f'<div class="cat-row">'
            f'<div class="cat-name">{_badge(cat)}</div>'
            f'<div class="cat-bar-wrap"><div class="cat-bar" style="width:{w_pct:.1f}%;background:{color}"></div></div>'
            f'<div class="cat-stats">{cnt:,} files &nbsp;·&nbsp; {fmt_size(size)} &nbsp;·&nbsp; {pct:.1f}%</div>'
            f'</div>'
        )
    cat_html = '\n'.join(cat_rows)

    ext_sorted = sorted(st.ext_count.items(), key=lambda x: x[1], reverse=True)
    max_ext    = ext_sorted[0][1] if ext_sorted else 1
    ext_rows   = []
    for ext, cnt in ext_sorted:
        size  = st.ext_size[ext]
        cat   = _cat(ext)
        color = CAT_COLOR.get(cat, '#64748b')
        pct   = cnt / st.total_files * 100 if st.total_files else 0
        w_pct = cnt / max_ext * 100
        label = f'<code>{esc(ext)}</code>' if ext else '<span style="color:#64748b"><em>(none)</em></span>'
        ext_rows.append(
            f'<tr>'
            f'<td>{label}</td>'
            f'<td>{_badge(cat)}</td>'
            f'<td data-val="{cnt}">{cnt:,}</td>'
            f'<td data-val="{size}">{fmt_size(size)}</td>'
            f'<td data-val="{pct:.4f}">{pct:.1f}%</td>'
            f'<td><div class="mini-bar-wrap"><div class="mini-bar" style="width:{w_pct:.1f}%;background:{color}"></div></div></td>'
            f'</tr>'
        )
    ext_table = _table('ext-table', [
        ('Extension', False, False),
        ('Category',  False, False),
        ('Files',     True,  True),
        ('Total Size',True,  False),
        ('% of Files',True,  False),
        ('Bar',       False, False),
    ], ''.join(ext_rows))

    top_file_rows = []
    for i, (size, fpath) in enumerate(st.top_files, 1):
        fname = os.path.basename(fpath)
        cat   = _cat(os.path.splitext(fname)[1].lower())
        top_file_rows.append(
            f'<tr>'
            f'<td style="color:#64748b;text-align:right;width:28px">{i}</td>'
            f'<td><code title="{esc(fpath)}">{esc(fname)}</code></td>'
            f'<td>{_badge(cat)}</td>'
            f'<td data-val="{size}" style="white-space:nowrap">{fmt_size(size)}</td>'
            f'<td class="path-cell" title="{esc(fpath)}">{esc(fpath)}</td>'
            f'</tr>'
        )
    top_files_table = _table('top-files-table', [
        ('#',       False, False),
        ('File',    False, False),
        ('Category',False, False),
        ('Size',    True,  True),
        ('Path',    False, False),
    ], ''.join(top_file_rows))

    top_folders = sorted(st.folder_count.items(), key=lambda x: x[1], reverse=True)[:TOP_N_FOLDERS]
    max_fld     = top_folders[0][1] if top_folders else 1
    folder_rows = []
    for fdir, cnt in top_folders:
        pct   = cnt / st.total_files * 100 if st.total_files else 0
        w_pct = cnt / max_fld * 100
        folder_rows.append(
            f'<tr>'
            f'<td class="path-cell" title="{esc(fdir)}">{esc(fdir)}</td>'
            f'<td data-val="{cnt}" style="white-space:nowrap">{cnt:,}</td>'
            f'<td data-val="{pct:.4f}" style="white-space:nowrap">{pct:.1f}%</td>'
            f'<td><div class="mini-bar-wrap" style="min-width:120px"><div class="mini-bar" style="width:{w_pct:.1f}%;background:#3b82f6"></div></div></td>'
            f'</tr>'
        )
    folder_table = _table('folder-table', [
        ('Folder',     False, False),
        ('Files',      True,  True),
        ('% of Total', True,  False),
        ('Bar',        False, False),
    ], ''.join(folder_rows))

    dup_groups = sorted(
        ((k, v) for k, v in st.basename_map.items() if len(v) > 1),
        key=lambda x: len(x[1]), reverse=True
    )
    dup_total  = len(dup_groups)
    dup_groups = dup_groups[:TOP_N_DUPS]
    dup_rows   = []
    for basename, paths in dup_groups:
        paths_html = '<br>'.join(f'<span class="path-cell">{esc(p)}</span>' for p in paths)
        dup_rows.append(
            f'<tr>'
            f'<td><code>{esc(basename)}</code></td>'
            f'<td data-val="{len(paths)}" style="white-space:nowrap">{len(paths)}</td>'
            f'<td>{paths_html}</td>'
            f'</tr>'
        )
    dup_table = _table('dup-table', [
        ('Filename', False, False),
        ('Count',    True,  True),
        ('Paths',    False, False),
    ], ''.join(dup_rows)) if dup_rows else '<p style="color:#64748b;padding:8px 0">No duplicate filenames found.</p>'

    dup_label = f"Duplicate Filenames &mdash; {dup_total:,} group{'s' if dup_total != 1 else ''}"
    if dup_total > TOP_N_DUPS:
        dup_label += f" (showing top {TOP_N_DUPS})"

    folder_title = esc(os.path.basename(st.folder) or st.folder)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Folder Analysis — {folder_title}</title>
<style>
:root{{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);padding:28px 36px;line-height:1.5}}
header{{margin-bottom:32px}}
header h1{{font-size:1.4rem;font-weight:700;margin-bottom:6px}}
.folder-path{{font-size:0.85rem;color:var(--muted);word-break:break-all;margin-bottom:4px}}
.meta{{font-size:0.78rem;color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:36px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}}
.card-label{{font-size:0.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}}
.card-value{{font-size:1.35rem;font-weight:700}}
.card-sub{{font-size:0.75rem;color:#ef4444;margin-top:4px}}
section{{margin-bottom:36px}}
h2{{font-size:0.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:14px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.cat-row{{display:flex;align-items:center;gap:14px;margin-bottom:10px}}
.cat-name{{width:100px;text-align:right;flex-shrink:0}}
.cat-bar-wrap{{flex:1;background:var(--border);border-radius:4px;height:16px;overflow:hidden}}
.cat-bar{{height:100%;border-radius:4px}}
.cat-stats{{font-size:0.8rem;color:var(--muted);width:230px;flex-shrink:0}}
table{{width:100%;border-collapse:collapse;font-size:0.83rem}}
th{{background:var(--surface);color:var(--muted);text-align:left;padding:9px 12px;border-bottom:2px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;z-index:1}}
th:hover{{color:var(--text)}}
th.sorted-asc::after{{content:" ▲";font-size:.65em;opacity:.7}}
th.sorted-desc::after{{content:" ▼";font-size:.65em;opacity:.7}}
td{{padding:7px 12px;border-bottom:1px solid var(--border);vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:rgba(255,255,255,.025)}}
code{{font-family:"JetBrains Mono","Fira Code",monospace;font-size:.88em}}
.badge{{display:inline-block;padding:2px 9px;border-radius:9999px;font-size:0.73rem;font-weight:600;white-space:nowrap}}
.mini-bar-wrap{{background:var(--border);border-radius:3px;height:6px;min-width:80px}}
.mini-bar{{height:100%;border-radius:3px}}
.path-cell{{font-size:0.76rem;color:var(--muted);word-break:break-all;max-width:500px}}
details{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px;margin-bottom:36px}}
summary{{cursor:pointer;font-size:0.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);user-select:none;padding-bottom:0}}
details[open] summary{{padding-bottom:14px;border-bottom:1px solid var(--border);margin-bottom:14px}}
summary:hover{{color:var(--text)}}
</style>
</head>
<body>
<header>
  <h1>Folder Analysis</h1>
  <p class="folder-path">{esc(st.folder)}</p>
  <p class="meta">Scanned {now} &nbsp;&middot;&nbsp; {st.scan_secs:.2f}s &nbsp;&middot;&nbsp; {st.total_files:,} files</p>
</header>

<div class="cards">{cards_html}</div>

<section>
  <h2>By Category</h2>
  {cat_html}
</section>

<section>
  <h2>Extensions &mdash; {len(st.ext_count)} unique</h2>
  {ext_table}
</section>

<section>
  <h2>Top {len(st.top_files)} Largest Files</h2>
  {top_files_table}
</section>

<section>
  <h2>Top {len(top_folders)} Folders by File Count</h2>
  {folder_table}
</section>

<details>
  <summary>{dup_label}</summary>
  {dup_table}
</details>

<script>
function sortTable(th, id, col, isNum) {{
  var t = document.getElementById(id);
  var tbody = t.querySelector('tbody');
  var rows = Array.from(tbody.rows);
  var asc = !th.classList.contains('sorted-asc');
  t.querySelectorAll('th').forEach(function(h) {{ h.classList.remove('sorted-asc', 'sorted-desc'); }});
  th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
  rows.sort(function(a, b) {{
    var av = (a.cells[col].dataset.val !== undefined) ? a.cells[col].dataset.val : a.cells[col].textContent.trim();
    var bv = (b.cells[col].dataset.val !== undefined) ? b.cells[col].dataset.val : b.cells[col].textContent.trim();
    if (isNum) {{ av = parseFloat(av) || 0; bv = parseFloat(bv) || 0; }}
    else {{ av = av.toLowerCase(); bv = bv.toLowerCase(); }}
    return asc ? (av < bv ? -1 : av > bv ? 1 : 0) : (av > bv ? -1 : av < bv ? 1 : 0);
  }});
  rows.forEach(function(r) {{ tbody.appendChild(r); }});
}}
</script>
</body>
</html>"""


# ── Background worker (used by web server) ────────────────────────────────────

def _analyze_worker(folder: str):
    from app.state import _state
    az = _state['analyze']
    az.update({'phase': 'scanning', 'scanned': 0, 'folder': folder,
               'msg': 'Starting scan…', 'report_html': '', 'summary': {}})

    try:
        def _progress(n):
            az['scanned'] = n
            az['msg'] = f'Scanned {n:,} files…'

        st = scan(folder, on_progress=_progress)
        az['report_html'] = render_html(st)

        os.makedirs(REPORTS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = os.path.join(REPORTS_DIR, f'{ts}.html')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(az['report_html'])

        az['summary'] = {
            'total_files': st.total_files,
            'total_size':  fmt_size(st.total_size),
            'ext_count':   len(st.ext_count),
            'scan_secs':   round(st.scan_secs, 2),
        }
        az['scanned'] = st.total_files
        az['phase']   = 'done'
        az['msg']     = f'Done — {st.total_files:,} files, {len(st.ext_count)} extensions'
    except Exception as e:
        az['phase'] = 'error'
        az['msg']   = str(e)
