#!/usr/bin/env python3
# Local-only calorie log server (core Python only).
#
# Serves:
#   GET  /                  -> site/index.html
#   GET  /log               -> site/log.html
#   GET  /styles.css        -> site/styles.css
#   GET  /app.js            -> site/app.js
#   GET  /log.js            -> site/log.js
#   GET  /data/entries.jsonl
#
# API:
#   GET  /api/entry?date=YYYY-MM-DD
#   POST /api/save          JSON { entry: {...}, merge: bool, overwrite: bool }

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "site"
DATA_DIR = REPO_ROOT / "data"
ENTRIES_PATH = DATA_DIR / "entries.jsonl"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ensure_paths() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not ENTRIES_PATH.exists():
        ENTRIES_PATH.write_text("", encoding="utf-8")


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".html":
        return "text/html; charset=utf-8"
    if ext == ".js":
        return "text/javascript; charset=utf-8"
    if ext == ".css":
        return "text/css; charset=utf-8"
    if ext == ".jsonl":
        return "application/json; charset=utf-8"
    if ext == ".json":
        return "application/json; charset=utf-8"
    if ext in (".png",):
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".svg":
        return "image/svg+xml; charset=utf-8"
    return "application/octet-stream"


def _read_jsonl_entries() -> list[dict]:
    _ensure_paths()
    raw = ENTRIES_PATH.read_text(encoding="utf-8", errors="replace")
    entries: list[dict] = []
    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        try:
            obj = json.loads(t)
            if isinstance(obj, dict):
                entries.append(obj)
        except Exception:
            # Ignore corrupt lines (dashboard JS also ignores)
            continue
    return entries


def _write_jsonl_entries(entries: list[dict]) -> None:
    _ensure_paths()

    # Always store newest -> oldest
    entries = _sort_entries_newest_first(entries)

    # One JSON object per line (compact)
    out_lines = [json.dumps(e, separators=(",", ":"), ensure_ascii=False) for e in entries]
    data = ("\n".join(out_lines) + ("\n" if out_lines else ""))

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(prefix="entries_", suffix=".jsonl", dir=str(DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
        os.replace(tmp_path, ENTRIES_PATH)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def _sort_entries_newest_first(entries: list[dict]) -> list[dict]:
    """
    Sort entries by date (YYYY-MM-DD) descending. Invalid/missing dates go last.
    """
    def key(e: dict) -> str:
        d = str(e.get("date", "") or "")
        return d if DATE_RE.match(d) else ""
    return sorted(entries, key=key, reverse=True)


def _find_entry_index(entries: list[dict], date_str: str) -> int:
    for i, e in enumerate(entries):
        if str(e.get("date", "")) == date_str:
            return i
    return -1


def _merge_entries(existing: dict, incoming: dict) -> dict:
    """
    Merge strategy:
      - meals_text: append per-key (with newline) if both exist and non-empty
      - estimates: shallow update (incoming keys overwrite)
      - notes: if incoming notes exists and non-empty:
               append with newline if existing notes exists and non-empty
      - other top-level keys: incoming overwrites if present (except date)
    """
    out = dict(existing)

    # Always preserve date from existing (or incoming if missing)
    if "date" in incoming:
        out["date"] = incoming["date"]
    elif "date" not in out:
        out["date"] = existing.get("date", "")

    # Top-level simple overwrite (but we'll handle meals_text/estimates/notes specially)
    for k, v in incoming.items():
        if k in ("meals_text", "estimates", "notes", "date"):
            continue
        out[k] = v

    # meals_text append
    ex_meals = out.get("meals_text") if isinstance(out.get("meals_text"), dict) else {}
    in_meals = incoming.get("meals_text") if isinstance(incoming.get("meals_text"), dict) else {}

    merged_meals = dict(ex_meals)
    for mk, mv in in_meals.items():
        if mv is None:
            continue
        new_txt = str(mv)
        old_txt = str(merged_meals.get(mk, "") or "")
        if old_txt.strip() and new_txt.strip():
            merged_meals[mk] = old_txt.rstrip() + "\n" + new_txt.lstrip()
        else:
            merged_meals[mk] = new_txt
    if merged_meals:
        out["meals_text"] = merged_meals

    # estimates shallow update
    ex_est = out.get("estimates") if isinstance(out.get("estimates"), dict) else {}
    in_est = incoming.get("estimates") if isinstance(incoming.get("estimates"), dict) else {}
    merged_est = dict(ex_est)
    for ek, ev in in_est.items():
        merged_est[ek] = ev
    if merged_est:
        out["estimates"] = merged_est

    # notes append
    in_notes = incoming.get("notes", None)
    if in_notes is not None:
        new_notes = str(in_notes)
        old_notes = str(out.get("notes", "") or "")
        if old_notes.strip() and new_notes.strip():
            out["notes"] = old_notes.rstrip() + "\n" + new_notes.lstrip()
        else:
            out["notes"] = new_notes

    out["updated_at"] = _now_iso_utc()
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "LoseItForReal/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # quieter
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        data = path.read_bytes()
        self._send(200, data, _guess_mime(path))

    def _safe_site_path(self, url_path: str) -> Path | None:
        # Map /foo to SITE_DIR/foo and prevent traversal
        rel = url_path.lstrip("/")
        if not rel:
            return None
        candidate = (SITE_DIR / rel).resolve()
        try:
            candidate.relative_to(SITE_DIR.resolve())
        except Exception:
            return None
        return candidate

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # Pages
        if path == "/" or path == "":
            return self._serve_file(SITE_DIR / "index.html")
        if path == "/log":
            return self._serve_file(SITE_DIR / "log.html")

        # Data
        if path == "/data/entries.jsonl":
            _ensure_paths()
            return self._serve_file(ENTRIES_PATH)

        # API
        if path == "/api/entry":
            qs = parse_qs(parsed.query or "")
            date_str = (qs.get("date") or [""])[0].strip()
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
            if not DATE_RE.match(date_str):
                return self._send_json(400, {"ok": False, "error": "Invalid date. Use YYYY-MM-DD."})

            entries = _read_jsonl_entries()
            idx = _find_entry_index(entries, date_str)
            if idx >= 0:
                return self._send_json(200, entries[idx])

            # Default template if not found
            tmpl = {
                "date": date_str,
                "day_type": "normal",
                "source": "manual",
                "meals_text": {
                    "breakfast": "",
                    "lunch": "",
                    "dinner": "",
                    "snacks": ""
                },
                "estimates": {},
                "notes": ""
            }
            return self._send_json(200, tmpl)

        # Static files from /site (styles.css, app.js, log.js, etc.)
        site_file = self._safe_site_path(path)
        if site_file is not None and site_file.exists() and site_file.is_file():
            return self._serve_file(site_file)

        return self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path != "/api/save":
            return self._send(404, b"Not found", "text/plain; charset=utf-8")

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0

        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            return self._send_json(400, {"ok": False, "error": "Invalid JSON body."})

        if not isinstance(payload, dict):
            return self._send_json(400, {"ok": False, "error": "Body must be a JSON object."})

        entry = payload.get("entry")
        merge = bool(payload.get("merge", False))
        overwrite = bool(payload.get("overwrite", False))

        if merge and overwrite:
            # Safer: prefer merge
            overwrite = False

        if not isinstance(entry, dict):
            return self._send_json(400, {"ok": False, "error": "Body.entry must be a JSON object."})

        date_str = str(entry.get("date", "")).strip()
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
            entry["date"] = date_str

        if not DATE_RE.match(date_str):
            return self._send_json(400, {"ok": False, "error": "Invalid entry.date. Use YYYY-MM-DD."})

        entries = _read_jsonl_entries()
        idx = _find_entry_index(entries, date_str)

        # Normalize
        entry["date"] = date_str
        entry["updated_at"] = _now_iso_utc()

        if idx < 0:
            # New date -> append
            entries.append(entry)
            _write_jsonl_entries(entries)
            return self._send_json(200, {"ok": True, "message": "Saved new entry.", "date": date_str})

        # Existing date
        if overwrite:
            entries[idx] = entry
            _write_jsonl_entries(entries)
            return self._send_json(200, {"ok": True, "message": "Overwrote existing entry.", "date": date_str})

        if merge:
            merged = _merge_entries(entries[idx], entry)
            entries[idx] = merged
            _write_jsonl_entries(entries)
            return self._send_json(200, {"ok": True, "message": "Merged into existing entry.", "date": date_str})

        # Default behavior if neither checkbox: overwrite (explicit, predictable)
        entries[idx] = entry
        _write_jsonl_entries(entries)
        return self._send_json(200, {"ok": True, "message": "Saved (replaced existing entry).", "date": date_str})


def main() -> int:
    port = 8787
    if len(sys.argv) >= 2:
        try:
            port = int(sys.argv[1])
        except Exception:
            port = 8787

    _ensure_paths()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving on http://127.0.0.1:{port}")
    print(f"- Dashboard: http://127.0.0.1:{port}/")
    print(f"- Log editor: http://127.0.0.1:{port}/log")
    print(f"- Data file: {ENTRIES_PATH}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
