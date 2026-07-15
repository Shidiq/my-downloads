"""Extension -> category / MIME mapping. Decides what opens in a browser tab
(inline stream) vs the macOS default app ("open")."""

CATEGORIES = {
    "documents": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "epub", "rtf"},
    "images": {"png", "jpg", "jpeg", "webp", "gif", "svg", "heic", "bmp", "tiff"},
    "archives": {"zip", "gz", "tgz", "tar", "7z", "rar", "bz2", "xz"},
    "installers": {"dmg", "iso", "exe", "pkg", "msi", "app", "deb", "rpm"},
    "video": {"mp4", "mov", "webm", "mkv", "avi"},
    "audio": {"mp3", "m4a", "wav", "flac", "ogg", "aac"},
    "code": {"json", "toml", "yaml", "yml", "js", "ts", "py", "html", "htm", "css", "csv", "log", "sh", "ipynb"},
}

CATEGORY_ORDER = ["documents", "images", "archives", "installers", "video", "audio", "code", "other", "folder"]

CATEGORY_EMOJI = {
    "documents": "📄",
    "images": "🖼️",
    "archives": "📦",
    "installers": "💿",
    "video": "🎬",
    "audio": "🎵",
    "code": "💻",
    "folder": "📁",
    "other": "❓",
}

_EXT_CATEGORY = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts}

# What a browser renders natively -> served inline with this MIME (new tab).
# Anything not listed opens via the macOS default app instead.
_BROWSER_MIME = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "html": "text/html",
    "htm": "text/html",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
}
_TEXT_EXTS = {"txt", "md", "json", "log", "csv", "toml", "yaml", "yml", "js", "ts", "py", "css", "sh"}

# Formats PyMuPDF can rasterize for thumbnails.
THUMBABLE = {"pdf", "png", "jpg", "jpeg", "webp", "gif", "bmp", "svg", "epub"}


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def category_for(name: str) -> str:
    return _EXT_CATEGORY.get(ext_of(name), "other")


def browser_mime(ext: str) -> str | None:
    """MIME to stream inline if the browser can view this ext, else None."""
    if ext in _BROWSER_MIME:
        return _BROWSER_MIME[ext]
    if ext in _TEXT_EXTS:
        return "text/plain; charset=utf-8"
    return None
