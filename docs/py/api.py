"""The SecondStitch JSON API, with no web server around it.

server.py (this computer) and static_api.py (the copy that runs inside the browser on GitHub Pages) both
call route(), so the two behave the same.
"""
import base64
import re
from datetime import datetime

import bot
import orders
import pricing
import telegram
import whatsapp
from orders import ApiError, store

WA_RE = re.compile(r"\d{10,15}")
SIM_PHOTO_RE = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")


def sim_message(body):
    """Turn a simulator chat action into a Cloud API webhook message and run it through the bot."""
    wa = str(body.get("wa", ""))
    if not WA_RE.fullmatch(wa):
        raise ApiError("Use the number in international format, digits only (e.g. 919876543210).")
    kind = body.get("kind")
    preview = None
    if kind == "text":
        text = str(body.get("text", ""))[:4096]
        if not text.strip():
            raise ApiError("Type a message.")
        message = {"type": "text", "text": {"body": text}}
    elif kind == "choice":
        reply = {"id": str(body.get("id", ""))[:200], "title": str(body.get("title", ""))[:24]}
        sub = "list_reply" if body.get("list") else "button_reply"
        message = {"type": "interactive", "interactive": {"type": sub, sub: reply}}
    elif kind == "image":
        m = SIM_PHOTO_RE.match(body.get("image") or "")
        if not m:
            raise ApiError("Photo must be a JPEG, PNG or WebP image.")
        media_id = whatsapp.register_sim_media(m.group(1), base64.b64decode(m.group(2)))
        message = {"type": "image", "image": {"id": media_id, "mime_type": m.group(1)}}
        preview = body["image"]
    else:
        raise ApiError("Unknown message kind.")
    payload = whatsapp.sim_payload(wa, str(body.get("name", ""))[:60], message)
    whatsapp.record(wa, "in", payload["entry"][0]["changes"][0]["value"]["messages"][0], preview)
    whatsapp.process_webhook(payload, channel="sim")


def route(method, path, body, query=None, ops_ok=True):
    """Run one API call. query is a parse_qs dict; ops_ok says whether this caller may use the ops desk."""
    query = query or {}
    if path.startswith("/api/ops/") and not ops_ok:
        raise ApiError("Enter the ops desk PIN shown in the server window.", 401)
    if (method, path) == ("GET", "/api/catalogue"):
        return pricing.catalogue()
    if (method, path) == ("GET", "/api/channels"):
        return {"telegram": telegram.username or None, "whatsapp": whatsapp.LIVE}
    if (method, path) == ("GET", "/api/calendar"):
        return {"today": datetime.now().date().isoformat(), "days": pricing.calendar(datetime.now().date())}
    if (method, path) == ("POST", "/api/quote"):
        return pricing.quote(body)
    if (method, path) == ("POST", "/api/orders"):
        return orders.public_view(orders.create_order(body))
    if (method, path) == ("GET", "/api/ops/orders"):
        return {"orders": store.all(), "statuses": orders.STATUSES}
    if (method, path) == ("GET", "/api/ops/jobs"):
        return orders.tailor_jobs(store.all())

    if path.startswith("/api/bot-sim/"):
        return bot_sim(method, path, body, query)

    m = re.fullmatch(r"/api/(ops/)?orders/(SS-[A-Z0-9]{5})(?:/([a-z-]+))?", path)
    if m:
        ops, oid, action = m.groups()
        view = (lambda o: o) if ops else orders.public_view
        if method == "GET" and not action:
            return view(store.get(oid))
        if method == "POST":
            actions = {
                (None, "cancel"): orders.cancel,
                (None, "rate"): lambda o: orders.rate(o, body.get("stars")),
                ("ops/", "scan"): orders.scan,
                ("ops/", "qc-fail"): orders.qc_fail,
                ("ops/", "tailor-done"): orders.tailor_done,
            }
            fn = actions.get((ops, action))
            if fn:
                done = store.update(oid, fn)
                return orders.tailor_view(done) if action == "tailor-done" else view(done)
    raise ApiError("Not found", 404)


def bot_sim(method, path, body, query):
    if (method, path) == ("GET", "/api/bot-sim/info"):
        return whatsapp.info()
    wa = body.get("wa") if method == "POST" else query.get("wa", [""])[0]
    if not WA_RE.fullmatch(str(wa or "")):
        raise ApiError("Use the number in international format, digits only (e.g. 919876543210).")
    if (method, path) == ("GET", "/api/bot-sim/outbox"):
        after = int(query.get("after", ["0"])[0] or 0)
        return {"messages": whatsapp.outbox_since(wa, after)}
    if (method, path) == ("POST", "/api/bot-sim/message"):
        sim_message(body)
        return {"messages": whatsapp.outbox_since(wa, int(body.get("after") or 0))}
    if (method, path) == ("POST", "/api/bot-sim/reset"):
        bot.reset_session(wa)
        whatsapp.clear_outbox(wa)
        return {"ok": True}
    raise ApiError("Not found", 404)
