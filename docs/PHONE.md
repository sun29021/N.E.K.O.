# Neko on your phone (0.8)

Chat with Neko from anywhere through Telegram, or call her and talk live. Everything still runs on your
PC: the phone is only a remote control and a microphone/speaker.

## What you can do
- **Chat** in Telegram: type, or send **voice notes**. She replies with text, plus a voice note when you
  sent one (`voice_replies`: auto / always / never).
- **Photos**: send a picture with "what is this?" (needs a vision model). Caption it "save" to only keep it.
- **Files** (PDF, Word, ...): "summarize this", "make study notes", or "save". Files are saved on the PC
  in your first writable folder under **From phone**.
- **Control the PC**: "lock my PC", "play Believer on the PC", "open Spotify", "what's the battery?",
  "send me my screen" (asks first), `/status`.
- **Reminders**: "remind me at 6 to call Ammu". When it's due she says it on the PC *and* messages you.
- **Upgrade and teach her**: "upgrade yourself so you can ...", "restart yourself", "undo the last upgrade",
  "publish the update" (PIN), and "learn this" with text, a link or a file captioned "learn this".
- **Alerts**: a long job on the PC (study notes, Claude Code) finished; the PC battery is low.
- **Live calls**: `/call` sends you a private link. Open it, tap **Call** and just talk. She answers
  sentence by sentence with live subtitles; talk over her to interrupt. Bluetooth earbuds and Ray-Ban Meta
  glasses work as the headset (they are just the phone's audio).

## Setting it up (once, about 5 minutes)
1. **Internet on**: Command Center > Settings > tick "Allow internet" > Save settings.
2. **Make your bot** (you do this yourself, in Telegram):
   open **@BotFather** > send `/newbot` > give it a name (e.g. "Sun's Neko") and a username ending in
   `bot` > BotFather replies with a **key** like `123456789:AA...`. Keep it private.
3. **Command Center > Phone**: paste the key in "1. Telegram bot key", tick "Chat with Neko from
   Telegram", click **Save & connect**. Status shows "waiting for pairing".
4. **Pair**: click **Pair my phone**. It shows a code. In Telegram open your new bot and send
   `/pair 123456` (that code, within 10 minutes). She answers "Paired!". From now on she only answers
   this chat.
5. **Approval PIN** (recommended): type 4-8 digits in "3. Approval PIN" > **Set PIN**. High-risk actions
   from the phone (delete, send, pay, shut down...) need it.
6. **Calls** (optional):
   - Install the free **Tailscale** app on the phone and sign in with the same account as this PC.
   - Command Center > Phone > **Turn on calls** (confirm). Then **Send call link to my phone**.
   - Tap the link on the phone, allow the microphone, tap **Call**. Tip: "Add to Home screen" makes it an
     app icon. The link contains your private call key - don't share it.

## Owner and everyday phones (0.10)
- The first phone you pair is the **owner** (approvals, PIN, upgrades, publishing, programs setup, the PC
  link). **Pair an everyday phone** adds day-to-day phones: their risky requests come to the owner's phone.
- **Unpair all** removes the owner and every everyday phone.

## Safety - what protects you
- Only your paired chat is answered; anyone else who finds the bot gets no reply at all. Group chats are
  ignored. Pairing codes work once and expire after 10 minutes.
- Approvals for things you asked from the phone come to the phone as **Approve / Deny** buttons (the PC
  shows the same question; the first answer wins). Typed "yes" or a voice note never approves.
- High-risk actions need the PIN. The PIN message is deleted from the chat; only a scrambled version is
  stored. 5 wrong PINs lock phone approval of high-risk actions for an hour (the PC still works).
- **Forwarded** messages are treated as someone else's words: she reads them but won't act on them
  without asking.
- Telegram: Neko only makes outgoing connections to api.telegram.org - nothing on your PC listens to the
  internet. Your messages pass through Telegram's servers (normal bot chats are not end-to-end encrypted),
  so don't send passwords or bank details.
- Calls: the call page listens on 127.0.0.1 only. Tailscale shares it as https **inside your own
  tailnet** (never the internet, `tailscale serve`, not `funnel`). Each request also needs the call key.
  Turning calls off removes the share. Your other Tailscale shares are not touched.
- The PC's orb stays quiet: phone conversations are not shown or spoken on the PC.

## Turning it off
- Untick "Chat with Neko from Telegram" > Save & connect. **Unpair** forgets the phone.
- **Turn off calls** removes the Tailscale share and stops the call page.
- To make the bot useless forever: in @BotFather send `/revoke` (new key) or `/deletebot`.

## Troubleshooting
- "Couldn't reach Telegram": check the internet; corporate networks sometimes block Telegram.
- Call page says "Can't reach Neko": the PC is off/asleep, or Tailscale isn't connected on the phone.
- "Tailscale refused": HTTPS certificates must be enabled for your tailnet (Tailscale admin console >
  DNS > HTTPS Certificates). Yours already are (your other share uses https).
- Voice notes need voice to be on in Settings (she uses the PC's Whisper to listen).

## Files
- `%LOCALAPPDATA%\NEKO\phone.json` - paired chat, scrambled PIN, call key. Delete it to forget everything.
- `%LOCALAPPDATA%\NEKO\secrets.toml` - the bot key (`telegram_bot_token`), next to your cloud keys.
- Config: `[phone]` in config.toml (`telegram`, `calls`, `call_port` 8791, `call_https_port` 8443,
  `voice_replies`, `notify_long_jobs`, `notify_battery`).
