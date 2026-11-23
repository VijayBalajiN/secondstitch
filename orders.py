"""SecondStitch order system, shared by every channel (website, WhatsApp bot, ops desk).

Orders are kept in data/orders.json and photos in data/uploads/. Every status change is one
QR scan; listeners registered in `listeners` hear about it (the WhatsApp notifier is one).
"""
import base64
import copy
import json
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

import pricing

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("SECONDSTITCH_DATA") or ROOT / "data")
UPLOADS = DATA / "uploads"
ORDERS_FILE = DATA / "orders.json"
MAX_PHOTO = 3 * 1024 * 1024

STATUSES = [
    ("confirmed", "Order confirmed"),
    ("collected", "Garment collected"),
    ("with_tailor", "With tailor"),
    ("qc_passed", "Quality checked"),
    ("out_for_delivery", "Out for delivery"),
    ("delivered", "Delivered"),
]
STATUS_LABEL = dict(STATUSES) | {"cancelled": "Cancelled"}
NEXT_STATUS = {a[0]: b[0] for a, b in zip(STATUSES, STATUSES[1:])}

ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
ID_RE = re.compile(r"SS-[2-9A-HJ-NP-Z]{5}")
PHOTO_RE = re.compile(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$")

# Callables taking (kind, order); kind is "created", "status" or "rework". They get a copy.
listeners = []


class ApiError(Exception):
    def __init__(self, message, status=400, errors=None):
        super().__init__(message)
        self.status = status
        self.errors = errors or [message]


class OrderStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        UPLOADS.mkdir(parents=True, exist_ok=True)
        self.orders = json.loads(path.read_text("utf-8")) if path.exists() else {}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.orders, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path)

    def new_id(self):
        while True:
            oid = "SS-" + "".join(secrets.choice(ID_ALPHABET) for _ in range(5))
            if oid not in self.orders:
                return oid

    def add(self, order):
        with self.lock:
            self.orders[order["id"]] = order
            self._save()

    def get(self, oid):
        order = self.orders.get(oid)
        if order is None:
            raise ApiError("No order with that ID.", 404)
        return order

    def update(self, oid, change):
        with self.lock:
            order = self.get(oid)
            change(order)
            self._save()
            return order

    def all(self):
        return sorted(self.orders.values(), key=lambda o: o["created_at"], reverse=True)

    def by_phone(self, phone):
        return [o for o in self.all() if o["customer"]["phone"] == phone]


store = OrderStore(ORDERS_FILE)


def emit(kind, order):
    for fn in listeners:
        fn(kind, copy.deepcopy(order))


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value, field, max_len, required=False):
    text = " ".join(str(value or "").split()) if field != "note" else str(value or "").strip()
    if required and not text:
        raise ApiError(f"Please enter your {field}.")
    if len(text) > max_len:
        raise ApiError(f"{field.capitalize()} is too long (max {max_len} characters).")
    return text


def clean_phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ApiError("Enter a 10-digit Indian mobile number.")
    return digits


def save_photo(data_url, oid, index):
    m = PHOTO_RE.match(data_url or "")
    if not m:
        raise ApiError(f"Garment {index}: photo must be a JPEG, PNG or WebP image.")
    raw = base64.b64decode(m.group(2), validate=True)
    if len(raw) > MAX_PHOTO:
        raise ApiError(f"Garment {index}: photo is larger than 3 MB.")
    name = f"{oid}-{index}.{m.group(1)}"
    (UPLOADS / name).write_bytes(raw)
    return f"/uploads/{name}"


def event(status, note=""):
    return {"status": status, "label": STATUS_LABEL[status], "at": now_iso(), "note": note}


def create_order(body, source="web"):
    """Validate, price and save an order. `body` is the same JSON the website posts."""
    request = {k: body.get(k) for k in ("tier", "speed", "handover", "date")}
    garments_in = body.get("garments") if isinstance(body.get("garments"), list) else []
    request["garments"] = [{"fabric": g.get("fabric"), "jobs": g.get("jobs")} for g in garments_in
                           if isinstance(g, dict)]
    q = pricing.quote(request)
    if not q["ok"]:
        raise ApiError("Please fix the order.", errors=q["errors"])

    customer_in = body.get("customer") if isinstance(body.get("customer"), dict) else {}
    customer = {"name": clean_text(customer_in.get("name"), "name", 80, required=True),
                "phone": clean_phone(customer_in.get("phone"))}
    if request["handover"] == "counter":
        counter = next((c for c in pricing.COUNTERS if c["id"] == customer_in.get("counter")), None)
        if counter is None:
            raise ApiError("Choose a partner counter.")
        customer["counter"] = counter["name"]
    else:
        customer["address"] = clean_text(customer_in.get("address"), "address", 300, required=True)

    oid = store.new_id()
    details = []
    for qg, g in zip(q["garments"], garments_in):
        i = qg["index"]
        fit = None
        if qg["has_fit_job"]:
            method = (g.get("fit") or {}).get("method")
            if method not in pricing.FIT_METHODS:
                raise ApiError(f"Garment {i}: tell us how you will mark the fit.")
            fit = {"method": method, "label": pricing.FIT_METHODS[method],
                   "value": clean_text((g.get("fit") or {}).get("value"), "fit detail", 80)}
            if method == "measurement" and not fit["value"]:
                raise ApiError(f"Garment {i}: enter the measurement.")
        details.append({
            "label": clean_text(g.get("label"), "garment name", 60) or f"Garment {i}",
            "note": clean_text(g.get("note"), "note", 500),
            "fit": fit,
        })
    # Photos are written last so a rejected order leaves no files behind.
    for d, g, qg in zip(details, garments_in, q["garments"]):
        d["photo"] = save_photo(g["photo"], oid, qg["index"]) if g.get("photo") else None

    order = {"id": oid, "created_at": now_iso(), "source": source, "customer": customer, "quote": q,
             "garments": details, "status": "confirmed", "events": [event("confirmed")],
             "rating": None, "qc_failures": 0}
    store.add(order)
    emit("created", order)
    return order


def public_view(order):
    """What the tracking page may show: the phone number is masked."""
    view = copy.deepcopy(order)
    phone = view["customer"]["phone"]
    view["customer"]["phone"] = phone[:2] + "•" * 5 + phone[-3:]
    view["customer"]["name"] = view["customer"]["name"].split(" ")[0]
    view.pop("qc_failures", None)
    view.pop("tailor_done_at", None)
    return view


def tailor_view(order):
    """What a tailor sees: the work to do and what it pays. No phone number, name or address."""
    q = order["quote"]
    return {
        "id": order["id"], "status": order["status"], "created_at": order["created_at"],
        "tier": q["tier"], "speed": q["speed"], "ready": q["ready"], "ready_by": q.get("ready_by"),
        "earns": q["tailor_earns"], "rework": order.get("qc_failures", 0) > 0,
        "finished_at": order.get("tailor_done_at"),
        "garments": [{"label": d["label"], "fabric": g["fabric"], "fabric_label": g["fabric_label"],
                      "jobs": [{"id": j["id"], "name": j["name"], "qty": j["qty"]} for j in g["jobs"]],
                      "fit": d["fit"], "note": d["note"], "photo": d["photo"]}
                     for g, d in zip(q["garments"], order["garments"])],
    }


def tailor_jobs(all_orders):
    """The cluster's queue for the tailor app, plus what has been earned. Orders are not assigned to
    individual tailors yet, so this is one shared queue."""
    incoming = [o for o in all_orders if o["status"] == "collected"]
    working = [o for o in all_orders if o["status"] == "with_tailor"]
    paid = [o for o in all_orders if o["status"] in ("qc_passed", "out_for_delivery", "delivered")]
    sums = lambda xs: sum(o["quote"]["tailor_earns"] for o in xs)
    in_qc = [o for o in working if o.get("tailor_done_at")]
    to_do = [o for o in working if not o.get("tailor_done_at")]
    return {
        "jobs": [tailor_view(o) for o in working + incoming],
        "earnings": {"paid": sums(paid), "paid_jobs": len(paid), "in_qc": sums(in_qc), "in_qc_jobs": len(in_qc),
                     "to_do": sums(to_do), "to_do_jobs": len(to_do)},
    }


def tailor_done(order):
    if order["status"] != "with_tailor":
        raise ApiError("Only a job that is with a tailor can be marked finished.", 409)
    if order.get("tailor_done_at"):
        raise ApiError("This job is already marked finished.", 409)
    order["tailor_done_at"] = now_iso()


def cancel(order):
    if order["status"] != "confirmed":
        raise ApiError("Orders can be cancelled free only before pickup. Call us for anything later.", 409)
    order["status"] = "cancelled"
    order["events"].append(event("cancelled", "Cancelled before pickup, no charge"))
    emit("status", order)


def rate(order, stars):
    if order["status"] != "delivered":
        raise ApiError("You can rate the work once it is delivered.", 409)
    if order["rating"] is not None:
        raise ApiError("This order is already rated.", 409)
    if stars not in (1, 2, 3, 4, 5):
        raise ApiError("Rating must be 1 to 5.")
    order["rating"] = stars


def scan(order):
    nxt = NEXT_STATUS.get(order["status"])
    if nxt is None:
        raise ApiError("This order has no next scan.", 409)
    order["status"] = nxt
    order["events"].append(event(nxt))
    emit("status", order)


def qc_fail(order):
    if order["status"] != "with_tailor":
        raise ApiError("QC runs when the finished pouch is back at central storage.", 409)
    order["qc_failures"] += 1
    order["tailor_done_at"] = None
    if order["qc_failures"] == 1:
        note = "Failed central QC: free redo by a master tailor on the express loop (+1 day)"
    else:
        note = "Failed QC again: ops lead to decide redo, refund or compensation"
    order["events"].append({"status": "with_tailor", "label": "Rework", "at": now_iso(), "note": note})
    emit("rework", order)
