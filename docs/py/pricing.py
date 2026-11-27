"""SecondStitch pricing engine.

Follows "SecondStitch — Services & Pricing" (Oct 2026):

    Job price   = Setup + rate_min x work minutes          (rounded to the nearest Rs 10)
    Order total = max(sum(job price x garment factor x season factor), Rs 99)
                  + express add-on + handover fee

All money is in whole rupees. Factors are kept as Fractions so 380 x 1.3 is exactly 494.
"""
from datetime import date, datetime, timedelta
from fractions import Fraction
import math

MIN_ORDER = 99
EXPRESS_RATE = Fraction(40, 100)
EXPRESS_MIN = 150
EXPRESS_CUTOFF_HOUR = 11
PICKUP_WAIVER = 1200
BOOKING_WINDOW_DAYS = 30
MAX_QTY = 20
MAX_GARMENTS = 8

TAILOR_SHARE = Fraction(55, 100)
TAILOR_PEAK_SHARE = Fraction(80, 100)
TAILOR_EXPRESS_SHARE = Fraction(60, 100)

TIERS = {
    "standard": {"label": "Standard", "who": "Home tailor", "setup": 20, "per_min": 4},
    "premium": {"label": "Premium", "who": "Master tailor", "setup": 30, "per_min": 7},
}

# id, name, work minutes, premium only, fit job (needs a measurement, mark or reference)
_CATALOGUE = [
    ("button", "Button, hook or press-stud (first one)", 5, False, False),
    ("extra-button", "Each extra button or hook on the same garment", 3, False, False),
    ("open-seam", "Open seam repair, up to 10 cm", 10, False, False),
    ("darn", "Small tear darn or patch, up to 5 cm", 5, False, False),
    ("elastic", "Elastic or drawstring replace", 20, False, False),
    ("salwar-shorten", "Salwar, pyjama or palazzo length shorten", 20, False, True),
    ("trouser-hem", "Trouser or jeans hem, plain fold", 25, False, True),
    ("kurta-hem", "Kurta, skirt or dress hem, straight", 30, False, True),
    ("sleeve-shorten", "Sleeve shorten, unlined, no cuff", 30, False, True),
    ("side-seams", "Take in or let out side seams, up to 1 inch, unlined", 30, False, True),
    ("lace", "Lace or border attach, up to 2 m", 40, False, False),
    ("saree-fall", "Saree fall and pico", 45, False, False),
    ("jeans-original-hem", "Jeans original hem (keeps factory stitch)", 40, True, True),
    ("fly-zip", "Trouser or jeans fly zip replace", 40, True, False),
    ("sleeve-cuff", "Sleeve shorten with cuff or lining", 45, True, True),
    ("waist", "Trouser or jeans waist take in or let out", 45, True, True),
    ("dress-zip", "Kurta, dress or skirt zip replace (side or back)", 50, True, False),
    ("blouse", "Blouse alteration, body, lined", 50, True, True),
    ("lehenga-waist", "Lehenga or skirt waist adjust", 50, True, True),
    ("taper", "Taper trouser or jeans legs", 60, True, True),
    ("kurta-resize", "Kurta, kameez or top resize (sides and sleeves, up to 2 inches)", 60, True, True),
    ("shoulder", "Shirt shoulder alteration", 60, True, True),
    ("lining", "Lining repair, partial", 60, True, False),
    ("jacket-zip", "Jacket open-end zip replace", 70, True, False),
    ("flare", "Flare reduction (palazzo, lehenga, skirt)", 70, True, True),
    ("blazer-sleeve", "Blazer sleeve shorten", 75, True, True),
    ("refit", "Open and re-stitch, complete refit", 90, True, True),
    ("new-stitch", "Stitch a new garment to your measurements", 140, True, True),
]

FABRICS = {
    "everyday": {"label": "Everyday", "detail": "Cotton, denim, linen, polyester",
                 "factor": Fraction(1), "premium_only": False},
    "delicate": {"label": "Delicate", "detail": "Silk, georgette, chiffon, satin, velvet",
                 "factor": Fraction(13, 10), "premium_only": False},
    "embellished": {"label": "Embellished", "detail": "Embroidery, sequins or beadwork near the work area",
                    "factor": Fraction(3, 2), "premium_only": True},
}

HANDOVER = {
    "counter": {"label": "Partner dry cleaner counter", "fee": 0},
    "pickup-4": {"label": "Home pickup and return, within 4 km", "fee": 99},
    "pickup-8": {"label": "Home pickup and return, 4–8 km", "fee": 149},
}

# Placeholder counters for the demo; real partners are signed during launch step 2.
COUNTERS = [
    {"id": "c-market", "name": "Partner counter · Market Road", "short": "Market Road"},
    {"id": "c-station", "name": "Partner counter · Station Road", "short": "Station Road"},
    {"id": "c-campus", "name": "Campus laundry counter", "short": "Campus laundry"},
]

FIT_METHODS = {
    "measurement": "Measurement in inches",
    "mark": "Pin or chalk mark on the garment",
    "reference": "Well-fitting reference garment sent along",
    "none": "No fit mark (redo covers workmanship only)",
}

# Illustrative season calendar, published a month ahead. Edit before launch.
FESTIVAL_WEEKS = [
    (date(2026, 11, 2), date(2026, 11, 10), "Diwali week"),
    (date(2027, 2, 26), date(2027, 3, 4), "Holi week"),
]
WEDDING_SEASON = [(date(2026, 11, 15), date(2027, 2, 28))]

PEAK = Fraction(12, 10)
OFF_PEAK = Fraction(9, 10)


def round_half_up(x):
    return math.floor(Fraction(x) + Fraction(1, 2))


def round10(x):
    return 10 * round_half_up(Fraction(x) / 10)


def job_price(service, tier):
    """Rate-card price of one job, or None when the tier cannot take it."""
    if service["premium_only"] and tier != "premium":
        return None
    t = TIERS[tier]
    if service["addon"]:
        return round10(t["per_min"] * service["minutes"])
    return round10(t["setup"] + t["per_min"] * service["minutes"])


SERVICES = []
for _id, _name, _minutes, _premium_only, _fit in _CATALOGUE:
    _svc = {"id": _id, "name": _name, "minutes": _minutes, "premium_only": _premium_only,
            "fit": _fit, "addon": _id == "extra-button"}
    _svc["prices"] = {tier: job_price(_svc, tier) for tier in TIERS}
    SERVICES.append(_svc)
SERVICE_BY_ID = {s["id"]: s for s in SERVICES}


def season(d):
    for start, end, name in FESTIVAL_WEEKS:
        if start <= d <= end:
            return {"kind": "peak", "factor": PEAK, "label": name}
    for start, end in WEDDING_SEASON:
        if start <= d <= end and d.weekday() >= 5:
            return {"kind": "peak", "factor": PEAK, "label": "Wedding-season weekend"}
    if d.weekday() <= 2:
        return {"kind": "offpeak", "factor": OFF_PEAK, "label": "Off-peak (Mon–Wed)"}
    return {"kind": "normal", "factor": Fraction(1), "label": "Normal week"}


def calendar(today, days=BOOKING_WINDOW_DAYS):
    out = []
    for i in range(days + 1):
        d = today + timedelta(days=i)
        s = season(d)
        out.append({"date": d.isoformat(), "kind": s["kind"], "factor": float(s["factor"]), "label": s["label"]})
    return out


def next_non_peak(d, today):
    last = today + timedelta(days=BOOKING_WINDOW_DAYS)
    d = d + timedelta(days=1)
    while d <= last:
        if season(d)["kind"] != "peak":
            return d
        d += timedelta(days=1)
    return None


def catalogue():
    """Everything the website needs to draw menus and price tables."""
    return {
        "tiers": TIERS,
        "services": SERVICES,
        "fabrics": {k: {**v, "factor": float(v["factor"])} for k, v in FABRICS.items()},
        "handover": HANDOVER,
        "counters": COUNTERS,
        "fit_methods": FIT_METHODS,
        "rules": {"min_order": MIN_ORDER, "express_rate": float(EXPRESS_RATE), "express_min": EXPRESS_MIN,
                  "express_cutoff_hour": EXPRESS_CUTOFF_HOUR, "pickup_waiver": PICKUP_WAIVER},
    }


def _parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def quote(req, now=None):
    """Price an order request. Returns {"ok": False, "errors": [...]} or the full breakdown."""
    now = now or datetime.now()
    today = now.date()
    errors = []

    tier = req.get("tier")
    speed = req.get("speed") or "standard"
    handover = req.get("handover")
    d = _parse_date(req.get("date"))
    garments = req.get("garments") or []

    if tier not in TIERS:
        errors.append("Choose Standard or Premium.")
    if speed not in ("standard", "express"):
        errors.append("Choose a speed.")
    if handover not in HANDOVER:
        errors.append("Choose how you will hand the garment over.")
    if d is None or not today <= d <= today + timedelta(days=BOOKING_WINDOW_DAYS):
        errors.append(f"Pick a day within the next {BOOKING_WINDOW_DAYS} days.")
    if not isinstance(garments, list) or not garments:
        errors.append("Add at least one garment.")
        garments = []
    if len(garments) > MAX_GARMENTS:
        errors.append(f"Up to {MAX_GARMENTS} garments per order.")
    if errors:
        return {"ok": False, "errors": errors}

    if speed == "express":
        if tier != "premium":
            errors.append("Express is Premium only.")
        if d == today and now.hour >= EXPRESS_CUTOFF_HOUR:
            errors.append("Today's Express cut-off (11 am) has passed. Pick tomorrow or later.")

    garments_out = []
    base_work = Fraction(0)
    for gi, g in enumerate(garments, start=1):
        g = g if isinstance(g, dict) else {}
        fabric_key = g.get("fabric") or "everyday"
        fabric = FABRICS.get(fabric_key)
        if fabric is None:
            errors.append(f"Garment {gi}: unknown fabric.")
            continue
        if fabric["premium_only"] and tier != "premium":
            errors.append(f"Garment {gi}: embellished pieces are Premium only.")
        jobs = g.get("jobs") or []
        if not jobs:
            errors.append(f"Garment {gi}: add at least one fix.")
            continue

        ids = set()
        jobs_out = []
        jobs_total = 0
        for j in jobs:
            j = j if isinstance(j, dict) else {}
            svc = SERVICE_BY_ID.get(j.get("id"))
            if svc is None:
                errors.append(f"Garment {gi}: unknown service.")
                continue
            try:
                qty = int(j.get("qty", 1))
            except (TypeError, ValueError):
                qty = 0
            if not 1 <= qty <= MAX_QTY:
                errors.append(f"Garment {gi}: quantity must be 1–{MAX_QTY}.")
                continue
            unit = job_price(svc, tier)
            if unit is None:
                errors.append(f"Garment {gi}: “{svc['name']}” is Premium only.")
                continue
            ids.add(svc["id"])
            jobs_out.append({"id": svc["id"], "name": svc["name"], "qty": qty, "unit": unit,
                             "amount": unit * qty, "fit": svc["fit"]})
            jobs_total += unit * qty
        if "extra-button" in ids and "button" not in ids:
            errors.append(f"Garment {gi}: add the first button before extra ones.")

        g_work = jobs_total * fabric["factor"]
        base_work += g_work
        garments_out.append({
            "index": gi, "fabric": fabric_key, "fabric_label": fabric["label"],
            "fabric_factor": float(fabric["factor"]), "jobs": jobs_out, "jobs_total": jobs_total,
            "fabric_adjustment": round_half_up(g_work) - jobs_total, "subtotal": round_half_up(g_work),
            "has_fit_job": any(j["fit"] for j in jobs_out),
        })

    if errors:
        return {"ok": False, "errors": errors}

    s = season(d)
    work = base_work * s["factor"]
    work_r = round_half_up(work)
    season_adjustment = work_r - round_half_up(base_work)
    topup = max(0, MIN_ORDER - work_r)
    express = max(EXPRESS_MIN, round_half_up(work * EXPRESS_RATE)) if speed == "express" else 0
    fee = HANDOVER[handover]["fee"]
    waived = fee > 0 and work_r + topup >= PICKUP_WAIVER
    handover_charged = 0 if waived else fee
    total = work_r + topup + express + handover_charged

    uplift = work - base_work if s["kind"] == "peak" else 0
    tailor = round_half_up(base_work * TAILOR_SHARE + uplift * TAILOR_PEAK_SHARE + express * TAILOR_EXPRESS_SHARE)

    if speed == "express":
        ready_by, ready_usual = d + timedelta(days=1), None
        ready = f"by 3 pm, {ready_by.strftime('%a %d %b')}"
    else:
        ready_by, ready_usual = d + timedelta(days=3), d + timedelta(days=2)
        ready = f"by {ready_by.strftime('%a %d %b')} (usually {ready_usual.strftime('%a %d %b')})"

    alt = next_non_peak(d, today) if s["kind"] == "peak" else None
    return {
        "ok": True,
        "tier": tier, "tier_label": TIERS[tier]["label"], "speed": speed,
        "handover": handover, "handover_label": HANDOVER[handover]["label"],
        "date": d.isoformat(),
        "season": {"kind": s["kind"], "factor": float(s["factor"]), "label": s["label"],
                   "next_normal_date": alt.isoformat() if alt else None},
        "garments": garments_out,
        "jobs_total": sum(g["jobs_total"] for g in garments_out),
        "season_adjustment": season_adjustment,
        "work": work_r,
        "min_order_topup": topup,
        "express": express,
        "handover_fee": fee,
        "handover_waived": waived,
        "handover_charged": handover_charged,
        "total": total,
        "tailor_earns": tailor,
        "ready": ready,
        "ready_by": ready_by.isoformat(),
        "ready_usual": ready_usual.isoformat() if ready_usual else None,
    }
