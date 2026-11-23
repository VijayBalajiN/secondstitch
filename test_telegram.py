"""Telegram tests: full conversations against a fake Bot API server, message conversion, phone
sharing, status messages and polling.

Run:  python3 -m unittest test_telegram.py
"""
import base64
import itertools
import json
import os
import re
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["SECONDSTITCH_DATA"] = tempfile.mkdtemp(prefix="ss-test-")
for key in ("WA_TOKEN", "WA_PHONE_NUMBER_ID", "WA_VERIFY_TOKEN", "WA_APP_SECRET", "WA_STATUS_TEMPLATE", "TELEGRAM_TOKEN"):
    os.environ[key] = ""  # never pick up a real .env during tests

import bot  # noqa: E402
import orders  # noqa: E402
import pricing  # noqa: E402
import telegram  # noqa: E402

bot.notify_inline = True
TOKEN = "123456:TEST-TOKEN"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
update_ids = itertools.count(1)


class FakeBotApi(BaseHTTPRequestHandler):
    """Answers the Bot API methods the bot uses and records every call."""
    calls = []  # (method, payload, message_id or None)
    updates = []
    lock = threading.Lock()

    def do_POST(self):
        m = re.fullmatch(r"/bot([^/]+)/(\w+)", self.path)
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if not m or m.group(1) != TOKEN:
            return self.reply(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
        method = m.group(2)
        with self.lock:
            mid = len(self.calls) + 1 if method == "sendMessage" else None
            self.calls.append((method, payload, mid))
            result = {"sendMessage": {"message_id": mid}, "getMe": {"username": "SecondStitchTestBot"},
                      "getFile": {"file_id": payload.get("file_id"), "file_path": "photos/file_7.png",
                                  "file_size": len(PNG)},
                      "getUpdates": self.updates[:]}.get(method, True)
            if method == "getUpdates":
                self.updates.clear()
        self.reply(200, {"ok": True, "result": result})

    def do_GET(self):
        if self.path == f"/file/bot{TOKEN}/photos/file_7.png":
            self.send_response(200)
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            self.wfile.write(PNG)
        else:
            self.reply(404, {"ok": False})

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def setUpModule():
    global server
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBotApi)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    telegram.API = f"http://127.0.0.1:{server.server_address[1]}"
    telegram.TOKEN, telegram.LIVE = TOKEN, True


def tearDownModule():
    server.shutdown()
    telegram.TOKEN, telegram.LIVE = "", False


def buttons(body):
    return [b["callback_data"] for row in (body.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]


def texts(sent):
    return " ".join(b["text"] for _, b in sent)


class TgChat:
    """One Telegram user talking to the bot in a private chat."""

    def __init__(self, chat_id, first="Asha", last="Rao"):
        self.id = chat_id
        self.user = {"id": chat_id, "is_bot": False, "first_name": first, "last_name": last}
        self.sent = []  # (message_id, sendMessage payload) for this chat
        bot.reset_session(telegram.chat_key(chat_id))

    def _update(self, **kind):
        before = len(FakeBotApi.calls)
        telegram.handle_update({"update_id": next(update_ids), **kind})
        return self.collect(before)

    def collect(self, before):
        new = [(mid, p) for m, p, mid in FakeBotApi.calls[before:] if m == "sendMessage" and p["chat_id"] == str(self.id)]
        self.sent += new
        return new

    def message(self, **fields):
        return self._update(message={"message_id": 1, "chat": {"id": self.id, "type": "private"}, "from": self.user,
                                     "date": 0, **fields})

    def say(self, text):
        return self.message(text=text)

    def tap(self, data):
        mid, body = next((mid, b) for mid, b in reversed(self.sent) if data in buttons(b))
        return self._update(callback_query={"id": f"cq{mid}", "from": self.user, "data": data, "message": {
            "message_id": mid, "chat": {"id": self.id, "type": "private"}, "reply_markup": body["reply_markup"]}})

    def share(self, phone="+91 90000 00101", own=True):
        return self.message(contact={"phone_number": phone, "first_name": "Asha",
                                     "user_id": self.id if own else 4242})

    def photo(self):
        return self.message(photo=[{"file_id": "small", "width": 90}, {"file_id": "big", "width": 1280}])


class ConversionTest(unittest.TestCase):
    def test_formatting_is_escaped_html(self):
        out = telegram.to_telegram(bot.T("*Bold* & _italic_ <script>"))
        self.assertEqual(out["text"], "<b>Bold</b> &amp; <i>italic</i> &lt;script&gt;")

    def test_list_rows_become_buttons_with_details_in_text(self):
        s = {"wa": "tg:1", "cat": "hems", "draft": {"garments": [bot.new_garment()]}}
        out = telegram.to_telegram(bot.ask_service(s)[0])
        self.assertIn("svc:trouser-hem", buttons(out))
        pr = pricing.SERVICE_BY_ID["trouser-hem"]["prices"]
        self.assertIn(f"<b>Trouser/jeans hem</b>: ₹{pr['standard']} Standard · ₹{pr['premium']} Premium", out["text"])

    def test_every_button_fits_telegram_limits(self):
        s = {"wa": "tg:1", "draft": {"garments": [bot.new_garment()], "speed": "standard", "handover": "counter"}}
        msgs = bot.ask_category(s) + bot.ask_counter(s) + bot.ask_date(s) + bot.ask_fit(s) + [bot.ask_rating()]
        for key in bot.CATEGORY:
            s["cat"] = key
            msgs += bot.ask_service(s)
        for msg in msgs:
            out = telegram.to_telegram(msg)
            self.assertLessEqual(len(out["text"]), 4096)
            for row in out["reply_markup"]["inline_keyboard"]:
                for b in row:
                    self.assertTrue(b["text"])
                    self.assertLessEqual(len(b["callback_data"].encode()), 64, b)


class ConversationTest(unittest.TestCase):
    def test_full_order_with_phone_share_photo_status_and_rating(self):
        self.assertTrue(pricing.SERVICE_BY_ID["trouser-hem"]["fit"])
        c = TgChat(7001)
        out = c.say("/start")
        self.assertIn("Hi Asha", texts(out))
        self.assertEqual(out[-1][1]["parse_mode"], "HTML")
        self.assertEqual(buttons(out[-1][1]), ["new", "track", "prices"])
        self.assertIn("<b>Popular prices</b>", texts(c.say("/prices")))

        for data, expect in [("new", "cat:hems"), ("cat:hems", "svc:trouser-hem"), ("svc:trouser-hem", "fab:everyday"),
                             ("fab:everyday", "done"), ("done", "fit:measurement")]:
            out = c.tap(data)
            self.assertIn(expect, buttons(out[-1][1]), (data, out))
        self.assertIn("Type the measurement", texts(c.tap("fit:measurement")))
        self.assertIn("skip", buttons(c.say("Shorten by 1 inch")[-1][1]))
        out = c.photo()
        self.assertIn("Got the photo", texts(out))
        self.assertIn("tier:standard", buttons(out[-1][1]))
        self.assertIn("ho:counter", buttons(c.tap("tier:standard")[-1][1]))
        self.assertIn("ct:c-market", buttons(c.tap("ho:counter")[-1][1]))
        self.assertIn(f"dt:{TOMORROW}", buttons(c.tap("ct:c-market")[-1][1]))

        out = c.tap(f"dt:{TOMORROW}")
        keyboard = out[-1][1]["reply_markup"]["keyboard"]
        self.assertTrue(keyboard[0][0]["request_contact"])
        self.assertIn("Typed numbers", texts(c.say("9000000101")))
        self.assertIn("someone else's", texts(c.share(own=False)))
        out = c.share()
        self.assertEqual(out[0][1]["reply_markup"], {"remove_keyboard": True})
        self.assertIn("Total", texts(out))
        before = len(FakeBotApi.calls)
        self.assertIn("is confirmed", texts(c.tap("confirm")))
        edits = [p for m, p, _ in FakeBotApi.calls[before:] if m == "editMessageReplyMarkup"]
        self.assertEqual(edits[0]["reply_markup"]["inline_keyboard"][0][0]["text"], "✓ Confirm order")
        self.assertIn("answerCallbackQuery", [m for m, _, _ in FakeBotApi.calls[before:]])

        order = orders.store.by_phone("9000000101")[0]
        self.assertEqual((order["source"], order["customer"]["name"]), ("telegram", "Asha Rao"))
        self.assertEqual(order["garments"][0]["fit"]["value"], "Shorten by 1 inch")
        self.assertTrue((orders.UPLOADS / order["garments"][0]["photo"].split("/")[-1]).exists())
        self.assertEqual(list(bot.MEDIA_DIR.glob("tg-7001-*")), [])

        before = len(FakeBotApi.calls)
        orders.store.update(order["id"], orders.scan)
        self.assertIn("collected", texts(c.collect(before)))
        before = len(FakeBotApi.calls)
        for _ in range(4):
            orders.store.update(order["id"], orders.scan)
        out = c.collect(before)
        self.assertIn("delivered", texts(out))
        self.assertIn("rate:4", buttons(out[-1][1]))
        self.assertIn("4/5", texts(c.tap("rate:4")))
        self.assertEqual(orders.store.get(order["id"])["rating"], 4)

    def test_tapping_the_chosen_tick_does_nothing(self):
        c = TgChat(7002)
        c.say("hi")
        before = len(FakeBotApi.calls)
        telegram.handle_update({"update_id": next(update_ids), "callback_query": {
            "id": "x", "from": c.user, "data": telegram.NOOP,
            "message": {"message_id": 5, "chat": {"id": c.id, "type": "private"}}}})
        self.assertEqual([m for m, _, _ in FakeBotApi.calls[before:]], ["answerCallbackQuery"])

    def test_foreign_number_is_refused(self):
        c = TgChat(7003)
        s = bot.sessions.get(telegram.chat_key(c.id))
        s.update(channel="telegram", step="phone", draft={"garments": []})
        out = c.share(phone="+44 7700 900123")
        self.assertIn("Indian mobile", texts(out))
        self.assertEqual(bot.sessions.get(telegram.chat_key(c.id))["step"], "idle")

    def test_website_order_for_shared_number_updates_telegram(self):
        c = TgChat(7004)
        s = bot.sessions.get(telegram.chat_key(c.id))
        s.update(channel="telegram", phone="9000000104")
        before = len(FakeBotApi.calls)
        order = orders.create_order({"tier": "standard", "speed": "standard", "handover": "counter", "date": TOMORROW,
                                     "garments": [{"fabric": "everyday", "jobs": [{"id": "trouser-hem", "qty": 1}],
                                                   "fit": {"method": "mark"}}],
                                     "customer": {"name": "Ravi K", "phone": "9000000104", "counter": "c-market"}})
        self.assertIn(f"{order['id']}</b> is confirmed", texts(c.collect(before)))
        self.assertIn(order["id"], texts(c.say("/track")))

    def test_group_chats_are_ignored(self):
        before = len(FakeBotApi.calls)
        telegram.handle_update({"update_id": next(update_ids), "message": {
            "message_id": 1, "chat": {"id": -100, "type": "group"}, "from": {"id": 1, "first_name": "A"}, "text": "hi"}})
        self.assertEqual(FakeBotApi.calls[before:], [])


class TransportTest(unittest.TestCase):
    def test_poll_once_handles_updates_and_advances_offset(self):
        c = TgChat(7005)
        FakeBotApi.updates.append({"update_id": 900, "message": {
            "message_id": 1, "chat": {"id": c.id, "type": "private"}, "from": c.user, "date": 0, "text": "hi"}})
        before = len(FakeBotApi.calls)
        self.assertEqual(telegram.poll_once(None), 901)
        self.assertIn("Hi Asha", texts(c.collect(before)))
        self.assertEqual(telegram.poll_once(901), 901)

    def test_errors_never_show_the_token(self):
        telegram.TOKEN = "999:WRONG"
        try:
            with self.assertRaises(RuntimeError) as e:
                telegram.call("getMe")
        finally:
            telegram.TOKEN = TOKEN
        self.assertIn("401", str(e.exception))
        self.assertNotIn("WRONG", str(e.exception))

    def test_start_reports_bot_link(self):
        real, telegram.poll_forever = telegram.poll_forever, lambda: None  # no background polling in tests
        try:
            self.assertIn("t.me/SecondStitchTestBot", telegram.start())
        finally:
            telegram.poll_forever = real
        commands = [p for m, p, _ in FakeBotApi.calls if m == "setMyCommands"][-1]["commands"]
        self.assertEqual([c["command"] for c in commands], ["start", "track", "prices", "cancel"])


if __name__ == "__main__":
    unittest.main()
