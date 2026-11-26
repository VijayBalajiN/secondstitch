#!/usr/bin/env python3
"""SecondStitch local website: static pages, the JSON order API and the WhatsApp bot.

Run:   python3 server.py            (then open http://127.0.0.1:8080)
       python3 server.py --lan      (share on your Wi-Fi; prints the address to give others)
       PORT=9000 python3 server.py

Standard library only. Orders live in data/orders.json (see orders.py). By default the server binds
to 127.0.0.1, so only this computer can reach it. With --lan it listens on every network interface;
the ops desk API asks other devices, including visitors through a tunnel, for a PIN (OPS_PIN, or a
random one printed at start), while this computer needs none. The WhatsApp webhook always stays on 127.0.0.1.
WhatsApp and Telegram settings come from .env (see .env.example, WHATSAPP.md and TELEGRAM.md).
"""
import base64
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import api
import bot
import orders
import pricing
import telegram
import whatsapp
from orders import ApiError, store

sim_message = api.sim_message   # kept here for the tests that import it from server

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"

LAN = "--lan" in sys.argv[1:]
HOST = "0.0.0.0" if LAN else "127.0.0.1"
OPS_PIN = os.environ.get("OPS_PIN") or f"{secrets.randbelow(10**6):06d}"
FORWARD_HEADERS = ("X-Forwarded-For", "Forwarded", "Cf-Connecting-Ip", "X-Real-Ip")
PORT = int(os.environ.get("PORT", "8080"))
MAX_BODY = 16 * 1024 * 1024

PAGES = {"/": "index.html", "/order": "order.html", "/help": "help.html", "/track": "track.html",
         "/ops": "ops.html", "/bot": "bot.html", "/credits": "credits.html"}
UPLOAD_RE = re.compile(r"^/uploads/(SS-[A-Z0-9]{5}-\d\.(?:jpeg|png|webp))$")
WA_RE = re.compile(r"\d{10,15}")
SIM_PHOTO_RE = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")


def lan_address():
    """This computer's address on the local network (no packets are sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return None


class Handler(BaseHTTPRequestHandler):
    server_version = "SecondStitch/0.2"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("GET", path)
        if path.startswith("/uploads/"):
            return self.serve_upload(path)
        return self.serve_static(path)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("POST", path)
        self.send_json({"error": "Not found"}, 404)

    def api(self, method, path):
        try:
            body = self.read_json() if method == "POST" else {}
            self.send_json(self.route(method, path, body))
        except ApiError as e:
            self.send_json({"error": str(e), "errors": e.errors}, e.status)
        except Exception as e:  # keep the demo server alive and say what broke
            self.log_error("API error on %s: %r", path, e)
            self.send_json({"error": "Something went wrong on the server."}, 500)

    def ops_allowed(self):
        """The ops desk is open to this computer; other devices (Wi-Fi or a tunnel) need the PIN.
        A tunnel such as cloudflared connects from 127.0.0.1, so forwarded requests count as remote."""
        forwarded = any(self.headers.get(h) for h in FORWARD_HEADERS)
        if self.client_address[0] in ("127.0.0.1", "::1") and not forwarded:
            return True
        return secrets.compare_digest(self.headers.get("X-Ops-Pin", ""), OPS_PIN)

    def route(self, method, path, body):
        return api.route(method, path, body, parse_qs(urlparse(self.path).query), self.ops_allowed())

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError("Request too large.", 413)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise ApiError("Request body must be JSON.")
        if not isinstance(data, dict):
            raise ApiError("Request body must be a JSON object.")
        return data

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_file(self, file):
        data = file.read_bytes()
        ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def serve_static(self, path):
        name = PAGES.get(path.rstrip("/") or "/", path.lstrip("/"))
        file = (PUBLIC / name).resolve()
        if PUBLIC not in file.parents or not file.is_file():
            return self.send_json({"error": "Not found"}, 404)
        self.send_file(file)

    def serve_upload(self, path):
        m = UPLOAD_RE.match(path)
        file = orders.UPLOADS / m.group(1) if m else None
        if not file or not file.is_file():
            return self.send_json({"error": "Not found"}, 404)
        self.send_file(file)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SecondStitch running at http://127.0.0.1:{PORT}  (ops desk: /ops, bot simulator: /bot)  Ctrl+C to stop")
    if LAN:
        ip = lan_address()
        print(f"Shared on your Wi-Fi: http://{ip or 'THIS-COMPUTERS-IP'}:{PORT}")
        print("Anyone on this network can open the site and bot simulator. Stop with Ctrl+C when done.")
    print(f"Ops desk PIN for other devices (Wi-Fi or tunnel): {OPS_PIN}  (this computer needs none)")
    print(whatsapp.start_webhook_server("127.0.0.1"))
    print(telegram.start())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
