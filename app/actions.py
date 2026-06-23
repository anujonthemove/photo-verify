import os
import shutil
import time
from pathlib import Path

from app.state import _state
from app.constants import MISSING_DIR, REVIEW_DIR


def do_action_path(src: str, dest_type: str) -> tuple[bool, str]:
    """Copy/move a source file to missing_dir or review_dir by path."""
    if not src:
        return False, 'Empty path'
    if not os.path.exists(src):
        return False, f'Source file not found: {src}'
    return _copy_to_output(src, dest_type)


def do_action(src_idx: int, dest_type: str) -> tuple[bool, str]:
    """Copy/move a source file to missing_dir or review_dir by index."""
    photos = _state['src_photos']
    if not (0 <= src_idx < len(photos)):
        return False, f'Invalid photo index {src_idx} (total {len(photos)})'
    return _copy_to_output(photos[src_idx], dest_type)


def _copy_to_output(src: str, dest_type: str) -> tuple[bool, str]:

    folder_key = 'missing_dir' if dest_type == 'missing' else 'review_dir'
    out_dir = os.path.expanduser(_state['cfg'][folder_key] or '')
    if not out_dir:
        out_dir = MISSING_DIR if dest_type == 'missing' else REVIEW_DIR
    ts = _state.get('session_ts', '')
    if ts:
        out_dir = os.path.join(out_dir, ts)

    # Safety: refuse to write into src or dest (skip check if either is unconfigured)
    out_real = os.path.realpath(out_dir)
    for guarded in (_state['cfg']['src'], _state['cfg']['dest']):
        if not guarded:
            continue
        g = os.path.realpath(guarded)
        if out_real == g or out_real.startswith(g + os.sep):
            return False, 'Output folder must not be inside src or dest!'

    os.makedirs(out_dir, exist_ok=True)

    name = Path(src).name
    dst  = os.path.join(out_dir, name)
    stem, suf = Path(src).stem, Path(src).suffix

    if os.path.exists(dst):
        # Same size → almost certainly the same file already copied; skip
        if os.path.getsize(dst) == os.path.getsize(src):
            return False, '_skipped_'
        # Different file sharing the same filename → rename with timestamp
        dst = os.path.join(out_dir, f"{stem}_{int(time.time() * 1000)}{suf}")

    try:
        if _state['cfg']['move_mode']:
            shutil.move(src, dst)
            verb = 'Moved'
        else:
            shutil.copy2(src, dst)
            verb = 'Copied'
        _state['action_log'].append({
            't':    time.time(),
            'src':  src,
            'dst':  dst,
            'type': dest_type,
            'verb': verb,
        })
        return True, dst
    except Exception as e:
        return False, str(e)
