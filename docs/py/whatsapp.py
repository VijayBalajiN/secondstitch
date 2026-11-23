"""WhatsApp Cloud API transport: sending, webhook, media download, and the local simulator outbox.

Settings come from environment variables or website/.env (see .env.example).

- Without WA_TOKEN and WA_PHONE_NUMBER_ID nothing leaves this computer: every message goes to the
  outbox that the /bot simulator page reads.
- With them, replies to real WhatsApp users go to the Graph API. The webhook listens on its own port
  (WA_WEBHOOK_PORT, default 8081) and serves only /webhook, so a tunnel to that port never exposes
  the ops desk or the simulator. It refuses to start without WA_VERIFY_TOKEN and WA_APP_SECRET.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent


def _load_env(path):
    if not path.exists():
        return
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env(ROOT / ".env")

TOKEN = os.environ.get("WA_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("WA_PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "")
APP_SECRET = os.environ.get("WA_APP_SECRET", "")
API_VERSION = os.environ.get("WA_API_VERSION", "v23.0")
STATUS_TEMPLATE = os.environ.get("WA_STATUS_TEMPLATE", "")
TEMPLATE_LANG = os.environ.get("WA_TEMPLATE_LANG", "en")
WEBHOOK_PORT = int(os.environ.get("WA_WEBHOOK_PORT", "8081"))
LIVE = bool(TOKEN and PHONE_NUMBER_ID)
GRAPH = f"https://graph.facebook.com/{API_VERSION}"
MAX_WEBHOOK_BODY = 1024 * 1024

# Set by bot.py: called as message_handler(wa_id, profile_name, parsed_input, channel).
message_handler = None

# ---------- Message builders (Cloud API "messages" payload bodies) ----------

LIMITS = {"text": 4096, "body": 1024, "footer": 60, "buttons": 3, "button_title": 20, "list_button": 20,
          "sections": 10, "rows": 10, "section_title": 24, "row_title": 24, "row_desc": 72, "id": 200}


def text(body):
    return {"type": "text", "text": {"preview_url": False, "body": body}}


def buttons(body, items):
    """items: [(id, title), ...], at most 3."""
    return {"type": "interactive", "interactive": {
        "type": "button", "body": {"text": body},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t}} for i, t in items]},
    }}


def list_message(body, button, sections):
    """sections: [(title, [(id, title, description), ...]), ...], at most 10 rows in total."""
    return {"type": "interactive", "interactive": {
        "type": "list", "body": {"text": body},
        "action": {"button": button, "sections": [
            {"title": st, "rows": [{"id": i, "title": t, **({"description": d} if d else {})} for i, t, d in rows]}
            for st, rows in sections]},
    }}


def template(name, lang, params):
    return {"type": "template", "template": {
        "name": name, "language": {"code": lang},
        "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}],
    }}


def problems(msg):
    """WhatsApp rejects messages that break these limits; return what is wrong (empty if fine)."""
    out = []
    if msg["type"] == "text" and len(msg["text"]["body"]) > LIMITS["text"]:
        out.append("text body too long")
    if msg["type"] != "interactive":
        return out
    ia = msg["interactive"]
    if len(ia["body"]["text"]) > LIMITS["body"]:
        out.append("interactive body too long")
    action = ia["action"]
    if ia["type"] == "button":
        if not 1 <= len(action["buttons"]) <= LIMITS["buttons"]:
            out.append("need 1-3 buttons")
        for b in action["buttons"]:
            r = b["reply"]
            if len(r["title"]) > LIMITS["button_title"]:
                out.append(f"button title too long: {r['title']!r}")
            if len(r["id"]) > LIMITS["id"]:
                out.append("button id too long")
    else:
        if len(action["button"]) > LIMITS["list_button"]:
            out.append(f"list button too long: {action['button']!r}")
        rows = [r for s in action["sections"] for r in s["rows"]]
        if not 1 <= len(rows) <= LIMITS["rows"]:
            out.append(f"need 1-10 rows, got {len(rows)}")
        ids = [r["id"] for r in rows]
        if len(ids) != len(set(ids)):
            out.append("duplicate row ids")
        for s in action["sections"]:
            if len(s.get("title", "")) > LIMITS["section_title"]:
                out.append(f"section title too long: {s['title']!r}")
        for r in rows:
            if len(r["title"]) > LIMITS["row_title"]:
                out.append(f"row title too long: {r['title']!r}")
            if len(r.get("description", "")) > LIMITS["row_desc"]:
                out.append(f"row description too long: {r['description']!r}")
    return out


# ---------- Outbox (simulator and dry-run log) ----------

_outbox = []
_outbox_lock = threading.Lock()
_seq = 0


def record(wa, direction, payload, preview=None):
    global _seq
    with _outbox_lock:
        _seq += 1
        entry = {"seq": _seq, "at": datetime.now().isoformat(timespec="seconds"), "wa": wa,
                 "dir": direction, "payload": payload}
        if preview:
            entry["preview"] = preview
        _outbox.append(entry)
        del _outbox[:-2000]
        return entry


def outbox_since(wa, after=0):
    with _outbox_lock:
        return [e for e in _outbox if e["wa"] == wa and e["seq"] > after]


def clear_outbox(wa):
    with _outbox_lock:
        _outbox[:] = [e for e in _outbox if e["wa"] != wa]


# ---------- Graph API ----------

def _graph(method, url, payload=None, raw=False):
    req = urllib.request.Request(
        url if url.startswith("https://") else GRAPH + url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = res.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Graph API {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from None
    return data if raw else json.loads(data)


def send(wa, msg, channel):
    """Send one message. channel "whatsapp" goes to Meta when LIVE; anything else to the outbox."""
    issues = problems(msg)
    if issues:
        print(f"[whatsapp] message to {wa} breaks limits: {issues}")
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": wa, **msg}
    if channel == "whatsapp" and LIVE:
        try:
            _graph("POST", f"/{PHONE_NUMBER_ID}/messages", payload)
            print(f"[whatsapp] sent {msg['type']} to {wa}")
        except (RuntimeError, OSError) as e:
            print(f"[whatsapp] send to {wa} failed: {e}")
        return
    record(wa, "out", payload)


_sim_media = {}


def register_sim_media(mime, data):
    media_id = "sim:" + secrets.token_hex(8)
    _sim_media[media_id] = (mime, data)
    return media_id


def fetch_media(media_id):
    """Return (mime_type, bytes) for an incoming image."""
    if media_id.startswith("sim:"):
        return _sim_media.pop(media_id)
    meta = _graph("GET", f"/{media_id}")
    return meta.get("mime_type", "image/jpeg"), _graph("GET", meta["url"], raw=True)


# ---------- Webhook ----------

_seen = OrderedDict()
_seen_lock = threading.Lock()


def _first_time(message_id):
    """Meta retries webhooks; handle each message id once."""
    with _seen_lock:
        if message_id in _seen:
            return False
        _seen[message_id] = True
        while len(_seen) > 1000:
            _seen.popitem(last=False)
        return True


def parse_message(m):
    kind = m.get("type")
    if kind == "text":
        return {"kind": "text", "text": m["text"].get("body", "")}
    if kind == "interactive":
        ia = m["interactive"]
        reply = ia.get("button_reply") or ia.get("list_reply") or {}
        return {"kind": "choice", "id": reply.get("id", ""), "title": reply.get("title", "")}
    if kind == "button":  # quick-reply button on a template message
        return {"kind": "text", "text": m["button"].get("text", "")}
    if kind == "image":
        return {"kind": "image", "media_id": m["image"]["id"], "mime": m["image"].get("mime_type", ""),
                "caption": m["image"].get("caption", "")}
    return {"kind": "other", "type": kind}


def process_webhook(payload, channel="whatsapp"):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for m in value.get("messages", []):  # delivery receipts arrive as "statuses" and are ignored
                if not _first_time(m.get("id")):
                    continue
                try:
                    message_handler(m["from"], names.get(m["from"], ""), parse_message(m), channel)
                except Exception as e:  # one bad message must not stop the rest
                    print(f"[whatsapp] could not handle message from {m.get('from')}: {e!r}")


def valid_signature(raw, header):
    if not APP_SECRET or not header:
        return False
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.encode("utf-8", "replace"))


def sim_payload(wa, name, message):
    """Wrap a simulated user message in the same envelope Meta posts to the webhook."""
    message = {"from": wa, "id": "wamid.sim." + secrets.token_hex(8),
               "timestamp": str(int(datetime.now().timestamp())), **message}
    return {"object": "whatsapp_business_account", "entry": [{"id": "sim", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "sim"},
        "contacts": [{"profile": {"name": name}, "wa_id": wa}], "messages": [message]}}]}]}


class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "SecondStitchWebhook/0.1"

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/webhook":
            return self.reply(404, "Not found")
        q = parse_qs(url.query)
        token = q.get("hub.verify_token", [""])[0]
        if q.get("hub.mode", [""])[0] == "subscribe" and hmac.compare_digest(token.encode(), VERIFY_TOKEN.encode()):
            return self.reply(200, q.get("hub.challenge", [""])[0])
        self.reply(403, "Forbidden")

    def do_POST(self):
        if urlparse(self.path).path != "/webhook":
            return self.reply(404, "Not found")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_WEBHOOK_BODY:
            return self.reply(413, "Too large")
        raw = self.rfile.read(length)
        if not valid_signature(raw, self.headers.get("X-Hub-Signature-256")):
            return self.reply(401, "Bad signature")
        self.reply(200, "OK")  # answer Meta at once; replies go out from a worker thread
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        threading.Thread(target=process_webhook, args=(payload,), daemon=True).start()

    def reply(self, status, body):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_webhook_server(host="127.0.0.1"):
    """Start the /webhook listener in the background when live settings are complete."""
    if not LIVE:
        return "WhatsApp: simulator only (no WA_TOKEN / WA_PHONE_NUMBER_ID). Open /bot to chat."
    missing = [k for k, v in (("WA_VERIFY_TOKEN", VERIFY_TOKEN), ("WA_APP_SECRET", APP_SECRET)) if not v]
    if missing:
        return f"WhatsApp: can send, but webhook NOT started (missing {', '.join(missing)})."
    server = ThreadingHTTPServer((host, WEBHOOK_PORT), WebhookHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tmpl = f", status template '{STATUS_TEMPLATE}'" if STATUS_TEMPLATE else ", no status template"
    return f"WhatsApp: live. Webhook at http://{host}:{WEBHOOK_PORT}/webhook (tunnel this port{tmpl})."


def info():
    return {"live": LIVE, "webhook_ready": LIVE and bool(VERIFY_TOKEN and APP_SECRET),
            "status_template": STATUS_TEMPLATE or None, "api_version": API_VERSION}
