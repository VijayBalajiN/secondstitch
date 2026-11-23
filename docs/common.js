// Helpers shared by every page. Names the server sends in English (services, fabrics, seasons, handover)
// are shown in the current language through i18n; an unknown name falls back to the server's text.

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

const rupees = (n) => "₹" + Number(n).toLocaleString("en-IN");

const signed = (n) => (n < 0 ? "−" : "+") + rupees(Math.abs(n));

// Ops desk PIN, needed only when the site is shared on Wi-Fi (server.py --lan).
let opsPinMemo = "";
function opsPin() {
  try { return sessionStorage.getItem("ops-pin") || opsPinMemo; } catch { return opsPinMemo; }
}

async function api(path, body) {
  const headers = path.startsWith("/secondstitch/api/ops/") ? { "X-Ops-Pin": opsPin() } : {};
  const res = await fetch(path, body === undefined ? { headers } : {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ error: "The server sent an unreadable reply." }));
  if (!res.ok) {
    const err = new Error(data.error || "Request failed");
    err.errors = data.errors || [err.message];
    err.status = res.status;
    throw err;
  }
  return data;
}

const dateLocale = () => i18n.locale;

function fmtDate(iso, opts = { weekday: "short", day: "numeric", month: "short" }) {
  return new Date(iso.length === 10 ? iso + "T00:00:00" : iso).toLocaleDateString(dateLocale(), opts);
}

function fmtDateTime(iso) {
  return new Date(iso).toLocaleString(dateLocale(), {
    day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
  });
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.setAttribute("role", "status");
  el.textContent = msg;
  document.body.append(el);
  setTimeout(() => el.remove(), 2600);
}

// ---------- Server names in the current language ----------

const svcName = (id, fallback) => tOr("svc." + id, fallback);
const fabricName = (key, fallback) => tOr("fabric." + key, fallback);
const handoverName = (key, fallback) => tOr("ho.q." + key, fallback);
const counterName = (id, fallback) => tOr("counter." + id, fallback);
const statusName = (key, fallback) => tOr("st." + key, fallback);

function seasonName(season) {
  const label = season.label;
  const key = label.startsWith("Off-peak") ? "offpeak" : label === "Normal week" ? "normal"
    : label.startsWith("Wedding") ? "wedding" : label.split(" ")[0].toLowerCase();
  return tOr("season." + key, label);
}

function readyText(q) {
  if (!q.ready_by) return q.ready;
  const short = (iso) => fmtDate(iso, { weekday: "short", day: "numeric", month: "short" });
  return q.speed === "express"
    ? t("ready.express", { date: short(q.ready_by) })
    : t("ready.standard", { by: short(q.ready_by), usual: short(q.ready_usual) });
}

// Itemised price lines for a locked or live quote (used by the order summary and tracking page).
function quoteLines(q) {
  const rows = [];
  q.garments.forEach((g) => {
    rows.push(`<div class="sum-group">${esc(t("o.garment", { n: g.index }))}${g.fabric !== "everyday" ? " · " + esc(fabricName(g.fabric, g.fabric_label)) : ""}</div>`);
    g.jobs.forEach((j) => rows.push(
      `<div class="sum-line"><span>${esc(svcName(j.id, j.name))}${j.qty > 1 ? ` × ${j.qty}` : ""}</span><span>${rupees(j.amount)}</span></div>`));
    if (g.fabric_adjustment) {
      rows.push(`<div class="sum-line adj"><span>${esc(t("sum.fabricx", { fabric: fabricName(g.fabric, g.fabric_label), f: g.fabric_factor }))}</span><span>${signed(g.fabric_adjustment)}</span></div>`);
    }
  });
  rows.push(`<div class="sum-group">${esc(t("sum.adj"))}</div>`);
  if (q.season_adjustment) {
    rows.push(`<div class="sum-line adj ${q.season_adjustment < 0 ? "minus" : ""}"><span>${esc(seasonName(q.season))} × ${q.season.factor}</span><span>${signed(q.season_adjustment)}</span></div>`);
  }
  if (q.min_order_topup) {
    rows.push(`<div class="sum-line adj"><span>${esc(t("sum.topup"))}</span><span>${signed(q.min_order_topup)}</span></div>`);
  }
  if (q.express) {
    rows.push(`<div class="sum-line"><span>${esc(t("sum.express"))}</span><span>${signed(q.express)}</span></div>`);
  }
  const fee = q.handover_waived
    ? `<s>${rupees(q.handover_fee)}</s> ${esc(t("sum.waived"))}`
    : q.handover_charged ? rupees(q.handover_charged) : esc(t("ho.counter.tag"));
  rows.push(`<div class="sum-line"><span>${esc(handoverName(q.handover, q.handover_label))}</span><span>${fee}</span></div>`);
  return rows.join("");
}

// Decorative QR-like grid for job cards (not a scannable code).
function fakeQr(el, seed) {
  let x = [...String(seed)].reduce((a, c) => a * 31 + c.charCodeAt(0), 7) >>> 0;
  const corner = (r, c) => (r < 3 && c < 3) || (r < 3 && c > 5) || (r > 5 && c < 3);
  el.innerHTML = Array.from({ length: 81 }, (_, i) => {
    const r = Math.floor(i / 9), c = i % 9;
    x = (x * 1103515245 + 12345) >>> 0;
    const on = corner(r, c) || (x >> 16) % 2;
    return `<span class="${on ? "" : "off"}"></span>`;
  }).join("");
}
