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
  $("#g-stage").innerHTML = `<svg viewBox="0 0 300 370" role="group" aria-label="${esc(t(g.label))}">${g.art}${pins}</svg>`;
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
    return `<li><span class="nm">${esc(svcName(s.id, s.name))} <small>· ${esc(t("board.min", { n: s.minutes }))}</small></span><span class="dots"></span><span class="pr">${prices}</span></li>`;
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

// ---------- Tailors ----------

const TAILORS = [
  { n: 1, skin: "#c98b5e", hair: "#2b211c", top: "#c8442f", bun: true },
  { n: 2, skin: "#b87a52", hair: "#241c18", top: "#3b5b8c", specs: true, beard: true },
  { n: 3, skin: "#d69a6e", hair: "#8a8a8a", top: "#2f7d5a", bun: true, bindi: true },
];

function avatar(a) {
  return `<svg viewBox="0 0 84 84" aria-hidden="true">
    <path d="M8 84 C8 62 27 56 42 56 S76 62 76 84Z" fill="${a.top}"/>
    <path d="M31 58 L36 84 M53 58 L48 84" stroke="#f3e3a3" stroke-width="6" fill="none"/>
    <path d="M31 58 L36 84 M53 58 L48 84" stroke="#1f2a44" stroke-width="1" stroke-dasharray="1.2 3" fill="none"/>
    <rect x="37" y="46" width="10" height="14" rx="4" fill="${a.skin}"/>
    ${a.bun ? `<circle cx="42" cy="15" r="7" fill="${a.hair}"/>` : ""}
    <circle cx="42" cy="35" r="16" fill="${a.skin}"/>
    <path d="M26 36 Q25 17 42 17 Q59 17 58 36 Q55 25 42 25 Q29 25 26 36Z" fill="${a.hair}"/>
    ${a.beard ? `<path d="M30 40 Q42 62 54 40 Q42 50 30 40Z" fill="${a.hair}"/>` : ""}
    ${a.specs ? `<g fill="none" stroke="#1f2a44" stroke-width="1.6"><circle cx="35" cy="35" r="5"/><circle cx="49" cy="35" r="5"/><path d="M40 35h4"/></g>` : ""}
    ${a.bindi ? `<circle cx="42" cy="27" r="1.7" fill="#c8442f"/>` : ""}
  </svg>`;
}

function renderTailors() {
  $("#tailors-grid").innerHTML = TAILORS.map((a) => `
    <article class="tailor">
      <span class="stamp">${esc(t("tailors.sample"))}</span>
      ${avatar(a)}
      <h3>${esc(t(`tailors.t${a.n}.name`))}</h3>
      <p class="where">${esc(t(`tailors.t${a.n}.where`))}</p>
      <dl><dt>${esc(t("tailors.dt.years"))}</dt><dd>${esc(t(`tailors.t${a.n}.years`))}</dd>
          <dt>${esc(t("tailors.dt.spec"))}</dt><dd>${esc(t(`tailors.t${a.n}.spec`))}</dd></dl>
      <p class="quote">“${esc(t(`tailors.t${a.n}.quote`))}”</p>
    </article>`).join("");
}

// ---------- Start ----------

let chatHref = "/bot";

function renderAll() {
  if (!C) return;
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
  if (chatHref === "/bot") { $("#chat-cta").dataset.i18n = "hero.chat.demo"; i18n.apply($("#chat-cta").parentElement); }
  renderAll();
}

document.addEventListener("languagechange", renderAll);
init();
