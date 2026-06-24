# Idea: Telegram Bot for Mobile Session Replies

## What

Send a Telegram message to yourself when a Claude session needs input. Reply in Telegram to inject the response back into the session — no browser, no laptop, no context switch.

## Why it's interesting

The MemBridge dashboard solves the multi-session overview problem on desktop. On mobile it's read-only at best (`http://192.168.0.13:7842` over LAN). If Claude is waiting on a decision while you're away from your desk, you currently have no way to unblock it. A Telegram bot gives you a persistent, low-friction input channel that works from anywhere.

## Architecture

```
Claude Stop/Notification hook
        │
        ▼
MemBridge server (awaiting_input = 1)
        │
        ├─→ Dashboard SSE refresh (existing)
        │
        └─→ Telegram Bot API: sendMessage to your chat ID
                  │  "Session 'alembic/main' is waiting for input"
                  ▼
            You reply in Telegram
                  │
                  ▼
        MemBridge receives via Telegram webhook/poll
                  │
                  ▼
        osascript: tell iTerm2 session <uuid> to write text "<reply>\n"
```

## Components and difficulty

### 1. Telegram Bot setup — trivial
- Create bot via BotFather (`/newbot`) → get token
- Get your personal chat ID (send a message, read it via `getUpdates`)
- Store both in `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- **Effort:** 10 minutes, zero code

### 2. Outbound notification — easy
Add a `_notify_telegram(session_id, message)` call alongside the existing `_notify_stop()` osascript call in `server.py`. One HTTP POST to `api.telegram.org/bot<token>/sendMessage`.

```python
import httpx

def _notify_telegram(session_id: str, project: str, branch: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    short_id = session_id[:8]
    text = f"🔔 *{project}* (`{branch}`) is waiting for input\nID: `{short_id}`"
    httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=5,
    )
```

**Effort:** ~30 lines, 1 hour including testing

### 3. Inbound reply handling — moderate

Two options for receiving messages:

**Option A — Long polling (simpler, no public URL needed):**
Run a background asyncio task in `server.py` that calls `getUpdates` every 2s, parses replies, and routes them. Works on LAN-only machines with no port forwarding.

**Option B — Webhook (cleaner, requires public URL):**
Telegram POSTs to `https://your-domain/api/telegram-webhook`. Requires exposing MemBridge to the internet (ngrok, Tailscale funnel, or a VPS). Not appropriate for LAN-only setup.

**Recommended:** Option A (long polling) since MemBridge is local-first.

**Effort:** ~60 lines, half a day

### 4. Reply injection into iTerm2 — the hard part

This is the same blocker as `session-reply.md`. Once we have the reply text, we need to deliver it to the waiting Claude session:

```applescript
tell application "iTerm2"
  tell session id "<iterm_session_uuid>"
    write text "yes\n"
  end tell
end tell
```

**What works:** `write text` via osascript does inject keystrokes into the iTerm2 session. Claude Code receives it as if typed.

**What's needed:**
- macOS Accessibility permission granted to whoever calls osascript (the launchd agent — this is a known pain point; launchd processes often don't have GUI permissions)
- The session must still be alive and at a prompt (not mid-response)
- The iTerm2 session UUID must be current (tracked in `sessions.iterm_session_uuid`)

**Effort:** 1–2 days including permission debugging. The osascript itself is 5 lines. Getting launchd to have Accessibility permission is the unknown.

**Mitigation:** Fall back to copying the reply to clipboard + sending a push notification to focus the tab — user still has to paste, but the friction is much lower than typing.

### 5. Decision prompt handling — nice to have

When `last_stop_reason = 'notification:permission_prompt'`, we know Claude is showing numbered options. The Telegram message could include the choices inline:

```
⚠️ alembic/main needs a decision:

"Allow bash command rm -rf /tmp/foo?"
1. Yes, allow
2. No, deny
3. Always allow

Reply with 1, 2, or 3
```

Extracting the actual option text requires capturing the notification `message` field from the hook payload and storing it. We already pass `message` through the notification hook but don't persist it. One extra DB column.

**Effort:** ~2 hours once inbound routing works

## Overall difficulty

| Phase | Effort | Blocked on |
|-------|--------|------------|
| Bot setup | Trivial | Nothing |
| Outbound notification | Easy (1h) | Nothing |
| Inbound long polling | Moderate (4h) | Nothing |
| Reply injection | Hard (1–2 days) | launchd Accessibility permission |
| Decision text capture | Easy (2h) | Inbound routing |

Total realistic estimate: **1–2 days** if the Accessibility permission works cleanly, **longer** if it doesn't and we need a fallback path.

## Revisit when

- `session-reply.md` osascript injection is proven to work from launchd context
- Tailscale (or similar) is set up, enabling webhook mode for cleaner inbound handling
- We want a proper mobile companion beyond read-only dashboard access
