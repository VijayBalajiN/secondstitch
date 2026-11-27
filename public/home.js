// Home page: garment picker, price board and tailor profiles. Prices come from /api/catalogue.

let C = null;
const pick = { garment: 0, spot: 0 };
const $ = (sel) => document.querySelector(sel);
const svc = (id) => C.services.find((s) => s.id === id);
const fromPrice = (s) => s.prices.standard ?? s.prices.premium;

// ---------- Garment picker ----------

function renderTabs() {
  $("#g-tabs").innerHTML = GARMENTS.map((g, i) =>
    `<button type="button" class="tab" data-g="${i}" aria-pressed="${i === pick.garment}">${tb(g.label)}</button>`).join("");
}

function renderStage() {
  const g = GARMENTS[pick.garment];
  const pins = g.spots.map((s, i) => `
    <g class="pin" role="button" tabindex="0" data-s="${i}" aria-pressed="${i === pick.spot}" aria-label="${esc(t("picker.pin", { name: t(s.name), n: i + 1, total: g.spots.length }))}" transform="translate(${s.x} ${s.y})">
      <circle r="24" fill="transparent"/><circle class="halo" r="13"/><circle class="dot" r="12"/><text text-anchor="middle" dy="4">${i + 1}</text>
    </g>`).join("");
  $("#g-stage").innerHTML = `<svg viewBox="0 0 300 400" role="group" aria-label="${esc(t(g.label))}"><image href="/img/${g.photo}.jpg" width="300" height="400" preserveAspectRatio="xMidYMid slice"/>${pins}</svg>`;
}

function renderPanel() {
  const g = GARMENTS[pick.garment];
  const spot = g.spots[pick.spot];
  const rows = spot.services.map((id) => {
    const s = svc(id);
    if (!s) return "";
    const price = t("picker.from", { price: rupees(fromPrice(s)) });
    return `<li>
      <span class="nm">${esc(svcName(id, s.name))}</span>
      <span class="meta">${esc(price)} · ${esc(t("picker.min", { n: s.minutes }))}${s.premium_only ? ` · <span class="pill dark">${esc(t("picker.premium"))}</span>` : ""}</span>
      <a class="btn btn-small go" href="/order?add=${encodeURIComponent(id)}">${esc(t("picker.add"))}</a>
    </li>`;
  }).join("");
  $("#spot-panel").innerHTML = `
    <h3>${esc(t(g.label))} · ${esc(t(spot.name))}</h3>
    <ul class="spot-list">${rows}</ul>
    <p class="fine" style="margin:14px 0 0">${esc(t("picker.notsure"))} <a href="${chatHref}">${esc(chatHref === "/bot" ? t("hero.chat.demo") : t("hero.chat"))}</a></p>`;
}

function renderPicker() {
  renderTabs();
  renderStage();
  renderPanel();
}

$("#g-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest("[data-g]");
  if (!tab) return;
  pick.garment = Number(tab.dataset.g);
  pick.spot = 0;
  renderPicker();
  $("#g-tabs").querySelector(`[data-g="${pick.garment}"]`)?.focus();
});

function choosePin(e) {
  const pin = e.target.closest("[data-s]");
  if (!pin || (e.type === "keydown" && e.key !== "Enter" && e.key !== " ")) return;
  e.preventDefault();
  pick.spot = Number(pin.dataset.s);
  renderStage();
  renderPanel();
  $("#g-stage").querySelector(`[data-s="${pick.spot}"]`)?.focus();
}
$("#g-stage").addEventListener("click", choosePin);
$("#g-stage").addEventListener("keydown", choosePin);

// ---------- Price board ----------

function boardRows(list, both) {
  return `<ul>${list.map((s) => {
    const plus = s.addon ? "+" : "";
    const prices = both
      ? `<b>${plus}${rupees(s.prices.standard)}</b><i>${plus}${rupees(s.prices.premium)}</i>`
      : `<b>${rupees(s.prices.premium)}</b>`;
    return `<li><span class="nm">${svcThumb(s.id)}<span>${esc(svcName(s.id, s.name))} <small>· ${esc(t("board.min", { n: s.minutes }))}</small></span></span><span class="pr">${prices}</span></li>`;
  }).join("")}</ul>`;
}

function renderBoard() {
  const quick = C.services.filter((s) => !s.premium_only);
  const prem = C.services.filter((s) => s.premium_only);
  $("#board-quick").innerHTML = `
    <h3>${tb("board.quick")}</h3><p class="sub">${esc(t("board.quick.sub"))}</p>
    <div class="head"><span>${esc(t("board.standard"))}</span><span>${esc(t("board.premium"))}</span></div>
    ${boardRows(quick, true)}`;
  $("#board-prem").innerHTML = `
    <h3>${tb("board.prem")}</h3><p class="sub">${esc(t("board.prem.sub"))}</p>
    <div class="head"><span>${esc(t("board.premium"))}</span></div>
    ${boardRows(prem, false)}`;
}

// ---------- What we fix: photo cards ----------

const GROUPS = [
  { key: "hem", img: "svc-hem", ids: ["trouser-hem", "jeans-original-hem", "kurta-hem", "salwar-shorten"] },
  { key: "zip", img: "svc-zip", ids: ["fly-zip", "dress-zip", "jacket-zip"] },
  { key: "button", img: "svc-button", ids: ["button", "extra-button"] },
  { key: "saree", img: "svc-saree", ids: ["saree-fall"] },
  { key: "blouse", img: "svc-blouse", ids: ["blouse"] },
  { key: "kurta", img: "svc-kurta", ids: ["kurta-resize", "side-seams"] },
  { key: "blazer", img: "svc-blazer", ids: ["blazer-sleeve", "sleeve-cuff", "shoulder", "lining", "sleeve-shorten"] },
  { key: "fit", img: "svc-fit", ids: ["waist", "taper", "refit"] },
  { key: "new", img: "tapehoop", ids: ["new-pants", "new-kurta"] },
  { key: "mend", img: "svc-mend", ids: ["open-seam", "darn"] },
  { key: "lehenga", img: "svc-lehenga", ids: ["lehenga-waist", "flare", "lace"] },
  { key: "elastic", img: "svc-elastic", ids: ["elastic"] },
];
const CHAT_ICON = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg>';

function renderServices() {
  const cards = GROUPS.map((g) => {
    const found = g.ids.map(svc).filter(Boolean);
    if (!found.length) return "";
    const lowest = Math.min(...found.map(fromPrice));
    return `<a class="svc-card" href="/order?add=${encodeURIComponent(found[0].id)}">
      <img src="/img/${g.img}.jpg" alt="" width="800" height="600" loading="lazy">
      <span class="meta"><b>${esc(t("svc.cat." + g.key))}</b><span class="from">${esc(t("picker.from", { price: rupees(lowest) }))}</span></span>
    </a>`;
  }).join("");
  const other = `<a class="svc-card other" href="${chatHref}">${CHAT_ICON}<b>${esc(t("svc.other.t"))}</b><p>${esc(t("svc.other.p"))}</p></a>`;
  $("#svc-grid").innerHTML = cards + other;
}

// ---------- Tailors ----------

const TAILORS = [
  { n: 1, face: "tailor-1", work: "svc-saree" },
  { n: 2, face: "tailor-2", work: "svc-hem" },
  { n: 3, face: "tailor-3", work: "spec-3" },
];

function renderTailors() {
  $("#tailors-grid").innerHTML = TAILORS.map((a) => `
    <article class="tailor">
      <span class="stamp">${esc(t("tailors.sample"))}</span>
      <img class="spec-img" src="/img/${a.work}.jpg" alt="" width="800" height="600" loading="lazy">
      <img class="avatar" src="/img/${a.face}.jpg" alt="" width="360" height="360" loading="lazy">
      <div class="body">
        <h3>${esc(t(`tailors.t${a.n}.name`))}</h3>
        <p class="where">${esc(t(`tailors.t${a.n}.where`))}</p>
        <dl><dt>${esc(t("tailors.dt.years"))}</dt><dd>${esc(t(`tailors.t${a.n}.years`))}</dd>
            <dt>${esc(t("tailors.dt.spec"))}</dt><dd>${esc(t(`tailors.t${a.n}.spec`))}</dd></dl>
        <p class="quote">“${esc(t(`tailors.t${a.n}.quote`))}”</p>
      </div>
    </article>`).join("");
}

// ---------- Start ----------

let chatHref = "/bot";

function renderAll() {
  if (!C) return;
  renderServices();
  renderPicker();
  renderBoard();
  renderTailors();
}

async function init() {
  await i18n.ready;
  fakeQr($("#hero-qr"), "SS-7K2QD");
  try {
    C = await api("/api/catalogue");
  } catch {
    $("#spot-panel").innerHTML = `<p class="errors">${esc(t("e.server"))}</p>`;
    return;
  }
  try {
    const ch = await api("/api/channels");
    if (ch.telegram) chatHref = `https://t.me/${ch.telegram}`;
  } catch { /* channels are optional */ }
  $("#chat-cta").href = chatHref;
  if (chatHref === "/bot") { const label = $("#chat-cta span"); label.dataset.i18n = "hero.chat.demo"; i18n.apply($("#chat-cta")); }
  renderAll();
}

document.addEventListener("languagechange", renderAll);
init();
