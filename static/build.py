#!/usr/bin/env python3
"""Build the GitHub Pages copy of the site: python3 static/build.py [output folder] [/base-path]

The pages are the same files as public/. Three things differ: every root path ("/styles.css", "/order",
"/api/...") gets the base path in front (project sites live under /secondstitch), static-api.js is loaded
first so that /api/ calls are answered by the Python files running in the browser, and the footer says
that orders stay in this browser. Defaults: docs/ (GitHub Pages serves it) and /secondstitch.
"""
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE.parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else WEB / "docs"
BASE = (sys.argv[2] if len(sys.argv) > 2 else "/secondstitch").rstrip("/")
PY_MODULES = ["pricing", "orders", "whatsapp", "telegram", "bot", "api", "static_api"]

# Root paths inside quotes: "/", "/#how", "/track?id=", "/styles.css", "/api/quote", "/lang/..." and so on.
ROOT_PATH = re.compile(
    r"""(["'`])/(?=(?:api/|lang/|uploads/|styles\.css|favicon\.svg|(?:layout|i18n|common|home|order|track|ops|bot|garments)\.js"""
    r"""|(?:bot|track|order|ops|help)(?=["'`?#])|[#?]|["'`]))"""
)
NOTE = {
    "en": " Orders you place are saved in this browser only.",
    "hi": " आपके ऑर्डर सिर्फ़ इसी ब्राउज़र में सेव होते हैं।",
    "ta": " நீங்கள் இடும் ஆர்டர்கள் இந்த உலாவியில் மட்டுமே சேமிக்கப்படும்.",
}

if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(WEB / "public", OUT)
shutil.copytree(HERE / "pyodide", OUT / "pyodide", ignore=shutil.ignore_patterns("PACKAGE-*"))
(OUT / "py").mkdir()
for m in PY_MODULES:
    shutil.copy(WEB / f"{m}.py", OUT / "py" / f"{m}.py")
shutil.copy(HERE / "static-api.js", OUT / "static-api.js")

for f in list(OUT.glob("*.html")) + list(OUT.glob("*.js")) + list(OUT.glob("*.css")):
    if f.name == "static-api.js":
        continue
    text = ROOT_PATH.sub(lambda m: f"{m.group(1)}{BASE}/", f.read_text("utf-8"))
    if f.suffix == ".html":
        text = text.replace("<head>", f'<head>\n  <script src="{BASE}/static-api.js"></script>', 1)
    f.write_text(text, "utf-8")

for name, extra in NOTE.items():
    f = OUT / "lang" / f"{name}.json"
    data = json.loads(f.read_text("utf-8"))
    data["footer.note"] += extra
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")

(OUT / ".nojekyll").write_text("")
(OUT / "404.html").write_text(
    f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    f'<title>Not found — SecondStitch</title><body style="font:1.1rem system-ui;max-width:32rem;margin:15vh auto;padding:0 20px">'
    f'<h1>That page is not here</h1><p><a href="{BASE}/">Back to SecondStitch</a></p></body>', "utf-8")
size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
print(f"Built {OUT} (base {BASE}/, {size:.1f} MB)")
