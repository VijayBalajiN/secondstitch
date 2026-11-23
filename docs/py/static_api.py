"""The whole SecondStitch API, run inside the browser by Pyodide for the GitHub Pages copy (see static/).

There is no server there, so every visitor gets their own private copy of the data: orders, the ops desk
and the bot simulator all work on what that browser has stored. static/static-api.js loads the saved data
into /data before this module is imported, calls handle() for every /api/ request, and saves dump() after
each change.
"""
import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs

os.environ.setdefault("SECONDSTITCH_DATA", "/data")

import api  # noqa: E402
import bot  # noqa: E402
import orders  # noqa: E402
import whatsapp  # noqa: E402
from orders import ApiError  # noqa: E402

DATA = Path(os.environ["SECONDSTITCH_DATA"])
OUTBOX_FILE = DATA / "outbox.json"
UPLOAD_URL = re.compile(r"^/uploads/(SS-[A-Z0-9]{5}-\d\.(?:jpeg|png|webp))$")
MIME = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

bot.notify_inline = True   # no threads in the browser: send status messages right away

if OUTBOX_FILE.exists():   # the bot simulator's chat history
    saved = json.loads(OUTBOX_FILE.read_text("utf-8"))
    whatsapp._outbox[:] = saved.get("outbox", [])
    whatsapp._seq = saved.get("seq", 0)


def inline_photos(value):
    """Photos are files on the server; here they become data: URLs, since nothing can serve /uploads/."""
    if isinstance(value, dict):
        return {k: inline_photos(v) for k, v in value.items()}
    if isinstance(value, list):
        return [inline_photos(v) for v in value]
    if isinstance(value, str):
        m = UPLOAD_URL.match(value)
        if m and (orders.UPLOADS / m.group(1)).is_file():
            raw = (orders.UPLOADS / m.group(1)).read_bytes()
            return f"data:{MIME[m.group(1).rsplit('.', 1)[1]]};base64,{base64.b64encode(raw).decode()}"
    return value


def handle(method, path, query_string, body_text):
    """Returns JSON text: {"status": 200, "body": ...}. Same behaviour as server.py's /api/ routes."""
    try:
        body = json.loads(body_text) if body_text else {}
        if not isinstance(body, dict):
            raise ApiError("Request body must be a JSON object.")
        result = inline_photos(api.route(method, path, body, parse_qs(query_string)))
        return json.dumps({"status": 200, "body": result}, ensure_ascii=False)
    except ApiError as e:
        return json.dumps({"status": e.status, "body": {"error": str(e), "errors": e.errors}}, ensure_ascii=False)
    except json.JSONDecodeError:
        return json.dumps({"status": 400, "body": {"error": "Request body must be JSON."}})
    except Exception as e:  # keep the demo alive and say what broke
        print(f"API error on {path}: {e!r}")
        return json.dumps({"status": 500, "body": {"error": "Something went wrong."}})


def dump():
    """Everything the browser should remember: files under /data as {relative path: base64}."""
    OUTBOX_FILE.write_text(json.dumps({"outbox": whatsapp._outbox, "seq": whatsapp._seq}), "utf-8")
    return json.dumps({str(p.relative_to(DATA)): base64.b64encode(p.read_bytes()).decode()
                       for p in sorted(DATA.rglob("*")) if p.is_file() and p.suffix != ".tmp"})
