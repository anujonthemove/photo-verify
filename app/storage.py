import os
import json
import time
from datetime import datetime
try:
    import yaml
    YAML_OK = True
except ImportError:
    YAML_OK = False

from app.constants import CACHE_DIR, INDEX_DIR, SESSION_DIR, CONFIG_DIR
from app.state import _state
from app.logger import _log


def list_cache_files() -> list:
    """Return cache entries sorted newest-first."""
    if not os.path.isdir(CACHE_DIR):
        return []
    entries = []
    for name in sorted(os.listdir(CACHE_DIR), reverse=True):
        if not name.endswith("_photoverify_cache.json"):
            continue
        full = os.path.join(CACHE_DIR, name)
        try:
            with open(full) as f:
                meta = json.load(f)
            n = sum(len(v) for v in meta.get('fname', {}).values())
            entries.append({
                'file': full,
                'name': name,
                'dest': meta.get('dest', ''),
                'ts':   meta.get('ts', 0),
                'n':    n,
            })
        except Exception:
            pass
    return entries

def list_index_files() -> list:
    """Return saved master indexes sorted newest-first."""
    if not os.path.isdir(INDEX_DIR):
        return []
    entries = []
    for fname in sorted(os.listdir(INDEX_DIR), reverse=True):
        if not fname.endswith('_index.json'):
            continue
        full = os.path.join(INDEX_DIR, fname)
        try:
            with open(full, encoding='utf-8') as f:
                meta = json.load(f)
            entries.append({
                'file':   full,
                'name':   meta.get('name', fname),
                'folder': meta.get('folder', ''),
                'total':  meta.get('total', 0),
                'built':  meta.get('built', ''),
                'ts':     meta.get('ts', 0),
            })
        except Exception:
            pass
    return entries

def _load_index(index_file: str):
    """Load a master index file into _state['dest_idx']."""
    with open(index_file, encoding='utf-8') as f:
        data = json.load(f)
    # Support legacy cache format (no 'name' field)
    _state['dest_idx']['fname'] = data.get('fname', {})
    _state['dest_idx']['exif']  = data.get('exif',  {})
    _state['dest_idx']['video'] = data.get('video', {})
    _state['dest_idx']['hash']  = {}
    _state['active_index'] = index_file
    # Set cfg.dest so deep_find can scan the master folder if needed
    folder = data.get('folder', '') or data.get('dest', '')
    if folder:
        _state['cfg']['dest'] = folder
    return data

def _get_active_index_folder() -> str:
    """Return the master folder path from the currently loaded index, or ''."""
    idx_file = _state.get('active_index', '')
    if not idx_file or not os.path.isfile(idx_file):
        return ''
    try:
        with open(idx_file, encoding='utf-8') as f:
            data = json.load(f)
        return data.get('folder', '') or data.get('dest', '')
    except Exception:
        return ''

def _config_path() -> str:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    ts = _state.get('session_ts', '') or datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(CONFIG_DIR, f"{ts}_photoverify_config.yaml")

def _apply_config_dict(saved: dict):
    for k in ('src', 'dest', 'missing_dir', 'review_dir', 'move_mode'):
        if k in saved:
            _state['cfg'][k] = saved[k]

def _nearest_config_yaml(ts: str):
    """Return path to the config yaml closest in time to ts (within 5 min), or None."""
    if not os.path.isdir(CONFIG_DIR):
        return None
    try:
        cache_dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
    except ValueError:
        return None
    best_path, best_delta = None, None
    for fname in os.listdir(CONFIG_DIR):
        if not fname.endswith('_photoverify_config.yaml'):
            continue
        f_ts = '_'.join(fname.split('_')[:2])
        try:
            delta = abs((datetime.strptime(f_ts, "%Y%m%d_%H%M%S") - cache_dt).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta, best_path = delta, os.path.join(CONFIG_DIR, fname)
        except ValueError:
            continue
    return best_path if (best_delta is not None and best_delta <= 300) else None

def _load_config_for_cache(cache_path: str):
    """Load the config file whose timestamp matches the given cache file."""
    if not YAML_OK:
        return
    basename = os.path.basename(cache_path)
    ts       = '_'.join(basename.split('_')[:2])
    cfg_path = os.path.join(CONFIG_DIR, f"{ts}_photoverify_config.yaml")
    if not os.path.isfile(cfg_path):
        cfg_path = _nearest_config_yaml(ts)
    if not cfg_path:
        return
    try:
        with open(cfg_path) as f:
            _apply_config_dict(yaml.safe_load(f) or {})
    except Exception as e:
        print(f"  Config load for cache failed: {e}")

def _persist_config():
    """Write current config to config/<session_ts>_photoverify_config.yaml."""
    if not YAML_OK:
        return
    try:
        with open(_config_path(), 'w') as f:
            yaml.dump(dict(_state['cfg']), f, default_flow_style=False, allow_unicode=True)
    except Exception as e:
        print(f"  Config save failed: {e}")

def _new_session(index_file: str, source: str) -> str:
    """Create a new session JSON and activate it. Returns session file path."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    ts_str   = datetime.now().strftime("%Y%m%d_%H%M%S")
    ses_path = os.path.join(SESSION_DIR, f"{ts_str}_session.json")
    data = {
        'index_file': index_file,
        'source':     source,
        'ts':         time.time(),
        'started':    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'progress':   {},
        'last_idx':   0,
        'stats':      {'found': 0, 'missing': 0, 'review': 0},
    }
    with open(ses_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
    _state['active_session'] = ses_path
    _state['session_ts']     = ts_str
    _state['progress']       = {}
    _state['last_idx']       = 0
    _state['_saved_paths']   = set()
    return ses_path

def _save_session():
    """Persist current progress/stats to the active session file."""
    ses = _state.get('active_session', '')
    if not ses:
        return
    try:
        with open(ses, encoding='utf-8') as f:
            data = json.load(f)
        data['progress'] = _state['progress']
        data['last_idx'] = _state['last_idx']
        data['stats']    = {
            'found':   sum(1 for s in _state['progress'].values() if s == 'found'),
            'missing': sum(1 for s in _state['progress'].values() if s == 'missing'),
            'review':  sum(1 for s in _state['progress'].values() if s == 'review'),
        }
        with open(ses, 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
    except Exception as e:
        _log(f"Session save failed: {e}")

def _load_session(ses_path: str) -> dict:
    """Load a session file, restore index + source + progress into _state."""
    from app.scanner import scan_all_media
    with open(ses_path, encoding='utf-8') as f:
        data = json.load(f)
    idx_file = data.get('index_file', '')
    if idx_file and os.path.isfile(idx_file):
        _load_index(idx_file)
    source = data.get('source', '')
    if source:
        _state['cfg']['src']  = source
        _state['src_photos']  = scan_all_media(source) if os.path.isdir(source) else []
    _state['progress']       = data.get('progress', {})
    _state['last_idx']       = data.get('last_idx', 0)
    _state['active_session'] = ses_path
    _state['session_ts']     = '_'.join(os.path.basename(ses_path).split('_')[:2])
    return data

def list_session_files() -> list:
    """Return sessions sorted newest-first."""
    if not os.path.isdir(SESSION_DIR):
        return []
    entries = []
    for fname in sorted(os.listdir(SESSION_DIR), reverse=True):
        if not fname.endswith('_session.json'):
            continue
        full = os.path.join(SESSION_DIR, fname)
        try:
            with open(full, encoding='utf-8') as f:
                d = json.load(f)
            entries.append({
                'file':       full,
                'source':     d.get('source', ''),
                'index_file': d.get('index_file', ''),
                'index':      os.path.basename(d.get('index_file', '')),
                'started':    d.get('started', ''),
                'ts':         d.get('ts', 0),
                'stats':      d.get('stats', {}),
            })
        except Exception:
            pass
    return entries

def _save_progress(src_path: str, status: str):
    """Write one progress entry into the active session or legacy cache file."""
    _state['progress'][src_path] = status
    # New flow: persist to session file
    ses = _state.get('active_session', '')
    if ses and os.path.isfile(ses):
        _save_session()
        return
    # Legacy flow: persist to cache file
    cache_file = _state.get('active_cache', '')
    if not cache_file or not os.path.isfile(cache_file):
        return
    try:
        with open(cache_file) as f:
            data = json.load(f)
        data['progress'] = _state['progress']
        data['last_idx'] = _state['last_idx']
        with open(cache_file, 'w') as f:
            json.dump(data, f, separators=(',', ':'))
    except Exception as e:
        _log(f"Progress save failed: {e}")
