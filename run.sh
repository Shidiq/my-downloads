#!/bin/sh
# Start my-downloads on http://127.0.0.1:<port> (env MYDOWNLOADS_PORT > config.json > 8010)
cd "$(dirname "$0")"
PORT="${MYDOWNLOADS_PORT:-$(.venv/bin/python -c '
import json, pathlib
p = pathlib.Path("config.json")
print(json.loads(p.read_text()).get("port", 8010) if p.exists() else 8010)
' 2>/dev/null || echo 8010)}"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
