import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Settings precedence: env var > config.json > default. config.json is written
# by the in-app settings menu; env vars keep launch configs (fixtures) working.
CONFIG_PATH = PROJECT_ROOT / "config.json"

_DEFAULTS = {
    # The Downloads folder is treated as read-only, except a user-initiated
    # delete (or duplicate resolve) moves files to the trash.
    "downloads_root": str(Path.home() / "Downloads"),
    # Metadata DB, thumbnails, and backups stay in the project tree.
    "data_dir": str(PROJECT_ROOT / "data"),
    "port": 8010,
}

_ENV_VARS = {
    "downloads_root": "MYDOWNLOADS_ROOT",
    "data_dir": "MYDOWNLOADS_DATA_DIR",
    "port": "MYDOWNLOADS_PORT",
}


def load_file() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def env_overridden(key: str) -> bool:
    return _ENV_VARS.get(key) in os.environ


def effective(key: str):
    env_var = _ENV_VARS.get(key)
    if env_var and env_var in os.environ:
        return os.environ[env_var]
    return load_file().get(key, _DEFAULTS[key])


def save(updates: dict) -> None:
    cfg = load_file()
    cfg.update(updates)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    _apply_runtime()


def _apply_runtime() -> None:
    # Only settings safe to change without restart. DATA_DIR (and DB_PATH etc.)
    # must not move under a running scan thread or backup.
    global DOWNLOADS_ROOT
    DOWNLOADS_ROOT = Path(effective("downloads_root")).expanduser()


_apply_runtime()

DATA_DIR = Path(effective("data_dir")).expanduser()
DB_PATH = DATA_DIR / "downloads.db"
BACKUP_DIR = DATA_DIR / "backups"
THUMBS_DIR = DATA_DIR / "thumbs"

BACKUPS_TO_KEEP = 10
THUMB_WIDTH = 320
THUMB_JPEG_QUALITY = 75
HASH_CHUNK = 1024 * 1024  # 1 MB chunks; some downloads (ISOs) are multi-GB

HOST = "127.0.0.1"
PORT = int(effective("port"))

# Snapshots for "restart required" detection in the settings UI.
STARTUP_DATA_DIR = str(DATA_DIR)
STARTUP_PORT = PORT


def ensure_dirs() -> None:
    for d in (DATA_DIR, BACKUP_DIR, THUMBS_DIR):
        d.mkdir(parents=True, exist_ok=True)
