// Ops desk: list orders, record QR scans, log QC failures.

const rows = document.getElementById("rows");
let orders = [];
let labels = {};
let filter = "open";
const open = new Set();

const SCAN_LABEL = {
  confirmed: "Scan: collected",
  collected: "Scan: to tailor",
  with_tailor: "Scan: QC pass",
  qc_passed: "Scan: out for delivery",
  out_for_delivery: "Scan: delivered",
};

function statusPill(o) {
  const cls = o.status === "delivered" ? "ok" : o.status === "cancelled" ? "grey" : o.status === "confirmed" ? "warn" : "";
  return `<span class="pill ${cls}">${esc(labels[o.status] || "Cancelled")}</span>`;
}

function detailRow(o) {
  const q = o.quote;
  return `<tr class="ops-detail"><td colspan="7">
    <div class="track-grid">
      <div>
        <strong>Job card</strong>
        ${q.garments.map((g, i) => {
          const d = o.garments[i];
          return `<div class="garment-card"><strong>${esc(d.label)}</strong> · ${esc(g.fabric_label)}
            <ul style="margin:6px 0;padding-left:18px">${g.jobs.map((j) => `<li>${esc(j.name)}${j.qty > 1 ? ` × ${j.qty}` : ""} — ${rupees(j.amount)}</li>`).join("")}</ul>
            ${d.fit ? `<div class="fine">Fit: ${esc(d.fit.label)}${d.fit.value ? ` — ${esc(d.fit.value)}` : ""}</div>` : ""}
            ${d.note ? `<div class="fine">Note: ${esc(d.note)}</div>` : ""}
            ${d.photo ? `<div class="photos"><img src="${esc(d.photo)}" alt="Customer photo"></div>` : ""}</div>`;
        }).join("")}
      </div>
      <div>
        <strong>Contact</strong>
        <p class="fine" style="margin:4px 0 12px">${esc(o.customer.name)} · ${esc(o.customer.phone)}<br>${esc(o.customer.counter || o.customer.address)}</p>
        <strong>Scan log</strong>
        <ul style="margin:4px 0 12px;padding-left:18px" class="fine">${o.events.map((e) =>
          `<li>${fmtDateTime(e.at)} — ${esc(e.label)}${e.note ? `: ${esc(e.note)}` : ""}</li>`).join("")}</ul>
        <strong>Money</strong>
        <p class="fine" style="margin:4px 0 0">Customer pays ${rupees(q.total)} · tailor earns ${rupees(q.tailor_earns)}${o.rating ? ` · rated ${o.rating}/5` : ""}</p>
      </div>
    </div>
  </td></tr>`;
}

function render() {
  const shown = orders.filter((o) => filter === "all"
    || (filter === "open" && !["delivered", "cancelled"].includes(o.status))
    || (filter === "done" && ["delivered", "cancelled"].includes(o.status)));
  const count = (pred) => orders.filter(pred).length;
  document.getElementById("stats").innerHTML = [
    ["Open", count((o) => !["delivered", "cancelled"].includes(o.status))],
    ["With tailors", count((o) => o.status === "with_tailor")],
    ["Express", count((o) => o.quote.speed === "express" && o.status !== "cancelled")],
    ["Delivered", count((o) => o.status === "delivered")],
  ].map(([k, v]) => `<div class="stat"><b>${v}</b><small>${k}</small></div>`).join("");

  if (!shown.length) {
    rows.innerHTML = `<tr><td colspan="7" class="empty">No orders here yet. Place one on the <a href="/#order">customer site</a>.</td></tr>`;
    return;
  }
  rows.innerHTML = shown.map((o) => {
    const q = o.quote;
    const jobs = q.garments.reduce((n, g) => n + g.jobs.reduce((m, j) => m + j.qty, 0), 0);
    return `<tr>
      <td><strong>${esc(o.id)}</strong><div class="fine">${fmtDateTime(o.created_at)}</div></td>
      <td>${esc(o.customer.name)}</td>
      <td>${esc(q.tier_label)}${q.speed === "express" ? ' <span class="pill">Express</span>' : ""}<div class="fine">${q.garments.length} garment${q.garments.length > 1 ? "s" : ""}, ${jobs} job${jobs > 1 ? "s" : ""}</div></td>
      <td>${q.handover === "counter" ? "Counter" : "Home pickup"}<div class="fine">${fmtDate(q.date)}</div></td>
      <td class="num">${rupees(q.total)}</td>
      <td>${statusPill(o)}</td>
      <td><div class="actions">
        ${SCAN_LABEL[o.status] ? `<button class="btn btn-small btn-dark" data-act="scan" data-id="${o.id}">${SCAN_LABEL[o.status]}</button>` : ""}
        ${o.status === "with_tailor" ? `<button class="btn btn-small btn-ghost" data-act="qc-fail" data-id="${o.id}">QC fail</button>` : ""}
        <button class="btn btn-small btn-ghost" data-act="toggle" data-id="${o.id}" aria-expanded="${open.has(o.id)}">${open.has(o.id) ? "Hide" : "Details"}</button>
      </div></td>
    </tr>${open.has(o.id) ? detailRow(o) : ""}`;
  }).join("");
}

async function load() {
  try {
    const data = await api("/api/ops/orders");
    orders = data.orders;
    labels = Object.fromEntries(data.statuses);
    render();
  } catch (err) {
    if (err.status === 401) return askPin(err.message);
    rows.innerHTML = `<tr><td colspan="7" class="errors">${esc(err.message)}</td></tr>`;
  }
}

function askPin(message) {
  rows.innerHTML = `<tr><td colspan="7" class="empty">
    <form id="pin-form" class="actions" style="justify-content:center">
      <label for="pin" class="fine">${esc(message)}</label>
      <input id="pin" inputmode="numeric" autocomplete="off" style="width:9em">
      <button class="btn btn-small btn-dark">Open desk</button>
    </form></td></tr>`;
  const input = document.getElementById("pin");
  input.focus();
  document.getElementById("pin-form").addEventListener("submit", (e) => {
    e.preventDefault();
    opsPinMemo = input.value.trim();
    try { sessionStorage.setItem("ops-pin", opsPinMemo); } catch { /* PIN lasts this page only */ }
    load();
  });
}

rows.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const { act, id } = btn.dataset;
  if (act === "toggle") {
    open.has(id) ? open.delete(id) : open.add(id);
    return render();
  }
  try {
    const updated = await api(`/api/ops/orders/${id}/${act}`, {});
    orders = orders.map((o) => (o.id === id ? updated : o));
    render();
    toast(act === "scan" ? `${id}: ${labels[updated.status]}` : `${id}: sent for rework`);
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById("filter").addEventListener("change", (e) => { filter = e.target.value; render(); });
load();
setInterval(() => { if (!document.getElementById("pin-form")) load(); }, 10000);
