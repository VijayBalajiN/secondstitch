// The GitHub Pages copy has no server. This script starts Pyodide (Python in the browser), loads the same
// Python files the local server uses (../static_api.py and friends), and answers every fetch("/api/...")
// from them. Orders and bot chats are saved in this browser (IndexedDB), so each visitor has their own demo.
// Add ?reset-demo to any page address to wipe what this browser saved.
(() => {
  const BASE = new URL(".", document.currentScript.src).pathname.replace(/\/$/, "");
  const MODULES = ["pricing", "orders", "whatsapp", "telegram", "bot", "api", "static_api"];
  const DB = "secondstitch-demo";
  const realFetch = window.fetch.bind(window);

  // ---- saved data ----
  const idb = (mode, fn) => new Promise((resolve, reject) => {
    const open = indexedDB.open(DB, 1);
    open.onupgradeneeded = () => open.result.createObjectStore("kv");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const req = fn(open.result.transaction("kv", mode).objectStore("kv"));
      req.onsuccess = () => { resolve(req.result); open.result.close(); };
      req.onerror = () => reject(req.error);
    };
  });
  const loadSaved = () => idb("readonly", (s) => s.get("data")).catch(() => null);
  const writeSaved = (text) => idb("readwrite", (s) => s.put(text, "data")).catch(() => {});

  // ---- the little "starting" notice ----
  const note = document.createElement("div");
  note.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:100;background:#1f2a44;color:#f3ebda;padding:10px 16px;border-radius:6px;font:500 .9rem system-ui,sans-serif;box-shadow:0 6px 18px rgba(0,0,0,.25);max-width:92vw;text-align:center";
  note.setAttribute("role", "status");
  note.textContent = "Starting the demo… the first visit downloads about 15 MB.";
  const showNote = () => document.body ? document.body.appendChild(note) : document.addEventListener("DOMContentLoaded", () => document.body.appendChild(note));

  // ---- start Pyodide ----
  let handle = null;
  let dump = null;
  const ready = (async () => {
    showNote();
    if (/[?&]reset-demo\b/.test(location.search)) await idb("readwrite", (s) => s.delete("data")).catch(() => {});
    await new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = `${BASE}/pyodide/pyodide.js`;
      s.onload = ok;
      s.onerror = () => fail(new Error("Could not load the Python runtime."));
      document.head.appendChild(s);
    });
    const [py, sources, saved] = await Promise.all([
      loadPyodide({ indexURL: `${BASE}/pyodide/` }),
      Promise.all(MODULES.map((m) => realFetch(`${BASE}/py/${m}.py`).then((r) => r.text()))),
      loadSaved(),
    ]);
    py.FS.mkdirTree("/app");
    py.FS.mkdirTree("/data");
    MODULES.forEach((m, i) => py.FS.writeFile(`/app/${m}.py`, sources[i]));
    if (saved) {
      for (const [rel, b64] of Object.entries(JSON.parse(saved))) {
        const full = `/data/${rel}`;
        py.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
        py.FS.writeFile(full, Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)));
      }
    }
    // Sample orders (from the team's test runs, phone numbers hidden) show up for every visitor, added once if missing.
    try {
      const samples = await realFetch(`${BASE}/sample-orders.json`).then((r) => r.json());
      let mine = {};
      try { mine = JSON.parse(new TextDecoder().decode(py.FS.readFile("/data/orders.json"))); } catch { /* none saved yet */ }
      const seen = (() => { try { return JSON.parse(localStorage.getItem("ss-samples") || "[]"); } catch { return []; } })();
      const fresh = Object.keys(samples).filter((id) => !mine[id] && !seen.includes(id));
      if (fresh.length) {
        fresh.forEach((id) => { mine[id] = samples[id]; });
        py.FS.writeFile("/data/orders.json", JSON.stringify(mine));
        try { localStorage.setItem("ss-samples", JSON.stringify(seen.concat(fresh))); } catch { /* fine */ }
      }
    } catch { /* the demo works without them */ }
    py.runPython("import sys; sys.path.insert(0, '/app'); import static_api");
    handle = py.runPython("static_api.handle");
    dump = py.runPython("static_api.dump");
    note.remove();
  })();
  ready.catch((err) => { note.textContent = `The demo could not start: ${err.message}`; note.style.background = "#a8341f"; });

  // ---- answer /api/ calls ----
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    const at = url.pathname.indexOf("/api/");
    if (url.origin !== location.origin || at < 0 || url.pathname.slice(0, at) !== BASE) return realFetch(input, init);
    await ready;
    const method = (init?.method || (typeof input === "string" ? "GET" : input.method) || "GET").toUpperCase();
    const reply = JSON.parse(handle(method, url.pathname.slice(at), url.search.slice(1), init?.body ? String(init.body) : ""));
    if (method !== "GET") writeSaved(dump());
    return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
  };
})();
