"""live_scanner.py — Scan a folder and pair Live Photos (image + .MOV same basename)."""

import os
from dataclasses import dataclass
from pathlib import Path

from app.constants import PHOTO_EXT, VIDEO_EXT


@dataclass
class PhotoItem:
    type:       str   # 'live' | 'static' | 'video'
    path:       str   # absolute path to the primary file (image for live/static, video for video)
    name:       str   # display filename
    video_path: str   # absolute path to video (paired .MOV for live, same as path for video)


def scan_live_photos(folder: str) -> list:
    """Walk folder, pair .MOV files with same-stem images, return sorted PhotoItem list.

    Types returned:
      'live'   — image file paired with a same-stem .MOV (Apple Live Photo)
      'static' — image file with no paired video
      'video'  — standalone video file (no paired image)
    """
    items = []

    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        images = {}   # stem_lower → full_path  (first image wins if multiple exts)
        movs   = {}   # stem_lower → full_path  (.mov only — Apple Live Photo pairing)
        others = []   # all non-.mov VIDEO_EXT files (always standalone)

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
            elif ext in VIDEO_EXT:
                others.append(full)

        # Image items — paired .mov = live, unpaired = static
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

        # Standalone .mov files — no paired image
        for stem, vid_path in movs.items():
            if stem not in images:
                items.append(PhotoItem(
                    type='video',
                    path=vid_path,
                    name=os.path.basename(vid_path),
                    video_path=vid_path,
                ))

        # All other video formats (.mp4, .mkv, etc.) — always standalone
        for vid_path in others:
            items.append(PhotoItem(
                type='video',
                path=vid_path,
                name=os.path.basename(vid_path),
                video_path=vid_path,
            ))

    items.sort(key=lambda x: x.path.lower())
    return items


def scan_summary(items: list) -> dict:
    live   = sum(1 for it in items if it.type == 'live')
    video  = sum(1 for it in items if it.type == 'video')
    static = len(items) - live - video
    return {'total': len(items), 'live': live, 'static': static, 'video': video}


def items_to_dicts(items: list) -> list:
    return [
        {'type': it.type, 'path': it.path, 'name': it.name, 'video_path': it.video_path}
        for it in items
    ]
