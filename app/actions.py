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

    name = Path(src).name
    dst  = os.path.join(out_dir, name)
    stem, suf = Path(src).stem, Path(src).suffix

    # Skip if this exact source path was already copied this session
    saved = _state.setdefault('_saved_paths', set())
    if src in saved:
        return False, '_skipped_'

    os.makedirs(out_dir, exist_ok=True)

    if os.path.exists(dst):
        # Name collision with a different source file → disambiguate with parent folder name
        parent = Path(src).parent.name
        dst = os.path.join(out_dir, f"{stem}_{parent}{suf}")
        if os.path.exists(dst):
            dst = os.path.join(out_dir, f"{stem}_{parent}_{int(time.time() * 1000)}{suf}")

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
        saved.add(src)
        return True, dst
    except Exception as e:
        return False, str(e)
