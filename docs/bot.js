// Bot simulator: posts chat actions to /api/bot-sim and draws the Cloud API payloads that come back.

const chat = document.getElementById("chat");
const waInput = document.getElementById("sim-wa");
const nameInput = document.getElementById("sim-name");
const sheet = document.getElementById("sheet");
let lastSeq = 0;
let busy = false;
const lists = new Map(); // seq -> list payload, for opening the row sheet

const wa = () => waInput.value.replace(/\D/g, "");

// WhatsApp formatting: *bold*, _italic_, line breaks.
function waFormat(s) {
  return esc(s).replace(/\*([^*\n]+)\*/g, "<b>$1</b>").replace(/(^|\s)_([^_\n]+)_/g, "$1<i>$2</i>").replace(/\n/g, "<br>");
}

const time = (iso) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });

function bubbleIn(e) {
  const m = e.payload;
  let body = "";
  if (m.type === "text") body = waFormat(m.text.body);
  else if (m.type === "interactive") body = esc((m.interactive.button_reply || m.interactive.list_reply).title);
  else if (m.type === "image") body = e.preview ? `<img src="${e.preview}" alt="Photo you sent">` : "📷 Photo";
  return `<div class="msg in"><div class="bubble">${body}<span class="t">${time(e.at)}</span></div></div>`;
}

function bubbleOut(e) {
  const p = e.payload;
  let body = "", extra = "";
  if (p.type === "text") body = waFormat(p.text.body);
  if (p.type === "template") {
    const params = p.template.components[0].parameters.map((x) => x.text);
    body = `<span class="fine">Template “${esc(p.template.name)}”</span><br>${params.map(esc).join(" · ")}`;
  }
  if (p.type === "interactive") {
    const ia = p.interactive;
    body = waFormat(ia.body.text);
    if (ia.type === "button") {
      extra = `<div class="reply-btns">${ia.action.buttons.map((b) =>
        `<button type="button" data-id="${esc(b.reply.id)}" data-title="${esc(b.reply.title)}">${esc(b.reply.title)}</button>`).join("")}</div>`;
    } else {
      lists.set(e.seq, ia);
      extra = `<div class="reply-btns"><button type="button" data-list="${e.seq}">☰ ${esc(ia.action.button)}</button></div>`;
    }
  }
  return `<div class="msg out"><div class="bubble">${body}<span class="t">${time(e.at)}</span></div>${extra}</div>`;
}

function append(entries) {
  const fresh = entries.filter((e) => e.seq > lastSeq);
  if (!fresh.length) return;
  chat.querySelector(".chat-empty")?.remove();
  chat.insertAdjacentHTML("beforeend", fresh.map((e) => (e.dir === "in" ? bubbleIn(e) : bubbleOut(e))).join(""));
  lastSeq = Math.max(...fresh.map((e) => e.seq));
  chat.scrollTop = chat.scrollHeight;
}

function emptyState() {
  chat.innerHTML = `<div class="chat-empty">Say <b>hi</b> to start.</div>`;
}

async function send(message) {
  if (busy) return;
  busy = true;
  try {
    const res = await api("/secondstitch/api/bot-sim/message", { wa: wa(), name: nameInput.value, after: lastSeq, ...message });
    append(res.messages);
  } catch (err) {
    toast(err.message);
  } finally {
    busy = false;
  }
}

async function poll() {
  if (busy || !wa()) return;
  try {
    const res = await api(`/secondstitch/api/bot-sim/outbox?wa=${wa()}&after=${lastSeq}`);
    append(res.messages);
  } catch { /* server restarting; try again next tick */ }
}

function openList(seq) {
  const ia = lists.get(Number(seq));
  document.getElementById("sheet-title").textContent = ia.action.button;
  document.getElementById("sheet-body").innerHTML = ia.action.sections.map((s) => `
    ${s.title ? `<div class="sheet-section">${esc(s.title)}</div>` : ""}
    ${s.rows.map((r) => `<button type="button" class="sheet-row" data-row="${esc(r.id)}" data-title="${esc(r.title)}">
      <strong>${esc(r.title)}</strong>${r.description ? `<small>${esc(r.description)}</small>` : ""}</button>`).join("")}`).join("");
  sheet.hidden = false;
  sheet.querySelector(".sheet-row")?.focus();
}

chat.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-id]");
  if (btn) return send({ kind: "choice", id: btn.dataset.id, title: btn.dataset.title });
  const list = e.target.closest("[data-list]");
  if (list) openList(list.dataset.list);
});

sheet.addEventListener("click", (e) => {
  const row = e.target.closest("[data-row]");
  if (row) {
    sheet.hidden = true;
    send({ kind: "choice", list: true, id: row.dataset.row, title: row.dataset.title });
  } else if (e.target === sheet || e.target.closest("#sheet-close")) {
    sheet.hidden = true;
  }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") sheet.hidden = true; });

document.getElementById("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("sim-text");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  send({ kind: "text", text });
});

document.getElementById("sim-photo").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    send({ kind: "image", image: canvas.toDataURL("image/jpeg", 0.82) });
  } catch {
    toast("Couldn't read that image. Try a JPEG or PNG.");
  }
});

document.getElementById("sim-reset").addEventListener("click", async () => {
  try {
    await api("/secondstitch/api/bot-sim/reset", { wa: wa() });
    lastSeq = 0;
    lists.clear();
    emptyState();
    toast("Chat cleared");
  } catch (err) {
    toast(err.message);
  }
});

waInput.addEventListener("change", () => { lastSeq = 0; lists.clear(); emptyState(); poll(); });

api("/secondstitch/api/bot-sim/info").then((i) => {
  document.getElementById("sim-mode").textContent = i.live
    ? `Live WhatsApp is configured (API ${i.api_version}). This page still stays local: nothing typed here is sent to WhatsApp.`
    : "Simulator only: no WhatsApp credentials are set, so nothing leaves this computer. See WHATSAPP.md to connect Meta's test number.";
}).catch(() => {});

emptyState();
poll();
setInterval(poll, 1500);
