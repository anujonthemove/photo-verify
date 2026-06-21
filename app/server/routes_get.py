import os
import json
import mimetypes as _mt
from pathlib import Path
from urllib.parse import unquote

from app.state import _state
from app.storage import (
    list_cache_files, list_index_files, list_session_files,
    _get_active_index_folder,
)
from app.scanner import make_thumbnail, scan_all_media, get_exif_datetime
from app.matcher import find_match, deep_find
from app.constants import ALL_MEDIA_EXT, VIDEO_EXT
from app.logger import _log

import shutil

STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static')


def _serve_file(handler, path, mime):
    if not os.path.isfile(path):
        handler._404(); return
    data = open(path, 'rb').read()
    handler.send_response(200)
    handler.send_header('Content-Type', mime)
    handler.send_header('Content-Length', str(len(data)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(data)


def dispatch(handler, u, qs):
    if u.path == '/':
        _serve_file(handler, os.path.join(STATIC_DIR, 'index.html'), 'text/html; charset=utf-8')
        return
    if u.path.startswith('/static/'):
        rel  = u.path[len('/static/'):]
        path = os.path.realpath(os.path.join(STATIC_DIR, rel))
        if not path.startswith(os.path.realpath(STATIC_DIR) + os.sep):
            handler._404(); return
        mime, _ = _mt.guess_type(path)
        _serve_file(handler, path, mime or 'application/octet-stream')
        return

    if u.path == '/api/state':
        active_idx = _state.get('active_index', '')
        idx_meta   = {}
        if active_idx and os.path.isfile(active_idx):
            try:
                with open(active_idx, encoding='utf-8') as f:
                    d = json.load(f)
                idx_meta = {'name': d.get('name',''), 'total': d.get('total', 0),
                            'folder': d.get('folder', d.get('dest', ''))}
            except Exception:
                pass
        handler._json({
            'cfg':           _state['cfg'],
            'src_count':     len(_state['src_photos']),
            'idx':           _state['idx_status'],
            'pil':           _get_pil_ok(),
            'log_count':     len(_state['action_log']),
            'active_cache':  _state.get('active_cache', ''),
            'active_index':  active_idx,
            'active_index_meta': idx_meta,
            'browse_root':   _state.get('browse_root', ''),
        })

    elif u.path == '/api/list':
        page    = int(qs.get('p', ['0'])[0])
        per     = 200
        photos  = _state['src_photos']
        start   = page * per
        batch   = photos[start:start + per]
        handler._json({
            'items': [{'i': start + j, 'name': Path(p).name, 'path': p}
                      for j, p in enumerate(batch)],
            'total': len(photos),
            'page':  page,
            'pages': max(1, -(-len(photos) // per)),
        })

    elif u.path == '/api/photo':
        i = int(qs.get('i', ['0'])[0])
        photos = _state['src_photos']
        if 0 <= i < len(photos):
            p = photos[i]
            dt = get_exif_datetime(p) or '—'
            handler._json({
                'idx':  i,
                'name': Path(p).name,
                'path': p,
                'size': os.path.getsize(p),
                'exif_dt': dt,
                'total': len(photos),
            })
        else:
            handler._404()

    elif u.path == '/api/match':
        i = int(qs.get('i', ['0'])[0])
        photos = _state['src_photos']
        if 0 <= i < len(photos):
            handler._json({'match': find_match(photos[i])})
        else:
            handler._404()

    elif u.path == '/api/deep_match':
        i = int(qs.get('i', ['0'])[0])
        photos = _state['src_photos']
        if 0 <= i < len(photos):
            m = deep_find(photos[i])
            handler._json({'match': m})
        else:
            handler._404()

    elif u.path == '/api/log':
        handler._json({'log': _state['action_log'][-200:]})

    elif u.path == '/api/list_caches':
        handler._json({'caches': list_cache_files()})

    elif u.path == '/api/list_indexes':
        handler._json({'indexes': list_index_files()})

    elif u.path == '/api/index_info':
        idx_file = unquote(qs.get('file', [''])[0])
        if not idx_file or not os.path.isfile(idx_file):
            handler._json({'ok': False, 'msg': 'File not found'})
            return
        try:
            with open(idx_file, encoding='utf-8') as f:
                d = json.load(f)
            handler._json({
                'ok':      True,
                'name':    d.get('name', ''),
                'folder':  d.get('folder', d.get('dest', '')),
                'built':   d.get('built', ''),
                'total':   d.get('total', 0),
                'n_fname': len(d.get('fname', {})),
                'n_exif':  len(d.get('exif', {})),
                'n_video': len(d.get('video', {})),
                'file':    idx_file,
                'size_mb': round(os.path.getsize(idx_file) / 1048576, 1),
            })
        except Exception as e:
            handler._json({'ok': False, 'msg': str(e)})

    elif u.path == '/api/list_sessions':
        handler._json({'sessions': list_session_files()})

    elif u.path == '/api/idx_status':
        handler._json(_state['idx_status'])

    # ── Thumbnails ────────────────────────────────────────────────────────────

    elif u.path == '/thumb/src':
        i = int(qs.get('i', ['-1'])[0])
        photos = _state['src_photos']
        if 0 <= i < len(photos):
            data = make_thumbnail(photos[i])
            if data:
                handler._image(data)
            else:
                handler._404()
        else:
            handler._404()

    elif u.path == '/thumb/dest':
        p = unquote(qs.get('p', [''])[0])
        if p and os.path.isfile(p):
            data = make_thumbnail(p)
            if data:
                handler._image(data)
            else:
                handler._404()
        else:
            handler._404()

    elif u.path == '/api/browse_tree':
        req_path = unquote(qs.get('path', [''])[0])
        if not req_path:
            # v2: prefer browse_root override, then active index folder, then cfg.src
            req_path = (_state.get('browse_root', '')
                        or _get_active_index_folder()
                        or _state['cfg'].get('src', ''))
        if not req_path or not os.path.isdir(req_path):
            handler._json({'ok': False, 'msg': 'Invalid path', 'dirs': [], 'files': []})
            return
        dirs, files = [], []
        try:
            with os.scandir(req_path) as it:
                for entry in sorted(it, key=lambda e: e.name.lower()):
                    if entry.name.startswith('.'):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        dirs.append({'name': entry.name, 'path': entry.path})
                    elif entry.is_file(follow_symlinks=False):
                        ext = Path(entry.name).suffix.lower()
                        if ext in ALL_MEDIA_EXT:
                            st = entry.stat()
                            files.append({
                                'name':     entry.name,
                                'path':     entry.path,
                                'is_video': ext in VIDEO_EXT,
                                'size':     st.st_size,
                                'mtime':    st.st_mtime,
                            })
        except PermissionError:
            pass
        handler._json({'ok': True, 'path': req_path, 'dirs': dirs, 'files': files})

    elif u.path == '/api/media':
        p = unquote(qs.get('path', [''])[0])
        if not p or not os.path.isfile(p):
            handler._404()
            return
        # Security: file must be under one of the known roots
        real_p = os.path.realpath(p)
        allowed_roots = [
            _state['cfg'].get('src', ''),
            _state.get('browse_root', ''),
            _get_active_index_folder(),
        ]
        if not any(
            real_p == os.path.realpath(r) or
            real_p.startswith(os.path.realpath(r) + os.sep)
            for r in allowed_roots if r
        ):
            handler.send_response(403)
            handler.end_headers()
            return
        ext  = Path(p).suffix.lower()
        mime = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.gif': 'image/gif',  '.webp': 'image/webp', '.heic': 'image/heic',
            '.mp4': 'video/mp4',  '.mov': 'video/quicktime', '.m4v': 'video/mp4',
            '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo',
            '.3gp': 'video/3gpp', '.wmv': 'video/x-ms-wmv',
            '.webm': 'video/webm', '.flv': 'video/x-flv',
        }.get(ext, 'application/octet-stream')
        file_size = os.path.getsize(p)
        range_hdr = handler.headers.get('Range', '')
        if range_hdr and range_hdr.startswith('bytes='):
            # Partial content (needed for video seeking)
            byte_range = range_hdr[6:].split('-')
            start = int(byte_range[0]) if byte_range[0] else 0
            end   = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
            end   = min(end, file_size - 1)
            length = end - start + 1
            handler.send_response(206)
            handler.send_header('Content-Type', mime)
            handler.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            handler.send_header('Content-Length', str(length))
            handler.send_header('Accept-Ranges', 'bytes')
            handler.end_headers()
            with open(p, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    remaining -= len(chunk)
        else:
            handler.send_response(200)
            handler.send_header('Content-Type', mime)
            handler.send_header('Content-Length', str(file_size))
            handler.send_header('Accept-Ranges', 'bytes')
            handler.send_header('Cache-Control', 'max-age=60')
            handler.end_headers()
            with open(p, 'rb') as f:
                shutil.copyfileobj(f, handler.wfile)

    else:
        handler._404()


def _get_pil_ok():
    try:
        from app.scanner import PIL_OK
        return PIL_OK
    except Exception:
        return False
