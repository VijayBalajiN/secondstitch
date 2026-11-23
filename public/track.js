// Tracking page: status timeline, job card and locked price for one order.

const STEPS = ["confirmed", "collected", "with_tailor", "qc_passed", "out_for_delivery", "delivered"];

const result = document.getElementById("result");
const input = document.getElementById("order-id");
let current = null;     // the order on screen, redrawn when the language changes
let counterIds = {};    // counter display name -> id, to translate counter names

function normaliseId(raw) {
  const s = raw.trim().toUpperCase().replace(/\s+/g, "");
  return s.startsWith("SS-") ? s : s.startsWith("SS") ? "SS-" + s.slice(2) : "SS-" + s;
}

// Orders saved with no garment name get the English default "Garment 1"; show it in the current language.
const garmentLabel = (label, i) => (/^Garment \d+$/.test(label) ? t("o.garment", { n: i + 1 }) : label);

const counterLabel = (order) => counterName(counterIds[order.customer.counter], order.customer.counter);

function timeline(order) {
  if (order.status === "cancelled") {
    const ev = order.events.at(-1);
    return `<ol class="timeline"><li class="done current"><span class="dot"></span><strong>${esc(t("st.cancelled"))}</strong>
      <div class="when">${fmtDateTime(ev.at)}</div><div class="note">${esc(ev.note)}</div></li></ol>`;
  }
  const reached = new Map(order.events.filter((e) => e.label !== "Rework").map((e) => [e.status, e]));
  const reworks = order.events.filter((e) => e.label === "Rework");
  const now = STEPS.indexOf(order.status);
  return `<ol class="timeline">${STEPS.map((s, i) => {
    const ev = reached.get(s);
    const cls = [i <= now ? "done" : "", i === now ? "current" : ""].join(" ");
    let html = `<li class="${cls}"><span class="dot"></span><strong>${esc(t("st." + s))}</strong>
      <div class="when">${ev ? fmtDateTime(ev.at) : i === now + 1 ? esc(t("track.next")) : ""}</div>
      ${i <= now ? `<div class="muted" style="font-size:.9rem">${esc(t("st." + s + ".d"))}</div>` : ""}</li>`;
    if (s === "with_tailor") {
      html += reworks.map((r) => `<li class="rework"><span class="dot"></span><strong>${esc(t("track.rework"))}</strong>
        <div class="when">${fmtDateTime(r.at)}</div><div class="note">${esc(r.note)}</div></li>`).join("");
    }
    return html;
  }).join("")}</ol>`;
}

function jobCard(order) {
  return order.quote.garments.map((g, i) => {
    const d = order.garments[i];
    const label = garmentLabel(d.label, i);
    return `<div class="garment-card">
      <strong>${esc(label)}</strong> <span class="pill grey">${esc(fabricName(g.fabric, g.fabric_label))}</span>
      <ul style="margin:8px 0;padding-left:18px">${g.jobs.map((j) => `<li>${esc(svcName(j.id, j.name))}${j.qty > 1 ? ` × ${j.qty}` : ""}</li>`).join("")}</ul>
      ${d.fit ? `<div class="fine">${esc(t("track.fit"))}: ${esc(tOr("fitm." + d.fit.method, d.fit.label))}${d.fit.value ? ` — ${esc(d.fit.value)}` : ""}</div>` : ""}
      ${d.note ? `<div class="fine">${esc(t("track.note"))}: ${esc(d.note)}</div>` : ""}
      ${d.photo ? `<img src="${esc(d.photo)}" alt="${esc(t("track.photoalt", { label }))}" style="width:96px;height:96px;object-fit:cover;border-radius:4px;margin-top:8px">` : ""}
    </div>`;
  }).join("");
}

function actions(order) {
  if (order.status === "confirmed") {
    return `<div class="panel"><h3>${esc(t("track.changed"))}</h3><p class="muted">${esc(t("track.cancelnote"))}</p>
      <button class="btn btn-ghost" data-act="cancel">${esc(t("track.cancel"))}</button></div>`;
  }
  if (order.status === "delivered") {
    if (order.rating) {
      return `<div class="panel"><h3>${esc(t("track.thanks.t"))}</h3><p class="muted">${esc(t("track.thanks.p", { stars: "★".repeat(order.rating) + "☆".repeat(5 - order.rating) }))}</p></div>`;
    }
    return `<div class="panel"><h3>${esc(t("track.rate.t"))}</h3><p class="muted">${esc(t("track.rate.p"))}</p>
      <div class="stars" role="group" aria-label="${esc(t("track.rate.aria"))}">${[1, 2, 3, 4, 5].map((n) =>
        `<button type="button" data-stars="${n}" aria-label="${esc(t("track.stars", { n }))}">★</button>`).join("")}</div>
      <p class="fine">${esc(t("track.rate.redo"))}</p></div>`;
  }
  return "";
}

function render(order) {
  current = order;
  const q = order.quote;
  const where = q.handover === "counter" ? counterLabel(order) : t("track.home");
  result.innerHTML = `
    <div class="track-grid">
      <div>
        <div class="panel">
          <h3>${esc(order.id)} <span class="pill ${order.status === "delivered" ? "ok" : order.status === "cancelled" ? "grey" : ""}">${esc(t("st." + order.status))}</span></h3>
          ${timeline(order)}
        </div>
        ${actions(order)}
        <p class="contact-line">${esc(t("help.contact"))}</p>
      </div>
      <div>
        <div class="panel">
          <h3>${esc(t("ticket.label"))}</h3>
          <dl class="kv" style="margin-bottom:14px">
            <dt>${esc(t("track.for"))}</dt><dd>${esc(order.customer.name)} · ${esc(order.customer.phone)}</dd>
            <dt>${esc(t("track.tier"))}</dt><dd>${esc(t("board." + q.tier))}${q.speed === "express" ? " · " + esc(t("o.speed.exp")) : ""}</dd>
            <dt>${esc(t("step.3"))}</dt><dd>${esc(where)}, ${fmtDate(q.date)}</dd>
            <dt>${esc(t("track.returns"))}</dt><dd>${esc(readyText(q))}</dd>
          </dl>
          ${jobCard(order)}
        </div>
        <div class="panel">
          <h3>${esc(t("track.locked"))}</h3>
          ${quoteLines(q)}
          <div class="sum-total"><span>${esc(t("sum.total"))}</span><span class="amount">${rupees(q.total)}</span></div>
        </div>
      </div>
    </div>`;
}

async function load(id) {
  result.innerHTML = `<p class="muted">${esc(t("track.looking", { id }))}</p>`;
  try {
    render(await api(`/api/orders/${encodeURIComponent(id)}`));
    history.replaceState(null, "", `/track?id=${encodeURIComponent(id)}`);
  } catch (err) {
    current = null;
    result.innerHTML = `<div class="panel"><p class="errors">${esc(err.message)}</p><p class="muted">${esc(t("track.hint"))}</p></div>`;
  }
}

document.getElementById("track-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = normaliseId(input.value);
  input.value = id;
  load(id);
});

result.addEventListener("click", async (e) => {
  const id = current?.id;                  // the order on screen, not whatever is typed in the box
  if (!id) return;
  const cancelBtn = e.target.closest("[data-act=cancel]");
  const star = e.target.closest("[data-stars]");
  try {
    if (cancelBtn && confirm(t("track.confirmcancel"))) {
      render(await api(`/api/orders/${id}/cancel`, {}));
      toast(t("track.cancelled"));
    }
    if (star) {
      render(await api(`/api/orders/${id}/rate`, { stars: Number(star.dataset.stars) }));
      toast(t("track.rated"));
    }
  } catch (err) {
    toast(err.message);
  }
});

document.addEventListener("languagechange", () => { if (current) render(current); });

(async function start() {
  await i18n.ready;
  try {
    const cat = await api("/api/catalogue");
    counterIds = Object.fromEntries(cat.counters.map((c) => [c.name, c.id]));
  } catch { /* names stay in English */ }
  const params = new URLSearchParams(location.search);
  let initial = params.get("id");
  if (!initial) {
    try { initial = localStorage.getItem("ss-last-order"); } catch { /* storage unavailable */ }
  }
  if (initial) {
    input.value = normaliseId(initial);
    load(input.value);
  }
})();
