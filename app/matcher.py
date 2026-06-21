import os
from pathlib import Path

from app.state import _state
from app.scanner import get_exif_datetime, file_md5, scan_photos
from app.constants import VIDEO_EXT


def find_match(src_path: str) -> dict | None:
    """Fast match: filename → EXIF. Returns match dict or None."""
    idx = _state['dest_idx']

    # 1. Filename (case-insensitive)
    fname = Path(src_path).name.lower()
    if fname in idx['fname']:
        hits = idx['fname'][fname]
        return {'method': 'filename', 'path': hits[0], 'n': len(hits)}

    # 2. EXIF datetime + file size (photos)
    ext = Path(src_path).suffix.lower()
    if ext not in VIDEO_EXT:
        dt = get_exif_datetime(src_path)
        if dt:
            sz  = os.path.getsize(src_path)
            key = f"{dt}|{sz}"
            if key in idx['exif']:
                hits = idx['exif'][key]
                return {'method': 'exif', 'path': hits[0], 'n': len(hits)}

    # 3. Video: filename|size key
    if ext in VIDEO_EXT:
        sz  = os.path.getsize(src_path)
        key = f"{fname}|{sz}"
        if key in idx.get('video', {}):
            hits = idx['video'][key]
            return {'method': 'video', 'path': hits[0], 'n': len(hits)}

    return None

def deep_find(src_path: str) -> dict | None:
    """
    Hash-based match. Computes MD5 of src, then scans entire dest folder
    computing hashes on the fly (slow — only call when fast match fails).
    Results are cached to speed up subsequent calls.
    """
    src_hash = file_md5(src_path)
    if not src_hash:
        return None

    hash_idx = _state['dest_idx']['hash']

    # Check already-computed hash cache
    if src_hash in hash_idx:
        return {'method': 'hash', 'path': hash_idx[src_hash], 'n': 1}

    # Scan dest, building hash cache as we go
    dest = _state['cfg']['dest']
    for dp in scan_photos(dest):
        if dp in hash_idx.values():
            continue  # already cached this path → different hash
        dh = file_md5(dp)
        if dh:
            hash_idx[dh] = dp
            if dh == src_hash:
                return {'method': 'hash', 'path': dp, 'n': 1}

    return None
