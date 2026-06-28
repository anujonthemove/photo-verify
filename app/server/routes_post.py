import os
import json
import threading
from pathlib import Path

from app.state import _state
from app.storage import (
    _persist_config, _load_index, _new_session, _load_session,
    _load_config_for_cache, _save_session, _save_progress, list_cache_files,
)
from app.scanner import scan_all_media
from app.matcher import find_match
from app.actions import do_action, do_action_path  # noqa: F401
from app.indexer import _build_index_worker, _index_worker
from app.constants import INDEX_DIR, MISSING_DIR
from app.logger import _log


def dispatch(handler, u, body):
    try:
        _dispatch_inner(handler, u, body)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        _log(f"Unhandled POST error:\n{tb.rstrip()}")
        handler._json({'ok': False, 'msg': tb.splitlines()[-1]}, code=500)


def _dispatch_inner(handler, u, body):
    if u.path == '/api/configure':
        cfg = body.get('cfg', {})
        for k in ('src', 'dest', 'missing_dir', 'review_dir', 'move_mode'):
            if k in cfg:
                _state['cfg'][k] = cfg[k]
        _persist_config()
        # Backfill src into the active cache so future loads can recover it
        cache_file = _state.get('active_cache', '')
        if cache_file and os.path.isfile(cache_file) and _state['cfg'].get('src'):
            try:
                with open(cache_file) as f:
                    cdata = json.load(f)
                cdata['src'] = _state['cfg']['src']
                with open(cache_file, 'w') as f:
                    json.dump(cdata, f, separators=(',', ':'))
            except Exception:
                pass
        # Re-scan src (use scan_all_media so videos are included)
        src = _state['cfg']['src']
        if src:
            _state['src_photos'] = scan_all_media(src) if os.path.isdir(src) else []
        handler._json({'ok': True, 'src_count': len(_state['src_photos'])})

    elif u.path == '/api/start_index':
        if _state['idx_status']['phase'] in ('scanning', 'building'):
            handler._json({'ok': False, 'msg': 'Already indexing — please wait.'})
            return
        if body.get('dest'):
            _state['cfg']['dest'] = body['dest']
        dest = _state['cfg'].get('dest', '')
        if not dest:
            handler._json({'ok': False, 'msg': 'Set destination folder first.'})
            return
        # Reset
        _state['dest_idx'] = {'fname': {}, 'exif': {}, 'hash': {}, 'video': {}}
        _state['idx_status'] = {
            'phase': 'starting', 'current': 0, 'total': 0, 'msg': 'Starting…'
        }
        threading.Thread(target=_index_worker, daemon=True).start()
        handler._json({'ok': True})

    elif u.path == '/api/build_index':
        folder = body.get('folder', '').strip()
        name   = body.get('name', '').strip()
        if not folder or not os.path.isdir(folder):
            handler._json({'ok': False, 'msg': f'Folder not found: {folder}'})
            return
        if not name:
            name = Path(folder).name or 'index'
        if _state['idx_status']['phase'] in ('scanning', 'building'):
            handler._json({'ok': False, 'msg': 'Already indexing — please wait.'})
            return
        _state['dest_idx'] = {'fname': {}, 'exif': {}, 'hash': {}, 'video': {}}
        _state['idx_status'] = {
            'phase': 'starting', 'current': 0, 'total': 0, 'msg': 'Starting…'
        }
        threading.Thread(
            target=_build_index_worker, args=(folder, name), daemon=True
        ).start()
        handler._json({'ok': True})

    elif u.path == '/api/abort_index':
        _state['idx_status']['abort'] = True
        handler._json({'ok': True})

    elif u.path == '/api/load_index':
        idx_file = body.get('file', '').strip()
        if not idx_file or not os.path.isfile(idx_file):
            handler._json({'ok': False, 'msg': f'Index file not found: {idx_file}'})
            return
        try:
            data = _load_index(idx_file)
            handler._json({
                'ok':     True,
                'name':   data.get('name', ''),
                'total':  data.get('total', 0),
                'folder': data.get('folder', ''),
            })
        except Exception as e:
            handler._json({'ok': False, 'msg': str(e)})

    elif u.path == '/api/new_session':
        idx_file = body.get('index_file', '').strip()
        source   = body.get('source', '').strip()
        if not idx_file or not os.path.isfile(idx_file):
            handler._json({'ok': False, 'msg': 'Load an index first.'})
            return
        if not source or not os.path.isdir(source):
            handler._json({'ok': False, 'msg': f'Source folder not found: {source}'})
            return
        _load_index(idx_file)
        _state['cfg']['src']  = source
        _state['src_photos']  = scan_all_media(source)
        ses_path = _new_session(idx_file, source)
        _persist_config()
        handler._json({
            'ok':      True,
            'session': ses_path,
            'n_src':   len(_state['src_photos']),
        })

    elif u.path == '/api/load_session':
        ses_file = body.get('file', '').strip()
        if not ses_file or not os.path.isfile(ses_file):
            handler._json({'ok': False, 'msg': f'Session file not found: {ses_file}'})
            return
        try:
            data     = _load_session(ses_file)
            progress = _state['progress']
            n_src    = len(_state['src_photos'])
            handler._json({
                'ok':      True,
                'n_src':   n_src,
                'last_idx': data.get('last_idx', 0),
                'progress': {k: v for k, v in list(progress.items())[:500]},
                'stats':   data.get('stats', {}),
                'source':  data.get('source', ''),
                'index':   os.path.basename(data.get('index_file', '')),
                'cfg':     _state['cfg'],
            })
        except Exception as e:
            handler._json({'ok': False, 'msg': str(e)})

    elif u.path == '/api/delete_index':
        idx_file = body.get('file', '').strip()
        # Security: only allow deleting files inside INDEX_DIR
        if not idx_file or not os.path.abspath(idx_file).startswith(os.path.abspath(INDEX_DIR)):
            handler._json({'ok': False, 'msg': 'Invalid path.'})
            return
        try:
            if os.path.isfile(idx_file):
                os.remove(idx_file)
            handler._json({'ok': True})
        except Exception as e:
            handler._json({'ok': False, 'msg': str(e)})

    elif u.path == '/api/move':
        dest_type = body.get('type', 'missing')
        path = body.get('path', '')
        if path:
            ok, result = do_action_path(path, dest_type)
        else:
            ok, result = do_action(body.get('i', -1), dest_type)
        handler._json({'ok': ok, 'result': result})

    elif u.path == '/api/load_cache':
        file = body.get('file', '')
        if not file or not os.path.isfile(file):
            handler._json({'ok': False, 'msg': 'Cache file not found.'})
            return
        try:
            with open(file) as f:
                cache = json.load(f)
            _state['dest_idx']['fname'] = cache['fname']
            _state['dest_idx']['exif']  = cache['exif']
            _state['dest_idx']['hash']  = {}
            _state['progress']    = cache.get('progress', {})
            _state['last_idx']    = cache.get('last_idx', 0)
            _state['active_cache'] = file
            _state['session_ts'] = '_'.join(os.path.basename(file).split('_')[:2])
            # src/dest are stored in the cache itself — always restore them
            if cache.get('src'):
                _state['cfg']['src']  = cache['src']
            if cache.get('dest'):
                _state['cfg']['dest'] = cache['dest']
            # missing_dir/review_dir/move_mode come from the matching config yaml
            _load_config_for_cache(file)
            n = sum(len(v) for v in cache['fname'].values())
            _state['idx_status'].update({
                'phase': 'done', 'current': n, 'total': n,
                'msg': f'Loaded from cache — {n} photos indexed.',
            })
            handler._json({'ok': True, 'n': n,
                        'progress': _state['progress'],
                        'last_idx': _state['last_idx'],
                        'cfg': _state['cfg']})
        except Exception as e:
            handler._json({'ok': False, 'msg': str(e)})

    elif u.path == '/api/save_progress_bulk':
        idx_map  = body.get('idx_map', {})
        last_idx = body.get('last_idx', 0)
        cache_file = _state.get('active_cache', '')
        if not cache_file:
            handler._json({'ok': False, 'msg': 'No active cache — index or load a cache first.'})
            return
        photos = _state['src_photos']
        progress = {}
        for idx_str, status in idx_map.items():
            idx = int(idx_str)
            if 0 <= idx < len(photos) and status in ('found', 'missing', 'review'):
                progress[photos[idx]] = status
        _state['progress'] = progress
        _state['last_idx'] = last_idx
        try:
            with open(cache_file) as f:
                data = json.load(f)
            data['progress'] = progress
            data['last_idx'] = last_idx
            with open(cache_file, 'w') as f:
                json.dump(data, f, separators=(',', ':'))
            handler._json({'ok': True, 'saved': len(progress)})
        except Exception as e:
            _log(f"Bulk progress save failed: {e}")
            handler._json({'ok': False, 'msg': str(e)})

    elif u.path == '/api/bulk_action':
        paths     = body.get('paths', [])
        dest_type = body.get('type', 'missing')
        succeeded, failed, skipped = [], [], 0
        out_folder = ''
        for path in paths:
            ok, result = do_action_path(path, dest_type)
            if ok:
                succeeded.append(path)
                if not out_folder:
                    out_folder = os.path.dirname(result)
            elif result == '_skipped_':
                skipped += 1
            else:
                failed.append({'path': path, 'msg': result})
        handler._json({'ok': True, 'saved': len(succeeded),
                    'skipped': skipped, 'failed': failed,
                    'out_folder': out_folder})

    elif u.path == '/api/batch_match':
        force   = body.get('force', False)
        start   = int(body.get('start', 0))
        count   = body.get('count', None)
        photos  = _state['src_photos']
        prog    = _state['progress']
        results = []
        found   = missing = skipped = 0
        subset  = photos[start:start + count] if count is not None else photos[start:]
        for j, path in enumerate(subset):
            i = start + j
            if not force and path in prog:
                skipped += 1
                results.append({'i': i, 'path': path, 'status': prog[path], 'method': None})
                continue
            m = find_match(path)
            if m:
                status = 'found'
                found += 1
            else:
                status = 'missing'
                missing += 1
            prog[path] = status
            results.append({'i': i, 'path': path, 'status': status,
                            'method':     m['method'] if m else None,
                            'match_path': m['path']   if m else None,
                            'match_n':    m['n']       if m else 0})
        _state['progress'] = prog
        # Persist to active session or legacy cache
        ses = _state.get('active_session', '')
        if ses and os.path.isfile(ses):
            _save_session()
        else:
            cache_file = _state.get('active_cache', '')
            if cache_file and os.path.isfile(cache_file):
                try:
                    with open(cache_file, encoding='utf-8') as f:
                        data = json.load(f)
                    data['progress'] = prog
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, separators=(',', ':'))
                except Exception as e:
                    _log(f"Batch match cache write failed: {e}")
        handler._json({'ok': True, 'results': results,
                    'found': found, 'missing': missing,
                    'skipped': skipped, 'total': len(photos)})

    elif u.path == '/api/set_browse_root':
        root = body.get('root', '').strip()
        if root and os.path.isdir(root):
            _state['browse_root'] = root
            handler._json({'ok': True, 'root': root})
        else:
            handler._json({'ok': False, 'msg': f'Folder not found: {root}'})

    elif u.path == '/api/save_position':
        idx = body.get('idx', 0)
        _state['last_idx'] = idx
        cache_file = _state.get('active_cache', '')
        if cache_file and os.path.isfile(cache_file):
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                data['last_idx'] = idx
                with open(cache_file, 'w') as f:
                    json.dump(data, f, separators=(',', ':'))
            except Exception as e:
                _log(f"Position save failed: {e}")
        handler._json({'ok': True})

    elif u.path == '/api/update_progress':
        src_path = body.get('path', '')
        status   = body.get('status', '')
        if src_path and status in ('found', 'missing', 'review'):
            _save_progress(src_path, status)
            handler._json({'ok': True})
        else:
            handler._json({'ok': False, 'msg': 'Invalid path or status'})

    elif u.path == '/api/clear_cache':
        file = body.get('file', '')
        try:
            if file:
                os.remove(file)
                msg = f'Deleted: {os.path.basename(file)}'
            else:
                # delete all
                deleted = 0
                for e in list_cache_files():
                    try: os.remove(e['file']); deleted += 1
                    except Exception: pass
                msg = f'Deleted {deleted} cache file(s).'
        except FileNotFoundError:
            msg = 'Cache file not found.'
        except Exception as ex:
            msg = str(ex)
        handler._json({'ok': True, 'msg': msg})

    elif u.path == '/api/compare/start':
        master  = body.get('master', '').strip()
        backups = [f.strip() for f in body.get('backups', []) if f.strip()]
        if not master:
            handler._json({'ok': False, 'msg': 'Master folder is required.'})
            return
        if not os.path.isdir(master):
            handler._json({'ok': False, 'msg': f'Master folder not found: {master}'})
            return
        if len(backups) < 1:
            handler._json({'ok': False, 'msg': 'Provide at least one backup folder.'})
            return
        bad = [f for f in backups if not os.path.isdir(f)]
        if bad:
            handler._json({'ok': False, 'msg': f'Not a directory: {bad[0]}'})
            return
        if _state['compare']['phase'] == 'scanning':
            handler._json({'ok': False, 'msg': 'Comparison already in progress.'})
            return
        from app.comparator import _compare_master_worker
        threading.Thread(
            target=_compare_master_worker, args=(master, backups), daemon=True
        ).start()
        handler._json({'ok': True})

    elif u.path == '/api/compare/save_missing':
        cz = _state['compare']
        if cz['phase'] != 'done':
            handler._json({'ok': False, 'msg': 'Run a comparison first.'})
            return
        missing = cz.get('missing_files', [])
        if not missing:
            handler._json({'ok': False, 'msg': 'No missing files to save.'})
            return
        import datetime as _dt
        from app.comparator import save_missing_files
        ts      = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        out_dir = os.path.join(MISSING_DIR, ts)
        result  = save_missing_files(missing, out_dir)
        handler._json({'ok': True, **result})

    elif u.path == '/api/browse/load':
        folder = body.get('folder', '').strip()
        if not folder or not os.path.isdir(folder):
            handler._json({'ok': False, 'msg': f'Folder not found: {folder}'})
            return
        from app.live_scanner import scan_live_photos, scan_summary, items_to_dicts
        br = _state['browse']
        br['phase']  = 'scanning'
        br['folder'] = folder
        br['items']  = []
        br['summary'] = {}
        try:
            items = scan_live_photos(folder)
            br['items']   = items_to_dicts(items)
            br['summary'] = scan_summary(items)
            br['phase']   = 'done'
            br['msg']     = ''
            handler._json({'ok': True, **br['summary']})
        except Exception as e:
            br['phase'] = 'error'
            br['msg']   = str(e)
            handler._json({'ok': False, 'msg': str(e)})

    elif u.path == '/api/analyze/start':
        folder = body.get('folder', '').strip()
        if not folder or not os.path.isdir(folder):
            handler._json({'ok': False, 'msg': f'Folder not found: {folder}'})
            return
        if _state['analyze']['phase'] == 'scanning':
            handler._json({'ok': False, 'msg': 'Scan already in progress.'})
            return
        from app.analyzer import _analyze_worker
        threading.Thread(target=_analyze_worker, args=(folder,), daemon=True).start()
        handler._json({'ok': True})

    elif u.path == '/api/shutdown':
        srv = _state.get('_server')
        if not srv:
            handler._json({'ok': False, 'msg': 'No server reference.'})
            return
        handler._json({'ok': True, 'msg': 'Shutting down…'})
        threading.Thread(target=srv.shutdown, daemon=True).start()

    else:
        handler._404()
