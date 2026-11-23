# SecondStitch WhatsApp bot

The bot is a fourth way into the same order system as the website. It prices orders with
`pricing.py`, places them with `orders.py`, and the ops desk and tracking page see them like any
other order. Every scan on the ops desk sends the customer a status message, whichever channel
they ordered through.

## 1. Try it without Meta (simulator)

```bash
cd website
python3 server.py
```

Open <http://127.0.0.1:8080/bot> and say **hi**. Replies are the exact Cloud API message payloads the
bot would send, drawn the way WhatsApp shows them (buttons, lists, bold text). Nothing leaves your
computer. Record scans on <http://127.0.0.1:8080/ops> and the status messages appear in the chat.

What the bot does:

- **New order**: category → fix → fabric → more fixes or garments → fit mark (for hems,
  sleeves, take-ins) → optional photo → Standard or Premium (forced to Premium for structural work
  or embellished fabric) → speed (Premium only) → counter or home pickup → day (with season
  prices) → itemised summary → confirm.
- **Track**: lists your open orders, or looks up any ID you type.
- **Prices**: popular prices at a glance.
- **Status messages** on every scan, a rework notice on a QC failure, and a 1–5 rating
  request on delivery.
- Type **menu** or **hi** to restart and **cancel** to clear an order in progress.

## 2. Connect Meta's free test number

You do these steps yourself in your browser; they need your Facebook login.

1. Go to <https://developers.facebook.com>, create an app of type **Business**, and add the
   **WhatsApp** product. Meta gives you a test phone number.
2. In **WhatsApp → API Setup**:
   - Copy the **temporary access token** (it expires after about 24 hours; a system-user token
     from Business Settings lasts longer) and the **Phone number ID**.
   - Under **To**, add the phone numbers you will test with and confirm each one with the code
     WhatsApp sends. The test number can only message these numbers.
3. In **App settings → Basic**, copy the **App secret**.
4. Copy `.env.example` to `.env` and fill in `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET`,
   and a random `WA_VERIFY_TOKEN` you make up.
5. Start the server. It prints `WhatsApp: live. Webhook at http://127.0.0.1:8081/webhook`.

## 3. Give Meta a public HTTPS address for the webhook

Meta has to reach the webhook from the internet. Use a tunnel to **port 8081 only**: that port
serves nothing but `/webhook`, so the website, ops desk and simulator on 8080 stay private.

Either tool works (install it yourself from its official site):

```bash
cloudflared tunnel --url http://127.0.0.1:8081
```

```bash
ngrok http 8081
```

Then, in **WhatsApp → Configuration → Webhook**:

1. **Callback URL**: the tunnel's `https://…` address followed by `/webhook`.
2. **Verify token**: the same value as `WA_VERIFY_TOKEN`. Click **Verify and save**.
3. Under **Webhook fields**, subscribe to **messages**.

Send "hi" from one of your verified phones to the test number. The server log shows each reply
it sends, or the Graph API error if one fails.

The free tunnel address changes each time you restart the tunnel; update the callback URL when it does.

## 4. Status messages and the 24-hour rule

WhatsApp lets a business send ordinary messages only within 24 hours of the customer's last
message. The bot follows that:

- Inside the window, a scan sends a normal text (and the rating list on delivery).
- Outside it, for example an order placed on the website by someone who never messaged the bot,
  it sends the template named in `WA_STATUS_TEMPLATE`. Create one in **WhatsApp Manager →
  Message templates**, category **Utility**, with a body that has two parameters, such as
  `SecondStitch update for order {{1}}: {{2}}.` It can only be used once Meta approves it.
- With no template set, the update is skipped and the server log says so.

Business-initiated template messages are charged per message by Meta; replies inside the
24-hour window are free. Check Meta's current pricing for India before going beyond the test number.

## Files

| File | Role |
|---|---|
| `whatsapp.py` | Cloud API transport: message builders with WhatsApp's size limits, sending, media download, webhook (verify handshake, `X-Hub-Signature-256` check, duplicate filtering), simulator outbox |
| `bot.py` | The conversation, session state (`data/bot_sessions.json`) and status messages |
| `orders.py` | The shared order system every channel uses |
| `public/bot.html`, `public/bot.js` | The simulator page |
| `test_bot.py` | Full conversations, limits, status messages, 24-hour rule, templates, webhook security |

## Limits of this demo

- One shared process and JSON files: fine for a pilot with a few users, not for production.
- No payment step; the live service would send a UPI payment link before confirming.
- English only. Indian numbers only (`91` + 10 digits), because orders need an Indian mobile.
- The temporary access token expires; when replies stop, check the server log for a 401 and
  paste a fresh token into `.env`.
