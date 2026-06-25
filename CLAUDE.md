# PhotoVerify — Developer Reference

## Purpose

PhotoVerify is a local photo backup checker. Given a **source folder** (phone backup, camera card)
and a pre-built **index** of a destination (NAS, external drive), it identifies which source files
are missing from the destination. Runs entirely offline as a `localhost:7734` web app.

---

## Architecture

```
run.py                      ← entry point; starts HTTPServer on port 7734
app/
  constants.py              ← PORT, all *_DIR paths, PHOTO_EXT, VIDEO_EXT, ALL_MEDIA_EXT
  state.py                  ← single _state dict (in-memory; resets on restart)
  logger.py                 ← file logger → logs/
  storage.py                ← index / session / cache / config file helpers
  scanner.py                ← scan_all_media, get_exif_datetime, file_md5, make_thumbnail
  indexer.py                ← _build_index_worker (runs in a background thread)
  matcher.py                ← find_match (3-tier), deep_find (hash-based, slow)
  actions.py                ← _copy_to_output (copies missing files to output folder)
  server/
    handler.py              ← BaseHTTPRequestHandler; delegates GET→routes_get, POST→routes_post
    routes_get.py           ← all GET endpoints + static file serving
    routes_post.py          ← all POST endpoints
static/
  index.html                ← two-tab shell (Index + Verify)
  css/app.css
  js/
    api.js                  ← get(), post(), v(), esc(), fmtSize(), basename()
    app.js                  ← switchTab(), updateIndexChip(), init()
    index-tab.js            ← idxRefreshList, buildIndex, idxPollProgress, idxViewProps, idxDelete
    verify-tab.js           ← V state, vScanAll, vShowPhoto, vSaveAllMissing, session mgmt
```

---

## Data Directories

All auto-created under `BASE_DIR` (`e:\photo-verify\` — two `dirname` calls up from `app/constants.py`).

| Directory   | Purpose |
|-------------|---------|
| `indexes/`  | Master index JSON files — permanent, only rebuilt by explicit user action |
| `sessions/` | Per-run scan progress JSON — one file per "Load Source" action |
| `missing/`  | Output for files confirmed missing; timestamped subfolders per session |
| `review/`   | Output for files sent to review |
| `cache/`    | Legacy cache files (pre-session system; kept for backwards compatibility) |
| `config/`   | YAML config snapshots (src/dest/move_mode) per session |
| `logs/`     | Error logs; one file per session_ts |

---

## Three-Tier Matching (`find_match` in `matcher.py`)

Called per source file during Scan All. Returns on first hit; never reads or modifies any file.

1. **Filename** (fastest) — `basename(src).lower()` → `idx['fname']` dict lookup (O(1))
2. **EXIF + size** (photos only) — reads EXIF `DateTimeOriginal`, forms key `"datetime|bytes"` → `idx['exif']` (O(1))
3. **Video filename + size** — `"filename.lower()|bytes"` → `idx['video']` (O(1))
4. **Hash / `deep_find`** — user-triggered only; computes MD5 of source then walks entire dest folder hashing each file until a match is found. Results cached in `_state['dest_idx']['hash']` for the session lifetime. Never called during Scan All.

---

## Index File Format (`indexes/*.json`)

```json
{
  "name":   "OnePlus 7T",
  "folder": "\\\\NAS\\Photos\\OnePlus 7T",
  "built":  "2026-06-21 17:04:31",
  "total":  17031,
  "fname":  { "img_001.jpg": ["\\\\NAS\\...\\img_001.jpg", ...] },
  "exif":   { "2022:03:11 09:13:56|4521984": ["\\\\NAS\\..."] },
  "video":  { "vid_001.mp4|52428800": ["\\\\NAS\\..."] }
}
```

The index is **read-only after build** — verify never writes to it. All three lookup dicts map
their key to a list of matching destination paths (duplicates are possible).

---

## Session File Format (`sessions/*.json`)

```json
{
  "index_file": "E:\\photo-verify\\indexes\\20260621_170431_OnePlus_7T_index.json",
  "source":     "E:\\OnePlus-7T",
  "src_photos": ["E:\\OnePlus-7T\\IMG_001.jpg", ...],
  "started":    "2026-06-21 20:18:14",
  "progress":   { "E:\\OnePlus-7T\\IMG_001.jpg": "found", ... },
  "last_idx":   0,
  "stats":      { "found": 2670, "missing": 1168, "review": 0 }
}
```

`src_photos` is stored so resume never needs to re-scan the source folder.

---

## Key Design Constraints

- **No framework** — stdlib `http.server` only; adding Flask/FastAPI would require pip dependencies
- **Single-threaded server** — `HTTPServer` (not `ThreadingHTTPServer`); safe for localhost/single-user. The `_state_lock` exists but is not required while single-threaded. If `ThreadingHTTPServer` is ever used, all `_state` mutations must be wrapped with the lock.
- **State resets on restart** — `_state` is in-memory only. Session files in `sessions/` are the persistence layer.
- **Never modifies source or dest** — scanner/matcher/indexer are read-only. Only `actions.py` writes files, and only to `missing/` or `review/`.
- **`scan_all_media` vs `scan_photos`** — always use `scan_all_media` for source scanning (includes videos). `scan_photos` exists for legacy reasons but should not be used in new code.

---

## Running

```bash
python run.py
# Browser opens automatically at http://localhost:7734
```

Dependencies (`Pillow`, `pyyaml`) are auto-installed on first run if missing.

---

## Known Limitations

- **HEIC EXIF**: `PIL._getexif()` may not extract EXIF from `.heic` files without `pillow-heif`. HEIC falls back to filename-only matching.
- **Deep search is slow**: hashes all destination files on first call (~5 ms/file × 17k files ≈ 85 s). Results are cached for the session.
- **Session list shows all sessions**: not filtered by the currently loaded index. Resuming a session from a different index silently loads the wrong index.
- **No progress export**: found/missing/review list cannot be exported to CSV from the UI.
- **Index build is not cancellable** once started.
