"""WhatsApp bot tests: full conversations through the webhook path, message limits, status messages,
signatures and the 24-hour rule.

Run:  python3 -m unittest test_bot.py
"""
import base64
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

os.environ["SECONDSTITCH_DATA"] = tempfile.mkdtemp(prefix="ss-test-")
for key in ("WA_TOKEN", "WA_PHONE_NUMBER_ID", "WA_VERIFY_TOKEN", "WA_APP_SECRET", "WA_STATUS_TEMPLATE", "TELEGRAM_TOKEN"):
    os.environ[key] = ""  # never pick up a real .env during tests

import bot  # noqa: E402
import orders  # noqa: E402
import pricing  # noqa: E402
import whatsapp  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

bot.notify_inline = True
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


class Chat:
    """Drives one simulated WhatsApp user through the real webhook parsing path."""

    def __init__(self, wa, name="Asha Rao"):
        self.wa, self.name, self.seen = wa, name, 0
        bot.reset_session(wa)
        whatsapp.clear_outbox(wa)

    def _send(self, message):
        whatsapp.process_webhook(whatsapp.sim_payload(self.wa, self.name, message), channel="sim")
        return self.new()

    def new(self):
        out = [e["payload"] for e in whatsapp.outbox_since(self.wa, self.seen) if e["dir"] == "out"]
        entries = whatsapp.outbox_since(self.wa, self.seen)
        if entries:
            self.seen = entries[-1]["seq"]
        return out

    def say(self, text):
        return self._send({"type": "text", "text": {"body": text}})

    def tap(self, reply_id, kind="button_reply"):
        return self._send({"type": "interactive", "interactive": {"type": kind, kind: {"id": reply_id, "title": "x"}}})

    def pick(self, reply_id):
        return self.tap(reply_id, "list_reply")

    def photo(self, data=PNG, mime="image/png"):
        return self._send({"type": "image", "image": {"id": whatsapp.register_sim_media(mime, data), "mime_type": mime}})


def ids(msg):
    ia = msg.get("interactive")
    if not ia:
        return []
    if ia["type"] == "button":
        return [b["reply"]["id"] for b in ia["action"]["buttons"]]
    return [r["id"] for s in ia["action"]["sections"] for r in s["rows"]]


def texts(msgs):
    return " ".join(m["text"]["body"] for m in msgs if m["type"] == "text")


class ConversationTest(unittest.TestCase):
    def assertValid(self, msgs):
        for m in msgs:
            self.assertEqual(whatsapp.problems(m), [], m)

    def test_premium_express_order_then_status_and_rating(self):
        c = Chat("919000000001")
        steps = [
            (c.say, "hi", "new"), (c.tap, "new", "cat:resize"), (c.pick, "cat:resize", "svc:blouse"),
            (c.pick, "svc:blouse", "fab:delicate"), (c.tap, "fab:delicate", "done"),
            (c.tap, "done", "fit:mark"), (c.pick, "fit:mark", "skip"),
        ]
        for action, arg, expect in steps:
            out = action(arg)
            self.assertValid(out)
            self.assertIn(expect, ids(out[-1]), (arg, out))

        out = c.photo()
        self.assertIn("Got the photo", texts(out))
        self.assertIn("Premium", texts(out))
        self.assertIn("sp:express", ids(out[-1]))
        out = c.tap("sp:express")
        self.assertIn("ho:counter", ids(out[-1]))
        out = c.tap("ho:counter")
        self.assertIn("ct:c-market", ids(out[-1]))
        out = c.pick("ct:c-market")
        self.assertIn(f"dt:{TOMORROW}", ids(out[-1]))
        out = c.pick(f"dt:{TOMORROW}")
        self.assertValid(out)
        self.assertIn("Total", texts(out))
        out = c.tap("confirm")
        self.assertIn("is confirmed", texts(out))

        order = orders.store.by_phone("9000000001")[0]
        expected = pricing.quote({"tier": "premium", "speed": "express", "handover": "counter", "date": TOMORROW,
                                  "garments": [{"fabric": "delicate", "jobs": [{"id": "blouse", "qty": 1}]}]})
        self.assertEqual(order["source"], "whatsapp")
        self.assertEqual(order["quote"]["total"], expected["total"])
        self.assertEqual(order["garments"][0]["fit"]["method"], "mark")
        self.assertTrue((orders.UPLOADS / order["garments"][0]["photo"].split("/")[-1]).exists())
        self.assertEqual(list(bot.MEDIA_DIR.glob("919000000001-*")), [])  # temp photo cleaned up
        self.assertEqual(c.new(), [])  # no duplicate "confirmed" message for WhatsApp orders

        oid = order["id"]
        orders.store.update(oid, orders.scan)
        self.assertIn("collected", texts(c.new()))
        orders.store.update(oid, orders.scan)
        orders.store.update(oid, orders.qc_fail)
        out = c.new()
        self.assertIn("your tailor is on it", texts(out))
        self.assertIn("free redo", texts(out))
        for _ in range(3):
            orders.store.update(oid, orders.scan)
        out = c.new()
        self.assertIn("delivered", texts(out))
        self.assertIn("rate:5", ids(out[-1]))
        self.assertValid(out)
        out = c.pick("rate:5")
        self.assertIn("5/5", texts(out))
        self.assertEqual(orders.store.get(oid)["rating"], 5)

    def test_standard_two_garments_pickup_measurement(self):
        c = Chat("919000000002", name="")
        c.say("hi")
        c.tap("new")
        c.pick("cat:buttons")
        c.pick("svc:button")
        out = c.say("3")  # typed instead of tapped
        self.assertIn("fab:everyday", ids(out[-1]))
        c.tap("fab:everyday")
        out = c.tap("garment")
        self.assertIn("skip", ids(out[-1]))  # no fit job: straight to photo
        out = c.tap("skip")
        self.assertIn("Garment 2", out[-1]["interactive"]["body"]["text"])
        c.pick("cat:hems")
        c.pick("svc:trouser-hem")
        c.tap("fab:everyday")
        c.tap("done")
        c.pick("fit:measurement")
        c.say("Shorten by 1 inch")
        out = c.tap("skip")
        titles = [b["reply"]["title"] for b in out[-1]["interactive"]["action"]["buttons"]]
        self.assertTrue(any(t.startswith("Standard · ₹") for t in titles), titles)
        out = c.tap("tier:standard")
        self.assertIn("ho:pickup-4", ids(out[-1]))  # Standard skips the speed question
        c.tap("ho:pickup-4")
        out = c.say("Flat 4B, Lake View Apartments, near the park")
        first_day = ids(out[-1])[0]
        out = c.pick(first_day)
        self.assertIn("your name", texts(out))  # no profile name given
        out = c.say("Ravi Kumar")
        self.assertIn("Total", texts(out))
        c.tap("confirm")

        order = orders.store.by_phone("9000000002")[0]
        jobs = [(j["id"], j["qty"]) for g in order["quote"]["garments"] for j in g["jobs"]]
        self.assertEqual(jobs, [("button", 1), ("extra-button", 2), ("trouser-hem", 1)])
        self.assertEqual(order["garments"][1]["fit"], {"method": "measurement", "label": pricing.FIT_METHODS["measurement"],
                                                       "value": "Shorten by 1 inch"})
        self.assertEqual(order["customer"]["name"], "Ravi Kumar")
        self.assertIn("Lake View", order["customer"]["address"])

    def test_every_service_reachable_with_valid_rows(self):
        listed = {sid for _, _, _, sids in bot.CATEGORIES for sid in sids}
        self.assertEqual(listed | {"extra-button"}, set(pricing.SERVICE_BY_ID))
        c = Chat("919000000003")
        c.say("hi")
        c.tap("new")
        for key, *_ in bot.CATEGORIES:
            out = c.pick(f"cat:{key}")
            self.assertValid(out)
            c.pick("back")

    def test_nudges_cancel_and_prices(self):
        c = Chat("919000000004")
        c.say("hi")
        c.tap("new")
        out = c.say("blah")
        self.assertIn("Please pick", texts(out))
        self.assertTrue(ids(out[-1])[0].startswith("cat:"))
        out = c.say("cancel")
        self.assertIn("cleared", texts(out))
        out = c.tap("prices")
        self.assertIn("Popular prices", texts(out))
        self.assertValid(out)

    def test_website_order_gets_whatsapp_updates_and_tracking(self):
        c = Chat("919000000005")
        order = orders.create_order({"tier": "standard", "speed": "standard", "handover": "counter", "date": TOMORROW,
                                     "garments": [{"fabric": "everyday", "jobs": [{"id": "trouser-hem"}],
                                                   "fit": {"method": "mark"}}],
                                     "customer": {"name": "Meera", "phone": "9000000005", "counter": "c-campus"}})
        self.assertIn(f"*{order['id']}* is confirmed", texts(c.new()))
        out = c.say("track")
        self.assertIn(order["id"], texts(out))
        out = c.say(order["id"].lower())
        self.assertIn("Order confirmed", texts(out))

    def test_duplicate_webhook_delivery_handled_once(self):
        c = Chat("919000000006")
        payload = whatsapp.sim_payload(c.wa, "A", {"type": "text", "text": {"body": "hi"}})
        whatsapp.process_webhook(payload, channel="sim")
        whatsapp.process_webhook(payload, channel="sim")
        self.assertEqual(len(c.new()), 1)


class LiveRulesTest(unittest.TestCase):
    """Live sending with the Graph API call replaced by a recorder."""

    def setUp(self):
        self.sent = []
        self._saved = (whatsapp.LIVE, whatsapp._graph, whatsapp.STATUS_TEMPLATE)
        whatsapp.LIVE = True
        whatsapp._graph = lambda method, url, payload=None, raw=False: self.sent.append(payload) or {}

    def tearDown(self):
        whatsapp.LIVE, whatsapp._graph, whatsapp.STATUS_TEMPLATE = self._saved

    def order_for(self, phone):
        return orders.create_order({"tier": "standard", "handover": "counter", "date": TOMORROW,
                                    "garments": [{"jobs": [{"id": "button"}]}],
                                    "customer": {"name": "Live", "phone": phone, "counter": "c-market"}})

    def test_inside_24h_window_sends_text(self):
        bot.handle_inbound("919000000011", "Live", {"kind": "text", "text": "hi"}, "whatsapp")
        self.sent.clear()
        o = self.order_for("9000000011")
        self.assertEqual(self.sent[0]["type"], "text")
        self.assertEqual(self.sent[0]["to"], "919000000011")
        orders.store.update(o["id"], orders.scan)
        self.assertIn("collected", self.sent[-1]["text"]["body"])

    def test_outside_window_uses_template_or_skips(self):
        whatsapp.STATUS_TEMPLATE = "order_status_update"
        o = self.order_for("9000000012")  # never messaged the bot
        self.assertEqual(self.sent[-1]["type"], "template")
        self.assertEqual([p["text"] for p in self.sent[-1]["template"]["components"][0]["parameters"]][0], o["id"])
        whatsapp.STATUS_TEMPLATE = ""
        before = len(self.sent)
        orders.store.update(o["id"], orders.scan)
        self.assertEqual(len(self.sent), before)

    def test_stale_session_is_outside_window(self):
        bot.handle_inbound("919000000013", "Live", {"kind": "text", "text": "hi"}, "whatsapp")
        bot.sessions.data["919000000013"]["last_inbound"] = (datetime.now() - timedelta(hours=25)).isoformat()
        whatsapp.STATUS_TEMPLATE = "order_status_update"
        self.sent.clear()
        self.order_for("9000000013")
        self.assertEqual(self.sent[-1]["type"], "template")


class WebhookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        whatsapp.VERIFY_TOKEN, whatsapp.APP_SECRET = "verify-me", "app-secret"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), whatsapp.WebhookHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/webhook"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        whatsapp.VERIFY_TOKEN = whatsapp.APP_SECRET = ""

    def status(self, req):
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, ""

    def test_verify_handshake(self):
        ok = self.status(f"{self.base}?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=123")
        self.assertEqual(ok, (200, "123"))
        self.assertEqual(self.status(f"{self.base}?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1")[0], 403)

    def test_signed_post_is_processed_and_unsigned_rejected(self):
        wa = "919000000021"
        bot.reset_session(wa)
        whatsapp.clear_outbox(wa)
        raw = json.dumps(whatsapp.sim_payload(wa, "Sig", {"type": "text", "text": {"body": "hi"}})).encode()
        bad = urllib.request.Request(self.base, data=raw, method="POST", headers={"X-Hub-Signature-256": "sha256=00"})
        self.assertEqual(self.status(bad)[0], 401)
        sig = "sha256=" + hmac.new(b"app-secret", raw, hashlib.sha256).hexdigest()
        good = urllib.request.Request(self.base, data=raw, method="POST", headers={"X-Hub-Signature-256": sig})
        self.assertEqual(self.status(good)[0], 200)
        for _ in range(50):  # replies are sent from a worker thread
            if whatsapp.outbox_since(wa):
                break
            time.sleep(0.05)
        self.assertEqual(bot.sessions.data[wa]["channel"], "whatsapp")
        self.assertEqual(len(whatsapp.outbox_since(wa)), 1)  # not LIVE here, so the reply lands in the outbox


if __name__ == "__main__":
    unittest.main()
