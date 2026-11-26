// Photo credits: one line per picture, read from /credits.json.

async function showCredits() {
  await i18n.ready;
  const list = document.getElementById("credits-list");
  let items = [];
  try {
    items = await (await fetch("/credits.json")).json();
  } catch { list.textContent = t("e.server"); return; }
  list.innerHTML = items.map((c) => `<li>
    <img src="${esc(c.file)}" alt="" loading="lazy" width="84" height="62">
    <span><a href="${esc(c.url)}" rel="noopener">${esc(c.title || "Photo")}</a>
      <small>${esc(t("credits.by", { who: c.creator }))} · ${esc(c.license)}</small></span>
  </li>`).join("");
}
showCredits();
