"""Language file tests: every key the pages use exists in English, Hindi and Tamil, placeholders match,
Hindi and Tamil are written in their own scripts, and the English texts agree with the server's names.

Run:  python3 -m unittest test_i18n.py
"""
import json
import re
import unittest
from pathlib import Path

import pricing

PUBLIC = Path(__file__).resolve().parent / "public"
LANG = {n: json.loads((PUBLIC / "lang" / f"{n}.json").read_text("utf-8")) for n in ("en", "hi", "ta")}
PLACEHOLDER = re.compile(r"\{(\w+)\}")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
TAMIL = re.compile(r"[஀-௿]")


def used_keys():
    keys = set()
    for page in PUBLIC.glob("*.html"):
        text = page.read_text("utf-8")
        keys.update(re.findall(r'data-i18n(?:-html)?="([\w.-]+)"', text))
        for attr in re.findall(r'data-i18n-attr="([^"]+)"', text):
            keys.update(pair.split(":")[1].strip() for pair in attr.split(";"))
    for script in PUBLIC.glob("*.js"):
        if script.name == "i18n.js":  # its comments show example calls
            continue
        text = script.read_text("utf-8")
        keys.update(re.findall(r'(?<![\w.])(?:t|tb|tOr)\(\s*"([\w.-]+)"\s*[,)]', text))
        for attr in re.findall(r'data-i18n-attr="([^"]+)"', text):
            keys.update(pair.split(":")[1].strip() for pair in attr.split(";"))
    return keys


def literal_keys():
    """Keys passed around as plain strings (layout.js links, garments.js labels)."""
    keys = set()
    for script in PUBLIC.glob("*.js"):
        keys.update(k for k in re.findall(r'"([\w.-]+)"', script.read_text("utf-8")) if k in LANG["en"])
    return keys


def family_keys():
    """Keys the scripts build at run time, such as "svc." + id."""
    keys = set()
    keys.update(f"svc.{s['id']}" for s in pricing.SERVICES)
    for k in pricing.FABRICS:
        keys.update((f"fabric.{k}", f"fabric.{k}.d"))
    keys.update(f"ho.q.{k}" for k in pricing.HANDOVER)
    keys.update(f"counter.{c['id']}" for c in pricing.COUNTERS)
    for k in pricing.FIT_METHODS:
        keys.update((f"fitl.{k}", f"fitm.{k}", f"fitm.{k}.p"))
    keys.update(f"board.{t}" for t in pricing.TIERS)
    for s in ("confirmed", "collected", "with_tailor", "qc_passed", "out_for_delivery", "delivered"):
        keys.update((f"st.{s}", f"st.{s}.d"))
    keys.add("st.cancelled")
    keys.update(f"step.{n}" for n in range(1, 5))
    keys.update(f"svc.cat.{g}" for g in ("hem", "zip", "button", "saree", "blouse", "kurta", "blazer", "fit", "mend", "lehenga", "elastic"))
    keys.update(f"tailors.t{n}.{f}" for n in range(1, 4) for f in ("name", "where", "years", "spec", "quote"))
    keys.update(("season.offpeak", "season.normal", "season.wedding"))
    keys.update(f"season.{name.split()[0].lower()}" for _, _, name in pricing.FESTIVAL_WEEKS)
    return keys


class LanguageFiles(unittest.TestCase):
    def test_same_keys_everywhere(self):
        en = set(LANG["en"])
        for name in ("hi", "ta"):
            self.assertEqual(en - set(LANG[name]), set(), f"missing from {name}.json")
            self.assertEqual(set(LANG[name]) - en, set(), f"extra in {name}.json")

    def test_every_key_in_use_exists(self):
        missing = (used_keys() | family_keys()) - set(LANG["en"])
        self.assertEqual(missing, set())

    def test_no_unused_keys(self):
        unused = set(LANG["en"]) - used_keys() - literal_keys() - family_keys()
        self.assertEqual(unused, set(), "remove keys no page uses")

    def test_placeholders_match(self):
        for key, text in LANG["en"].items():
            for name in ("hi", "ta"):
                self.assertEqual(sorted(PLACEHOLDER.findall(text)), sorted(PLACEHOLDER.findall(LANG[name][key])), (key, name))
                self.assertEqual(text.count("<"), LANG[name][key].count("<"), (key, name, "html tags differ"))

    def test_hindi_and_tamil_use_their_scripts(self):
        for key, text in LANG["hi"].items():
            self.assertTrue(DEVANAGARI.search(text), f"hi.{key} has no Devanagari: {text!r}")
        for key, text in LANG["ta"].items():
            self.assertTrue(TAMIL.search(text), f"ta.{key} has no Tamil: {text!r}")

    def test_english_matches_server_names(self):
        en = LANG["en"]
        for s in pricing.SERVICES:
            self.assertEqual(en[f"svc.{s['id']}"], s["name"])
        for c in pricing.COUNTERS:
            self.assertEqual(en[f"counter.{c['id']}"], c["name"])
        for k, h in pricing.HANDOVER.items():
            self.assertEqual(en[f"ho.q.{k}"], h["label"])
        for k, f in pricing.FABRICS.items():
            self.assertEqual(en[f"fabric.{k}"], f["label"])
            self.assertEqual(en[f"fabric.{k}.d"], f["detail"])
        for d in pricing.calendar(__import__("datetime").date(2026, 11, 23)):
            if d["label"].startswith("Off-peak"):
                self.assertEqual(en["season.offpeak"], d["label"])
            elif d["label"] == "Normal week":
                self.assertEqual(en["season.normal"], d["label"])
            elif d["label"].startswith("Wedding"):
                self.assertEqual(en["season.wedding"], d["label"])

    def test_hindi_subtitles_exist_for_headings(self):
        """Headings marked data-bi need a Hindi text, or the "hien" mode would show nothing under them."""
        for page in PUBLIC.glob("*.html"):
            for key in re.findall(r'data-i18n="([\w.-]+)"[^>]*\bdata-bi\b', page.read_text("utf-8")):
                self.assertIn(key, LANG["hi"], f"{page.name}: {key}")


if __name__ == "__main__":
    unittest.main()
