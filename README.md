# my-downloads

Local web app to organize `~/Downloads`. Sister project of **my-books** — same stack (FastAPI + Jinja2 + HTMX + SQLite) and same BookBase / GitHub Dark theme.

- **Virtual organization** — files are never moved. Browse/filter by category (documents, images, archives, installers, video, audio, code, folders), search, sort, grid/list view. Top-level scan only; hidden entries skipped.
- **Open** — browser-viewable files (pdf, images, text, html, mp4, audio…) open inline in a new tab; everything else opens in the macOS default app; folders open in Finder.
- **Duplicate cleanup** — content-hash detection (size groups → SHA-256), review page shows each group, pick the keeper, the rest move to the macOS Trash (`send2trash`, recoverable). Deletes are the only write the app ever performs on the Downloads folder.

## Run

```sh
~/.pyenv/versions/3.12.3/bin/python -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh            # http://127.0.0.1:8010
```

## Dev fixtures

```sh
.venv/bin/python tests/make_fixtures.py
MYDOWNLOADS_ROOT=tests/fixtures MYDOWNLOADS_DATA_DIR=tests/data ./run.sh
```

Config precedence: env (`MYDOWNLOADS_ROOT`, `MYDOWNLOADS_DATA_DIR`, `MYDOWNLOADS_PORT`) > `config.json` (written by ⚙ settings) > defaults.
