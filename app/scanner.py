import os
import io
import hashlib
from pathlib import Path

try:
    from PIL import Image, ExifTags
    PIL_OK = True
except ImportError:
    PIL_OK = False

from app.constants import PHOTO_EXT, VIDEO_EXT, ALL_MEDIA_EXT, THUMB_SIZE, THUMB_CACHE_MAX
from app.state import _state


def scan_photos(folder: str) -> list:
    """Recursively scan folder; return sorted list of photo paths."""
    results = []
    try:
        for root, dirs, files in os.walk(folder, followlinks=False):
            # Skip hidden dirs (e.g. .@eaDir on Synology)
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if Path(f).suffix.lower() in PHOTO_EXT:
                    results.append(os.path.join(root, f))
    except PermissionError as e:
        print(f"  Permission denied: {e}")
    return sorted(results)

def scan_all_media(folder: str) -> list:
    """Recursively scan folder for all media (photos + videos); return sorted paths."""
    results = []
    try:
        for root, dirs, files in os.walk(folder, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if Path(f).suffix.lower() in ALL_MEDIA_EXT:
                    results.append(os.path.join(root, f))
    except PermissionError as e:
        print(f"  Permission denied: {e}")
    return sorted(results)

def get_exif_datetime(path: str):
    """Return EXIF DateTimeOriginal string or None."""
    if not PIL_OK:
        return None
    try:
        with Image.open(path) as img:
            exif = img._getexif()
            if exif:
                for tag_id, val in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, '')
                    if tag in ('DateTimeOriginal', 'DateTime'):
                        return str(val).strip()
    except Exception:
        pass
    return None

def dhash(img_path: str, hash_size: int = 8) -> int | None:
    """Compute difference hash of an image using Pillow. Returns 64-bit int or None on error."""
    if not PIL_OK:
        return None
    target = (hash_size + 1, hash_size)
    try:
        with Image.open(img_path) as img:
            # draft() tells the JPEG decoder to decode at the minimum needed resolution
            # instead of allocating the full pixel buffer (e.g. 144 MB for a 48 MP photo).
            # No-op for non-JPEG formats; safe to call unconditionally.
            img.draft('L', target)
            img = img.convert('L').resize(target, Image.LANCZOS)
            pixels = list(img.getdata())
            bits = (pixels[r * (hash_size + 1) + c] > pixels[r * (hash_size + 1) + c + 1]
                    for r in range(hash_size) for c in range(hash_size))
            return sum(b << i for i, b in enumerate(bits))
    except Exception:
        return None


def file_md5(path: str):
    """Compute MD5 hex digest of a file."""
    h = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(131072), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

_VIDEO_PLACEHOLDER: bytes | None = None

def _get_video_placeholder() -> bytes | None:
    global _VIDEO_PLACEHOLDER
    if _VIDEO_PLACEHOLDER is not None:
        return _VIDEO_PLACEHOLDER
    if PIL_OK:
        from PIL import ImageDraw
        img = Image.new('RGB', (320, 320), color=(28, 30, 38))
        draw = ImageDraw.Draw(img)
        draw.polygon([(108, 88), (108, 232), (242, 160)], fill=(160, 162, 180))
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=84)
        _VIDEO_PLACEHOLDER = buf.getvalue()
    return _VIDEO_PLACEHOLDER

def make_thumbnail(path: str, size: int = THUMB_SIZE) -> bytes | None:
    """Render a JPEG thumbnail, honouring EXIF rotation."""
    if Path(path).suffix.lower() in VIDEO_EXT:
        return _get_video_placeholder()
    if not PIL_OK:
        return None
    cache = _state['_thumb_cache']
    if path in cache:
        return cache[path]
    try:
        with Image.open(path) as img:
            # EXIF auto-rotate
            try:
                exif = img._getexif()
                if exif:
                    for tid, val in exif.items():
                        if ExifTags.TAGS.get(tid) == 'Orientation':
                            rot = {3: 180, 6: 270, 8: 90}
                            if val in rot:
                                img = img.rotate(rot[val], expand=True)
            except Exception:
                pass
            img.thumbnail((size, size), Image.LANCZOS)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, 'JPEG', quality=84, optimize=True)
            data = buf.getvalue()
    except Exception:
        return None

    # Cache with simple eviction
    order = _state['_thumb_order']
    if len(order) >= THUMB_CACHE_MAX:
        oldest = order.pop(0)
        cache.pop(oldest, None)
    cache[path] = data
    order.append(path)
    return data
