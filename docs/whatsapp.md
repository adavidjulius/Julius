# Julius WhatsApp Personal Agent — Full Documentation

## 1. Overview

Julius WhatsApp is a production-grade personal assistant integration operating directly inside Julius. It connects to the official WhatsApp Web application via persistent browser automation (Chromium / Playwright) using your own WhatsApp account — without paid third-party gateways, Twilio fees, or reverse-engineered protocol libraries.

### Key Capabilities
- **Official WhatsApp Web Interface**: Native browser session indistinguishable from manual web access.
- **QR-Code Linking**: Link once via phone; persistent session survives server restarts.
- **Strict Allowlist Policy**: Default is **ALL CHATS = DENY**. Julius will never read or respond to unknown chats.
- **Four Chat Modes**: `off`, `training`, `approval`, `auto`.
- **Personalized Writing Style**: Learns your greeting habits, emoji frequency, message lengths, vocabulary, and formality.
- **Safety Gate**: Automatically escalates sensitive topics (financial, legal, medical, commitments) to human approval even in auto mode.
- **24/7 Watchdog**: Continuous health monitoring, unresponsiveness detection, and bounded exponential backoff crash recovery.
- **Full TUI & Web Management**: Interactive `/whatsapp` commands in the TUI plus complete REST APIs.

---

## 2. Architecture

```
                                  ┌────────────────────────┐
                                  │      Julius Server      │
                                  │     (julius_gui.py)     │
                                  └───────────┬────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     │              WhatsAppService                    │
                     │         (integrations/whatsapp/)                │
                     └──────┬────────────┬─────────────┬───────────────┘
                            │            │             │
              ┌─────────────▼─┐   ┌──────▼──────┐   ┌──▼────────────┐
              │  Browser      │   │   Policy    │   │ Approval      │
              │  Adapter      │   │   Engine    │   │ Queue         │
              │  (Playwright) │   │ (Allowlist) │   │ (Human gate)  │
              └──────┬────────┘   └─────────────┘   └───────────────┘
                     │
              ┌──────▼────────┐   ┌─────────────┐   ┌───────────────┐
              │ WhatsApp Web  │   │  Persona &  │   │ 24/7 Watchdog │
              │ (Chromium     │   │  Training   │   │ (Auto-heal &  │
              │  Profile)     │   │  Engine     │   │  backoff)     │
              └───────────────┘   └─────────────┘   └───────────────┘
```

### Profile Isolation
WhatsApp runs in a dedicated browser profile located at:
`~/.julius/whatsapp_profile/` (permissions set to `0700`).
This is completely isolated from other Julius browser tasks to ensure credential integrity.

---

## 3. Getting Started & First-Time Login

### Step 1: Configure Environment
In your `.env` file:
```env
WHATSAPP_ENABLED=true
WHATSAPP_DEFAULT_MODE=approval
WHATSAPP_AUTO_START=false
WHATSAPP_HEADLESS=true
```

### Step 2: Start Julius Server
```bash
./scripts/julius-server.sh start
```

### Step 3: Connect and Scan QR Code
From the TUI or terminal:
```bash
./scripts/julius-whatsapp.sh connect
```
Or inside Julius TUI:
```
/whatsapp connect
```

Open WhatsApp on your phone:
1. Tap **Settings** -> **Linked Devices**.
2. Tap **Link a Device**.
3. Scan the QR code displayed in the Julius Web Portal (`http://localhost:8080/api/whatsapp/qr`) or interactive portal.

Once authenticated, the session state is saved to disk and survives subsequent restarts.

---

## 4. Chat Allowlist & Policies

Julius follows a strict security policy: **Default DENY**. No messages from unconfigured chats are processed.

### Adding a Chat to the Allowlist
In TUI:
```
/whatsapp add "John Doe" approval
/whatsapp add "Team Project Group" auto
```

Via REST API:
```bash
curl -X POST http://127.0.0.1:8080/api/whatsapp/chats \
  -H "Content-Type: application/json" \
  -d '{"chat_name": "John Doe", "mode": "approval"}'
```

### Operating Modes per Chat
1. **OFF (`off`)**: Chat is ignored.
2. **TRAINING (`training`)**: Predicts what Julius would reply and shows it to you, but never sends. Learns from your actual replies.
3. **APPROVAL (`approval`)**: Drafts responses and holds them in the Approval Queue for human review.
4. **AUTO (`auto`)**: Automatically replies with natural typing delays, subject to the Safety Gate.

### Group Chat Triggers
For group chats, specify when Julius should activate:
- `when_mentioned`: Only responds when your name or `@Julius` is tagged.
- `when_replying_to_me`: Only responds when a message quotes or replies to you.
- `every_relevant`: Analyzes every message in the group.
- `never`: Lurk only.

---

## 5. Human Approval Mode

In `approval` mode (or whenever auto-mode escalates a sensitive message):
1. An incoming message arrives.
2. Julius constructs context (recent conversation + facts + persona).
3. The LLM generates a candidate draft.
4. The draft is placed into the **Approval Queue**.
5. You receive a notification via WebSocket / TUI.

### Reviewing & Sending Approvals
In TUI:
```
/whatsapp approvals
/whatsapp approve <id>
/whatsapp approve <id> "Sure, let me check and get back to you by 3 PM"
/whatsapp reject <id>
```

---

## 6. Training & Style Personalization

Julius adapts to your authentic communication style across multiple dimensions:
- **Tone**: Casual vs. Neutral vs. Formal
- **Formality**: Low, Medium, High
- **Average Length**: Word counts matched to your typical replies
- **Emoji Habits**: Frequency and placement (e.g. at end of sentence vs inline)
- **Punctuation & Capitalization**: Preserves informal lowercase or standard casing
- **Avoid Patterns**: Automatically filters out corporate filler ("I hope this email finds you well", "Certainly!", "As an AI...").

### Inspecting Style Profile
```
/whatsapp persona
/whatsapp training
```

---

## 7. Safety Gate

The Safety Gate intercepts messages that could carry real-world consequence:
- **Financial**: Payments, transfers, UPI, credit cards, loans, cryptocurrency.
- **Commitments**: Legal guarantees, booking confirmations, deadlines, signing documents.
- **Medical & Legal**: Diagnoses, medications, legal advice, lawsuits.
- **Sensitive**: Passwords, secrets, personal relationship crises.

Whenever a pattern matches, auto-send is blocked and the message is escalated to **Human Approval**.

---

## 8. Emergency Stop & Controls

To immediately pause or cancel all WhatsApp assistant actions:
- **TUI**:
  ```
  /whatsapp pause
  /whatsapp resume
  /whatsapp stop
  ```
- **CLI**:
  ```bash
  ./scripts/julius-whatsapp.sh stop
  ```
Emergency stop pauses the message router, halts outgoing typing, and clears all pending approvals.

---

## 9. 24/7 Watchdog & Self-Healing

The `WhatsAppWatchdog` runs continuously in the background:
1. Pings the browser page every 20 seconds.
2. Detects session expiration or QR re-prompts.
3. Automatically triggers browser restart with bounded exponential backoff:
   `2s -> 5s -> 10s -> 30s -> 60s -> 120s -> 300s`.
4. Restores listener and active monitored chats without manual intervention.

---

## 10. API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/whatsapp/status` | `GET` | Health, connection, active chats, uptime |
| `/api/whatsapp/qr` | `GET` | Base64 QR code image |
| `/api/whatsapp/connect` | `POST` | Start browser and session |
| `/api/whatsapp/disconnect` | `POST` | Disconnect browser |
| `/api/whatsapp/pause` | `POST` | Pause auto-sending |
| `/api/whatsapp/resume` | `POST` | Resume auto-sending |
| `/api/whatsapp/stop` | `POST` | Emergency stop |
| `/api/whatsapp/chats` | `GET` | List allowlist chats |
| `/api/whatsapp/chats` | `POST` | Add/update chat policy |
| `/api/whatsapp/chats/{chat_name}` | `DELETE` | Remove chat from allowlist |
| `/api/whatsapp/approvals` | `GET` | List pending approval queue items |
| `/api/whatsapp/approvals/{id}/send` | `POST` | Approve and send draft |
| `/api/whatsapp/approvals/{id}/edit` | `POST` | Edit draft and send |
| `/api/whatsapp/approvals/{id}/reject` | `POST` | Reject draft |
| `/api/whatsapp/training` | `GET` | Training statistics |
| `/api/whatsapp/persona` | `GET` / `POST` | View or update style profile |
| `/api/whatsapp/audit` | `GET` | View action audit trail |
