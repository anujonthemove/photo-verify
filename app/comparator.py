"""comparator.py — Master vs backup folder comparison with strict exclusion filters."""

import os, time, datetime, html as _html, shutil
from collections import defaultdict
from dataclasses import dataclass

from app.constants import REPORTS_DIR, MISSING_DIR, PHOTO_EXT, VIDEO_EXT

# ── Exclusion rules ──────────────────────────────────────────────────────────

SKIP_DIR_SUBSTRINGS = ['/android/data/', '/.cache/', '/cache/', '/thumbnails/']

SKIP_EXTENSIONS = (
    PHOTO_EXT | VIDEO_EXT | frozenset({
        # App DBs & runtime state
        '.db', '.sqlite', '.crypt12', '.crypt14', '.crypt15', '.xml', '.json', '.log',
        # System garbage
        '', '.tmp', '.dat', '.xmp', '.nomedia', '.ini', '.bak',
    })
)

# ── Target categories ─────────────────────────────────────────────────────────

KEEP_MAP = {
    '.pdf': 'Document', '.docx': 'Document', '.xlsx': 'Document',
    '.csv': 'Document', '.txt':  'Document', '.pptx': 'Document',
    '.doc': 'Document', '.odt':  'Document', '.rtf':  'Document',
    '.aac': 'Audio',    '.ogg':  'Audio',    '.opus': 'Audio',
    '.mp3': 'Audio',    '.m4a':  'Audio',    '.wav':  'Audio',    '.amr': 'Audio',
    '.flac': 'Audio',
    '.zip': 'Archive',  '.rar':  'Archive',  '.7z':   'Archive',
}

CAT_COLOR = {
    'Document': '#6366f1',
    'Audio':    '#10b981',
    'Archive':  '#ec4899',
    'Other':    '#64748b',
}

MAX_FILES_PER_EXT = 200  # cap per extension in HTML report

# ── Helpers ───────────────────────────────────────────────────────────────────

def _should_skip_dir(dirpath: str) -> bool:
    norm = dirpath.replace('\\', '/').lower()
    if not norm.endswith('/'):
        norm += '/'
    return any(s in norm for s in SKIP_DIR_SUBSTRINGS)


def _cat(ext: str) -> str:
    return KEEP_MAP.get(ext, 'Other')


def fmt_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def esc(s) -> str:
    return _html.escape(str(s))


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class FolderScan:
    folder: str
    files: dict       # (name_lower, size) → [full_path, ...]
    total_files: int
    total_size: int
    scan_secs: float
    errors: int = 0


@dataclass
class MasterBackupResult:
    master_folder: str
    backup_folders: list
    missing: list           # list[dict] — name, ext, size, source_path, source_folder
    by_ext: dict            # ext → list[dict]
    total_missing_size: int
    master_scan: FolderScan
    backup_scans: list      # list[FolderScan]
    scan_secs: float


# ── Scanning ──────────────────────────────────────────────────────────────────

def scan_folder(folder: str, on_progress=None) -> FolderScan:
    files = defaultdict(list)
    total_files = total_size = errors = 0
    t0 = time.perf_counter()

    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [
            d for d in dirnames
            if not _should_skip_dir(os.path.join(dirpath, d))
        ]
        if _should_skip_dir(dirpath):
            continue

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SKIP_EXTENSIONS:
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                errors += 1
                continue

            key = (fname.lower(), size)
            files[key].append(fpath)
            total_files += 1
            total_size  += size

            if on_progress and total_files % 2_000 == 0:
                on_progress(total_files)

    return FolderScan(
        folder=folder,
        files=dict(files),
        total_files=total_files,
        total_size=total_size,
        scan_secs=time.perf_counter() - t0,
        errors=errors,
    )


# ── Comparison ────────────────────────────────────────────────────────────────

def find_missing_from_master(master_scan: FolderScan, backup_scans: list) -> MasterBackupResult:
    t0 = time.perf_counter()
    master_keys = set(master_scan.files.keys())

    seen_keys = set()
    missing = []

    for backup_scan in backup_scans:
        for key, paths in backup_scan.files.items():
            if key in master_keys or key in seen_keys:
                continue
            seen_keys.add(key)
            source_path = paths[0]
            exact_name = os.path.basename(source_path)
            ext = os.path.splitext(exact_name)[1].lower()
            missing.append({
                'name':          exact_name,
                'ext':           ext,
                'size':          key[1],
                'source_path':   source_path,
                'source_folder': backup_scan.folder,
            })

    by_ext = defaultdict(list)
    for mf in missing:
        by_ext[mf['ext']].append(mf)
    for ext_list in by_ext.values():
        ext_list.sort(key=lambda x: x['name'].lower())

    return MasterBackupResult(
        master_folder=master_scan.folder,
        backup_folders=[s.folder for s in backup_scans],
        missing=missing,
        by_ext=dict(by_ext),
        total_missing_size=sum(mf['size'] for mf in missing),
        master_scan=master_scan,
        backup_scans=backup_scans,
        scan_secs=time.perf_counter() - t0,
    )


# ── File saving ───────────────────────────────────────────────────────────────

def save_missing_files(missing_files: list, out_dir: str) -> dict:
    counts = defaultdict(int)
    errors = 0
    os.makedirs(out_dir, exist_ok=True)

    for mf in missing_files:
        ext_name = mf['ext'].lstrip('.') if mf['ext'] else 'no_ext'
        ext_dir  = os.path.join(out_dir, ext_name)
        os.makedirs(ext_dir, exist_ok=True)

        dest = os.path.join(ext_dir, mf['name'])
        if os.path.exists(dest):
            base, ext_part = os.path.splitext(mf['name'])
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(ext_dir, f'{base}_{counter}{ext_part}')
                counter += 1
        try:
            shutil.copy2(mf['source_path'], dest)
            counts[ext_name] += 1
        except OSError:
            errors += 1

    return {
        'saved_dir': out_dir,
        'total':     sum(counts.values()),
        'by_ext':    dict(counts),
        'errors':    errors,
    }


# ── HTML rendering ────────────────────────────────────────────────────────────

def _card(label, value, sub=''):
    sub_html = f'<div class="card-sub">{esc(sub)}</div>' if sub else ''
    return (f'<div class="card"><div class="card-label">{esc(label)}</div>'
            f'<div class="card-value">{value}</div>{sub_html}</div>')


def render_master_backup_html(result: MasterBackupResult) -> str:
    now       = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    n_missing = len(result.missing)
    n_exts    = len(result.by_ext)
    n_backups = len(result.backup_folders)

    cards_html = (
        _card('Missing Files',   f'{n_missing:,}',                    'not in master') +
        _card('Extensions',      str(n_exts),                         'unique file types') +
        _card('Backups Scanned', str(n_backups),                      '') +
        _card('Missing Size',    fmt_size(result.total_missing_size),  'total to recover')
    )

    # ── Extension breakdown table ─────────────────────────────────────────────
    exts_sorted = sorted(result.by_ext.items(), key=lambda x: len(x[1]), reverse=True)
    max_count   = max((len(v) for v in result.by_ext.values()), default=1) or 1

    ext_rows = []
    for ext, files in exts_sorted:
        cat    = _cat(ext)
        color  = CAT_COLOR.get(cat, '#64748b')
        count  = len(files)
        size   = sum(f['size'] for f in files)
        bar_w  = count / max_count * 100
        ext_rows.append(
            f'<tr>'
            f'<td><code>{esc(ext or "(no ext)")}</code></td>'
            f'<td><span class="badge" style="background:{color}22;color:{color}">{esc(cat)}</span></td>'
            f'<td>{count:,}</td>'
            f'<td>{fmt_size(size)}</td>'
            f'<td><div style="width:{bar_w:.1f}%;background:{color};height:6px;border-radius:3px;min-width:3px"></div></td>'
            f'</tr>'
        )
    ext_table = (
        '<table><thead><tr>'
        '<th>Extension</th><th>Category</th><th>Missing Files</th>'
        '<th>Total Size</th><th style="min-width:120px">Bar</th>'
        '</tr></thead><tbody>' + ''.join(ext_rows) + '</tbody></table>'
    )

    # ── Per-extension collapsible file listing ────────────────────────────────
    ext_sections = []
    for ext, files in exts_sorted:
        cat    = _cat(ext)
        color  = CAT_COLOR.get(cat, '#64748b')
        count  = len(files)
        total_size = sum(f['size'] for f in files)
        shown  = files[:MAX_FILES_PER_EXT]
        hidden = count - len(shown)

        rows = ''.join(
            f'<div class="miss-file">'
            f'<code class="miss-name">{esc(f["name"])}</code>'
            f'<span class="miss-sz">{fmt_size(f["size"])}</span>'
            f'<span class="miss-src" title="{esc(f["source_path"])}">'
            f'{esc(os.path.basename(f["source_folder"]) or f["source_folder"])}</span>'
            f'</div>'
            for f in shown
        )
        if hidden:
            rows += f'<div class="miss-more">… {hidden:,} more files — save to disk to see all</div>'

        ext_sections.append(
            f'<details>'
            f'<summary>'
            f'<span class="badge" style="background:{color}22;color:{color};margin-right:8px">'
            f'{esc(ext or "(no ext)")}</span>'
            f'<strong>{count:,} file{"s" if count != 1 else ""}</strong>'
            f'<span style="color:var(--muted);margin-left:10px;font-size:.82rem">'
            f'{fmt_size(total_size)}</span>'
            f'</summary>'
            f'<div class="miss-body">'
            f'<div class="miss-header"><span>Filename</span><span>Size</span><span>From Backup</span></div>'
            f'{rows}</div>'
            f'</details>'
        )

    sections_html = '\n'.join(ext_sections) if ext_sections else (
        '<p style="color:var(--muted);font-size:.85rem">No missing files found — master is already complete.</p>'
    )

    # ── Backup summary ────────────────────────────────────────────────────────
    backup_rows = ''.join(
        f'<tr><td><code title="{esc(f)}">{esc(os.path.basename(f) or f)}</code></td>'
        f'<td>{scan.total_files:,} files scanned</td>'
        f'<td>{fmt_size(scan.total_size)}</td>'
        f'<td>{scan.scan_secs:.1f}s</td></tr>'
        for f, scan in zip(result.backup_folders, result.backup_scans)
    )
    backup_table = (
        '<table><thead><tr><th>Backup Folder</th><th>Files Scanned</th>'
        '<th>Size</th><th>Scan Time</th></tr></thead>'
        f'<tbody>{backup_rows}</tbody></table>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Missing Files Report</title>
<style>
:root{{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);padding:28px 36px;line-height:1.5}}
header{{margin-bottom:28px}}
header h1{{font-size:1.4rem;font-weight:700;margin-bottom:6px}}
.meta{{font-size:0.78rem;color:var(--muted);margin-bottom:3px}}
.master-path{{font-size:0.82rem;color:#60a5fa;font-family:"JetBrains Mono","Fira Code",monospace;margin-top:6px;word-break:break-all}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:36px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}}
.card-label{{font-size:0.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}}
.card-value{{font-size:1.3rem;font-weight:700}}
.card-sub{{font-size:0.75rem;color:var(--muted);margin-top:4px}}
section{{margin-bottom:36px}}
h2{{font-size:0.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:14px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:0.83rem}}
th{{background:var(--surface);color:var(--muted);text-align:left;padding:9px 12px;border-bottom:2px solid var(--border);white-space:nowrap}}
td{{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:rgba(255,255,255,.025)}}
code{{font-family:"JetBrains Mono","Fira Code",monospace;font-size:.88em}}
.badge{{display:inline-block;padding:2px 9px;border-radius:9999px;font-size:0.73rem;font-weight:600;white-space:nowrap}}
details{{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:12px;overflow:hidden}}
summary{{cursor:pointer;padding:14px 18px;font-size:0.85rem;user-select:none;list-style:none;display:flex;align-items:center;gap:6px}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:"▶";font-size:.65em;color:var(--muted);transition:transform .2s;flex-shrink:0}}
details[open] summary::before{{transform:rotate(90deg)}}
.miss-body{{padding:0 0 8px}}
.miss-header{{display:grid;grid-template-columns:1fr 90px 130px;gap:12px;padding:6px 18px;font-size:0.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);border-bottom:1px solid var(--border);background:rgba(0,0,0,.15)}}
.miss-file{{display:grid;grid-template-columns:1fr 90px 130px;align-items:center;gap:12px;padding:5px 18px;border-bottom:1px solid rgba(51,65,85,.5);font-size:0.8rem}}
.miss-file:last-of-type{{border-bottom:none}}
.miss-file:hover{{background:rgba(255,255,255,.03)}}
.miss-name{{word-break:break-all}}
.miss-sz{{color:var(--muted);white-space:nowrap;text-align:right}}
.miss-src{{color:#60a5fa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;font-size:.76rem}}
.miss-more{{font-size:0.78rem;color:var(--muted);padding:8px 18px;font-style:italic}}
</style>
</head>
<body>
<header>
  <h1>Files Missing from Master</h1>
  <p class="meta">{now} &nbsp;·&nbsp; {n_backups} backup{"s" if n_backups != 1 else ""} compared &nbsp;·&nbsp; {n_missing:,} missing file{"s" if n_missing != 1 else ""}</p>
  <p class="meta">Master folder:</p>
  <p class="master-path">{esc(result.master_folder)}</p>
</header>

<div class="cards">{cards_html}</div>

<section>
  <h2>Missing by Extension</h2>
  {ext_table}
</section>

<section>
  <h2>File Listing by Extension</h2>
  <p style="color:#94a3b8;font-size:.82rem;margin-bottom:16px">
    Click an extension to expand the full list of missing filenames.
    <em>From Backup</em> shows which backup folder the file was found in.
  </p>
  {sections_html}
</section>

<section>
  <h2>Backups Scanned</h2>
  {backup_table}
</section>
</body>
</html>"""


# ── Background worker ─────────────────────────────────────────────────────────

def _compare_master_worker(master_folder: str, backup_folders: list):
    from app.state import _state
    cz = _state['compare']
    n_total = 1 + len(backup_folders)
    cz.update({
        'phase': 'scanning', 'current': 0, 'total': n_total,
        'msg': 'Starting…', 'report_html': '', 'summary': {},
        'missing_files': [],
    })

    try:
        # Scan master
        cz['msg'] = f'Scanning master: {os.path.basename(master_folder) or master_folder}…'

        def _master_prog(n):
            cz['msg'] = f'Master: {n:,} files scanned…'

        master_scan = scan_folder(master_folder, on_progress=_master_prog)
        cz['current'] = 1

        # Scan each backup
        backup_scans = []
        for i, folder in enumerate(backup_folders):
            cz['msg'] = f'Scanning backup {i + 1}/{len(backup_folders)}: {os.path.basename(folder) or folder}…'

            def _backup_prog(n, _i=i):
                cz['msg'] = f'Backup {_i + 1}/{len(backup_folders)}: {n:,} files scanned…'

            backup_scans.append(scan_folder(folder, on_progress=_backup_prog))
            cz['current'] = 2 + i

        cz['msg'] = 'Computing missing files…'
        result = find_missing_from_master(master_scan, backup_scans)

        cz['report_html'] = render_master_backup_html(result)
        cz['missing_files'] = result.missing   # stored for save action

        os.makedirs(REPORTS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = os.path.join(REPORTS_DIR, f'compare_{ts}.html')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(cz['report_html'])

        top_exts = [
            f'{ext}: {len(files)}'
            for ext, files in sorted(result.by_ext.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        ]
        cz['summary'] = {
            'n_missing':    len(result.missing),
            'n_backups':    len(backup_folders),
            'n_exts':       len(result.by_ext),
            'missing_size': fmt_size(result.total_missing_size),
            'top_exts':     top_exts,
            'report_path':  report_path,
        }
        cz['phase'] = 'done'
        cz['msg']   = (
            f'Done — {len(result.missing):,} missing file{"s" if len(result.missing) != 1 else ""} '
            f'across {len(result.by_ext)} extension{"s" if len(result.by_ext) != 1 else ""}'
        )

    except Exception as e:
        import traceback
        cz['phase']  = 'error'
        cz['msg']    = str(e)
        cz['detail'] = traceback.format_exc()
