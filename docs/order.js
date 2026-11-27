// Order page: a four-step builder (garment, tailor, handover, details). Prices always come from /api/quote.
// /order?add=trouser-hem,button starts the first garment with those fixes (used by the garment picker).

let C = null;      // catalogue from /api/catalogue
let days = [];     // season calendar from /api/calendar
let gid = 0;
let tierSwitched = false;
let quoteSeq = 0;
let quoteTimer = null;
let lastQuote = null;
let step = 1;
let maxStep = 1;
let confirmed = false;
let shownErrors = [];
const LAST_STEP = 4;

const state = {
  tier: "standard",
  speed: "standard",
  handover: "counter",
  counter: "",
  address: "",
  date: null,
  garments: [],
};

const $ = (sel) => document.querySelector(sel);
const svc = (id) => C.services.find((s) => s.id === id);
const name = (s) => svcName(s.id, s.name);
const newGarment = () => ({ key: ++gid, label: "", fabric: "everyday", jobs: [], note: "", fit: { method: "", value: "" }, photo: null });
const garmentByKey = (key) => state.garments.find((g) => g.key === Number(key));
const priceFor = (s) => s.prices[s.premium_only ? "premium" : state.tier];

function premiumReasons() {
  const reasons = [];
  state.garments.forEach((g) => {
    g.jobs.forEach((j) => { if (svc(j.id).premium_only) reasons.push(`“${name(svc(j.id))}”`); });
    if (C.fabrics[g.fabric].premium_only) reasons.push(t("o.reason.embellished"));
  });
  return [...new Set(reasons)];
}

function expressCutoffPassed() {
  return state.date === days[0].date && new Date().getHours() >= C.rules.express_cutoff_hour;
}

function enforceRules() {
  const reasons = premiumReasons();
  if (reasons.length && state.tier !== "premium") {
    state.tier = "premium";
    tierSwitched = true;
  }
  if (!reasons.length) tierSwitched = false;
  if (state.speed === "express" && (state.tier !== "premium" || expressCutoffPassed())) state.speed = "standard";
}

// ---------- Step bar (a tape measure with button markers) ----------

function renderTape() {
  $("#tape-steps").innerHTML = [1, 2, 3, 4].map((n) => `
    <button type="button" data-go="${n}" ${n > maxStep ? "disabled" : ""} class="${n < step ? "done" : ""}" ${n === step ? 'aria-current="step"' : ""}>
      <span class="no">${n}</span><span class="lbl">${esc(t("step." + n))}</span>
    </button>`).join("");
}

function showStep(n) {
  step = n;
  maxStep = Math.max(maxStep, n);
  document.querySelectorAll(".step-box").forEach((box) => { box.hidden = Number(box.dataset.step) !== n; });
  $("#back-btn").hidden = n === 1;
  $("#next-btn").hidden = n === LAST_STEP;
  $("#submit-btn").hidden = n !== LAST_STEP;
  showErrors([]);
  renderTape();
  saveDraft();
}

function goTo(n, scroll = true) {
  showStep(Math.max(1, Math.min(LAST_STEP, n)));
  if (scroll) $("#order-area").scrollIntoView({ behavior: "smooth", block: "start" });
  document.querySelector(`.step-box[data-step="${step}"] legend`)?.focus({ preventScroll: true });
}

// ---------- Keep keyboard focus when a part of the page is redrawn ----------

function focusKey(el) {
  if (!el || el === document.body || !el.dataset) return null;
  return { g: el.closest(".garment")?.dataset.key, f: el.dataset.f, act: el.dataset.act, job: el.dataset.job || el.closest("[data-job]")?.dataset.job,
    date: el.dataset.date, id: el.id, name: el.name, value: el.value, type: el.type };
}

function restoreFocus(k) {
  if (!k) return;
  const base = k.g ? `.garment[data-key="${k.g}"] ` : "";
  const tries = [];
  if (k.g && k.act) tries.push(`${base}[data-act="${k.act}"]${k.job ? `[data-job="${k.job}"]` : ""}`);
  if (k.g && k.f) tries.push(k.type === "radio" ? `${base}[data-f="${k.f}"][value="${k.value}"]` : `${base}[data-f="${k.f}"]`);
  if (k.date) tries.push(`[data-date="${k.date}"]`);
  if (k.id) tries.push(`#${k.id}`);
  if (k.name && k.type === "radio") tries.push(`input[name="${k.name}"][value="${k.value}"]`);
  if (k.g) tries.push(`${base}[data-f="add-job"]`, "#add-garment");   // the thing that was focused is gone: go to the nearest one
  for (const sel of tries) {
    const el = document.querySelector(sel);
    if (el && !el.disabled && !el.hidden) { el.focus({ preventScroll: true }); return; }
  }
}

function keepFocus(fn) {
  const k = focusKey(document.activeElement);
  fn();
  restoreFocus(k);
}

// ---------- Keep the order if the page is reloaded ----------

const DRAFT = "ss-order-draft";

function saveDraft() {
  if (!C || confirmed) return;
  try {
    sessionStorage.setItem(DRAFT, JSON.stringify({
      tier: state.tier, speed: state.speed, handover: state.handover, counter: state.counter, address: state.address, date: state.date,
      step, maxStep, name: $("#cust-name").value, phone: $("#cust-phone").value,
      garments: state.garments.map((g) => ({ label: g.label, fabric: g.fabric, jobs: g.jobs, note: g.note, fit: g.fit })),
    }));
  } catch { /* storage unavailable: the order just isn't kept on reload */ }
}

function loadDraft() {
  try {
    const d = JSON.parse(sessionStorage.getItem(DRAFT) || "null");
    if (!d || !Array.isArray(d.garments) || !d.garments.length || d.garments.length > 8) return false;
    if (!d.garments.every((g) => Array.isArray(g.jobs) && g.jobs.every((j) => svc(j.id) && j.qty >= 1 && j.qty <= 20))) return false;
    state.tier = d.tier === "premium" ? "premium" : "standard";
    state.speed = d.speed === "express" ? "express" : "standard";
    state.handover = C.handover[d.handover] ? d.handover : "counter";
    if (C.counters.some((c) => c.id === d.counter)) state.counter = d.counter;
    state.address = String(d.address || "").slice(0, 300);
    if (days.some((x) => x.date === d.date)) state.date = d.date;
    state.garments = d.garments.map((g) => ({
      ...newGarment(), label: String(g.label || "").slice(0, 60), fabric: C.fabrics[g.fabric] ? g.fabric : "everyday",
      jobs: g.jobs.map(({ id, qty }) => ({ id, qty })), note: String(g.note || "").slice(0, 500),
      fit: { method: C.fit_methods[g.fit?.method] ? g.fit.method : "", value: String(g.fit?.value || "").slice(0, 80) },
    }));
    maxStep = Math.min(LAST_STEP, Math.max(1, Number(d.maxStep) || 1));
    step = Math.min(maxStep, Math.max(1, Number(d.step) || 1));
    $("#cust-name").value = String(d.name || "").slice(0, 80);
    $("#cust-phone").value = String(d.phone || "").slice(0, 16);
    return true;
  } catch {
    return false;
  }
}

// ---------- Step 1: garments ----------

const FIT_ICONS = {
  measurement: '<rect x="3" y="11" width="26" height="10" rx="1.5"/><path d="M8 11v4M13 11v6M18 11v4M23 11v6"/>',
  mark: '<circle cx="22" cy="9" r="4"/><path d="M19 12L7 26M5 27l2-2"/>',
  reference: '<path d="M16 13v-2a3 3 0 1 0-3-3"/><path d="M16 13L4 23h24z"/>',
  none: '<circle cx="16" cy="16" r="11"/><path d="M9 23L23 9"/>',
};

const NEW_IDS = ["new-pants", "new-kurta"];

/** Two buttons for made-to-measure clothes, so nobody has to dig through the fix list for them. */
function newClothesHtml(g) {
  const buttons = NEW_IDS.filter((id) => svc(id) && !g.jobs.some((j) => j.id === id)).map((id) => `
    <button type="button" class="btn btn-ghost btn-small" data-act="add-new" data-new="${id}">+ ${esc(t(id === "new-pants" ? "o.new.pants" : "o.new.kurta"))} · ${rupees(svc(id).prices.premium)}</button>`).join("");
  return buttons ? `<div class="new-clothes"><span class="field-label">${esc(t("o.newq"))}</span><div class="new-btns">${buttons}</div></div>` : "";
}

function jobOptions(g) {
  const taken = new Set(g.jobs.map((j) => j.id));
  const hasButton = taken.has("button");
  const opt = (s) => `<option value="${s.id}">${esc(name(s))} — ${s.addon ? "+" : ""}${rupees(priceFor(s))}</option>`;
  const avail = C.services.filter((s) => !taken.has(s.id) && (!s.addon || hasButton));
  return `<option value="">${esc(t("o.addfix"))}</option>
    <optgroup label="${esc(t("o.grp.new"))}">${avail.filter((s) => NEW_IDS.includes(s.id)).map(opt).join("")}</optgroup>
    <optgroup label="${esc(t("o.grp.quick"))}">${avail.filter((s) => !s.premium_only && !NEW_IDS.includes(s.id)).map(opt).join("")}</optgroup>
    <optgroup label="${esc(t("o.grp.prem"))}">${avail.filter((s) => s.premium_only && !NEW_IDS.includes(s.id)).map(opt).join("")}</optgroup>`;
}

function garmentHtml(g, i) {
  const gname = `g${g.key}`;
  const fabrics = Object.entries(C.fabrics).map(([k, f]) => `
    <label title="${esc(tOr("fabric." + k + ".d", f.detail))}"><input type="radio" name="${gname}-fabric" value="${k}" data-f="fabric" ${g.fabric === k ? "checked" : ""}>
    <span>${esc(fabricName(k, f.label))}${f.factor !== 1 ? ` ×${f.factor}` : ""}</span></label>`).join("");

  const jobs = g.jobs.map((j) => {
    const s = svc(j.id);
    return `<li class="job-row">
      <span class="name">${svcThumb(s.id)}${esc(name(s))}${s.premium_only ? ` <span class="pill dark">${esc(t("board.premium"))}</span>` : ""}</span>
      <span class="qty" aria-label="${esc(t("o.qty"))}">
        <button type="button" data-act="dec" data-job="${j.id}" aria-label="${esc(t("o.fewer"))}">−</button>
        <output>${j.qty}</output>
        <button type="button" data-act="inc" data-job="${j.id}" aria-label="${esc(t("o.more"))}">+</button>
      </span>
      <span class="price">${rupees(priceFor(s) * j.qty)}</span>
      <button type="button" class="icon-btn" data-act="remove-job" data-job="${j.id}" aria-label="${esc(t("o.removejob", { name: name(s) }))}">×</button>
    </li>`;
  }).join("");

  const fitJob = g.jobs.some((j) => svc(j.id).fit);
  const fit = fitJob ? `
    <div class="fit-box">
      <span class="field-label">${esc(t("o.fit.q"))}</span>
      <div class="fit-methods">${Object.keys(C.fit_methods).map((k) => `
        <label><input type="radio" name="${gname}-fit" value="${k}" data-f="fit-method" ${g.fit.method === k ? "checked" : ""}>
        <span class="box"><svg viewBox="0 0 32 32" aria-hidden="true">${FIT_ICONS[k] || ""}</svg>${esc(tOr("fitl." + k, C.fit_methods[k]))}</span></label>`).join("")}
      </div>
      ${g.fit.method === "measurement" ? `<label class="field" style="margin:10px 0 0"><span class="visually-hidden">${esc(t("fitl.measurement"))}</span>
        <input type="text" data-f="fit-value" maxlength="80" placeholder="${esc(t("o.fit.ph"))}" value="${esc(g.fit.value)}"></label>` : ""}
      <p class="fine" style="margin:10px 0 0">${esc(t("o.fit.note"))} <a href="/secondstitch/help#fit">${esc(t("fit.title"))}</a></p>
    </div>` : "";

  const photo = g.photo
    ? `<img src="${g.photo}" alt="${esc(t("o.photo.alt", { n: i + 1 }))}"><button type="button" class="link-btn" data-act="remove-photo">${esc(t("o.photo.remove"))}</button>`
    : `<button type="button" class="btn btn-ghost btn-small" data-act="pick-photo">${esc(t("o.photo.add"))}</button>
       <input type="file" accept="image/*" data-f="photo" class="visually-hidden" tabindex="-1" aria-hidden="true">
       <span class="fine">${esc(t("o.photo.hint"))}</span>`;

  return `<div class="garment" data-key="${g.key}">
    <div class="garment-head">
      <h3>${esc(t("o.garment", { n: i + 1 }))}</h3>
      ${state.garments.length > 1 ? `<button type="button" class="link-btn" data-act="remove-garment">${esc(t("o.remove"))}</button>` : ""}
    </div>
    <div class="row">
      <label class="field"><span>${esc(t("o.whatisit"))} <span class="muted" style="font-weight:400">${esc(t("o.optional"))}</span></span>
        <input type="text" data-f="label" maxlength="60" placeholder="${esc(t("o.whatph"))}" value="${esc(g.label)}"></label>
      <div class="field"><span class="field-label">${esc(t("o.fabric"))}</span><div class="segmented">${fabrics}</div></div>
    </div>
    ${jobs ? `<ul class="job-list">${jobs}</ul>` : ""}
    ${newClothesHtml(g)}
    <label class="field"><select data-f="add-job" aria-label="${esc(t("o.addfix"))}">${jobOptions(g)}</select></label>
    ${fit}
    <label class="field"><span>${esc(t("o.note"))} <span class="muted" style="font-weight:400">${esc(t("o.optional"))}</span></span>
      <textarea data-f="note" maxlength="500" placeholder="${esc(t("o.noteph"))}">${esc(g.note)}</textarea></label>
    <div class="photo-row">${photo}</div>
  </div>`;
}

function renderGarments() {
  keepFocus(() => {
    $("#garments").innerHTML = state.garments.map(garmentHtml).join("");
    $("#add-garment").hidden = state.garments.length >= 8;
  });
}

async function shrinkPhoto(file) {
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bmp.width * scale);
  canvas.height = Math.round(bmp.height * scale);
  canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.82);
}

function onGarmentEvent(e) {
  const card = e.target.closest(".garment");
  if (!card) return;
  const g = garmentByKey(card.dataset.key);
  const f = e.target.dataset.f;
  const act = e.target.closest("[data-act]")?.dataset.act;

  if (e.type === "input") {
    if (f === "label") g.label = e.target.value;
    if (f === "note") g.note = e.target.value;
    if (f === "fit-value") g.fit.value = e.target.value;
    saveDraft();
    return;
  }
  if (e.type === "change") {
    if (f === "add-job" && e.target.value) {
      g.jobs.push({ id: e.target.value, qty: 1 });
      return renderAll();
    }
    if (f === "fabric") {
      g.fabric = e.target.value;
      return renderAll();
    }
    if (f === "fit-method") {
      g.fit.method = e.target.value;
      return renderGarments();
    }
    if (f === "photo" && e.target.files[0]) {
      shrinkPhoto(e.target.files[0])
        .then((url) => { g.photo = url; renderGarments(); })
        .catch(() => toast(t("o.photo.err")));
    }
    return;
  }
  if (!act) return;
  if (act === "add-new") { g.jobs.push({ id: e.target.closest("[data-new]").dataset.new, qty: 1 }); return renderAll(); }
  if (act === "pick-photo") return card.querySelector("[data-f=photo]").click();
  const job = g.jobs.find((j) => j.id === e.target.closest("[data-job]")?.dataset.job);
  if (act === "inc" && job.qty < 20) job.qty++;
  if (act === "dec") job.qty > 1 ? job.qty-- : (g.jobs = g.jobs.filter((j) => j !== job));
  if (act === "remove-job") g.jobs = g.jobs.filter((j) => j !== job);
  if (!g.jobs.some((j) => j.id === "button")) g.jobs = g.jobs.filter((j) => j.id !== "extra-button");
  if (act === "remove-garment") state.garments = state.garments.filter((x) => x !== g);
  if (act === "remove-photo") g.photo = null;
  renderAll();
}

// ---------- Steps 2 and 3 ----------

function choice(group, value, checked, disabled, title, tag, detail) {
  return `<label class="choice"><input type="radio" name="${group}" value="${value}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}>
    <span class="box"><span class="tag">${esc(tag)}</span><strong>${esc(title)}</strong><small>${esc(detail)}</small></span></label>`;
}

function workFor(tier) {
  return state.garments.reduce((sum, g) => sum + g.jobs.reduce((a, j) => {
    const s = svc(j.id);
    return a + (s.prices[tier] ?? s.prices.premium) * j.qty;
  }, 0), 0);
}

function renderTier() {
  const reasons = premiumReasons();
  const price = (tier) => (workFor(tier) ? rupees(workFor(tier)) : "");
  $("#tier-choices").innerHTML =
    choice("tier", "standard", state.tier === "standard", reasons.length > 0, `${t("board.standard")} · ${t("tier.std.name")}`, price("standard"), t("o.tier.std.d")) +
    choice("tier", "premium", state.tier === "premium", false, `${t("board.premium")} · ${t("tier.prem.name")}`, price("premium"), t("o.tier.prem.d"));
  const hint = $("#tier-hint");
  hint.hidden = !reasons.length;
  hint.className = "hint" + (tierSwitched ? " warn" : "");
  hint.textContent = tierSwitched ? t("o.tier.switched", { reason: reasons[0] }) : reasons.length ? t("o.tier.unavail", { reasons: reasons.join(", ") }) : "";
}

function renderSpeed() {
  const cutoff = expressCutoffPassed();
  const off = state.tier !== "premium" || cutoff;
  $("#speed-choices").innerHTML =
    choice("speed", "standard", state.speed === "standard", false, t("o.speed.std"), t("o.speed.std.tag"), t("tier.std.l2")) +
    choice("speed", "express", state.speed === "express", off, t("o.speed.exp"), "+40%", t("o.speed.exp.d"));
  const hint = $("#speed-hint");
  hint.hidden = !off;
  hint.textContent = state.tier !== "premium" ? t("o.speed.needprem") : t("o.speed.cutoff");
}

function renderHandover() {
  const h = C.handover;
  $("#handover-choices").innerHTML =
    choice("handover", "counter", state.handover === "counter", false, t("ho.counter"), t("ho.counter.tag"), t("ho.counter.d")) +
    choice("handover", "pickup-4", state.handover === "pickup-4", false, t("ho.pickup"), rupees(h["pickup-4"].fee), t("ho.pickup4.d")) +
    choice("handover", "pickup-8", state.handover === "pickup-8", false, t("ho.pickup"), rupees(h["pickup-8"].fee), t("ho.pickup8.d"));
  const detail = $("#handover-detail");
  if (state.handover === "counter") {
    detail.innerHTML = `<label class="field"><span>${esc(t("o.counter"))}</span><select id="counter">${C.counters.map((c) =>
      `<option value="${c.id}" ${c.id === state.counter ? "selected" : ""}>${esc(counterName(c.id, c.name))}</option>`).join("")}</select></label>`;
  } else {
    detail.innerHTML = `<label class="field"><span>${esc(t("o.address"))}</span>
      <textarea id="address" maxlength="300" autocomplete="street-address" placeholder="${esc(t("o.addressph"))}">${esc(state.address)}</textarea></label>`;
  }
}

function renderDates() {
  const strip = $("#date-strip");
  const scroll = strip.scrollLeft;
  strip.innerHTML = days.map((d, i) => {
    const dow = i === 0 ? t("o.today") : i === 1 ? t("o.tomorrow") : fmtDate(d.date, { weekday: "short" });
    const fac = d.kind === "peak" ? "+20%" : d.kind === "offpeak" ? "−10%" : "";
    return `<button type="button" class="date-chip ${d.kind}" data-date="${d.date}" aria-pressed="${d.date === state.date}" title="${esc(seasonName(d))}">
      <span class="dow">${esc(dow)}</span><span class="day">${fmtDate(d.date, { day: "numeric" })}</span>
      <span class="mon">${fmtDate(d.date, { month: "short" })}</span><span class="fac">${fac}</span></button>`;
  }).join("");
  strip.scrollLeft = scroll;
}

// ---------- Quote and summary ----------

function payload(withDetails = false) {
  return {
    tier: state.tier, speed: state.speed, handover: state.handover, date: state.date,
    garments: state.garments.map((g) => ({
      fabric: g.fabric,
      jobs: g.jobs.map(({ id, qty }) => ({ id, qty })),
      ...(withDetails ? { label: g.label, note: g.note, fit: g.fit, photo: g.photo } : {}),
    })),
  };
}

function scheduleQuote() {
  clearTimeout(quoteTimer);
  quoteTimer = setTimeout(async () => {
    const seq = ++quoteSeq;
    try {
      const q = await api("/secondstitch/api/quote", payload());
      if (seq === quoteSeq) renderSummary(q);
    } catch (err) {
      if (seq === quoteSeq) $("#summary").innerHTML = `<h3>${esc(t("sum.title"))}</h3><p class="errors">${esc(err.message)}</p>`;
    }
  }, 120);
}

function renderPriceBar(q) {
  const bar = $("#price-bar");
  bar.hidden = confirmed || !q || !q.ok;
  if (!bar.hidden) bar.innerHTML = `<span>${esc(t("sum.total"))} <strong>${rupees(q.total)}</strong></span><a href="#summary">${esc(t("o.pricebar.more"))}</a>`;
}

function renderSummary(q) {
  lastQuote = q;
  renderPriceBar(q);
  const box = $("#summary");
  if (!q) {
    box.innerHTML = `<h3>${esc(t("sum.title"))}</h3><p class="empty">${esc(t("sum.empty"))}</p>`;
    return;
  }
  if (!q.ok) {
    const noJobs = state.garments.every((g) => !g.jobs.length);
    box.innerHTML = `<h3>${esc(t("sum.title"))}</h3>` + (noJobs
      ? `<p class="empty">${esc(t("sum.empty"))}</p>`
      : `<div class="errors"><ul>${q.errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></div>`);
    return;
  }
  const peak = q.season.kind === "peak" && q.season.next_normal_date
    ? `<div class="sum-meta"><span class="pill warn">${esc(t("sum.peak", { label: seasonName(q.season) }))}</span>
       <span>${esc(t("sum.nextnormal", { date: fmtDate(q.season.next_normal_date) }))} <button type="button" class="link-btn" data-date="${q.season.next_normal_date}">${esc(t("sum.switch"))}</button></span></div>`
    : "";
  box.innerHTML = `
    <h3>${esc(t("sum.title"))}</h3>
    ${quoteLines(q)}
    <div class="sum-total"><span>${esc(t("sum.total"))}</span><span class="amount">${rupees(q.total)}</span></div>
    ${peak}
    <div class="sum-meta">
      <span><strong>${esc(t("board." + q.tier))}</strong> · ${esc(t(q.tier === "premium" ? "tier.prem.name" : "tier.std.name"))}${q.speed === "express" ? " · " + esc(t("o.speed.exp")) : ""}</span>
      <span>${esc(t("sum.handover", { date: fmtDate(q.date), ready: readyText(q) }))}</span>
    </div>
    <p class="fine" style="margin:10px 0 0">${esc(t("sum.locked"))}</p>`;
}

function renderAll() {
  enforceRules();
  keepFocus(() => {
    renderGarments();
    renderTier();
    renderSpeed();
    renderHandover();
    renderDates();
  });
  scheduleQuote();
  saveDraft();
}

// ---------- Validation and submit ----------

// An error is a plain string (from the server) or { key, params, el }: the text is looked up when it is
// shown, so it follows a language change, and the field it is about gets aria-invalid.
function showErrors(list) {
  shownErrors = list;
  document.querySelectorAll("#order-form [aria-invalid]").forEach((el) => { el.removeAttribute("aria-invalid"); el.removeAttribute("aria-describedby"); });
  const text = (e) => (typeof e === "string" ? e : t(e.key, e.params));
  $("#form-errors").innerHTML = list.length ? `<ul>${list.map((e) => `<li>${esc(text(e))}</li>`).join("")}</ul>` : "";
  list.forEach((e) => { if (e.el) { e.el.setAttribute("aria-invalid", "true"); e.el.setAttribute("aria-describedby", "form-errors"); } });
}

function focusFirstError(list) {
  list.find((e) => e.el)?.el.focus();
}

function stepErrors(n) {
  const errors = [];
  const card = (g) => document.querySelector(`.garment[data-key="${g.key}"]`);
  if (n === 1) {
    state.garments.forEach((g, i) => {
      if (!g.jobs.length) errors.push({ key: "e.nofix", el: card(g)?.querySelector("[data-f=add-job]") });
      if (g.jobs.some((j) => svc(j.id).fit) && !g.fit.method) errors.push({ key: "e.fit", params: { n: i + 1 }, el: card(g)?.querySelector("[data-f=fit-method]") });
      if (g.fit.method === "measurement" && !g.fit.value.trim()) errors.push({ key: "e.measure", params: { n: i + 1 }, el: card(g)?.querySelector("[data-f=fit-value]") });
    });
  }
  if (n === 3 && state.handover !== "counter" && state.address.trim().length < 5) errors.push({ key: "e.address", el: $("#address") });
  if (n === 4) {
    if (!$("#cust-name").value.trim()) errors.push({ key: "e.name", el: $("#cust-name") });
    if (!/^(\+?91)?[6-9]\d{9}$/.test($("#cust-phone").value.trim().replace(/[\s-]/g, ""))) errors.push({ key: "e.phone", el: $("#cust-phone") });
  }
  return errors;
}

function next() {
  const errors = stepErrors(step);
  showErrors(errors);
  if (errors.length) focusFirstError(errors);
  else goTo(step + 1);
}

async function submitOrder(e) {
  e.preventDefault();
  if (step !== LAST_STEP) return next();   // Enter in a text field means "next", not "place the order"
  for (let n = 1; n <= LAST_STEP; n++) {
    const errors = stepErrors(n);
    if (errors.length) {
      if (n !== step) goTo(n);
      showErrors(errors);
      return focusFirstError(errors);
    }
  }
  if (!lastQuote?.ok) return showErrors(lastQuote?.errors?.length ? lastQuote.errors : [{ key: "e.nofix" }]);

  const btn = $("#submit-btn");
  btn.disabled = true;
  btn.textContent = t("o.placing");
  try {
    const order = await api("/secondstitch/api/orders", {
      ...payload(true),
      customer: { name: $("#cust-name").value.trim(), phone: $("#cust-phone").value.trim(), counter: state.counter, address: state.address },
    });
    try { localStorage.setItem("ss-last-order", order.id); } catch { /* storage unavailable */ }
    showConfirmation(order);
  } catch (err) {
    showErrors(err.errors || [err.message]);
    btn.disabled = false;
    btn.textContent = t("o.place");
  }
}

function showConfirmation(order) {
  const q = order.quote;
  const where = q.handover === "counter"
    ? t("c.drop", { where: `<strong>${esc(counterName(C.counters.find((c) => c.name === order.customer.counter)?.id, order.customer.counter))}</strong>`, date: fmtDate(q.date) })
    : t("c.pickup", { date: fmtDate(q.date) });
  confirmed = true;
  try { sessionStorage.removeItem(DRAFT); } catch { /* ignore */ }
  $("#price-bar").hidden = true;
  document.querySelector(".section-lead").hidden = true;
  const first = (order.customer.name || "").trim().split(/\s+/)[0];
  $("#order-area").innerHTML = `
    <div class="confirm">
      <div class="check" aria-hidden="true">✓</div>
      <h3 class="thanks" tabindex="-1" id="confirm-title">${esc(t("c.title", { name: first }))}</h3>
      <div class="big-id">${esc(order.id)}</div>
      <p><button type="button" class="link-btn" id="copy-id">${esc(t("c.copy"))}</button></p>
      <p class="muted">${where}<br>${esc(t("c.total", { total: rupees(q.total), ready: readyText(q) }))}</p>
      <p class="fine">${esc(t("c.qr"))}</p>
      <div class="actions">
        <a class="btn" href="/secondstitch/track?id=${encodeURIComponent(order.id)}">${esc(t("c.track"))}</a>
        <a class="btn btn-ghost" href="/secondstitch/order">${esc(t("c.another"))}</a>
      </div>
      <p class="contact-line">${esc(t("help.contact"))}</p>
    </div>`;
  $("#copy-id").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(order.id); toast(t("c.copied")); } catch { toast(order.id); }
  });
  $("#confirm-title").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------- Start ----------

function preloadFromUrl() {
  const ids = (new URLSearchParams(location.search).get("add") || "").split(",").map((s) => s.trim()).filter(Boolean);
  const g = state.garments[0];
  ids.forEach((id) => {
    const s = svc(id);
    if (!s || g.jobs.some((j) => j.id === id) || (s.addon && !g.jobs.some((j) => j.id === "button"))) return;
    g.jobs.push({ id, qty: 1 });
  });
}

async function init() {
  await i18n.ready;
  try {
    const [cat, cal] = await Promise.all([api("/secondstitch/api/catalogue"), api("/secondstitch/api/calendar")]);
    C = cat;
    days = cal.days;
  } catch {
    $("#summary").innerHTML = `<h3>${esc(t("sum.title"))}</h3><p class="errors">${esc(t("e.server"))}</p>`;
    return;
  }
  state.date = days[0].date;
  state.counter = C.counters[0].id;
  const fromPicker = new URLSearchParams(location.search).has("add");
  if (fromPicker || !loadDraft()) {
    state.garments.push(newGarment());
    preloadFromUrl();
  }
  showStep(step);
  renderSummary(null);
  renderAll();

  const garments = $("#garments");
  ["click", "change", "input"].forEach((ev) => garments.addEventListener(ev, onGarmentEvent));
  $("#add-garment").addEventListener("click", () => { state.garments.push(newGarment()); renderAll(); });

  $("#order-form").addEventListener("change", (e) => {
    const { name: field, value, id } = e.target;
    if (shownErrors.length) showErrors([]);
    if (field === "tier") { state.tier = value; tierSwitched = false; renderAll(); }
    if (field === "speed") { state.speed = value; scheduleQuote(); }
    if (field === "handover") { state.handover = value; renderHandover(); scheduleQuote(); }
    if (id === "counter") state.counter = value;
    saveDraft();
  });
  $("#order-form").addEventListener("input", (e) => {
    if (e.target.id === "address") state.address = e.target.value;
    if (shownErrors.length) showErrors([]);
    saveDraft();
  });
  $("#order-form").addEventListener("submit", submitOrder);
  $("#next-btn").addEventListener("click", next);
  $("#back-btn").addEventListener("click", () => goTo(step - 1));
  $("#tape-steps").addEventListener("click", (e) => {
    const b = e.target.closest("[data-go]");
    if (b && !b.disabled) goTo(Number(b.dataset.go));
  });

  const pickDate = (e) => {
    const el = e.target.closest("[data-date]");
    if (!el) return;
    state.date = el.dataset.date;
    enforceRules();
    keepFocus(() => { renderSpeed(); renderDates(); });
    scheduleQuote();
    saveDraft();
  };
  $("#date-strip").addEventListener("click", pickDate);
  $("#summary").addEventListener("click", pickDate);

  document.addEventListener("languagechange", () => {
    renderAll();
    renderTape();
    renderSummary(lastQuote);
    showErrors(shownErrors);
  });
}

init();
