# SecondStitch design notes

The look is called **Workroom**: a tailor's bench. Pattern paper, ink, thread, tape. The website uses it
today; the app (customers, tailors, ops and counter staff) should reuse the same tokens, motifs and
language files so the three surfaces feel like one product.

## Why this look

Tailoring sites feel craft-led (navy and stone with photography, a flat-lay of scissors and spools,
line-drawn garments). Alteration services mostly feel like logistics apps. We lean craft: tools are the
decoration, and nothing needs a photo shoot. Gaps we fill that other sites don't: named tailors, a
"tap where it needs fixing" garment picker, fit capture as a visible step, chat-first ordering.

## Tokens (`public/styles.css`, `:root`)

| Token | Value | Use |
|---|---|---|
| `--paper` | `#f3ebda` | Page background, with a faint 28px pattern-paper grid |
| `--card` | `#fbf7ec` | Cards, panels, alternate sections |
| `--ink` | `#1f2a44` | Text, outlines, dark buttons, the Premium card |
| `--thread` | `#c8442f` | Primary action, pins, running stitches (`--thread-ink` `#a8341f` for text on paper) |
| `--tape` | `#f3e3a3` | Tape measure strips, highlights, the chosen option |
| `--line` / `--line-2` | `#d8cbae` / `#c4b48e` | Borders, dotted leaders |
| `--ok`, `--warn` | `#2f7d5a`, `#8a5200` | Success and caution, always with a tinted background |

Type: serif for headings (`Baskerville`, falling back through Georgia), system sans for text. No web fonts
on purpose: nothing is fetched from other sites, and Devanagari and Tamil use the system's own fonts
(`--deva`, `--tamil`). Hindi and Tamil need more line height and no letter-spacing (handled by `html[lang]` rules).

## Motifs

- **Tape-measure ruler** (`.ruler`, header edge, the order step bar): yellow strip, ink ticks.
- **Stitch line** (`.stitch`, button insets, outlines): dashed thread red.
- **Buttons as step numbers**: a circle with an inner ring.
- **Ticket stub** (hero job card): perforated notches; the QR is the garment's tag.
- **Receipt** (order summary): zig-zag edge.
- **Dotted-leader price board**: name .......... price, like a tailor's price board.
- **Pins and chalk lines** on garment drawings; pins are the tap targets.

Corners are small (4–8px), shadows are soft and rare, buttons are "stitched patches" not pills.

## Copy

Customer words, not ops words: "tailor" not "cluster node", "quality check" not "QC bench". One short line
per thing, each promise said once, nothing about how we are organised inside. The full rules, with what
other alteration sites write, are in `../app/COPY.md`; the website was rewritten to the same rules on
2026-11-23 (the app and the site now share the same wording). Prices are never hidden. No invented
reviews, ratings or customer counts: tailor profiles are labelled **Sample profile** until real ones exist.
Service names (`svc.*`) must match the names the server sends, so change them in `pricing.py` and the
language files together.

## Languages

Four modes, saved in `localStorage` as `ss-lang`, picked in the header:

| Mode | What it shows |
|---|---|
| `hien` (default) | English, with the Hindi underneath every heading marked `data-bi` |
| `en` | English only |
| `hi` | Hindi |
| `ta` | Tamil |

Texts live in `public/lang/{en,hi,ta}.json` (flat `key: text`, `{name}` placeholders). `i18n.js` loads them,
`t("key")` and `tb("key")` read them, `data-i18n="key"` fills HTML. A missing key falls back to English.
`test_i18n.py` fails if a page uses a key that's missing, a placeholder differs, or Hindi/Tamil texts aren't
in their script. The Hindi and Tamil were written by Claude and should be reviewed by native speakers:
send them the two JSON files.

To add a language: copy `en.json`, translate the values, add the mode to `i18n.js` (`MODES`, `LABELS`,
`HTML_LANG`, `LOCALE`) and a font stack to `styles.css`.

Not translated yet: the ops desk (staff, English by design), the chat bots' messages, and error text the
server itself sends (such as "Choose Standard or Premium.").

## What the app can reuse

- The same JSON API: `/api/catalogue`, `/api/calendar`, `/api/quote`, `/api/orders`, `/api/orders/<id>`,
  `/api/channels`, and for staff `/api/ops/orders` and `/api/ops/orders/<id>/scan|qc-fail`
  (the ops routes need the `X-Ops-Pin` header from other devices). The tailor screens use
  `/api/ops/jobs` (queue and earnings, no customer details) and `POST /api/ops/orders/<id>/tailor-done`.
- The same language files (`/lang/*.json`) and service ids (`svc.<id>`).
- Garment drawings and pin positions in `public/garments.js` (the picker).
- The Android app in `../app` does all this (see `app/README.md`). Audiences: **customers** (order, track, rate), **tailors** (job cards, scan QR, mark done,
  earnings) and **ops and counter staff** (scan stations, QC pass or fail).

## Review fixes (2026-11-23)

Six reviewers (usability, interaction, accessibility, visual and mobile, content and language, "is it human")
went through the site. What changed:

- **Order page:** Back, Next and Place order show only on their steps (`[hidden]` now wins over `.btn`); Enter in
  a text field means "next"; the order survives a reload (`sessionStorage` `ss-order-draft`); keyboard focus
  stays on the control you used when a part is redrawn; errors name the field (`aria-invalid`, focus moves
  to it) and follow a language change; step 2 has two labelled questions with prices; a sticky "Total" bar
  on phones; the photo button works with the keyboard.
- **Track page:** Cancel and rating act on the order on screen, not the text in the box.
- **Everywhere:** skip link, a darker focus ring, stronger input borders and `--ok`, bigger tap targets, a
  demo strip above the header, wrapping section links on phones, "Chat demo" and "Staff login" in the footer.
- **Wording:** "Price first" instead of "Fixed price" (the total does change with fabric, day and pickup), a
  thank-you with the customer's name on the confirmation, a copy-order-number button, a "message us" line on
  Help, the confirmation and tracking (no phone number yet: add one in `help.contact` when there is a real one),
  one line in each sample tailor's voice, human error messages, no "Rework", "Tmrw", "top-up" or "tailor share".

Not done: self-hosted Hindi and Tamil fonts (they use system fonts), asking for name and phone earlier in the
order, surnames or shop names for the sample tailors, a real contact number.


## Photos and copy pass (2026-11-27)

- **Photos.** 29 real photos live in `public/img/`, found through the Openverse API (CC0, public domain, CC BY, CC BY-SA only; no NC or ND). Every one is listed in `public/credits.json` with creator, licence and source link, and `/credits` shows them. If you add or swap a photo, add its line there too. Tailor portraits are crops of photos of tailors at work; the names and quotes are made up and the cards keep the "Sample profile" stamp.
- **Home page.** The hero has the tools photo as a full-width background and a three-photo collage; the order-ticket card sits on top, unchanged. "What we fix" is a grid of 11 photo cards (price from the live catalogue) plus a "send a photo" card. "How it works" is a timeline of four icon nodes on a stitched line, each with a photo. Tailor cards show a speciality photo and a round portrait. Price board rows and order job rows have a small photo (`SVC_IMG` in `common.js`).
- **Rupee icon.** The "Get a price" buttons carry a ₹ icon; on phones the header copy is hidden (the hero has one).
- **Copy.** Headlines that read like slogans or questions were rewritten in a plainer voice (see `lang/en.json`; Hindi and Tamil follow). Voice references: two clean samples from the writing-scaffold archive (casual, specific, deadpan) and claudish's rule of short sentences and everyday words. The archive is mostly meme and forum text, so it was used as a voice guide, not copied line by line.
- **Static build.** `static/build.py` now also rewrites `/img/` and `/credits` paths.
