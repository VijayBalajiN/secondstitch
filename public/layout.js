// Page chrome: header (logo, navigation, language picker) and footer, drawn the same on every page.
// A page sets <body data-page="home|order|help|track|ops|bot"> and has <header id="site-header"> and
// <footer id="site-footer"> placeholders. Ops desk and bot pages are staff tools: English only, no picker.

const RUPEE = `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h12M6 9h12M6 4h3a5 5 0 0 1 0 10H6l8 7"/></svg>`;
const LOGO = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="6" fill="#1F2A44"/>
<path d="M7 26 L23.5 7.5" stroke="#F3EBDA" stroke-width="2" stroke-linecap="round"/>
<ellipse cx="24.4" cy="6.6" rx="1.2" ry="2.3" transform="rotate(42 24.4 6.6)" fill="none" stroke="#F3EBDA" stroke-width="1.4"/>
<path d="M25.2 8.6 C30.5 12.5 27 21.5 19 20.8 C13 20.2 11.8 14.6 15.6 13.2" stroke="#C8442F" stroke-width="2" fill="none" stroke-linecap="round" stroke-dasharray="2.4 2.6"/></svg>`;

(() => {
  const page = document.body.dataset.page || "";
  const staff = page === "ops" || page === "bot";
  const header = document.getElementById("site-header");
  const footer = document.getElementById("site-footer");
  if (!header || !footer) return;

  const link = (href, key, text, cls = "", current = false) =>
    `<a href="${href}" class="${cls}" ${current ? 'aria-current="page"' : ""} ${staff ? "" : `data-i18n="${key}"`}>${text}</a>`;

  if (staff) {
    const badge = page === "ops" ? "Ops desk" : "Bot";
    header.className = "site-header";
    header.innerHTML = `<div class="wrap header-row">
      <a class="logo" href="/">${LOGO}SecondStitch <span class="pill dark" style="font-family:var(--sans)">${badge}</span></a>
      <nav class="nav" aria-label="Main">
        <a href="/" class="hide-sm">Customer site</a>
        ${page === "ops" ? '<a href="/bot">Bot</a>' : '<a href="/ops">Ops desk</a>'}
        <a href="/track">Track</a>
      </nav></div>`;
  } else {
    header.className = "site-header";
    header.innerHTML = `<a class="skip-link" href="#main" data-i18n="a11y.skip">Skip to content</a>
      <div class="wrap header-row">
      <a class="logo" href="/">${LOGO}SecondStitch</a>
      <nav class="nav" aria-label="Main">
        ${link("/#how", "nav.how", "How it works", "hide-md")}
        ${link("/#prices", "nav.prices", "Prices", "hide-sm")}
        ${link("/#tailors", "nav.tailors", "Our tailors", "hide-md")}
        ${link("/help", "nav.help", "Help", "hide-md", page === "help")}
        ${link("/track", "nav.track", "Track", "hide-sm", page === "track")}
        <select class="lang" id="lang-select" data-i18n-attr="aria-label:lang.label" aria-label="Language">
          ${i18n.options().map(([v, label]) => `<option value="${v}" lang="${v === "hi" || v === "ta" ? v : "en"}" ${v === i18n.mode ? "selected" : ""}>${label}</option>`).join("")}
        </select>
        ${page === "order" ? "" : `<a href="/order" class="btn btn-small nav-cta">${RUPEE}<span data-i18n="nav.order">Get a price</span></a>`}
      </nav></div>
      <nav class="subnav" aria-label="Sections">
        ${link("/#how", "nav.how", "How it works")}${link("/#prices", "nav.prices", "Prices")}${link("/#tailors", "nav.tailors", "Our tailors")}
        ${link("/help", "nav.help", "Help", "", page === "help")}${link("/track", "nav.track", "Track", "", page === "track")}
      </nav>`;
    document.querySelector("main")?.setAttribute("id", "main");
    const strip = document.createElement("div");
    strip.className = "demo-strip";
    strip.dataset.i18n = "demo.strip";
    strip.textContent = "Student demo. No real pickups, tailors or payments.";
    header.before(strip);
    i18n.ready.then(() => i18n.apply(strip));
    const select = document.getElementById("lang-select");
    select.addEventListener("change", () => i18n.set(select.value));
    i18n.ready.then(() => { select.value = i18n.mode; });
    document.addEventListener("languagechange", () => { select.value = i18n.mode; });
  }

  footer.innerHTML = `<div class="wrap">
    <span ${staff ? "" : 'data-i18n="footer.note"'}>SecondStitch · student project demo (DDR852, Group 1.1.1). Prices are illustrative.</span>
    <nav aria-label="Footer">
      ${staff ? '<a href="/">Home</a><a href="/track">Track an order</a><a href="/bot">Bot</a><a href="/ops">Ops desk</a>'
        : `${link("/", "footer.home", "Home")}${link("/help", "footer.help", "Help")}${link("/track", "footer.track", "Track an order")}${link("/bot", "footer.bot", "Chat bot")}${link("/credits", "footer.credits", "Photo credits")}${link("/ops", "footer.ops", "Ops desk")}`}
    </nav></div>`;
  i18n.ready.then(() => i18n.apply(header)).then(() => i18n.apply(footer));
})();
