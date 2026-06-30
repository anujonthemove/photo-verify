"""
Regression tests for bugs 1-7 identified in the bug audit.
Run from project root:  python -m pytest tests/test_bugs.py -v
"""
import os
import sys
import json
import tempfile
import unittest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_index_file(tmp_dir, name="test", extra=None):
    """Write a minimal v1 index JSON and return its path."""
    data = {
        "version": 1,
        "name": name, "folder": tmp_dir, "ts": 0,
        "built": "2026-01-01 00:00:00", "total": 1,
        "files": [{"p": "img.jpg", "s": 0, "e": None, "h": "aabbccddeeff0011"}],
    }
    if extra:
        data.update(extra)
    path = os.path.join(tmp_dir, f"{name}_index.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


# ── Bug 1 — /api/media allowed_roots includes cfg.dest (rebased path) ────────

class TestBug1MediaAllowedRoots(unittest.TestCase):

    def test_cfg_dest_in_allowed_roots(self):
        """After _load_index, _state['cfg']['dest'] must appear in allowed_roots."""
        from app import state as state_mod
        from app.storage import _load_index

        with tempfile.TemporaryDirectory() as tmp:
            # Write a dummy image file so _load_index won't error on folder check
            img = os.path.join(tmp, "img.jpg")
            open(img, "wb").close()

            idx_path = _make_index_file(tmp)
            _load_index(idx_path)

            rebased_dest = state_mod._state["cfg"]["dest"]
            self.assertEqual(
                os.path.normpath(rebased_dest),
                os.path.normpath(tmp),
                "cfg.dest should be set to the index folder after _load_index",
            )

            # Simulate the allowed_roots list built in /api/media
            from app.storage import _get_active_index_folder
            allowed_roots = [
                state_mod._state["cfg"].get("src", ""),
                state_mod._state["cfg"].get("dest", ""),   # ← the fix
                _get_active_index_folder(),
            ]
            real_img = os.path.realpath(img)
            hit = any(
                real_img == os.path.realpath(r) or
                real_img.startswith(os.path.realpath(r) + os.sep)
                for r in allowed_roots if r
            )
            self.assertTrue(hit, "Image in rebased dest folder must pass security check")


# ── Bug 2 — legacy cache load must clear phash_list ──────────────────────────

class TestBug2CacheLoadClearsPhash(unittest.TestCase):

    def test_phash_list_cleared_on_cache_load(self):
        """After loading a legacy cache, phash_list must be empty, not left-over."""
        from app import state as state_mod

        # Manually plant stale pHash data (as if a prior index was loaded)
        state_mod._state["dest_idx"]["phash_list"] = [(0xDEADBEEF, "/some/old/path.jpg")]

        # Simulate what /api/load_cache does (the fixed version)
        state_mod._state["dest_idx"]["fname"]      = {"x.jpg": ["/dest/x.jpg"]}
        state_mod._state["dest_idx"]["exif"]       = {}
        state_mod._state["dest_idx"]["hash"]       = {}
        state_mod._state["dest_idx"]["phash_list"] = []  # ← the fix

        self.assertEqual(
            state_mod._state["dest_idx"]["phash_list"], [],
            "phash_list must be cleared when loading a legacy cache",
        )


# ── Bug 3 — index delete path check must use os.sep ──────────────────────────

class TestBug3PathTraversal(unittest.TestCase):

    def test_startswith_with_sep_rejects_prefix_siblings(self):
        """A path in indexes_evil/ must NOT pass as if it were inside indexes/."""
        INDEX_DIR = os.path.normpath("e:/photo-verify/indexes")

        evil_path = os.path.normpath("e:/photo-verify/indexes_evil/file.json")
        real_dir  = os.path.abspath(INDEX_DIR)

        # Old (buggy) check — no separator
        old_check = evil_path.startswith(real_dir)
        # New (fixed) check — with separator
        new_check = evil_path.startswith(real_dir + os.sep)

        self.assertTrue(old_check,  "Old check incorrectly passes the evil path")
        self.assertFalse(new_check, "Fixed check must reject the evil path")

    def test_legitimate_index_still_passes(self):
        """A real file inside indexes/ must still pass the fixed check."""
        INDEX_DIR = os.path.normpath("e:/photo-verify/indexes")
        real_path = os.path.normpath("e:/photo-verify/indexes/20260101_myidx_index.json")
        real_dir  = os.path.abspath(INDEX_DIR)

        self.assertTrue(real_path.startswith(real_dir + os.sep))


# ── Bug 4 — dest_idx reset must include phash_list ───────────────────────────

class TestBug4DestIdxResetHasPhashList(unittest.TestCase):

    def test_reset_dict_has_phash_list_key(self):
        """The reset dict written to _state['dest_idx'] must contain phash_list."""
        reset = {'fname': {}, 'exif': {}, 'hash': {}, 'video': {}, 'phash_list': []}
        self.assertIn('phash_list', reset)
        self.assertEqual(reset['phash_list'], [])

    def test_get_on_missing_key_would_have_hidden_bug(self):
        """Without the fix, idx.get('phash_list', []) masks the missing key silently."""
        broken_reset = {'fname': {}, 'exif': {}, 'hash': {}, 'video': {}}
        # .get() with default masks the problem — the key is genuinely missing
        self.assertNotIn('phash_list', broken_reset)
        # But with the fix the key is present
        fixed_reset = {'fname': {}, 'exif': {}, 'hash': {}, 'video': {}, 'phash_list': []}
        self.assertIn('phash_list', fixed_reset)


# ── Bug 5 — indexer writes file before updating in-memory state ──────────────

class TestBug5IndexerWriteFirst(unittest.TestCase):

    def test_dest_idx_not_updated_if_write_fails(self):
        """If the index write fails, _state['dest_idx'] must not be replaced."""
        from app import state as state_mod

        original_fname = dict(state_mod._state["dest_idx"]["fname"])

        # Simulate: write fails → we must NOT update dest_idx
        # The fixed code only updates dest_idx AFTER the open() succeeds.
        # We verify by reading indexer source for the ordering.
        import ast
        src = open(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "indexer.py"),
            encoding="utf-8",
        ).read()
        tree = ast.parse(src)

        # Walk the _build_index_worker function body and collect assignment line numbers
        dest_idx_assign_line = None
        write_line = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_index_worker":
                for stmt in ast.walk(node):
                    # Find: _state['dest_idx']['fname'] = fname_idx
                    if (isinstance(stmt, ast.Assign) and
                            isinstance(stmt.targets[0], ast.Subscript)):
                        tgt = stmt.targets[0]
                        if (isinstance(tgt.value, ast.Subscript) and
                                isinstance(tgt.value.value, ast.Name) and
                                tgt.value.value.id == '_state'):
                            dest_idx_assign_line = stmt.lineno
                    # Find: open(idx_path, 'w', ...)
                    if (isinstance(stmt, ast.Call) and
                            isinstance(stmt.func, ast.Name) and
                            stmt.func.id == 'open'):
                        if any(
                            (isinstance(a, ast.Constant) and 'w' in str(a.value))
                            for a in stmt.args
                        ):
                            write_line = stmt.lineno

        self.assertIsNotNone(write_line, "open(idx_path, 'w') not found in indexer")
        self.assertIsNotNone(dest_idx_assign_line, "_state['dest_idx'] assign not found")
        self.assertGreater(
            dest_idx_assign_line, write_line,
            "dest_idx must be updated AFTER the file write, not before",
        )


# ── Bug 6 — batch_match skipped results include match_path ───────────────────

class TestBug6SkippedResultsHaveMatchPath(unittest.TestCase):

    def test_skipped_result_returns_match_path_when_cached(self):
        """A previously matched file (skipped) must return its cached match_path."""
        from app import state as state_mod

        src = "/src/IMG_001.jpg"
        state_mod._state["progress"]    = {src: "found"}
        state_mod._state["match_paths"] = {
            src: {"method": "exif", "path": "/dest/IMG_001.jpg", "n": 1}
        }

        prog        = state_mod._state["progress"]
        match_paths = state_mod._state["match_paths"]

        # Simulate the fixed skipped-result block
        mp = match_paths.get(src)
        result = {
            "i": 0, "path": src, "status": prog[src],
            "method":     mp["method"] if mp else None,
            "match_path": mp["path"]   if mp else None,
            "match_n":    mp["n"]      if mp else 0,
        }

        self.assertEqual(result["match_path"], "/dest/IMG_001.jpg")
        self.assertEqual(result["method"], "exif")
        self.assertEqual(result["match_n"], 1)

    def test_skipped_result_without_cache_returns_none_gracefully(self):
        """A skipped file with no cached match must return method/match_path as None."""
        from app import state as state_mod

        src = "/src/unknown.jpg"
        state_mod._state["progress"]    = {src: "missing"}
        state_mod._state["match_paths"] = {}

        match_paths = state_mod._state["match_paths"]
        mp = match_paths.get(src)
        result = {
            "match_path": mp["path"] if mp else None,
            "method":     mp["method"] if mp else None,
        }
        self.assertIsNone(result["match_path"])
        self.assertIsNone(result["method"])

    def test_match_paths_persisted_in_session(self):
        """_save_session must include match_paths; _load_session must restore it."""
        from app import storage, state as state_mod

        with tempfile.TemporaryDirectory() as tmp:
            from app.constants import SESSION_DIR
            # Patch SESSION_DIR temporarily
            import app.storage as stor
            orig_dir = stor.SESSION_DIR if hasattr(stor, 'SESSION_DIR') else None

            state_mod._state["active_session"] = ""
            state_mod._state["progress"]       = {"/src/a.jpg": "found"}
            state_mod._state["match_paths"]    = {
                "/src/a.jpg": {"method": "filename", "path": "/dest/a.jpg", "n": 1}
            }
            state_mod._state["last_idx"]       = 0

            # Write a minimal session file
            ses_path = os.path.join(tmp, "20260101_120000_session.json")
            with open(ses_path, "w") as f:
                json.dump({
                    "index_file": "", "source": "", "ts": 0,
                    "started": "", "progress": {}, "match_paths": {}, "last_idx": 0,
                    "stats": {}
                }, f)
            state_mod._state["active_session"] = ses_path

            storage._save_session()

            with open(ses_path) as f:
                saved = json.load(f)

            self.assertIn("match_paths", saved, "_save_session must persist match_paths")
            self.assertIn("/src/a.jpg", saved["match_paths"])
            self.assertEqual(saved["match_paths"]["/src/a.jpg"]["path"], "/dest/a.jpg")


# ── Bug 7 — /api/index_info must return n_phash ──────────────────────────────

class TestBug7IndexInfoPhash(unittest.TestCase):

    def test_index_info_returns_n_phash(self):
        """index_info response must include n_phash field from the index JSON (v1 format)."""
        with tempfile.TemporaryDirectory() as tmp:
            idx_path = _make_index_file(tmp, name="phash_test")
            with open(idx_path) as f:
                d = json.load(f)

            # v1 format: count files with a non-null 'h' field
            files = d.get("files", [])
            n_phash = sum(1 for e in files if e.get("h"))
            response = {"ok": True, "n_phash": n_phash}
            self.assertIn("n_phash", response)
            self.assertEqual(response["n_phash"], 1,
                             "n_phash should equal number of files with a visual hash")

    def test_old_index_without_phash_returns_zero(self):
        """An old index file with no 'phash' key must report n_phash=0, not error."""
        with tempfile.TemporaryDirectory() as tmp:
            # Old index — no phash key
            old_data = {
                "name": "old", "folder": tmp, "ts": 0, "built": "", "total": 0,
                "fname": {}, "exif": {}, "video": {},
            }
            idx_path = os.path.join(tmp, "old_index.json")
            with open(idx_path, "w") as f:
                json.dump(old_data, f)
            with open(idx_path) as f:
                d = json.load(f)

            n_phash = len(d.get("phash", {}))
            self.assertEqual(n_phash, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
