"""
File Integrity Test for Indexer + Visual Matcher
=================================================
Proves empirically that building an index and running visual matching (dHash)
do NOT modify, touch, or corrupt any image file on disk.

Usage:
    python tests/test_integrity.py <folder_path> [--verbose]

Exit codes:
    0 = PASS (no files were modified)
    1 = FAIL (one or more files were changed)
    2 = Usage error
"""

import os
import sys
import hashlib
import time
import threading
import argparse
from pathlib import Path

# ── bootstrap: add project root to path ──────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── project imports (no server needed) ───────────────────────────────────────
from app.scanner import scan_all_media       # noqa: E402
from app.indexer import _build_index_worker  # noqa: E402
from app.matcher import find_match           # noqa: E402
from app.state import _state                 # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _md5(path: str) -> str:
    """Return MD5 hex digest of a file. Catches read errors gracefully."""
    h = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        return f"ERROR:{exc}"


def _snapshot(paths: list, label: str) -> dict:
    """Record (md5, size_bytes, mtime_ns) for every path."""
    snap = {}
    n = len(paths)
    for i, p in enumerate(paths, 1):
        if i % 500 == 0 or i == n:
            print(f"  [{label}] {i:,}/{n:,} files hashed…", end='\r')
        try:
            st = os.stat(p)
            snap[p] = (_md5(p), st.st_size, st.st_mtime_ns)
        except OSError as exc:
            snap[p] = (f"STAT_ERROR:{exc}", -1, -1)
    print()
    return snap


def _run_indexer_with_progress(folder: str) -> tuple:
    """Run _build_index_worker in a thread; print live progress. Returns (elapsed, idx_file)."""
    t0 = time.time()
    worker = threading.Thread(
        target=_build_index_worker,
        args=(folder, "integrity_test"),
        daemon=True,
    )
    worker.start()

    last_line = ""
    while worker.is_alive():
        st = _state['idx_status']
        phase   = st.get('phase', '')
        current = st.get('current', 0)
        total   = st.get('total', 0)

        if phase == 'scanning':
            line = "  Scanning files…"
        elif phase == 'building' and total > 0:
            pct   = current * 100 // total
            bar_w = 30
            fill  = bar_w * current // total
            bar   = '█' * fill + '░' * (bar_w - fill)
            line  = (f"  Building: {current:,}/{total:,} ({pct}%)"
                     f"  [{bar}]")
        elif phase in ('done', 'error'):
            break
        else:
            line = f"  {phase}…"

        if line != last_line:
            print(line, end='\r')
            last_line = line
        time.sleep(0.25)

    worker.join()
    elapsed = time.time() - t0

    # clear the progress line
    print(' ' * 80, end='\r')

    status   = _state['idx_status']
    idx_file = status.get('last_index', '')
    return elapsed, idx_file, status


def _compare(before: dict, after: dict, verbose: bool) -> list:
    """Return list of human-readable change descriptions. Empty = no changes."""
    failures = []
    for path, (md5_b, size_b, mtime_b) in before.items():
        if path not in after:
            failures.append(f"  MISSING after run: {path}")
            continue
        md5_a, size_a, mtime_a = after[path]
        changes = []
        if size_b != size_a:
            changes.append(f"size {size_b} → {size_a}")
        if md5_b != md5_a:
            changes.append("MD5 changed")
        if mtime_b != mtime_a:
            changes.append("mtime changed")
        if changes:
            failures.append(f"  {path}  [{', '.join(changes)}]")
        elif verbose:
            print(f"    OK  {Path(path).name}")
    return failures


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Verify indexer + matcher leave image files untouched."
    )
    parser.add_argument("folder", help="Path to the test image folder")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-file OK lines")
    args = parser.parse_args()

    folder = os.path.normpath(args.folder)
    if not os.path.isdir(folder):
        print(f"ERROR: Not a directory: {folder}")
        sys.exit(2)

    print(f"\n{'='*60}")
    print("  PhotoVerify File Integrity Test")
    print(f"  Folder: {folder}")
    print(f"{'='*60}\n")

    # ── Phase 1: scan ────────────────────────────────────────────────────────
    print("[1/5] Scanning for media files…")
    paths = scan_all_media(folder)
    n = len(paths)
    if n == 0:
        print("  No media files found. Nothing to test.")
        sys.exit(2)
    print(f"  Found {n:,} files.\n")

    # ── Phase 2: pre-run snapshot ─────────────────────────────────────────────
    print("[2/5] Taking PRE-RUN snapshot (MD5 + size + mtime)…")
    before = _snapshot(paths, "pre")
    print(f"  Snapshot complete: {len(before):,} files.\n")

    # ── Phase 3: build index (threaded so progress is visible) ───────────────
    print("[3/5] Running indexer…")
    elapsed, idx_file, status = _run_indexer_with_progress(folder)
    if status['phase'] == 'error':
        print(f"  ERROR during index build: {status['msg']}")
        sys.exit(1)
    print(f"  {status['msg']}")
    print(f"  Elapsed: {elapsed:.1f}s\n")

    # ── Phase 4: run find_match on every file ─────────────────────────────────
    print("[4/5] Running find_match() on every file…")
    _state['src_photos'] = paths
    found = missing = errors = 0
    t1 = time.time()
    for i, path in enumerate(paths, 1):
        if i % 200 == 0 or i == n:
            pct = i * 100 // n
            print(f"  Matching: {i:,}/{n:,} ({pct}%)", end='\r')
        try:
            m = find_match(path)
            if m:
                found += 1
                if args.verbose:
                    print(f"    FOUND [{m['method']:8s}] {Path(path).name}")
            else:
                missing += 1
                if args.verbose:
                    print(f"    MISS            {Path(path).name}")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"\n  MATCH ERROR: {path}: {exc}")
    print(' ' * 60, end='\r')  # clear progress line
    elapsed2 = time.time() - t1
    print(f"  found: {found:,}  missing: {missing:,}"
          f"  errors: {errors:,}  ({elapsed2:.1f}s)\n")

    # ── Phase 5: post-run snapshot + compare ─────────────────────────────────
    print("[5/5] Taking POST-RUN snapshot and comparing…")
    after = _snapshot(paths, "post")
    failures = _compare(before, after, verbose=args.verbose)

    print()
    print("=" * 60)
    if failures:
        print(f"FAIL — {len(failures)} file(s) were MODIFIED during the test!\n")
        for line in failures:
            print(line)
        print()
        sys.exit(1)
    else:
        print(f"PASS — {n:,} files checked. Zero modifications detected.")
        if idx_file:
            print(f"  Index written: {idx_file}")
        print(f"  Match summary: {found:,} found  "
              f"{missing:,} missing  {errors} errors")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
