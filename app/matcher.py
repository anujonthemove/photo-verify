import os
from pathlib import Path

from app.state import _state
from app.scanner import get_exif_datetime, file_md5, scan_all_media, dhash
from app.constants import VIDEO_EXT

_PHASH_THRESHOLD = 10  # Hamming distance ≤ 10 = visually the same photo

def _hamming(a: int, b: int) -> int:
    try:
        return (a ^ b).bit_count()      # Python 3.10+
    except AttributeError:
        return bin(a ^ b).count('1')    # fallback for older Python


def _dest_size(path: str) -> int:
    """Return file size of a destination path, or -1 if inaccessible."""
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def find_match(src_path: str) -> dict | None:
    """Match: filename+size → EXIF+size → pHash (visual) → video name+size. Returns match dict or None."""
    idx = _state['dest_idx']

    # 1. Filename (case-insensitive) + byte size — prevents false positives on shared names
    fname = Path(src_path).name.lower()
    hits = idx['fname'].get(fname)
    if hits:
        try:
            src_sz = os.path.getsize(src_path)
            size_hits = [p for p in hits if _dest_size(p) == src_sz]
        except OSError:
            size_hits = []
        if size_hits:
            return {'method': 'filename', 'path': size_hits[0], 'n': len(size_hits)}
        # Filename matched but no size agreement — fall through

    ext = Path(src_path).suffix.lower()

    # 2. EXIF datetime + file size (photos only)
    if ext not in VIDEO_EXT:
        dt = get_exif_datetime(src_path)
        if dt:
            sz  = os.path.getsize(src_path)
            key = f"{dt}|{sz}"
            if key in idx['exif']:
                hits = idx['exif'][key]
                return {'method': 'exif', 'path': hits[0], 'n': len(hits)}

    # 3. Perceptual hash — catches re-encoded / re-compressed copies (photos only)
    if ext not in VIDEO_EXT:
        phash_list = idx.get('phash_list', [])
        if phash_list:
            src_h = dhash(src_path)
            if src_h is not None:
                for dest_h, dest_path in phash_list:
                    if _hamming(src_h, dest_h) <= _PHASH_THRESHOLD:
                        return {'method': 'phash', 'path': dest_path, 'n': 1}

    # 4. Video: filename|size key
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
    cached_paths = set(hash_idx.values())  # build once — O(n) not O(n²)
    for dp in scan_all_media(dest):
        if dp in cached_paths:
            continue
        dh = file_md5(dp)
        if dh:
            hash_idx[dh] = dp
            cached_paths.add(dp)
            if dh == src_hash:
                return {'method': 'hash', 'path': dp, 'n': 1}

    return None
