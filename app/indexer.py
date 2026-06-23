import os
import json
import time
import threading
from datetime import datetime
from pathlib import Path

from app.constants import INDEX_DIR, VIDEO_EXT, PHOTO_EXT
from app.state import _state
from app.scanner import scan_all_media, get_exif_datetime
from app.storage import _new_session
from app.logger import _log


def _build_index_worker(folder: str, name: str):
    """Build a master index for folder and save to indexes/."""
    st = _state['idx_status']

    if not folder or not os.path.isdir(folder):
        st.update({'phase': 'error', 'msg': f'Folder not accessible: {folder}'})
        return

    # ── Phase 1: Scan all media (photos + videos) ──
    st.update({'phase': 'scanning', 'current': 0, 'total': 0,
               'msg': f'Scanning {folder}…'})
    media = scan_all_media(folder)
    n = len(media)
    st.update({'total': n, 'msg': f'Found {n} files. Building index…'})

    # ── Phase 2: Build indexes ──
    st['phase'] = 'building'
    st['abort'] = False
    fname_idx: dict = {}
    exif_idx:  dict = {}
    video_idx: dict = {}

    for i, path in enumerate(media):
        if st.get('abort'):
            st.update({'phase': 'error', 'msg': 'Aborted by user.'})
            return
        st['current'] = i + 1
        ext = Path(path).suffix.lower()
        lname = Path(path).name.lower()

        fname_idx.setdefault(lname, []).append(path)

        if ext in VIDEO_EXT:
            sz  = os.path.getsize(path)
            key = f"{lname}|{sz}"
            video_idx.setdefault(key, []).append(path)
        else:
            dt = get_exif_datetime(path)
            if dt:
                sz  = os.path.getsize(path)
                key = f"{dt}|{sz}"
                exif_idx.setdefault(key, []).append(path)

    _state['dest_idx']['fname'] = fname_idx
    _state['dest_idx']['exif']  = exif_idx
    _state['dest_idx']['video'] = video_idx

    # ── Save index ──
    os.makedirs(INDEX_DIR, exist_ok=True)
    ts_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe    = "".join(c if c.isalnum() or c in '-_' else '_' for c in name)
    idx_path = os.path.join(INDEX_DIR, f"{ts_str}_{safe}_index.json")
    try:
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump({
                'name':   name,
                'folder': folder,
                'ts':     time.time(),
                'built':  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'total':  n,
                'fname':  fname_idx,
                'exif':   exif_idx,
                'video':  video_idx,
            }, f, separators=(',', ':'), ensure_ascii=False)
        _state['active_index'] = idx_path
        st['last_index'] = idx_path
    except Exception as e:
        st.update({'phase': 'error', 'msg': f'Index write failed: {e}'})
        return

    st.update({
        'phase':   'done',
        'current': n, 'total': n,
        'msg':     f'Done — {n} files indexed ({len(fname_idx)} filenames, '
                   f'{len(exif_idx)} EXIF, {len(video_idx)} video entries).',
    })

def _index_worker():
    """Legacy wrapper — builds index using configured dest folder."""
    _build_index_worker(
        folder=_state['cfg'].get('dest', ''),
        name=Path(_state['cfg'].get('dest', 'index')).name or 'index',
    )
