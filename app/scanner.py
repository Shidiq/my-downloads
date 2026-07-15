import datetime as dt
import hashlib
import threading

from . import config, db, filetypes, thumbs

# Single scan at a time; UI polls this state via /rescan/status.
_lock = threading.Lock()
state = {
    "running": False,
    "phase": "",  # "walk" | "hash"
    "total": 0,
    "done": 0,
    "added": 0,
    "updated": 0,
    "missing": 0,
    "hash_total": 0,
    "hash_done": 0,
    "errors": [],
    "finished_at": None,
}


def start_scan() -> bool:
    """Kick off a background scan. Returns False if one is already running."""
    with _lock:
        if state["running"]:
            return False
        state.update(
            running=True, phase="walk", total=0, done=0, added=0, updated=0,
            missing=0, hash_total=0, hash_done=0, errors=[], finished_at=None,
        )
    threading.Thread(target=_scan, daemon=True).start()
    return True


def _scan() -> None:
    try:
        _do_scan()
    except Exception as e:  # scan must never crash the app
        state["errors"].append(f"scan failed: {e}")
    finally:
        state["running"] = False
        state["phase"] = ""
        state["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")


def _do_scan() -> None:
    root = config.DOWNLOADS_ROOT
    if not root.is_dir():
        state["errors"].append(f"downloads folder not found: {root}")
        return

    # Top-level only: files directly in Downloads plus subfolders as entries.
    # Hidden entries (.DS_Store, .obsidian, ...) are skipped.
    entries = {
        p.name: p
        for p in root.iterdir()
        if not p.name.startswith(".") and (p.is_file() or p.is_dir())
    }
    state["total"] = len(entries)

    conn = db.connect()
    try:
        known = {
            r["relpath"]: r
            for r in conn.execute(
                "SELECT id, relpath, kind, size, mtime, missing, sha256 FROM files"
            )
        }

        for relpath, path in sorted(entries.items()):
            try:
                st = path.stat()
                row = known.get(relpath)
                if row is None:
                    _add_entry(conn, relpath, path, st)
                    state["added"] += 1
                elif (
                    row["missing"]
                    or (path.is_file()
                        and (row["mtime"] != st.st_mtime or row["size"] != st.st_size))
                ):
                    _update_entry(conn, row, path, st)
                    state["updated"] += 1
            except Exception as e:
                state["errors"].append(f"{relpath}: {e}")
            state["done"] += 1

        # Entries gone from disk: mark missing, keep the row.
        for relpath, row in known.items():
            if relpath not in entries and not row["missing"]:
                conn.execute("UPDATE files SET missing = 1 WHERE id = ?", (row["id"],))
                state["missing"] += 1
        conn.commit()

        _hash_size_collisions(conn)
        conn.commit()
    finally:
        conn.close()


def _add_entry(conn, relpath, path, st) -> None:
    if path.is_dir():
        kind, category, ext, size = "dir", "folder", None, None
    else:
        kind = "file"
        ext = filetypes.ext_of(relpath)
        category = filetypes.category_for(relpath)
        size = st.st_size
    cur = conn.execute(
        "INSERT INTO files (relpath, kind, category, ext, size, mtime, added_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (relpath, kind, category, ext, size, st.st_mtime,
         dt.datetime.now().isoformat(timespec="seconds")),
    )
    if kind == "file":
        thumbs.generate(cur.lastrowid, path, ext)


def _update_entry(conn, row, path, st) -> None:
    if path.is_dir():
        conn.execute(
            "UPDATE files SET mtime = ?, missing = 0 WHERE id = ?",
            (st.st_mtime, row["id"]),
        )
        return
    # Content may have changed -> stored hash is stale.
    conn.execute(
        "UPDATE files SET size = ?, mtime = ?, sha256 = NULL, missing = 0 WHERE id = ?",
        (st.st_size, st.st_mtime, row["id"]),
    )
    thumbs.generate(row["id"], path, filetypes.ext_of(row["relpath"]))


def _hash_size_collisions(conn) -> None:
    """Compute sha256 only for files sharing a size with another file —
    the only candidates that can be duplicates."""
    state["phase"] = "hash"
    rows = conn.execute(
        "SELECT id, relpath, size, sha256 FROM files "
        "WHERE kind = 'file' AND missing = 0 AND size IN ("
        "  SELECT size FROM files WHERE kind = 'file' AND missing = 0 "
        "  GROUP BY size HAVING COUNT(*) >= 2)"
    ).fetchall()
    todo = [r for r in rows if r["sha256"] is None]
    state["hash_total"] = len(todo)

    for r in todo:
        path = config.DOWNLOADS_ROOT / r["relpath"]
        try:
            digest = _sha256_file(path)
            conn.execute("UPDATE files SET sha256 = ? WHERE id = ?", (digest, r["id"]))
        except Exception as e:
            state["errors"].append(f"{r['relpath']}: hash failed ({e})")
        state["hash_done"] += 1


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(config.HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()
