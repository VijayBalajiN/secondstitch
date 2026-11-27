"""Checks the engine against the tables and worked examples in "SecondStitch — Services & Pricing".

Run:  python3 -m unittest test_pricing.py
"""
from datetime import datetime
import unittest

import pricing

NOW = datetime(2026, 10, 27, 9, 0)  # Tuesday morning
THURSDAY = "2026-10-29"             # normal week
WEDDING_SATURDAY = "2026-11-21"     # peak
MONDAY = "2026-11-16"               # off-peak

# Catalogue prices as printed in the Pricing doc: (Standard, Premium)
DOC_PRICES = {
    "button": (40, 70), "extra-button": (10, 20), "open-seam": (60, 100), "darn": (40, 70),
    "elastic": (100, 170), "salwar-shorten": (100, 170), "trouser-hem": (120, 210),
    "kurta-hem": (140, 240), "sleeve-shorten": (140, 240), "side-seams": (140, 240),
    "lace": (180, 310), "saree-fall": (200, 350),
    "jeans-original-hem": (None, 310), "fly-zip": (None, 310), "sleeve-cuff": (None, 350),
    "waist": (None, 350), "dress-zip": (None, 380), "blouse": (None, 380), "lehenga-waist": (None, 380),
    "taper": (None, 450), "kurta-resize": (None, 450), "shoulder": (None, 450), "lining": (None, 450),
    "jacket-zip": (None, 520), "flare": (None, 520), "blazer-sleeve": (None, 560), "refit": (None, 660),
}


def order(tier, garments, date=THURSDAY, speed="standard", handover="counter"):
    return pricing.quote({"tier": tier, "speed": speed, "handover": handover, "date": date,
                          "garments": garments}, now=NOW)


class CatalogueTest(unittest.TestCase):
    def test_27_services(self):
        self.assertEqual(len(pricing.SERVICES), 27)

    def test_prices_match_doc(self):
        for sid, (std, prem) in DOC_PRICES.items():
            prices = pricing.SERVICE_BY_ID[sid]["prices"]
            self.assertEqual((prices["standard"], prices["premium"]), (std, prem), sid)


class WorkedExamplesTest(unittest.TestCase):
    def test_silk_saree_fall(self):
        q = order("standard", [{"fabric": "delicate", "jobs": [{"id": "saree-fall"}]}])
        self.assertEqual((q["total"], q["tailor_earns"]), (260, 143))

    def test_jeans_peak_home_pickup(self):
        q = order("premium", [{"fabric": "everyday", "jobs": [{"id": "jeans-original-hem"}, {"id": "waist"}]}],
                  date=WEDDING_SATURDAY, handover="pickup-4")
        self.assertEqual((q["work"], q["total"], q["tailor_earns"]), (792, 891, 469))

    def test_silk_blouse_express(self):
        q = order("premium", [{"fabric": "delicate", "jobs": [{"id": "blouse"}]}], speed="express")
        self.assertEqual((q["express"], q["total"], q["tailor_earns"]), (198, 692, 391))

    def test_two_buttons_off_peak(self):
        q = order("standard", [{"fabric": "everyday", "jobs": [{"id": "button"}, {"id": "extra-button"}]}],
                  date=MONDAY)
        self.assertEqual((q["work"], q["min_order_topup"], q["total"], q["tailor_earns"]), (45, 54, 99, 28))


class RulesTest(unittest.TestCase):
    def test_premium_only_job_rejected_on_standard(self):
        self.assertFalse(order("standard", [{"jobs": [{"id": "fly-zip"}]}])["ok"])

    def test_embellished_needs_premium(self):
        self.assertFalse(order("standard", [{"fabric": "embellished", "jobs": [{"id": "button"}]}])["ok"])

    def test_express_needs_premium(self):
        self.assertFalse(order("standard", [{"jobs": [{"id": "trouser-hem"}]}], speed="express")["ok"])

    def test_express_cutoff(self):
        q = pricing.quote({"tier": "premium", "speed": "express", "handover": "counter", "date": "2026-10-27",
                           "garments": [{"jobs": [{"id": "fly-zip"}]}]}, now=datetime(2026, 10, 27, 11, 30))
        self.assertFalse(q["ok"])

    def test_express_minimum(self):
        q = order("premium", [{"jobs": [{"id": "button"}]}], speed="express")
        self.assertEqual(q["express"], 150)

    def test_pickup_waived_from_1200(self):
        q = order("premium", [{"jobs": [{"id": "refit"}, {"id": "blazer-sleeve"}]}], handover="pickup-8")
        self.assertEqual((q["work"], q["handover_charged"], q["handover_waived"]), (1220, 0, True))

    def test_extra_button_needs_first(self):
        self.assertFalse(order("standard", [{"jobs": [{"id": "extra-button"}]}])["ok"])

    def test_peak_suggests_next_normal_day(self):
        q = order("standard", [{"jobs": [{"id": "trouser-hem"}]}], date=WEDDING_SATURDAY)
        self.assertEqual(q["season"]["next_normal_date"], "2026-11-23")

    def test_date_outside_window(self):
        self.assertFalse(order("standard", [{"jobs": [{"id": "button"}]}], date="2027-01-30")["ok"])


if __name__ == "__main__":
    unittest.main()
