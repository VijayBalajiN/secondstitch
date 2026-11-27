"""SecondStitch chat bot: the order conversation and the status message sent on every scan.

The bot is one more channel into the shared order system. It prices with pricing.quote and
places orders with orders.create_order, exactly like the website, so a chat order shows up
on the ops desk and the tracking page like any other.

The same conversation runs on WhatsApp (whatsapp.py, and the /bot simulator) and on Telegram
(telegram.py). Messages are built in WhatsApp's format; telegram.py converts them. A chat is keyed
by its WhatsApp number, or by "tg:<chat id>" for Telegram.
"""
import base64
import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

import orders
import pricing
import telegram
import whatsapp

SESSIONS_FILE = orders.DATA / "bot_sessions.json"
MEDIA_DIR = orders.DATA / "bot_media"
SERVICE_WINDOW = timedelta(hours=24)  # free-form replies are allowed for 24 h after the customer's last message
DATE_ROWS = 10

notify_inline = False  # tests set True to send status messages without a worker thread

# Row titles in WhatsApp lists are limited to 24 characters.
SHORT = {
    "button": "Button or hook", "open-seam": "Open seam repair", "darn": "Tear darn or patch",
    "elastic": "Elastic or drawstring", "lining": "Lining repair", "salwar-shorten": "Salwar/pyjama shorten",
    "trouser-hem": "Trouser/jeans hem", "kurta-hem": "Kurta/skirt/dress hem", "jeans-original-hem": "Jeans original hem",
    "sleeve-shorten": "Sleeve shorten", "sleeve-cuff": "Sleeve with cuff/lining", "blazer-sleeve": "Blazer sleeve shorten",
    "side-seams": "Side seams in/out 1 in", "waist": "Trouser waist in/out", "lehenga-waist": "Lehenga/skirt waist",
    "taper": "Taper trouser legs", "flare": "Flare reduction", "fly-zip": "Fly zip replace",
    "dress-zip": "Kurta/dress zip", "jacket-zip": "Jacket zip replace", "kurta-resize": "Kurta/top resize",
    "shoulder": "Shirt shoulder", "blouse": "Lined blouse alteration", "refit": "Complete refit", "new-pants": "New pants", "new-kurta": "New kurta or top",
    "saree-fall": "Saree fall and pico", "lace": "Lace or border attach", "extra-button": "Extra buttons",
}

CATEGORIES = [
    ("buttons", "Buttons and hooks", "Buttons, hooks, press-studs", ["button"]),
    ("repairs", "Repairs", "Seams, tears, elastic, lining", ["open-seam", "darn", "elastic", "lining"]),
    ("hems", "Hems and length", "Trousers, jeans, kurtas, salwars",
     ["trouser-hem", "jeans-original-hem", "kurta-hem", "salwar-shorten"]),
    ("sleeves", "Sleeves", "Plain, cuffed or blazer sleeves", ["sleeve-shorten", "sleeve-cuff", "blazer-sleeve"]),
    ("fit", "Take in or let out", "Side seams, waists, tapering, flare",
     ["side-seams", "waist", "lehenga-waist", "taper", "flare"]),
    ("zips", "Zips", "Fly, side or back, jacket zips", ["fly-zip", "dress-zip", "jacket-zip"]),
    ("resize", "Resize and refit", "Kurtas, blouses, shoulders, full refits", ["kurta-resize", "blouse", "shoulder", "refit"]),
    ("saree", "Saree and trims", "Fall and pico, lace or border", ["saree-fall", "lace"]),
    ("new", "New clothes", "Stitched to your measurements", ["new-pants", "new-kurta"]),
]
CATEGORY = {key: (title, ids) for key, title, _, ids in CATEGORIES}

RESET_WORDS = {"hi", "hello", "hey", "menu", "start", "start over", "restart", "namaste"}
CANCEL_WORDS = {"cancel", "stop", "quit"}
FIT_ROWS = [
    ("measurement", "Measurement in inches", "Type it next, e.g. shorten by 1.5 inches"),
    ("mark", "Pin or chalk mark", "Mark the garment before you hand it over"),
    ("reference", "Reference garment", "Send a well-fitting garment along"),
    ("none", "No fit mark", "Our free redo then covers stitching only"),
]
RATING_ROWS = [("5", "Excellent"), ("4", "Good"), ("3", "Okay"), ("2", "Poor"), ("1", "Very poor")]

lock = threading.RLock()
T, B, L = whatsapp.text, whatsapp.buttons, whatsapp.list_message


def rupees(n):
    return f"₹{n:,}"


def now():
    return datetime.now()


def local_phone(wa):
    return wa[2:] if len(wa) == 12 and wa.startswith("91") else wa


def wa_id(phone):
    return "91" + phone


def is_telegram(s):
    return s["wa"].startswith("tg:")


def customer_phone(s):
    """The chat's 10-digit mobile: the WhatsApp number itself, or the number a Telegram user shared."""
    return s.get("phone") if is_telegram(s) else local_phone(s["wa"])


def send(wa, msg, channel):
    if channel == "telegram":
        telegram.send(wa.removeprefix("tg:"), msg)
    else:
        whatsapp.send(wa, msg, channel)


# ---------- Sessions ----------

class Sessions:
    def __init__(self, path):
        self.path = path
        self.data = json.loads(path.read_text("utf-8")) if path.exists() else {}

    def get(self, wa):
        return self.data.setdefault(wa, {"wa": wa, "name": "", "channel": "sim", "step": "idle",
                                         "draft": None, "last_inbound": None, "rate_order": None})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path)


sessions = Sessions(SESSIONS_FILE)


def reset(s):
    for g in (s.get("draft") or {}).get("garments", []):
        _drop_photo(g)
    s.update(step="idle", draft=None, cat=None)


def reset_session(wa):
    with lock:
        s = sessions.data.pop(wa, None)
        if s:
            reset(s)
        sessions.save()


# ---------- Entry point ----------

def handle_inbound(wa, name, inp, channel):
    with lock:
        s = sessions.get(wa)
        s["channel"] = channel
        s["last_inbound"] = now().isoformat(timespec="seconds")
        if name:
            s["name"] = name
        try:
            replies = respond(s, inp)
        except Exception as e:
            print(f"[bot] error for {wa}: {e!r}")
            reset(s)
            replies = [T("Sorry, something went wrong on our side. Type *menu* to start again.")]
        sessions.save()
    for msg in replies:
        send(wa, msg, channel)


whatsapp.message_handler = telegram.message_handler = handle_inbound


def respond(s, inp):
    text = (inp.get("text") or "").strip() if inp["kind"] == "text" else ""
    low = text.lower()
    cid = inp.get("id", "") if inp["kind"] == "choice" else ""

    if low in RESET_WORDS or cid == "menu":
        reset(s)
        return [greeting(s)]
    if low in CANCEL_WORDS:
        reset(s)
        return [T("Okay, I've cleared that. Type *hi* whenever you want to start again.")]
    if s.get("rate_order") and s["step"] in ("idle", "track") and (cid.startswith("rate:") or low in {"1", "2", "3", "4", "5"}):
        return rate_order(s, int(cid[5:] if cid else low))
    step = STEPS.get(s["step"], STEPS["idle"])
    return step["handle"](s, inp, text, cid)


def nudge(s, msg="Please pick one of the options below."):
    return [T(msg)] + STEPS[s["step"]]["ask"](s)


def go(s, step):
    s["step"] = step
    return STEPS[step]["ask"](s)


# ---------- Idle, menu, prices, tracking ----------

def greeting(s):
    first = s["name"].split(" ")[0] if s.get("name") else ""
    return B(f"Hi{' ' + first if first else ''}! This is SecondStitch. Hems, zips, buttons, saree fall: "
             "tell me what needs doing and a tailor near you does it. You'll see the price before you order.",
             [("new", "New order"), ("track", "Track an order"), ("prices", "Prices")])


def handle_idle(s, inp, text, cid):
    low = text.lower()
    if cid == "new" or low in ("new", "order", "new order"):
        return start_order(s)
    if cid == "track" or low in ("track", "status"):
        return start_track(s)
    if cid == "prices" or low in ("prices", "price"):
        return prices()
    if orders.ID_RE.search(text.upper()):
        return lookup(s, text)
    return [greeting(s)]


def prices():
    p = pricing.SERVICE_BY_ID
    both = ["button", "trouser-hem", "kurta-hem", "side-seams", "saree-fall"]
    prem = ["fly-zip", "waist", "kurta-resize", "refit"]
    lines = ["*Popular prices* (Standard / Premium)"]
    lines += [f"• {SHORT[i]}: {rupees(p[i]['prices']['standard'])} / {rupees(p[i]['prices']['premium'])}" for i in both]
    lines += [f"• {SHORT[i]} (Premium): {rupees(p[i]['prices']['premium'])}" for i in prem]
    lines.append("\nSilk and delicate fabric cost 30% more, embellished 50% more. Minimum order ₹99. "
                 "Drop-off at a dry cleaner is free; home pickup is ₹99 or ₹149.")
    return [T("\n".join(lines)), B("Want to place an order?", [("new", "New order"), ("track", "Track an order")])]


def start_track(s):
    phone = customer_phone(s)
    mine = [o for o in orders.store.by_phone(phone) if o["status"] not in ("delivered", "cancelled")] if phone else []
    s["step"] = "track"
    if not mine:
        return [T("Type your order number. It looks like *SS-7K2QD* and is in your confirmation message.")]
    lines = ["*Your open orders*"] + [status_line(o) for o in mine[:5]]
    lines.append("\nType another order number to look it up, or *menu* to go back.")
    return [T("\n".join(lines))]


def handle_track(s, inp, text, cid):
    if orders.ID_RE.search(text.upper()):
        return lookup(s, text)
    if cid or text:
        reset(s)
        return respond(s, inp)
    return [T("Type an order number like *SS-7K2QD*, or *menu* to go back.")]


def lookup(s, text):
    oid = orders.ID_RE.search(text.upper()).group(0)
    order = orders.store.orders.get(oid)
    if not order:
        return [T(f"I couldn't find *{oid}*. Check the number in your confirmation message.")]
    steps = [f"{fmt_time(e['at'])} · {e['label']}" for e in order["events"]]
    return [T(f"{status_line(order)}\nBack {order['quote']['ready']}.\n\n" + "\n".join(steps))]


def status_line(o):
    return f"*{o['id']}*: {orders.STATUS_LABEL[o['status']]} (updated {fmt_time(o['events'][-1]['at'])})"


def fmt_time(iso):
    dt = datetime.fromisoformat(iso)
    return f"{dt.day} {dt:%b}, {int(dt.strftime('%I'))}:{dt:%M %p}"


# ---------- Building the order ----------

def new_garment():
    return {"fabric": None, "jobs": [], "fit": None, "photo": None, "photo_asked": False}


def start_order(s):
    s["draft"] = {"garments": [new_garment()], "tier": None, "speed": "standard", "handover": None,
                  "counter": None, "address": "", "date": None, "after": None}
    return go(s, "category")


def garment(s):
    return s["draft"]["garments"][-1]


def jobs_text(g):
    return "\n".join(f"• {SHORT[j['id']]}{' × ' + str(j['qty']) if j['qty'] > 1 else ''}" for j in g["jobs"])


def ask_category(s):
    n = len(s["draft"]["garments"])
    rows = [(f"cat:{k}", title, desc) for k, title, desc, _ in CATEGORIES]
    return [L(f"Garment {n}: what do you want fixed?", "Choose a category", [("Categories", rows)])]


def handle_category(s, inp, text, cid):
    key = cid[4:] if cid.startswith("cat:") else ""
    if key not in CATEGORY:
        return nudge(s)
    s["cat"] = key
    return go(s, "service")


def service_row(sid):
    svc = pricing.SERVICE_BY_ID[sid]
    pr = svc["prices"]
    desc = f"Premium only · {rupees(pr['premium'])}" if svc["premium_only"] else \
        f"{rupees(pr['standard'])} Standard · {rupees(pr['premium'])} Premium"
    return (f"svc:{sid}", SHORT[sid], desc)


def ask_service(s):
    title, ids = CATEGORY[s["cat"]]
    rows = [service_row(i) for i in ids] + [("back", "Other categories", "Go back to the list")]
    return [L(f"*{title}*: pick the fix. Prices are for everyday fabric in a normal week.", "Choose a fix",
              [(title, rows)])]


def handle_service(s, inp, text, cid):
    if cid == "back":
        return go(s, "category")
    sid = cid[4:] if cid.startswith("svc:") else ""
    if sid not in CATEGORY[s["cat"]][1]:
        return nudge(s)
    g = garment(s)
    if any(j["id"] == sid for j in g["jobs"]):
        return [T(f"{SHORT[sid]} is already on this garment.")] + after_job(s)
    if sid == "button":
        return go(s, "button_qty")
    g["jobs"].append({"id": sid, "qty": 1})
    return after_job(s)


def ask_button_qty(s):
    return [B("How many buttons or hooks? If it's more than 3, type the number.",
              [("bq:1", "1 button"), ("bq:2", "2 buttons"), ("bq:3", "3 buttons")])]


def handle_button_qty(s, inp, text, cid):
    raw = cid[3:] if cid.startswith("bq:") else text
    if not raw.isdigit() or not 1 <= int(raw) <= pricing.MAX_QTY + 1:
        return nudge(s, f"Please tap a button or type a number from 1 to {pricing.MAX_QTY + 1}.")
    n = int(raw)
    g = garment(s)
    g["jobs"].append({"id": "button", "qty": 1})
    if n > 1:
        g["jobs"].append({"id": "extra-button", "qty": n - 1})
    return after_job(s)


def after_job(s):
    return go(s, "fabric" if garment(s)["fabric"] is None else "next")


def ask_fabric(s):
    return [B("What's the fabric?\n"
              "• *Everyday*: cotton, denim, linen, polyester\n"
              "• *Silk / delicate*: silk, georgette, chiffon, satin, velvet (×1.3)\n"
              "• *Embellished*: embroidery, sequins or beadwork near the work area (×1.5, Premium only)",
              [("fab:everyday", "Everyday"), ("fab:delicate", "Silk / delicate"), ("fab:embellished", "Embellished")])]


def handle_fabric(s, inp, text, cid):
    fabric = cid[4:] if cid.startswith("fab:") else ""
    if fabric not in pricing.FABRICS:
        return nudge(s)
    garment(s)["fabric"] = fabric
    return go(s, "next")


def ask_next(s):
    n = len(s["draft"]["garments"])
    return [B(f"Garment {n} so far:\n{jobs_text(garment(s))}\n\nAnything else?",
              [("more", "Another fix"), ("garment", "Another garment"), ("done", "That's all")])]


def handle_next(s, inp, text, cid):
    if cid == "more":
        return go(s, "category")
    if cid in ("garment", "done"):
        s["draft"]["after"] = cid
        return finish_garment(s)
    return nudge(s)


def finish_garment(s):
    g = garment(s)
    needs_fit = any(pricing.SERVICE_BY_ID[j["id"]]["fit"] for j in g["jobs"])
    if needs_fit and g["fit"] is None:
        return go(s, "fit")
    if not g["photo_asked"]:
        return go(s, "photo")
    if s["draft"]["after"] == "garment" and len(s["draft"]["garments"]) < pricing.MAX_GARMENTS:
        s["draft"]["garments"].append(new_garment())
        return go(s, "category")
    if s["draft"]["after"] == "garment":
        return [T(f"That's the most garments for one order ({pricing.MAX_GARMENTS}).")] + go_tier(s)
    return go_tier(s)


def ask_fit(s):
    return [L("This fix depends on fit. Show the tailor the size you want:", "Choose one",
              [("Fit mark", [(f"fit:{k}", t, d) for k, t, d in FIT_ROWS])])]


def handle_fit(s, inp, text, cid):
    method = cid[4:] if cid.startswith("fit:") else ""
    if method not in pricing.FIT_METHODS:
        return nudge(s)
    garment(s)["fit"] = {"method": method, "value": ""}
    if method == "measurement":
        return go(s, "fit_value")
    return finish_garment(s)


def ask_fit_value(s):
    return [T("Type the measurement, for example: *Shorten by 1.5 inches*")]


def handle_fit_value(s, inp, text, cid):
    if not 1 <= len(text) <= 80:
        return nudge(s, "Please type the measurement in a few words.")
    garment(s)["fit"]["value"] = text
    return finish_garment(s)


def ask_photo(s):
    return [B("Send a photo of the garment with the spot marked, so the tailor finds it fast. Or skip it.",
              [("skip", "Skip photo")])]


def handle_photo(s, inp, text, cid):
    g = garment(s)
    if inp["kind"] == "image":
        g["photo_asked"] = True
        try:
            fetch = telegram.fetch_media if is_telegram(s) else whatsapp.fetch_media
            mime, data = fetch(inp["media_id"])
            ext = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp"}.get(mime.split(";")[0])
            if not ext or len(data) > orders.MAX_PHOTO:
                raise ValueError(f"unsupported photo ({mime}, {len(data)} bytes)")
            MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            path = MEDIA_DIR / f"{s['wa'].replace(':', '-')}-{len(s['draft']['garments'])}.{ext}"
            path.write_bytes(data)
            g["photo"] = str(path)
            first = [T("Got the photo.")]
        except (ValueError, RuntimeError, OSError, KeyError) as e:
            print(f"[bot] photo from {s['wa']} not saved: {e}")
            first = [T("I couldn't use that photo, so we'll carry on without it.")]
        return first + finish_garment(s)
    if cid == "skip":
        g["photo_asked"] = True
        return finish_garment(s)
    return nudge(s, "Send a photo, or tap *Skip photo*.")


def _drop_photo(g):
    if g.get("photo"):
        try:
            Path(g["photo"]).unlink(missing_ok=True)
        except OSError:
            pass


# ---------- Tier, speed, handover, date ----------

def request(s, **override):
    d = s["draft"]
    req = {"tier": d["tier"] or "standard", "speed": d["speed"], "handover": d["handover"] or "counter",
           "date": d["date"] or now().date().isoformat(),
           "garments": [{"fabric": g["fabric"], "jobs": g["jobs"]} for g in d["garments"]]}
    req.update(override)
    return req


def needs_premium(s):
    return any(pricing.SERVICE_BY_ID[j["id"]]["premium_only"] or pricing.FABRICS[g["fabric"]]["premium_only"]
               for g in s["draft"]["garments"] for j in g["jobs"])


def go_tier(s):
    if needs_premium(s):
        s["draft"]["tier"] = "premium"
        return [T("Part of this needs a master tailor, so your order is *Premium*.")] + go_speed(s)
    return go(s, "tier")


def ask_tier(s):
    def work(tier):
        q = pricing.quote(request(s, tier=tier, speed="standard", handover="counter"))
        return rupees(q["work"] + q["min_order_topup"]) if q["ok"] else "n/a"
    return [B("Pick a tailor:\n"
              "• *Standard*: a home tailor near you\n"
              "• *Premium*: a master tailor, with Express next day\n\n"
              "Prices shown are for the work only.",
              [("tier:standard", f"Standard · {work('standard')}"), ("tier:premium", f"Premium · {work('premium')}")])]


def handle_tier(s, inp, text, cid):
    tier = cid[5:] if cid.startswith("tier:") else ""
    if tier not in pricing.TIERS:
        return nudge(s)
    s["draft"]["tier"] = tier
    return go_speed(s)


def go_speed(s):
    if s["draft"]["tier"] == "premium":
        return go(s, "speed")
    s["draft"]["speed"] = "standard"
    return go(s, "handover")


def ask_speed(s):
    tomorrow = (now().date() + timedelta(days=1)).isoformat()
    q = pricing.quote(request(s, speed="express", handover="counter", date=tomorrow))
    extra = rupees(q["express"]) if q["ok"] else "40%"
    return [B("Pick a speed:\n• *2–3 days*: included\n• *Express*: hand over by 11 am, back by 3 pm next day",
              [("sp:standard", "2–3 days"), ("sp:express", f"Next day +{extra}")])]


def handle_speed(s, inp, text, cid):
    speed = cid[3:] if cid.startswith("sp:") else ""
    if speed not in ("standard", "express"):
        return nudge(s)
    s["draft"]["speed"] = speed
    return go(s, "handover")


def ask_handover(s):
    return [B("Drop off or pickup?\n"
              "• *Partner counter*: drop it at a dry cleaner, free\n"
              "• *Home pickup and return*: ₹99 within 4 km, ₹149 for 4–8 km (free on work of ₹1,200+)",
              [("ho:counter", "Partner counter"), ("ho:pickup-4", "Pickup within 4 km"), ("ho:pickup-8", "Pickup 4–8 km")])]


def handle_handover(s, inp, text, cid):
    ho = cid[3:] if cid.startswith("ho:") else ""
    if ho not in pricing.HANDOVER:
        return nudge(s)
    s["draft"]["handover"] = ho
    return go(s, "counter" if ho == "counter" else "address")


def ask_counter(s):
    rows = [(f"ct:{c['id']}", c["short"], c["name"]) for c in pricing.COUNTERS]
    return [L("Choose a counter.", "Choose a counter", [("Partner counters", rows)])]


def handle_counter(s, inp, text, cid):
    cid = cid[3:] if cid.startswith("ct:") else ""
    if cid not in {c["id"] for c in pricing.COUNTERS}:
        return nudge(s)
    s["draft"]["counter"] = cid
    return go(s, "date")


def ask_address(s):
    return [T("Type the pickup and return address: flat, building, street and a landmark.")]


def handle_address(s, inp, text, cid):
    if not 5 <= len(text) <= 300:
        return nudge(s, "Please type the full address (at least a few words).")
    s["draft"]["address"] = text
    return go(s, "date")


def date_options(s):
    today = now().date()
    days = pricing.calendar(today)
    if s["draft"]["speed"] == "express" and now().hour >= pricing.EXPRESS_CUTOFF_HOUR:
        days = days[1:]  # today's Express cut-off has passed
    return days[:DATE_ROWS]


def ask_date(s):
    today = now().date()
    rows = []
    for d in date_options(s):
        day = datetime.fromisoformat(d["date"]).date()
        label = day.strftime("%a %d %b")
        title = ("Today · " if day == today else "Tomorrow · " if day == today + timedelta(days=1) else "") + label
        desc = {"peak": f"{d['label']}: 20% more", "offpeak": "Off-peak: 10% less"}.get(d["kind"], "Normal price")
        rows.append((f"dt:{d['date']}", title, desc))
    body = ("Pick a day for the pickup. Pickups run in the afternoon." if s["draft"]["handover"] != "counter"
            else "Pick a day to drop it at the counter.")
    return [L(body, "Choose a day", [("Next 10 days", rows)])]


def handle_date(s, inp, text, cid):
    day = cid[3:] if cid.startswith("dt:") else ""
    if day not in {d["date"] for d in date_options(s)}:
        return nudge(s)
    s["draft"]["date"] = day
    return go(s, details_step(s))


def details_step(s):
    if is_telegram(s) and not s.get("phone"):
        return "phone"
    return "name" if not s.get("name") else "confirm"


def ask_phone(s):
    return [telegram.contact_request("Last thing: we need your mobile number for pickup and delivery updates. "
                                     "Tap *Share my phone number* below.", "📱 Share my phone number")]


def handle_phone(s, inp, text, cid):
    if inp["kind"] != "contact":
        return nudge(s, "Please use the *Share my phone number* button. Typed numbers can't be checked.")
    if not inp["own"]:
        return nudge(s, "That's someone else's contact. Please share your own number with the button below.")
    try:
        s["phone"] = orders.clean_phone(inp["phone"])
    except orders.ApiError:
        reset(s)
        return [dict(T("Sorry, SecondStitch needs an Indian mobile number (+91), and this Telegram account uses "
                       "another country's number. You can order on our website instead."), remove_keyboard=True)]
    return [dict(T("Thanks, got your number."), remove_keyboard=True)] + go(s, details_step(s))


def ask_name(s):
    return [T("Send your name for the order.")]


def handle_name(s, inp, text, cid):
    if not 1 <= len(text) <= 80:
        return nudge(s, "Please type your name.")
    s["name"] = text
    return go(s, "confirm")


# ---------- Confirm and place ----------

def summary_text(q):
    lines = ["*Your order*"]
    for g in q["garments"]:
        lines.append(f"\n_Garment {g['index']} · {g['fabric_label']}_")
        lines += [f"• {j['name']}{' × ' + str(j['qty']) if j['qty'] > 1 else ''}: {rupees(j['amount'])}" for j in g["jobs"]]
        if g["fabric_adjustment"]:
            lines.append(f"  {g['fabric_label']} fabric ×{g['fabric_factor']}: +{rupees(g['fabric_adjustment'])}")
    lines.append("")
    if q["season_adjustment"]:
        sign = "+" if q["season_adjustment"] > 0 else "−"
        lines.append(f"{q['season']['label']} ×{q['season']['factor']}: {sign}{rupees(abs(q['season_adjustment']))}")
    if q["min_order_topup"]:
        lines.append(f"Small-order top-up to ₹99: +{rupees(q['min_order_topup'])}")
    if q["express"]:
        lines.append(f"Express next day: +{rupees(q['express'])}")
    fee = "waived" if q["handover_waived"] else rupees(q["handover_charged"]) if q["handover_charged"] else "free"
    lines.append(f"{q['handover_label']}: {fee}")
    lines.append(f"\n*Total: {rupees(q['total'])}*")
    lines.append(f"{q['tier_label']}{' · Express' if q['speed'] == 'express' else ''} · back {q['ready']}")
    lines.append(f"{rupees(q['tailor_earns'])} of this goes to your tailor.")
    if q["season"]["kind"] == "peak" and q["season"]["next_normal_date"]:
        alt = datetime.fromisoformat(q["season"]["next_normal_date"]).strftime("%a %d %b")
        lines.append(f"\nTip: {alt} is a normal-price day. Type *start over* to pick it.")
    return "\n".join(lines)


def ask_confirm(s):
    q = pricing.quote(request(s))
    if not q["ok"]:
        return [T("This order can't be priced:\n" + "\n".join(f"• {e}" for e in q["errors"])),
                B("Let's start again.", [("restart", "Start over")])]
    return [T(summary_text(q)), B("Place this order? Your price is fixed once you confirm.",
                                  [("confirm", "Confirm order"), ("restart", "Start over")])]


def handle_confirm(s, inp, text, cid):
    if cid == "restart":
        reset(s)
        return start_order(s)
    if cid == "confirm":
        return place_order(s)
    return nudge(s)


def photo_data_url(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    mime = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[p.suffix[1:]]
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def place_order(s):
    d = s["draft"]
    body = {**request(s),
            "garments": [{"fabric": g["fabric"], "jobs": g["jobs"], "fit": g["fit"], "photo": photo_data_url(g["photo"])}
                         for g in d["garments"]],
            "customer": {"name": s["name"], "phone": customer_phone(s), "counter": d["counter"], "address": d["address"]}}
    try:
        order = orders.create_order(body, source="telegram" if is_telegram(s) else "whatsapp")
    except orders.ApiError as e:
        return [T("Sorry, I couldn't place that:\n" + "\n".join(f"• {x}" for x in e.errors)),
                B("Want to try again?", [("restart", "Start over")])]
    reset(s)
    q = order["quote"]
    return [T(f"Order *{order['id']}* is confirmed.\nTotal {rupees(q['total'])} · back {q['ready']}.\n"
              f"{where(order)}\n\nI'll message you at every step. Type *track* any time.")]


def where(order):
    q = order["quote"]
    day = datetime.fromisoformat(q["date"]).strftime("%a %d %b")
    if q["handover"] == "counter":
        return f"Drop it at {order['customer']['counter']} on {day}."
    return f"We'll collect it from your address on the afternoon of {day}."


# ---------- Ratings ----------

def ask_rating():
    return L("How did we do?", "Rate us",
             [("Rating", [(f"rate:{n}", f"{n} · {label}", "") for n, label in RATING_ROWS])])


def rate_order(s, stars):
    oid = s["rate_order"]
    s["rate_order"] = None
    s["step"] = "idle"
    try:
        orders.store.update(oid, lambda o: orders.rate(o, stars))
    except orders.ApiError as e:
        return [T(str(e))]
    return [T(f"Thank you! You gave *{oid}* {stars}/5. Not quite right? We'll redo it free within 7 days.")]


STEPS = {
    "idle": {"ask": lambda s: [greeting(s)], "handle": handle_idle},
    "track": {"ask": lambda s: [T("Type an order number like *SS-7K2QD*.")], "handle": handle_track},
    "category": {"ask": ask_category, "handle": handle_category},
    "service": {"ask": ask_service, "handle": handle_service},
    "button_qty": {"ask": ask_button_qty, "handle": handle_button_qty},
    "fabric": {"ask": ask_fabric, "handle": handle_fabric},
    "next": {"ask": ask_next, "handle": handle_next},
    "fit": {"ask": ask_fit, "handle": handle_fit},
    "fit_value": {"ask": ask_fit_value, "handle": handle_fit_value},
    "photo": {"ask": ask_photo, "handle": handle_photo},
    "tier": {"ask": ask_tier, "handle": handle_tier},
    "speed": {"ask": ask_speed, "handle": handle_speed},
    "handover": {"ask": ask_handover, "handle": handle_handover},
    "counter": {"ask": ask_counter, "handle": handle_counter},
    "address": {"ask": ask_address, "handle": handle_address},
    "date": {"ask": ask_date, "handle": handle_date},
    "phone": {"ask": ask_phone, "handle": handle_phone},
    "name": {"ask": ask_name, "handle": handle_name},
    "confirm": {"ask": ask_confirm, "handle": handle_confirm},
}


# ---------- Status messages on every scan ----------

def status_text(kind, order):
    oid = order["id"]
    if kind == "created":
        first = order["customer"]["name"].split(" ")[0]
        return (f"Hi {first}, your SecondStitch order *{oid}* is confirmed. Total {rupees(order['quote']['total'])}. "
                f"{where(order)} Reply *track* any time.")
    if kind == "rework":
        return (f"Quick update on *{oid}*: it didn't pass our check, so a master tailor will do a free redo. "
                "It will be one day later than planned. Sorry!")
    counter = order["customer"].get("counter")
    return {
        "collected": f"*{oid}*: garment collected and tagged.",
        "with_tailor": f"*{oid}*: your tailor is on it.",
        "qc_passed": f"*{oid}*: checked and ready.",
        "out_for_delivery": f"*{oid}*: on its way back to {counter}. Collect it there this evening." if counter
        else f"*{oid}*: out for delivery this afternoon.",
        "delivered": f"*{oid}*: delivered. Thank you for using SecondStitch!",
        "cancelled": f"*{oid}*: cancelled before pickup. No charge.",
    }[order["status"]]


def template_status(kind, order):
    if kind == "rework":
        return "Sent back for a free redo; one day later than planned"
    if kind == "created":
        return f"Order confirmed, total {rupees(order['quote']['total'])}"
    return orders.STATUS_LABEL[order["status"]]


def on_order_event(kind, order):
    if kind == "created" and order.get("source") in ("whatsapp", "telegram"):
        return  # the chat already confirmed it
    if notify_inline:
        notify(kind, order)
    else:
        threading.Thread(target=notify, args=(kind, order), daemon=True).start()


def chat_for(order):
    """The chat that gets this order's updates. Telegram orders go back to their Telegram chat. Other
    orders go to the WhatsApp number, unless only a Telegram chat has shared (and so proved) that number."""
    phone = order["customer"]["phone"]
    wa = wa_id(phone)
    if order.get("source") == "telegram" or wa not in sessions.data:
        tg = next((k for k, s in sessions.data.items() if k.startswith("tg:") and s.get("phone") == phone), None)
        if tg:
            return tg
    return wa


def notify(kind, order):
    delivered = kind == "status" and order["status"] == "delivered"
    with lock:
        wa = chat_for(order)
        s = sessions.data.get(wa)
        if s is None and (delivered or not whatsapp.LIVE):
            s = sessions.get(wa)
            s["channel"] = "whatsapp" if whatsapp.LIVE else "sim"
            s["name"] = order["customer"]["name"]
        channel = s["channel"] if s else "whatsapp"
        last = s.get("last_inbound") if s else None
        in_window = bool(last) and now() - datetime.fromisoformat(last) < SERVICE_WINDOW
        if delivered:
            s["rate_order"] = order["id"]
        sessions.save()

    msgs = [T(status_text(kind, order))] + ([ask_rating()] if delivered else [])
    if channel != "whatsapp" or not whatsapp.LIVE or in_window:
        for m in msgs:
            send(wa, m, channel)
    elif whatsapp.STATUS_TEMPLATE:
        whatsapp.send(wa, whatsapp.template(whatsapp.STATUS_TEMPLATE, whatsapp.TEMPLATE_LANG,
                                            [order["id"], template_status(kind, order)]), channel)
    else:
        print(f"[bot] {order['id']} update not sent to {wa}: outside the 24-hour window and no WA_STATUS_TEMPLATE set")


orders.listeners.append(on_order_event)
