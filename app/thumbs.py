from pathlib import Path

import fitz

from . import config, filetypes


def thumb_path(file_id: int) -> Path:
    return config.THUMBS_DIR / f"{file_id}.jpg"


def generate(file_id: int, path: Path, ext: str) -> bool:
    """Render page 1 (PDF) or the image itself to a cached JPEG.
    Returns False if the file can't be rendered."""
    if ext not in filetypes.THUMBABLE:
        return False
    try:
        with fitz.open(path) as doc:
            page = doc.load_page(0)
            zoom = config.THUMB_WIDTH / page.rect.width if page.rect.width else 1.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            pix.save(thumb_path(file_id), jpg_quality=config.THUMB_JPEG_QUALITY)
        return True
    except Exception:
        thumb_path(file_id).unlink(missing_ok=True)
        return False
