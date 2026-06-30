import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from app.constants import INDEX_DIR, VIDEO_EXT
from app.state import _state
from app.scanner import scan_all_media, get_exif_datetime, dhash

_WORKERS = min(8, os.cpu_count() or 4)


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

    # ── Phase 2a: Sequential — fname / EXIF / video indexes ──
    st.update({'phase': 'building', 'abort': False, 'current': 0, 'total': n,
               'msg': f'Found {n} files. Building index…'})
    fname_idx = {}
    exif_idx = {}
    video_idx = {}
    phash_idx = {}
    photo_paths = []   # photos queued for dHash in phase 2b

    for i, path in enumerate(media):
        if st.get('abort'):
            st.update({'phase': 'error', 'msg': 'Aborted by user.'})
            return
        st['current'] = i + 1
        ext = Path(path).suffix.lower()
        lname = Path(path).name.lower()

        fname_idx.setdefault(lname, []).append(path)

        if ext in VIDEO_EXT:
            sz = os.path.getsize(path)
            key = f"{lname}|{sz}"
            video_idx.setdefault(key, []).append(path)
        else:
            dt = get_exif_datetime(path)
            if dt:
                sz = os.path.getsize(path)
                key = f"{dt}|{sz}"
                exif_idx.setdefault(key, []).append(path)
            photo_paths.append(path)

    # ── Phase 2b: Parallel dHash ──
    n_photos = len(photo_paths)
    st.update({
        'total': n + n_photos,
        'msg': f'Computing visual hashes for {n_photos} photos ({_WORKERS} threads)…',
    })

    completed = 0
    with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        futures = {executor.submit(dhash, p): p for p in photo_paths}
        for future in as_completed(futures):
            if st.get('abort'):
                executor.shutdown(wait=False, cancel_futures=True)
                st.update({'phase': 'error', 'msg': 'Aborted by user.'})
                return
            completed += 1
            st['current'] = n + completed
            h = future.result()
            if h is not None:
                path = futures[future]
                phash_idx.setdefault(format(h, '016x'), []).append(path)

    # ── Build v1 files array ──
    # Collect per-file metadata from the indexes we just built.
    # exif_idx key = "datetime|size", video_idx key = "lname|size"
    exif_by_path = {}
    for key, paths in exif_idx.items():
        dt_part = key.rsplit('|', 1)[0]
        for p in paths:
            exif_by_path[p] = dt_part

    phash_by_path = {}
    for hex_h, paths in phash_idx.items():
        for p in paths:
            phash_by_path[p] = hex_h

    files_arr = []
    folder_norm = folder.replace('\\', '/')
    for path in media:
        rel = path.replace('\\', '/').replace(folder_norm + '/', '', 1)
        files_arr.append({
            'p': rel,
            's': os.path.getsize(path),
            'e': exif_by_path.get(path),
            'h': phash_by_path.get(path),
        })

    # ── Save index (write first — only update in-memory state on success) ──
    os.makedirs(INDEX_DIR, exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in '-_' else '_' for c in name)
    idx_path = os.path.join(INDEX_DIR, f"{ts_str}_{safe}_index.json")
    try:
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump({
                'version': 1,
                'name': name,
                'folder': folder,
                'ts': time.time(),
                'built': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'total': n,
                'files': files_arr,
            }, f, separators=(',', ':'), ensure_ascii=False)
    except Exception as e:
        st.update({'phase': 'error', 'msg': f'Index write failed: {e}'})
        return

    # Write succeeded — now update in-memory index so it matches the saved file
    _state['dest_idx']['fname'] = fname_idx
    _state['dest_idx']['exif'] = exif_idx
    _state['dest_idx']['video'] = video_idx
    _state['dest_idx']['phash_list'] = [
        (int(h, 16), p) for h, paths in phash_idx.items() for p in paths
    ]
    _state['active_index'] = idx_path
    st['last_index'] = idx_path

    st.update({
        'phase': 'done',
        'current': n, 'total': n,
        'msg': (f'Done — {n} files indexed '
                f'({len(fname_idx)} filenames, {len(exif_idx)} EXIF, '
                f'{len(video_idx)} video, {len(phash_idx)} visual).'),
    })


def _index_worker():
    """Legacy wrapper — builds index using configured dest folder."""
    _build_index_worker(
        folder=_state['cfg'].get('dest', ''),
        name=Path(_state['cfg'].get('dest', 'index')).name or 'index',
    )
