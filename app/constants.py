import os

PORT        = 7734
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR   = os.path.join(BASE_DIR, "cache")
INDEX_DIR   = os.path.join(BASE_DIR, "indexes")
SESSION_DIR = os.path.join(BASE_DIR, "sessions")
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
CONFIG_DIR  = os.path.join(BASE_DIR, "config")
MISSING_DIR = os.path.join(BASE_DIR, "missing")
REVIEW_DIR  = os.path.join(BASE_DIR, "review")
THUMB_SIZE = 320   # px
THUMB_CACHE_MAX = 800  # entries kept in memory

PHOTO_EXT = {
    '.jpg', '.jpeg', '.png', '.heic', '.heif',
    '.raw', '.dng', '.cr2', '.nef', '.arw',
    '.tiff', '.tif', '.bmp', '.webp', '.gif',
    '.orf', '.rw2', '.pef', '.srw', '.x3f',
}

VIDEO_EXT = {
    '.mp4', '.mov', '.3gp', '.mkv', '.avi',
    '.m4v', '.wmv', '.flv', '.webm',
}

ALL_MEDIA_EXT = PHOTO_EXT | VIDEO_EXT
