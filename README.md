# SecondStitch website (local demo)

Customer site, order tracking, an ops desk and a WhatsApp bot for the SecondStitch operating plan.
Prices follow *SecondStitch — Services & Pricing*.

## Run

```bash
cd website
python3 server.py
```

Open <http://127.0.0.1:8080>. Python 3.9+ only, no packages to install. Stop with Ctrl+C.
Use another port with `PORT=9000 python3 server.py`.

| Page | What it does |
|---|---|
| `/` | Garment picker ("where does it need fixing?"), how it works, price board, tailors, FAQ |
| `/order` | Four-step order builder with a live itemised quote; `/order?add=trouser-hem` starts with a fix chosen |
| `/help` | How to mark your fit, fees and policies, questions |
| `/track` | Status timeline, order details and price; cancel before pickup, rate after delivery |
| `/ops` | Record QR scans (moves an order to its next status) and log QC failures |
| `/bot` | WhatsApp bot simulator; see [WHATSAPP.md](WHATSAPP.md) to connect Meta's test number |

The site speaks English, English with Hindi headings (the default), Hindi and Tamil: pick one in the header.
The look and the language system are described in [DESIGN.md](DESIGN.md).

The same bot also runs on Telegram with one token and no Meta account: see [TELEGRAM.md](TELEGRAM.md).

## Share it on your Wi-Fi

```bash
python3 server.py --lan
```

The server prints an address such as `http://10.184.59.207:8080`. Anyone on the same Wi-Fi or
hotspot can open it on their phone or laptop.

- The ops desk asks other devices for the PIN printed at start (set your own with
  `OPS_PIN=1234 python3 server.py --lan`). This computer needs none.
- The customer site, tracking page and bot simulator have no login. Anyone on the network can
  place orders, and anyone who types a number into the simulator sees that number's chat.
  Share it only on a network you trust, and stop it with Ctrl+C when the demo is over.
- If other devices can't connect, the Wi-Fi probably keeps devices apart (common on campus and
  café networks). Turn on your phone's hotspot, join it with this computer and the guests, and
  restart the server so it prints the new address.
- If macOS asks whether python3 may accept incoming connections, click **Allow**.

## Share it with someone who isn't nearby

A tunnel gives the site a temporary public `https://` address. Cloudflare's quick tunnel needs no
account. Install it once, keep the server running (no `--lan` needed), and in a second terminal run:

```bash
brew install cloudflared
cloudflared tunnel --url http://127.0.0.1:8080
```

It prints an address ending in `trycloudflare.com`. Send that to your friend. Visitors through the
tunnel need the ops desk PIN, like Wi-Fi visitors. Anyone who has the link can open the site, so
share it privately and press Ctrl+C in the tunnel window when you're done; the address stops working
and a new one is made next time.

## How it is built

- `pricing.py` is the single pricing engine: catalogue, garment and season factors, Express,
  minimum order, handover fees, and the tailor's share. The browser always asks the server for prices.
- `orders.py` is the order system every channel shares. Orders are saved in `data/orders.json`,
  photos in `data/uploads/`. Each scan notifies listeners; the WhatsApp bot is one.
- `server.py` serves `public/` and a JSON API (`/api/catalogue`, `/api/calendar`, `/api/quote`,
  `/api/orders`, `/api/channels`, `/api/ops/orders`, `/api/bot-sim/…`).
- `public/` is plain HTML, CSS and JavaScript, no build step. `layout.js` draws the header and footer,
  `i18n.js` and `lang/*.json` hold the translations, `garments.js` the garment drawings.
- `bot.py` is the chat bot; `whatsapp.py` and `telegram.py` carry it over WhatsApp's Cloud API and Telegram's Bot API.
- The server listens on 127.0.0.1 unless you pass `--lan`. Don't put port 8080 on the internet:
  the live WhatsApp webhook runs on its own port (8081, always on 127.0.0.1) so a tunnel exposes
  only `/webhook`.
- No payment is taken.

## Change things

- Prices, fees, counters and the season calendar are constants at the top of `pricing.py`.
  The festival and wedding dates there are illustrative.
- Words on the site are in `public/lang/en.json`, `hi.json` and `ta.json`. Edit a value and reload.
- To reset the demo, stop the server and delete the `data/` folder.

## Tests

```bash
python3 -m unittest test_pricing.py test_bot.py test_telegram.py test_i18n.py
```

`test_pricing.py` checks all 27 catalogue prices and the four worked examples from the Pricing doc.
`test_bot.py` runs whole WhatsApp conversations and checks message limits, status messages,
the 24-hour rule, templates and webhook security. `test_i18n.py` checks that every text the pages use
exists in all three language files. Tests use a temporary data folder.

## Live demo (GitHub Pages)

https://vijaybalajin.github.io/secondstitch/

GitHub Pages only hosts files, so there is no Python server there. The pages are the same as in `public/`, but
the API runs inside the browser: [Pyodide](https://pyodide.org) (Python compiled to WebAssembly, copied into
`static/pyodide/`) loads the same `pricing.py`, `orders.py`, `bot.py` and `api.py` that the local server uses, and
`static/static-api.js` answers every `/api/` request from them. Each visitor gets a private demo: orders, the ops
desk and the bot simulator work on data saved in that browser (IndexedDB). Add `?reset-demo` to any address to
clear it. The first visit downloads about 15 MB (the Python runtime); after that the browser keeps it.

To update the live site after changing anything here:

```bash
python3 static/build.py          # rewrites docs/ (same pages, "/secondstitch" in every path)
git add -A && git commit -m "Update site" && git push
```

`python3 static/build.py ./out /other-path` builds for a different address. WhatsApp and Telegram are not
connected in the browser copy (they need a server); the bot simulator works.

