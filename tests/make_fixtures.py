"""Generate a synthetic Downloads folder for manual end-to-end verification.

Covers: browser-viewable types (pdf, png, txt, md, html), system-open types
(zip, dmg), a subfolder entry, two exact duplicate pairs, and one
same-size-but-different-content pair (hashing must NOT flag it).

Run: .venv/bin/python tests/make_fixtures.py
Then: MYDOWNLOADS_ROOT=tests/fixtures MYDOWNLOADS_DATA_DIR=tests/data ./run.sh
"""

import os
import shutil
import zipfile
from pathlib import Path

import fitz

FIXTURES = Path(__file__).parent / "fixtures"


def make_pdf(path: Path, title: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    page.draw_rect(fitz.Rect(20, 20, 380, 580), color=(0.2, 0.4, 0.9), width=3)
    page.insert_textbox(fitz.Rect(40, 250, 360, 350), title, fontsize=24, align=1)
    doc.save(path)
    doc.close()


def make_png(path: Path, color: tuple) -> None:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 320, 480), False)
    pix.set_rect(pix.irect, color)
    pix.save(path)


def main() -> None:
    shutil.rmtree(FIXTURES, ignore_errors=True)
    FIXTURES.mkdir(parents=True)

    # Browser-viewable
    make_pdf(FIXTURES / "quarterly-report.pdf", "Quarterly Report")
    make_pdf(FIXTURES / "lecture-notes.pdf", "Lecture Notes")
    make_png(FIXTURES / "screenshot.png", (200, 80, 80))
    (FIXTURES / "todo.txt").write_text("- verify my-downloads\n- resolve duplicates\n")
    (FIXTURES / "readme.md").write_text("# Fixture readme\n\nHello from fixtures.\n")
    (FIXTURES / "page.html").write_text("<h1>Fixture page</h1>")

    # System-open types
    with zipfile.ZipFile(FIXTURES / "archive.zip", "w") as z:
        z.writestr("inside.txt", "zip content")
    (FIXTURES / "installer.dmg").write_bytes(os.urandom(4096))

    # Subfolder entry
    sub = FIXTURES / "unzipped-project"
    sub.mkdir()
    (sub / "main.py").write_text("print('hi')\n")

    # Exact duplicate pair 1: pdf downloaded twice
    shutil.copyfile(FIXTURES / "quarterly-report.pdf", FIXTURES / "quarterly-report (1).pdf")
    # Exact duplicate pair 2: image copy
    shutil.copyfile(FIXTURES / "screenshot.png", FIXTURES / "screenshot copy.png")

    # Same size, different content — must NOT be flagged as duplicates
    (FIXTURES / "data-a.bin").write_bytes(b"A" * 2048)
    (FIXTURES / "data-b.bin").write_bytes(b"B" * 2048)

    n = len(list(FIXTURES.rglob("*")))
    print(f"fixtures written to {FIXTURES} ({n} entries)")
    print("expect: 2 duplicate groups (quarterly-report pair, screenshot pair)")


if __name__ == "__main__":
    main()
