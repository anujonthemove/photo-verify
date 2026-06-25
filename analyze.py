#!/usr/bin/env python3
"""analyze.py — Scan any folder and open a self-contained HTML dashboard in the browser.

Usage:
    python analyze.py <folder>
"""

import os, sys, webbrowser

_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _root)

from app.analyzer import scan, render_html, fmt_size


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <folder>")
        sys.exit(1)

    folder = os.path.abspath(sys.argv[1])
    if not os.path.isdir(folder):
        print(f"Error: not a directory: {folder}")
        sys.exit(1)

    print(f"Scanning {folder} ...")

    def _progress(n):
        print(f"  ... {n:,} files scanned", end='\r', flush=True)

    st = scan(folder, on_progress=_progress)
    print(f"  {st.total_files:,} files  {fmt_size(st.total_size)}  "
          f"{len(st.ext_count)} extensions  {st.scan_secs:.2f}s")
    if st.errors:
        print(f"  {st.errors} file(s) could not be read (permission errors)")

    html_content = render_html(st)

    report_path = os.path.join(folder, '_analyze_report.html')
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    except OSError:
        import tempfile
        fd, report_path = tempfile.mkstemp(suffix='_analyze_report.html')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(html_content)

    print(f"  Report: {report_path}")
    webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")


if __name__ == '__main__':
    main()
