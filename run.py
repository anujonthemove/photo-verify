#!/usr/bin/env python3
import sys, webbrowser, threading, time
from http.server import HTTPServer

# ─── Dependency bootstrap ────────────────────────────────────────────────────

def _pip_install(pkg):
    import subprocess
    print(f"  Installing {pkg}...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

try:
    from PIL import Image, ExifTags
except ImportError:
    try:
        _pip_install("Pillow")
    except Exception as e:
        print(f"  Warning: Pillow unavailable ({e}). Thumbnails and EXIF matching disabled.")

try:
    import yaml
except ImportError:
    try:
        _pip_install("pyyaml")
    except Exception as e:
        print(f"  Warning: PyYAML unavailable ({e}). Config persistence disabled.")

from app.server.handler import PhotoVerifyHandler
from app.constants import PORT


class _QuietHTTPServer(HTTPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        import sys, traceback
        if sys.exc_info()[0] in (
            ConnectionAbortedError, ConnectionResetError, BrokenPipeError
        ):
            return  # browser cancelled the request — not an app error
        from app.logger import _log
        _log(f"Request from {client_address}:\n{traceback.format_exc().rstrip()}")


def main():
    print()
    print("┌─────────────────────────────────────────────┐")
    print("│   PhotoVerify — Photo Backup Checker         │")
    print("│   github: your local photo forensics tool    │")
    print("└─────────────────────────────────────────────┘")
    print()

    # Import here after bootstrap so PIL_OK reflects actual availability
    from app.scanner import PIL_OK
    if not PIL_OK:
        print("  ⚠  Pillow unavailable. Install with:  pip3 install Pillow")
        print()

    from app.constants import CACHE_DIR, CONFIG_DIR, LOGS_DIR
    print(f"  Serving at: http://localhost:{PORT}")
    print(f"  Cache dir:  {CACHE_DIR}")
    print(f"  Config dir: {CONFIG_DIR}")
    print(f"  Logs dir:   {LOGS_DIR}")
    print("  Press Ctrl+C to stop.")
    print()

    def _open():
        time.sleep(1.2)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=_open, daemon=True).start()

    from app.state import _state
    server = _QuietHTTPServer(("127.0.0.1", PORT), PhotoVerifyHandler)
    _state['_server'] = server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        import logging
        logging.shutdown()
        server.server_close()
        print("\n  Stopped. Goodbye.")
        sys.exit(0)

if __name__ == '__main__':
    main()
