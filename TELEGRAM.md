# SecondStitch Telegram bot

The same order bot as the WhatsApp version (`bot.py`), delivered through Telegram. No Meta or
Facebook account, no tunnel and no webhook: the server asks Telegram for new messages itself.

## Set it up (5 minutes)

1. In Telegram, open **@BotFather** (it has a blue tick) and send `/newbot`.
2. Give it a display name (for example *SecondStitch*) and a username ending in `bot`
   (for example `secondstitch_demo_bot`). BotFather replies with a **token** like
   `123456789:AA...`. Keep it private: anyone with it can control the bot.
3. In the `website` folder, create your settings file and open it:

   ```bash
   cp .env.example .env
   ```
   ```bash
   open -e .env
   ```

   Paste the token after `TELEGRAM_TOKEN=` and save.
4. Start (or restart) the server:

   ```bash
   python3 server.py
   ```

   It prints `Telegram: live as @your_bot. Open https://t.me/your_bot and press Start.`

Open that link on any phone, press **Start**, and order. Send the link to anyone: they don't need
to be on your Wi-Fi. Your laptop must stay on with the server running for the bot to reply.

## What it does

- The same conversation as WhatsApp: category → fix → fabric → fit mark → photo → Standard or
  Premium → speed → counter or pickup → day → summary → confirm. Buttons and lists become tap
  buttons; after a tap the buttons collapse to a ✓ showing the choice.
- Before the first order it asks the customer to tap **Share my phone number**. Telegram sends the
  number of the customer's own account, so it's verified; typed numbers and other people's
  contacts are refused. Orders need an Indian mobile (+91).
- Every scan on `/ops` sends a status message to the chat, at any time (Telegram has no 24-hour
  rule), and a 1–5 rating request on delivery. Website orders placed with a number that a Telegram
  chat has shared also get their updates on Telegram.
- Menu commands: `/start`, `/track`, `/prices`, `/cancel`. Typing *hi*, *menu* or *cancel* works too.
- Group chats are ignored.

## If it doesn't reply

Look at the server window:

| Message | Fix |
|---|---|
| `Telegram: off` | `TELEGRAM_TOKEN` isn't in `website/.env`, or the file isn't saved |
| `Telegram: NOT started (… 401 …)` | The token is wrong. Copy it again from @BotFather (`/mybots` → your bot → API Token) |
| `409 … another copy of the server running` | Two servers are using the same token. Stop one |
| `retrying in …s` | No internet connection; it reconnects by itself |

## Files

| File | Role |
|---|---|
| `telegram.py` | Bot API transport: converts the bot's messages to Telegram, long polling, photo download, phone sharing |
| `bot.py` | The conversation (shared with WhatsApp), sessions and status messages |
| `test_telegram.py` | Full conversations against a fake Bot API server, button limits, phone checks, polling |
