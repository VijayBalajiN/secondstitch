"""Telegram Bot API transport: the same bot conversation, delivered through a Telegram bot.

Set TELEGRAM_TOKEN in website/.env (from @BotFather in Telegram; see TELEGRAM.md). The server then
asks Telegram for new messages itself (long polling), so there is no webhook, tunnel or open port.
Without the token nothing is sent.

The bot builds WhatsApp-style messages (whatsapp.text / buttons / list_message). to_telegram turns
each one into a sendMessage call: *bold* and _italic_ become HTML, reply buttons and list rows
become inline keyboard buttons, and list row descriptions move into the message text.

Telegram does not tell a bot the user's phone number, so the bot asks once with a "Share my phone
number" button. Only the user's own contact is accepted, so a chat can't claim someone else's orders.
"""
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import whatsapp  # noqa: F401  (loads website/.env)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
LIVE = bool(TOKEN)
API = "https://api.telegram.org"
POLL_TIMEOUT = 30
MAX_FILE = 20 * 1024 * 1024  # largest file the Bot API lets a bot download
NOOP = "noop"  # callback data of the "✓ chosen" button left on a message after a tap
COMMANDS = [("start", "Main menu"), ("track", "Track an order"), ("prices", "Popular prices"),
            ("cancel", "Clear an order in progress")]

# Set by bot.py: called as message_handler(chat_key, name, parsed_input, "telegram").
message_handler = None
username = ""


def chat_key(chat_id):
    return f"tg:{chat_id}"


# ---------- Bot API calls ----------

def call(method, payload=None, timeout=20):
    """POST one Bot API method. Errors never include the URL, because it contains the token."""
    req = urllib.request.Request(f"{API}/bot{TOKEN}/{method}", data=json.dumps(payload or {}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read())
        except ValueError:
            data = {}
        raise RuntimeError(f"Telegram {method} {e.code}: {data.get('description', e.reason)}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Telegram {method}: {e.reason}") from None
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description', 'not ok')}")
    return data["result"]


# ---------- Messages ----------

def fmt(s):
    """WhatsApp-style *bold* and _italic_ to Telegram HTML."""
    s = html.escape(s, quote=False)
    s = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", s)
    return re.sub(r"(^|\s)_([^_\n]+)_", r"\1<i>\2</i>", s)


def contact_request(body, button):
    """A message with a keyboard button that shares the user's own phone number (Telegram only)."""
    return {"type": "contact_request", "body": body, "button": button}


def to_telegram(msg):
    """The sendMessage fields (all but chat_id) for one bot message."""
    if msg["type"] == "text":
        out = {"text": fmt(msg["text"]["body"])}
        if msg.get("remove_keyboard"):
            out["reply_markup"] = {"remove_keyboard": True}
        return out
    if msg["type"] == "contact_request":
        return {"text": fmt(msg["body"]), "reply_markup": {
            "keyboard": [[{"text": msg["button"], "request_contact": True}]],
            "resize_keyboard": True, "one_time_keyboard": True}}
    if msg["type"] == "template":  # WhatsApp-only; Telegram has no 24-hour rule, so send the words
        return {"text": fmt(" · ".join(p["text"] for p in msg["template"]["components"][0]["parameters"]))}
    ia = msg["interactive"]
    body = ia["body"]["text"]
    if ia["type"] == "button":
        items = [(b["reply"]["id"], b["reply"]["title"]) for b in ia["action"]["buttons"]]
    else:
        rows = [r for s in ia["action"]["sections"] for r in s["rows"]]
        items = [(r["id"], r["title"]) for r in rows]
        details = [f"• *{r['title']}*: {r['description']}" for r in rows if r.get("description")]
        if details:
            body += "\n\n" + "\n".join(details)
    return {"text": fmt(body),
            "reply_markup": {"inline_keyboard": [[{"text": t, "callback_data": i}] for i, t in items]}}


def send(chat_id, msg):
    try:
        call("sendMessage", {"chat_id": chat_id, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True},
                             **to_telegram(msg)})
    except (RuntimeError, OSError) as e:
        print(f"[telegram] send to {chat_id} failed: {e}")


def fetch_media(media_id):
    """Return (mime_type, bytes) for a photo the user sent."""
    f = call("getFile", {"file_id": media_id.removeprefix("tg:")})
    if f.get("file_size", 0) > MAX_FILE or "file_path" not in f:
        raise ValueError("photo too large to download")
    try:
        with urllib.request.urlopen(f"{API}/file/bot{TOKEN}/{f['file_path']}", timeout=30) as res:
            data = res.read(MAX_FILE + 1)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Telegram file download failed: {getattr(e, 'code', '') or e.reason}") from None
    ext = f["file_path"].rsplit(".", 1)[-1].lower()
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, ext), data


# ---------- Updates ----------

def _name(user):
    return " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)


def _ack(cq, msg, title):
    """Stop the button's spinner and replace the keyboard with the choice, so old options can't be tapped."""
    try:
        call("answerCallbackQuery", {"callback_query_id": cq["id"]})
        if msg.get("message_id") and title:
            call("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                            "reply_markup": {"inline_keyboard": [[{"text": f"✓ {title}", "callback_data": NOOP}]]}})
    except (RuntimeError, OSError) as e:
        if "not modified" not in str(e):
            print(f"[telegram] {e}")


def parse_update(u):
    """(chat_key, name, input) for an update the bot should answer, or None."""
    if "callback_query" in u:
        cq = u["callback_query"]
        msg = cq.get("message") or {}
        data = cq.get("data", "")
        buttons = [b for row in (msg.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]
        title = next((b["text"] for b in buttons if b.get("callback_data") == data), "")
        _ack(cq, msg, title if data != NOOP else "")
        if data == NOOP or msg.get("chat", {}).get("type") != "private":
            return None
        return chat_key(msg["chat"]["id"]), _name(cq["from"]), {"kind": "choice", "id": data, "title": title}

    m = u.get("message")
    if not m or m.get("chat", {}).get("type") != "private":
        return None  # groups and channels are ignored
    user = m.get("from", {})
    key, name = chat_key(m["chat"]["id"]), _name(user)
    if "contact" in m:
        c = m["contact"]
        own = c.get("user_id") == user.get("id")
        return key, name, {"kind": "contact", "own": own, "phone": c.get("phone_number", "") if own else ""}
    if m.get("photo"):
        return key, name, {"kind": "image", "media_id": "tg:" + m["photo"][-1]["file_id"], "mime": "image/jpeg",
                           "caption": m.get("caption", "")}
    doc = m.get("document") or {}
    if doc.get("mime_type", "").startswith("image/"):
        return key, name, {"kind": "image", "media_id": "tg:" + doc["file_id"], "mime": doc["mime_type"],
                           "caption": m.get("caption", "")}
    if "text" in m:
        text = m["text"]
        if text.startswith("/"):  # /start, /track, /prices, /cancel (and /track@BotName)
            text = text[1:].split()[0].split("@")[0] if text[1:].strip() else text
        return key, name, {"kind": "text", "text": text}
    return key, name, {"kind": "other", "type": "unsupported"}


def handle_update(u):
    try:
        parsed = parse_update(u)
        if parsed:
            message_handler(*parsed, "telegram")
    except Exception as e:  # one bad update must not stop the rest
        print(f"[telegram] could not handle update {u.get('update_id')}: {e!r}")


def poll_once(offset=None):
    """Wait up to POLL_TIMEOUT seconds for updates, handle them, and return the next offset."""
    payload = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message", "callback_query"]}
    if offset is not None:
        payload["offset"] = offset
    for u in call("getUpdates", payload, timeout=POLL_TIMEOUT + 10):
        offset = u["update_id"] + 1
        handle_update(u)
    return offset


def poll_forever():
    offset, delay = None, 1
    while True:
        try:
            offset = poll_once(offset)
            delay = 1
        except (RuntimeError, OSError) as e:
            hint = " (is another copy of the server running with this token?)" if "409" in str(e) else ""
            print(f"[telegram] {e}{hint}; retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 60)


def start():
    """Check the token and start polling in the background."""
    global username
    if not LIVE:
        return "Telegram: off (no TELEGRAM_TOKEN in .env; see TELEGRAM.md)."
    try:
        username = call("getMe")["username"]
    except (RuntimeError, OSError) as e:
        return f"Telegram: NOT started ({e}). Check TELEGRAM_TOKEN in .env and your internet connection."
    try:
        call("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMMANDS]})
    except (RuntimeError, OSError):
        pass  # the command menu is a nicety
    threading.Thread(target=poll_forever, daemon=True).start()
    return f"Telegram: live as @{username}. Open https://t.me/{username} and press Start."
