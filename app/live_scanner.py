"""live_scanner.py — Scan a folder and pair Live Photos (image + .MOV same basename)."""

import os
from dataclasses import dataclass
from pathlib import Path

from app.constants import PHOTO_EXT


@dataclass
class PhotoItem:
    type:       str   # 'live' | 'static'
    path:       str   # absolute path to the image file
    name:       str   # display filename (basename of image)
    video_path: str   # absolute path to paired .MOV, or '' for static


def scan_live_photos(folder: str) -> list:
    """Walk folder, pair .MOV files with same-stem images, return sorted PhotoItem list."""
    items = []

    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        images = {}   # stem_lower → full_path  (first image wins if multiple exts)
        movs   = {}   # stem_lower → full_path

        for fname in filenames:
            p    = Path(fname)
            ext  = p.suffix.lower()
            stem = p.stem.lower()
            full = os.path.join(dirpath, fname)

            if ext in PHOTO_EXT:
                if stem not in images:
                    images[stem] = full
            elif ext == '.mov':
                if stem not in movs:
                    movs[stem] = full

        for stem, img_path in images.items():
            if stem in movs:
                items.append(PhotoItem(
                    type='live',
                    path=img_path,
                    name=os.path.basename(img_path),
                    video_path=movs[stem],
                ))
            else:
                items.append(PhotoItem(
                    type='static',
                    path=img_path,
                    name=os.path.basename(img_path),
                    video_path='',
                ))

    items.sort(key=lambda x: x.path.lower())
    return items


def scan_summary(items: list) -> dict:
    live   = sum(1 for it in items if it.type == 'live')
    static = len(items) - live
    return {'total': len(items), 'live': live, 'static': static}


def items_to_dicts(items: list) -> list:
    return [
        {'type': it.type, 'path': it.path, 'name': it.name, 'video_path': it.video_path}
        for it in items
    ]
