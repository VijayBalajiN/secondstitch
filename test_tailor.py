"""Tailor queue tests: what a tailor may see, marking a job finished, earnings, and rework.

Run:  python3 -m unittest test_tailor.py
"""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta

os.environ["SECONDSTITCH_DATA"] = tempfile.mkdtemp(prefix="ss-test-")
for key in ("WA_TOKEN", "WA_PHONE_NUMBER_ID", "WA_VERIFY_TOKEN", "WA_APP_SECRET", "WA_STATUS_TEMPLATE", "TELEGRAM_TOKEN"):
    os.environ[key] = ""

import orders  # noqa: E402
import server  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
BODY = {"tier": "standard", "speed": "standard", "handover": "pickup-4", "date": TOMORROW,
        "customer": {"name": "Asha Rao", "phone": "9876543210", "address": "12 MG Road, Bengaluru"},
        "garments": [{"fabric": "everyday", "jobs": [{"id": "button", "qty": 2}], "label": "Blue shirt", "note": "Keep the old buttons"}]}


class TailorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.OPS_PIN = "123456"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {},
                                     data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def order_with_tailor(self):
        oid = orders.create_order(BODY)["id"]
        orders.store.update(oid, orders.scan)  # collected
        orders.store.update(oid, orders.scan)  # with tailor
        return oid

    def test_job_is_in_the_queue_without_customer_details(self):
        oid = self.order_with_tailor()
        status, data = self.call("/api/ops/jobs")
        self.assertEqual(status, 200)
        job = next(j for j in data["jobs"] if j["id"] == oid)
        text = json.dumps(job)
        for secret in ("Asha", "9876543210", "MG Road", "customer", "address"):
            self.assertNotIn(secret, text)
        self.assertEqual(job["garments"][0]["jobs"][0]["qty"], 2)
        self.assertEqual(job["garments"][0]["note"], "Keep the old buttons")
        self.assertGreater(job["earns"], 0)

    def test_finish_then_earnings_move_to_waiting_for_qc(self):
        oid = self.order_with_tailor()
        before = self.call("/api/ops/jobs")[1]["earnings"]
        status, job = self.call(f"/api/ops/orders/{oid}/tailor-done", {})
        self.assertEqual(status, 200)
        self.assertTrue(job["finished_at"])
        self.assertNotIn("customer", job)
        after = self.call("/api/ops/jobs")[1]["earnings"]
        self.assertEqual(after["in_qc"] - before["in_qc"], job["earns"])
        self.assertEqual(before["to_do"] - after["to_do"], job["earns"])

    def test_cannot_finish_twice_or_before_it_arrives(self):
        oid = self.order_with_tailor()
        self.assertEqual(self.call(f"/api/ops/orders/{oid}/tailor-done", {})[0], 200)
        self.assertEqual(self.call(f"/api/ops/orders/{oid}/tailor-done", {})[0], 409)
        fresh = orders.create_order(BODY)["id"]
        self.assertEqual(self.call(f"/api/ops/orders/{fresh}/tailor-done", {})[0], 409)

    def test_failed_qc_sends_the_job_back_to_the_tailor(self):
        oid = self.order_with_tailor()
        self.call(f"/api/ops/orders/{oid}/tailor-done", {})
        self.call(f"/api/ops/orders/{oid}/qc-fail", {})
        job = next(j for j in self.call("/api/ops/jobs")[1]["jobs"] if j["id"] == oid)
        self.assertTrue(job["rework"])
        self.assertIsNone(job["finished_at"])

    def test_paid_once_quality_checked(self):
        oid = self.order_with_tailor()
        before = self.call("/api/ops/jobs")[1]["earnings"]["paid"]
        self.call(f"/api/ops/orders/{oid}/scan", {})  # quality checked
        after = self.call("/api/ops/jobs")[1]["earnings"]["paid"]
        self.assertGreater(after, before)

    def test_customers_never_see_the_tailor_fields(self):
        oid = self.order_with_tailor()
        self.call(f"/api/ops/orders/{oid}/tailor-done", {})
        status, view = self.call(f"/api/orders/{oid}")
        self.assertEqual(status, 200)
        self.assertNotIn("tailor_done_at", view)

    def test_queue_needs_the_pin_from_other_devices(self):
        status, _ = self.call("/api/ops/jobs", headers={"X-Forwarded-For": "1.2.3.4"})
        self.assertEqual(status, 401)
        status, _ = self.call("/api/ops/jobs", headers={"X-Forwarded-For": "1.2.3.4", "X-Ops-Pin": "123456"})
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
