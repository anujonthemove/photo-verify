import threading

_state = {
    'cfg': {
        'src':         '',
        'dest':        '',
        'missing_dir': '',
        'review_dir':  '',
        'move_mode':   False,   # False = copy, True = move
    },
    'src_photos': [],           # sorted list of absolute paths
    'dest_idx': {
        'fname':      {},       # lowercase_basename → [path, ...]
        'exif':       {},       # "YYYY:MM:DD HH:MM:SS|size" → [path, ...]
        'hash':       {},       # md5hex → path  (built lazily)
        'video':      {},       # "filename|size" → [path, ...]
        'phash_list': [],       # [(dhash_int, path), ...] built at index load time
    },
    'idx_status': {
        'phase':   'idle',      # idle | scanning | building | done | error
        'current': 0,
        'total':   0,
        'msg':     'Not started.',
    },
    'action_log': [],
    'progress':    {},          # src_path → 'found'|'missing'|'review'
    'match_paths': {},          # src_path → {method, path, n}  (parallel to progress)
    'active_cache':   '',        # path to the currently-active legacy cache file
    'active_index':   '',        # path to the currently-loaded master index file
    'active_session': '',        # path to the current session file
    'browse_root':    '',        # folder the Browse tab is currently rooted at
    'last_idx':       0,         # last viewed photo index
    'session_ts':     '',        # timestamp subfolder for output files this session
    '_thumb_cache':  {},        # path → jpeg_bytes  (LRU-ish)
    '_thumb_order':  [],        # insertion order for eviction
    '_state_lock':   threading.Lock(),
    'browse': {
        'phase':   'idle',   # idle | done | error
        'msg':     '',
        'items':   [],       # list[dict] — type, path, name, video_path
        'folder':  '',
        'summary': {},       # {total, live, static}
    },
    'analyze': {
        'phase':       'idle',  # idle | scanning | done | error
        'folder':      '',
        'scanned':     0,
        'msg':         '',
        'report_html': '',
        'summary':     {},
    },
    'compare': {
        'phase':         'idle',  # idle | scanning | done | error
        'current':       0,
        'total':         0,
        'msg':           '',
        'report_html':   '',
        'summary':       {},
        'missing_files': [],      # list[dict] for save action
    },
}
