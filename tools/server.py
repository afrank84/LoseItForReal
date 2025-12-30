
#!/usr/bin/env python3
# Local-only logger + dashboard server (core Python only).
# - /log  -> paste form that saves to data/entries.jsonl
# - /     -> dashboard (site/index.html)
# - /data/entries.jsonl served for dashboard to read

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SITE_DIR = REPO_ROOT / "site"
ENTRIES_PATH = DATA_DIR / "entries.jsonl"

TZ_NAME = "America/New_York"


def now_local_date_str() -> str:
    if ZoneInfo is not None:
        dt = datetime.now(ZoneInfo(TZ_NAME))
    else:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d")


# ----------------------------
# Minimal "YAML-ish" parser
# Supports:
#   key: value
#   key:
#     child: value
#   key: |
#     multiline...
# Indentation must be 2 spaces per level.
# ----------------------------

@dataclass
class ParseError(Exception):
    message: str


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if s == "":
        return ""
    # null
    if s.lower() in ("null", "none"):
        return None
    # bool
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    # int
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except Exception:
            return s
    # float
    if re.fullmatch(r"-?\d+\.\d+", s):
        try:
            return float(s)
        except Exception:
            return s
    return s


def parse_block(text: str) -> Dict[str, Any]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Drop leading/trailing empty lines
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()

    if not lines:
        raise ParseError("Paste is empty.")

    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(0, root)]
    i = 0

    def current_container(indent: int) -> Dict[str, Any]:
        # Pop until we find a container with indent < current indent
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            # If this happens, indentation is malformed
            raise ParseError("Indentation error (bad nesting). Use 2 spaces per level.")
        return stack[-1][1]

    while i < len(lines):
        raw = lines[i]
        if raw.strip() == "":
            i += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2 != 0:
            raise ParseError(f"Indentation must be multiples of 2 spaces. Line {i+1}: {raw!r}")

        line = raw.strip()

        # Expect "key: ..." form
        m = re.match(r"^([A-Za-z0-9_]+)\s*:\s*(.*)$", line)
        if not m:
            raise ParseError(f"Bad line format. Expected 'key: value'. Line {i+1}: {raw!r}")

        key = m.group(1)
        rest = m.group(2)

        parent = current_container(indent)

        # Multiline block key: |
        if rest == "|":
            # Gather following indented lines (indent+2 or more)
            block_lines: List[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() == "":
                    block_lines.append("")
                    i += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent <= indent:
                    break
                # remove exactly indent+2 spaces if present, otherwise remove leading spaces
                cut = indent + 2
                block_lines.append(nxt[cut:] if len(nxt) >= cut else nxt.lstrip(" "))
                i += 1
            parent[key] = "\n".join(block_lines).rstrip("\n")
            continue

        # Nested object key:  (empty rest)
        if rest == "":
            obj: Dict[str, Any] = {}
            parent[key] = obj
            # push current key container with its indent+2 level boundary
            stack.append((indent, obj))
            i += 1
            continue

        # Scalar
        parent[key] = _parse_scalar(rest)
        i += 1

    return root


# ----------------------------
# JSONL storage helpers
# ----------------------------

def _ensure_paths() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    if not ENTRIES_PATH.exists():
        ENTRIES_PATH.write_text("", encoding="utf-8")


def load_entries() -> List[Dict[str, Any]]:
    _ensure_paths()
    out: List[Dict[str, Any]] = []
    txt = ENTRIES_PATH.read_text(encoding="utf-8")
    for line in txt.splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            # If a line is corrupted, keep going but preserve a marker
            out.append({"_corrupt_line": line})
    return out


def write_entries(entries: List[Dict[str, Any]]) -> None:
    _ensure_paths()
    with ENTRIES_PATH.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def upsert_entry(new_entry: Dict[str, Any], overwrite: bool) -> Tuple[bool, str]:
    """
    Returns (saved, message).
    saved=True if written. saved=False if rejected.
    """
    date = str(new_entry.get("date", "")).strip()
    if not date:
        raise ParseError("Missing required field: date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ParseError("date must be YYYY-MM-DD")

    entries = load_entries()
    found_idx: Optional[int] = None
    for idx, e in enumerate(entries):
        if str(e.get("date", "")).strip() == date:
            found_idx = idx
            break

    if found_idx is not None and not overwrite:
        return (False, f"Entry for {date} already exists. Check overwrite to replace it.")

    if found_idx is None:
        entries.append(new_entry)
        write_entries(entries)
        return (True, f"Saved new entry for {date}.")
    else:
        entries[found_idx] = new_entry
        write_entries(entries)
        return (True, f"Overwrote existing entry for {date}.")


def normalize_entry(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accepts your paste block dict and normalizes into a stable JSON record.
    Required: date
    Recommended: meals_text + estimates, but not required.
    """
    date = str(d.get("date", "")).strip()
    if not date:
        # default to today if omitted
        date = now_local_date_str()

    day_type = d.get("day_type", None)
    source = d.get("source", None)
    notes = d.get("notes", None)

    meals_text = d.get("meals_text", None)
    estimates = d.get("estimates", None)

    # Allow shorthand: kcal / protein_g / etc at top-level
    if estimates is None:
        estimates = {}

    if isinstance(estimates, dict):
        # support top-level "kcal" alias
        if "total_kcal" not in estimates and "kcal" in d:
            estimates["total_kcal"] = d.get("kcal")
        # support top-level protein/weight alias
        if "protein_g" not in estimates and "protein_g" in d:
            estimates["protein_g"] = d.get("protein_g")
        if "weight_lb" not in estimates and "weight_lb" in d:
            estimates["weight_lb"] = d.get("weight_lb")

        # If meal kcal fields exist, compute total if missing
        meal_keys = ["breakfast_kcal", "lunch_kcal", "dinner_kcal", "snacks_kcal"]
        if "total_kcal" not in estimates:
            total = 0
            any_meal = False
            for k in meal_keys:
                v = estimates.get(k, None)
                if isinstance(v, int):
                    total += v
                    any_meal = True
            if any_meal:
                estimates["total_kcal"] = total

    # If meals_text exists, ensure it's a dict of strings
    if meals_text is not None and not isinstance(meals_text, dict):
        raise ParseError("meals_text must be a nested block of meal keys (breakfast/lunch/dinner/snacks).")

    if meals_text is None:
        meals_text = {}

    # Ensure strings
    mt: Dict[str, str] = {}
    for k, v in meals_text.items():
        mt[str(k)] = "" if v is None else str(v)

    # Validate estimates dict
    if estimates is not None and not isinstance(estimates, dict):
        raise ParseError("estimates must be a nested block of numeric fields.")
    if estimates is None:
        estimates = {}

    est: Dict[str, Any] = {}
    for k, v in estimates.items():
        est[str(k)] = v

    entry: Dict[str, Any] = {
        "date": date,
        "day_type": (None if day_type is None else str(day_type)),
        "source": (None if source is None else str(source)),
        "notes": (None if notes is None else str(notes)),
        "meals_text": mt,
        "estimates": est,
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }

    # Remove None fields for cleanliness
    for k in ["day_type", "source", "notes"]:
        if entry.get(k, None) is None or entry.get(k, "") == "":
            entry.pop(k, None)

    return entry


# ----------------------------
# HTTP Handler
# ----------------------------

LOG_PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Calorie Log - Paste Entry</title>
  <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
      .wrap {{ max-width: 980px; margin: 0 auto; }}
      textarea {{ width: 100%; height: 320px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; font-size: 14px; padding: 12px; }}
      .row {{ display: flex; gap: 16px; align-items: center; margin: 12px 0; flex-wrap: wrap; }}
      button {{ padding: 10px 14px; font-size: 14px; cursor: pointer; }}
      input[type="checkbox"] {{ transform: scale(1.2); }}
      .msg {{ padding: 10px 12px; border-radius: 8px; background: #f3f4f6; margin: 12px 0; }}
      .err {{ background: #fee2e2; }}
      .ok {{ background: #dcfce7; }}
      a {{ color: inherit; }}
      .hint {{ color: #444; font-size: 13px; line-height: 1.35; }}
      pre.sample {{ background: #111; color: #eee; padding: 12px; border-radius: 8px; overflow: auto; }}
</style>
</head>
<body>
  <div class="wrap">
    <h1>Paste Daily Entry</h1>
    <div class="row">
      <a href="/">Dashboard</a>
      <a href="/data/entries.jsonl">entries.jsonl</a>
    </div>

    {message_block}

    <form method="POST" action="/save">
      <div class="row">
        <label><input type="checkbox" name="overwrite" value="1"/> Overwrite if date exists</label>
        <button type="submit">Save Entry</button>
      </div>
      <textarea name="payload" placeholder="Paste your daily log block here...">{payload}</textarea>
    </form>

    <h2>Paste Format</h2>
    <div class="hint">
      Required: date (YYYY-MM-DD) OR omit date to default to today. Recommended: meals_text + estimates.
      Indentation: 2 spaces. Multiline uses |.
    </div>
<pre class="sample">date: 2025-12-30
day_type: normal
source: ai_estimate

meals_text:
  breakfast: |
    2 eggs
    toast with butter
    coffee w/ cream
  lunch: |
    chicken rice bowl
    broccoli
    sauce
  dinner: |
    burger
    medium fries
    mayo
  snacks: |
    protein bar

estimates:
  breakfast_kcal: 350
  lunch_kcal: 650
  dinner_kcal: 1050
  snacks_kcal: 220
  total_kcal: 2270
  protein_g: 140

notes: |
  late dinner, ate out</pre>
  </div>
</body>
</html>
"""


DASH_REDIRECT = """<!doctype html><html><head>
<meta http-equiv="refresh" content="0; url=/">
</head><body>Redirecting...</body></html>"""


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
    return "application/octet-stream"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            if self.path == "/" or self.path == "":
                self._serve_file(SITE_DIR / "index.html")
                return
            if self.path == "/app.js":
                self._serve_file(SITE_DIR / "app.js")
                return
            if self.path == "/log":
                self._serve_log_page(message=None, ok=False, payload="")
                return
            if self.path == "/data/entries.jsonl":
                _ensure_paths()
                self._serve_file(ENTRIES_PATH)
                return

            # fallback: try serving static files from /site and /data by exact path
            if self.path.startswith("/site/"):
                p = SITE_DIR / self.path[len("/site/"):]
                self._serve_file(p)
                return
            if self.path.startswith("/data/"):
                p = DATA_DIR / self.path[len("/data/"):]
                self._serve_file(p)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as e:
            self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, f"Server error: {e}")

    def do_POST(self) -> None:
        try:
            if self.path != "/save":
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8", errors="replace")

            form = self._parse_www_form(body)
            payload = form.get("payload", "").strip()
            overwrite = form.get("overwrite", "") == "1"

            if not payload:
                self._serve_log_page(message="Paste is empty.", ok=False, payload="")
                return

            parsed = parse_block(payload)
            entry = normalize_entry(parsed)
            saved, msg = upsert_entry(entry, overwrite=overwrite)

            if not saved:
                self._serve_log_page(message=msg, ok=False, payload=payload)
                return

            # success -> show message and keep payload (or clear; I keep it so you can copy/edit)
            self._serve_log_page(message=msg, ok=True, payload=payload)
        except ParseError as pe:
            self._serve_log_page(message=pe.message, ok=False, payload=self._safe_form_payload())
        except Exception as e:
            self._serve_log_page(message=f"Server error: {e}", ok=False, payload=self._safe_form_payload())

    def _safe_form_payload(self) -> str:
        return ""

    def _parse_www_form(self, body: str) -> Dict[str, str]:
        # minimal x-www-form-urlencoded parser
        out: Dict[str, str] = {}
        for pair in body.split("&"):
            if not pair:
                continue
            if "=" in pair:
                k, v = pair.split("=", 1)
            else:
                k, v = pair, ""
            k = self._url_decode(k)
            v = self._url_decode(v)
            out[k] = v
        return out

    def _url_decode(self, s: str) -> str:
        s = s.replace("+", " ")
        def repl(m: re.Match[str]) -> str:
            return chr(int(m.group(1), 16))
        return re.sub(r"%([0-9A-Fa-f]{2})", repl, s)

    def _serve_log_page(self, message: Optional[str], ok: bool, payload: str) -> None:
        msg_html = ""
        if message:
            css = "ok" if ok else "err"
            msg_html = f'<div class="msg {css}">{html.escape(message)}</div>'
    
        # Avoid str.format() so CSS/HTML braces can never break rendering.
        page = LOG_PAGE
        page = page.replace("{message_block}", msg_html)
        page = page.replace("{payload}", html.escape(payload))
    
        self._send_html(HTTPStatus.OK, page)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _guess_mime(path))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, status: int, html_str: str) -> None:
        data = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, status: int, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        # quieter logs
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    port = 8787
    if len(sys.argv) >= 2:
        try:
            port = int(sys.argv[1])
        except Exception:
            print("Usage: python tools/server.py [port]")
            return 2

    _ensure_paths()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving on http://127.0.0.1:{port}")
    print(f"- Dashboard: http://127.0.0.1:{port}/")
    print(f"- Paste log: http://127.0.0.1:{port}/log")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
