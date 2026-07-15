import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from send2trash import send2trash
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, filetypes, scanner, thumbs

SORTS = {
    "name": "relpath COLLATE NOCASE",
    "size": "size",
    "mtime": "mtime",
    "added_at": "added_at",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.backup_db()
    scanner.start_scan()
    yield


app = FastAPI(title="my-downloads", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def human_size(n) -> str:
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return ""


def timestamp(t) -> str:
    if not t:
        return "—"
    import datetime as dt
    return dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")


templates.env.filters["human_size"] = human_size
templates.env.filters["timestamp"] = timestamp
templates.env.globals["emoji"] = filetypes.CATEGORY_EMOJI
templates.env.globals["browser_mime"] = filetypes.browser_mime


def _resolve_path(row) -> Path:
    path = (config.DOWNLOADS_ROOT / row["relpath"]).resolve()
    if not path.is_relative_to(config.DOWNLOADS_ROOT.resolve()) or not path.exists():
        raise HTTPException(404, "not found on disk")
    return path


def _get_file(file_id: int):
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404)
    return row


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    sort: str = "mtime",
    order: str = "",
    category: str = "",
    view: str = "grid",
):
    sort_sql = SORTS.get(sort, SORTS["mtime"])
    if order not in ("asc", "desc"):
        order = "asc" if sort == "name" else "desc"

    where, params = [], []
    if q:
        where.append("relpath LIKE ?")
        params.append(f"%{q}%")
    if category in filetypes.CATEGORY_ORDER:
        where.append("category = ?")
        params.append(category)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    conn = db.connect()
    try:
        files = conn.execute(
            f"SELECT * FROM files {where_sql} ORDER BY {sort_sql} {order}",
            params,
        ).fetchall()
        counts = conn.execute(
            "SELECT category, COUNT(*) AS n FROM files GROUP BY category"
        ).fetchall()
        dup_groups = db.duplicate_group_count(conn)
    finally:
        conn.close()

    current = {"q": q, "sort": sort, "order": order, "category": category, "view": view}

    def qs(**over):
        merged = {**current, **over}
        return "?" + urlencode({k: v for k, v in merged.items() if v})

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "qs": qs,
            "files": files,
            "categories": filetypes.CATEGORY_ORDER,
            "category_counts": {r["category"]: r["n"] for r in counts},
            "dup_groups": dup_groups,
            "total": len(files),
            "q": q, "sort": sort, "order": order, "category": category, "view": view,
            "scan": scanner.state,
        },
    )


@app.post("/rescan", response_class=HTMLResponse)
def rescan(request: Request):
    scanner.start_scan()
    return templates.TemplateResponse(request, "_scan_status.html", {"scan": scanner.state})


@app.get("/rescan/status", response_class=HTMLResponse)
def rescan_status(request: Request):
    return templates.TemplateResponse(request, "_scan_status.html", {"scan": scanner.state})


@app.get("/thumbs/{file_id}")
def thumb(file_id: int):
    path = thumbs.thumb_path(file_id)
    if path.exists():
        return FileResponse(path, media_type="image/jpeg")
    row = _get_file(file_id)
    icon = filetypes.CATEGORY_EMOJI.get(row["category"], "❓")
    placeholder = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300" width="200" height="300">'
        '<style>'
        'rect { fill: #eff1f5; stroke: #cbd5e1; stroke-width: 1.5; }'
        '@media (prefers-color-scheme: dark) {'
        '  rect { fill: #161b22; stroke: #30363d; }'
        '}'
        '</style>'
        '<rect x="0.75" y="0.75" width="198.5" height="298.5" rx="4"/>'
        f'<text x="50%" y="50%" font-family="sans-serif" font-size="48" text-anchor="middle" dominant-baseline="middle">{icon}</text></svg>'
    )
    return Response(placeholder, media_type="image/svg+xml")


@app.get("/files/{file_id}/view")
def view_file(file_id: int):
    """Inline stream for browser-viewable types — the new-tab target."""
    row = _get_file(file_id)
    if row["kind"] != "file":
        raise HTTPException(400, "not a file")
    mime = filetypes.browser_mime(row["ext"] or "")
    if mime is None:
        raise HTTPException(400, "not browser-viewable — use open")
    path = _resolve_path(row)
    return FileResponse(
        path,
        media_type=mime,
        content_disposition_type="inline",
        filename=path.name,
    )


@app.post("/files/{file_id}/open")
def open_file(file_id: int):
    """macOS `open`: file -> default app, folder -> Finder."""
    row = _get_file(file_id)
    path = _resolve_path(row)
    subprocess.Popen(["open", str(path)])
    return Response(status_code=204)


@app.delete("/files/{file_id}")
def delete_file(file_id: int):
    row = _get_file(file_id)
    if not row["missing"]:
        path = (config.DOWNLOADS_ROOT / row["relpath"]).resolve()
        if path.is_relative_to(config.DOWNLOADS_ROOT.resolve()) and path.exists():
            send2trash(path)
    thumbs.thumb_path(file_id).unlink(missing_ok=True)
    conn = db.connect()
    try:
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
    finally:
        conn.close()
    return Response(status_code=204, headers={"HX-Refresh": "true"})


def _dup_groups(conn):
    rows = conn.execute(
        "SELECT * FROM files WHERE kind = 'file' AND missing = 0 AND sha256 IN ("
        "  SELECT sha256 FROM files WHERE kind = 'file' AND missing = 0 "
        "  AND sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*) >= 2) "
        "ORDER BY size DESC, sha256, mtime"
    ).fetchall()
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["sha256"], []).append(r)
    return groups


@app.get("/duplicates", response_class=HTMLResponse)
def duplicates(request: Request, resolved: int = 0):
    conn = db.connect()
    try:
        groups = _dup_groups(conn)
    finally:
        conn.close()
    wasted = sum(g[0]["size"] * (len(g) - 1) for g in groups.values())
    return templates.TemplateResponse(
        request,
        "duplicates.html",
        {"groups": groups, "wasted": wasted, "resolved": resolved, "scan": scanner.state},
    )


@app.post("/duplicates/resolve", response_class=HTMLResponse)
async def duplicates_resolve(request: Request):
    form = await request.form()
    scope = form.get("group", "all")
    conn = db.connect()
    try:
        groups = _dup_groups(conn)
        targets = [scope] if scope != "all" else list(groups)
        trashed = 0
        for sha in targets:
            rows = groups.get(sha)
            keep_raw = form.get(f"keep_{sha}", "")
            if not rows or not keep_raw.isdigit():
                continue
            keep_id = int(keep_raw)
            if keep_id not in {r["id"] for r in rows}:
                continue
            for r in rows:
                if r["id"] == keep_id:
                    continue
                path = (config.DOWNLOADS_ROOT / r["relpath"]).resolve()
                if path.is_relative_to(config.DOWNLOADS_ROOT.resolve()) and path.is_file():
                    send2trash(path)
                thumbs.thumb_path(r["id"]).unlink(missing_ok=True)
                conn.execute("DELETE FROM files WHERE id = ?", (r["id"],))
                trashed += 1
        conn.commit()
    finally:
        conn.close()
    return Response(
        status_code=204,
        headers={"HX-Redirect": f"/duplicates?resolved={trashed}"},
    )


def _settings_ctx(values=None, errors=None, saved=False, notes=None):
    return {
        "values": values
        or {
            "downloads_root": str(config.DOWNLOADS_ROOT),
            "data_dir": config.effective("data_dir"),
            "port": config.effective("port"),
        },
        "env": {k: config.env_overridden(k) for k in ("downloads_root", "data_dir", "port")},
        "errors": errors or {},
        "saved": saved,
        "notes": notes or [],
    }


@app.get("/settings", response_class=HTMLResponse)
def settings_form(request: Request):
    return templates.TemplateResponse(request, "settings.html", _settings_ctx())


@app.post("/settings", response_class=HTMLResponse)
def settings_save(
    request: Request,
    downloads_root: str = Form(""),
    data_dir: str = Form(""),
    port: str = Form(""),
):
    errors = {}

    new_root = None
    if not config.env_overridden("downloads_root"):
        new_root = Path(downloads_root.strip()).expanduser()
        if not new_root.is_dir():
            errors["downloads_root"] = "Folder does not exist"

    if not config.env_overridden("data_dir"):
        d = Path(data_dir.strip()).expanduser()
        if d.exists():
            if not d.is_dir():
                errors["data_dir"] = "Not a folder"
        elif not d.parent.is_dir():
            errors["data_dir"] = "Parent folder does not exist"

    port_val = None
    if not config.env_overridden("port"):
        try:
            port_val = int(port)
            if not 1 <= port_val <= 65535:
                raise ValueError
        except ValueError:
            errors["port"] = "Port must be a number between 1 and 65535"

    if errors:
        values = {"downloads_root": downloads_root, "data_dir": data_dir, "port": port}
        return templates.TemplateResponse(
            request, "settings.html", _settings_ctx(values=values, errors=errors)
        )

    updates = {}
    root_changed = False
    if new_root is not None:
        root_changed = new_root.resolve() != config.DOWNLOADS_ROOT.resolve()
        updates["downloads_root"] = str(new_root)
    if not config.env_overridden("data_dir"):
        updates["data_dir"] = str(Path(data_dir.strip()).expanduser())
    if port_val is not None:
        updates["port"] = port_val
    config.save(updates)

    notes = []
    if root_changed:
        if scanner.start_scan():
            notes.append("Downloads folder changed — rescan started.")
        else:
            notes.append("Downloads folder changed — a scan is already running, rescan after it finishes.")
    if str(config.effective("data_dir")) != config.STARTUP_DATA_DIR:
        notes.append("Data folder change takes effect after restart.")
    if int(config.effective("port")) != config.STARTUP_PORT:
        notes.append("Port change takes effect after restart.")

    return templates.TemplateResponse(
        request, "settings.html", _settings_ctx(saved=True, notes=notes)
    )
