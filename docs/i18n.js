// Language engine shared by every customer page and, later, the app.
//
// Four modes: "en" (English), "hien" (English with Hindi under headings, the default), "hi" and "ta".
// Texts live in /lang/en.json, /lang/hi.json and /lang/ta.json (flat key -> string, {name} placeholders).
// A missing key falls back to English, then to the key itself.
//
//   <h2 data-i18n="board.title" data-bi>      text, plus the Hindi line under it in "hien" mode
//   <p data-i18n-html="hero.lead">            same, but the string may contain <b>, <br>, <a>
//   <input data-i18n-attr="placeholder:order.name">
//   t("order.total"), t("hero.years", { n: 22 }), tb("board.title")   from scripts
//
// Pages wait for `i18n.ready`, then re-render dynamic parts whenever "languagechange" fires.

const i18n = (() => {
  const MODES = ["hien", "en", "hi", "ta"];
  const LABELS = { en: "English", hien: "EN + हिन्दी", hi: "हिन्दी", ta: "தமிழ்" };
  const HTML_LANG = { en: "en", hien: "en", hi: "hi", ta: "ta" };
  const LOCALE = { en: "en-IN", hien: "en-IN", hi: "hi-IN", ta: "ta-IN" };
  const dicts = {};
  let mode = "hien";

  const read = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
  const write = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } };

  async function load(name) {
    if (dicts[name]) return dicts[name];
    try {
      const res = await fetch(`/secondstitch/lang/${name}.json`);
      dicts[name] = res.ok ? await res.json() : {};
    } catch {
      dicts[name] = {};
    }
    return dicts[name];
  }

  const fill = (s, vars) => (vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : s);
  const source = () => (mode === "hi" ? dicts.hi : mode === "ta" ? dicts.ta : dicts.en) || {};

  function t(key, vars) {
    const s = source()[key] ?? dicts.en?.[key] ?? key;
    return fill(s, vars);
  }

  // Like t, but returns `fallback` when no language has the key (for server-supplied names).
  function tOr(key, fallback, vars) {
    const s = source()[key] ?? dicts.en?.[key];
    return s === undefined ? fallback : fill(s, vars);
  }

  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Heading text; in "hien" mode the Hindi sits on a second line.
  function tb(key, vars) {
    const main = t(key, vars);
    if (mode !== "hien" || !dicts.hi?.[key]) return main;
    return `${main}<span class="hi-sub" lang="hi">${escapeHtml(fill(dicts.hi[key], vars))}</span>`;
  }

  function apply(root = document) {
    document.documentElement.lang = HTML_LANG[mode];
    document.documentElement.dataset.mode = mode;
    root.querySelectorAll("[data-i18n], [data-i18n-html]").forEach((el) => {
      const key = el.dataset.i18n || el.dataset.i18nHtml;
      if (el.hasAttribute("data-bi")) el.innerHTML = tb(key);
      else if (el.dataset.i18nHtml) el.innerHTML = t(key);
      else el.textContent = t(key);
    });
    root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      el.dataset.i18nAttr.split(";").forEach((pair) => {
        const [attr, key] = pair.split(":");
        el.setAttribute(attr.trim(), t(key.trim()));
      });
    });
    const title = document.querySelector("head > title[data-i18n]");
    if (title) document.title = t(title.dataset.i18n);
  }

  async function set(next, { silent, persist = true } = {}) {
    if (!MODES.includes(next)) next = "hien";
    await Promise.all([load("en"), next === "ta" ? load("ta") : load("hi")]);
    mode = next;
    if (persist) write("ss-lang", mode);
    apply();
    if (!silent) document.dispatchEvent(new CustomEvent("languagechange", { detail: mode }));
  }

  // Staff pages (ops desk, bot simulator) set <body data-force-lang="en"> and ignore the saved choice.
  const forced = document.body?.dataset.forceLang;
  const fromUrl = new URLSearchParams(location.search).get("lang");
  const ready = forced
    ? set(forced, { silent: true, persist: false })
    : set(MODES.includes(fromUrl) ? fromUrl : read("ss-lang") || "hien", { silent: true });

  return {
    ready, set, t, tOr, tb, apply, MODES, LABELS,
    get mode() { return mode; },
    get locale() { return LOCALE[mode]; },
    // Rows for the language picker: [value, label]
    options: () => MODES.map((m) => [m, LABELS[m]]),
  };
})();

const t = i18n.t;
const tOr = i18n.tOr;
const tb = i18n.tb;
