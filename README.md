# custom-xAI-mllm

Transparent WebSocket proxy between [Agora Conversational AI](https://docs.agora.io/en/conversational-ai/models/mllm/xai) and the [xAI Grok Voice Agent API](https://docs.x.ai/developers/model-capabilities/audio/voice-agent).

## Docs

- [prd.md](./prd.md) — product requirements
- [spec.md](./spec.md) — implementation spec
- [debate-architcture.md](./debate-architcture.md) — debate demo architecture (consumer app)

---

## Setup (one time)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```env
XAI_API_KEY=xai-your-key-here
# Shared with Next.js — HMAC per-debate auth (empty = auth disabled for quick local dev)
PROXY_MASTER_SECRET=
```

Set `PROXY_MASTER_SECRET` locally to test secured flows (same value as the debate app). Leave empty only when you want auth disabled. Vendor keys stay in this proxy only — not in the debate app.

> **Port:** Default is **8081** (8080 is often taken by Docker on macOS).

---

## Run the server locally

**Terminal 1** — start the proxy:

```bash
source .venv/bin/activate
uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload
```

Verify:

```bash
curl http://localhost:8081/health
# {"status":"ok","version":"0.1.0","active_sessions":0}
```

Smoke test (direct xAI):

```bash
python scripts/smoke_xai.py
```

Smoke test (through proxy):

```bash
python scripts/smoke_xai.py --via-proxy --port 8081
```

### Run all tests from one script

```bash
python scripts/run_tests.py              # list every test + how to run it
python scripts/run_tests.py unit         # pytest (79 tests, no server)
python scripts/run_tests.py smoke-llm    # cascade LLM smoke
python scripts/run_tests.py all-smoke    # health + proxy smokes (server must be up)
```

---

## Expose via ngrok (for Agora testing)

Agora connects **outbound** to your proxy — it cannot reach `localhost`. Use ngrok to get a public URL.

**Terminal 2** — while the proxy is running on 8081:

```bash
ngrok http 8081
```

Copy the **HTTPS** forwarding URL from the ngrok output, e.g.:

```
https://sensationally-unpeppered-eleanor.ngrok-free.dev
```

Your Agora WebSocket URL is:

```
wss://sensationally-unpeppered-eleanor.ngrok-free.dev/realtime?debate_session_id=YOUR-ROOM-ID&side=pro
```

Use `side=con` for the con agent. Pass your debate app's existing room/session ID as `debate_session_id`.

Verify through ngrok:

```bash
curl https://sensationally-unpeppered-eleanor.ngrok-free.dev/health
```

### Debate app config

In the debate app (separate repo), set only `mllm.url` — keep `vendor: "xai"`:

```json
{
  "mllm": {
    "enable": true,
    "vendor": "xai",
    "url": "wss://YOUR-NGROK-SUBDOMAIN.ngrok-free.dev/realtime?debate_session_id=YOUR-ROOM-ID&side=pro",
    "api_key": "any-placeholder",
    "output_modalities": ["audio", "text"],
    "params": {
      "voice": "eve",
      "language": "en",
      "sample_rate": 24000
    },
    "turn_detection": {
      "mode": "server_vad",
      "server_vad_config": {
        "threshold": 0.5,
        "prefix_padding_ms": 640,
        "silence_duration_ms": 900
      }
    },
    "greeting_message": "Hello, let's begin."
  }
}
```

When the agent connects, proxy logs should show:

```
session.created
session.upstream_connected
ws.message ...
```

---

## Live context injection (`/inject`)

Debate app pushes sanitized tweets to each agent via HTTP side-channel (not through the voice WebSocket).

**1. Discover proxy session IDs for your room:**

With `PROXY_MASTER_SECRET` set (recommended), use the demo script — it sends the session HMAC automatically:

```bash
python scripts/check_demo.py sessions --debate-session-id YOUR-ROOM-ID
```

Without auth (`PROXY_MASTER_SECRET` empty), raw curl also works:

```bash
curl "http://localhost:8081/sessions?debate_session_id=YOUR-ROOM-ID"
```

**2. Inject pro/con buffers separately:**

```bash
curl -X POST "http://localhost:8081/inject/PROXY-SESSION-UUID" \
  -H "Content-Type: application/json" \
  -d '{"text": "[LIVE X - PRO] @user: tweet...", "trigger_response": false}'
```

Use `trigger_response: false` for silent inject (agent not interrupted; context applies on next turn).

| Field | Purpose |
|-------|---------|
| `debate_session_id` | Your debate room ID (in Agora `mllm.url`) |
| `side` | `pro` or `con` |
| `session_id` | Proxy UUID from `GET /sessions` — used in inject URL |

See [spec.md](./spec.md) §6.3 for full inject contract.

---

## Live demo — monitor sessions and KB

Use this while a debate is running to show **active pro/con WebSocket sessions** and **how many live-X points are in memory** (KB). The script reads `PROXY_MASTER_SECRET` from your `.env` and derives the session HMAC automatically — no manual Bearer token.

**Prerequisites**

- Proxy running (`uvicorn` on 8081)
- `PROXY_MASTER_SECRET` set in `.env` (same value as the debate app)
- Debate id from the Agora channel name: `debate-{8-char-id}` (e.g. `debate-4383d7ca`)

**Terminal 3** — set your debate id once per demo (copy from debate app URL or proxy logs):

```bash
cd /path/to/custom-xAI-mllm
source .venv/bin/activate
export DEBATE_ID=debate-4383d7ca   # <-- change to your live session
```

### List active proxy sessions (pro + con UUIDs)

Shows each side's proxy `session_id` (used for MLLM `/inject/{session_id}`), upstream connection status, and provider:

```bash
python scripts/check_demo.py sessions --debate-session-id $DEBATE_ID
```

Example output:

```
GET /sessions?debate_session_id=debate-4383d7ca -> 200

=== Sessions for debate-4383d7ca ===
  active: 2 (pro=1, con=1)
  pro: session_id=8f2a... upstream=True provider=xai
  con: session_id=c41b... upstream=True provider=xai
```

Full JSON:

```bash
python scripts/check_demo.py sessions --debate-session-id $DEBATE_ID --json
```

### Inspect KB — ingested live-X points (one shot)

**LLM / cascade mode** stores tweets via `POST /kb/ingest`. This shows how many pro/con points are in memory and the latest text on each side:

```bash
python scripts/check_demo.py kb --debate-session-id $DEBATE_ID
```

Example output:

```
GET /kb?debate_session_id=debate-4383d7ca -> 200

=== KB for debate-4383d7ca ===
  pro points: 7
  con points: 7
  latest pro [tweet-123]: E20 fuel prices are...
  latest con [tweet-456]: Actually subsidies...
```

Full JSON (all points, newest first per side):

```bash
python scripts/check_demo.py kb --debate-session-id $DEBATE_ID --json
```

### All KB details — every pro and con point

Use this when you want the **full list** of ingested tweets for both sides (`id`, `text`, `ingested_at` for each point):

```bash
python scripts/inspect_kb.py --debate-session-id $DEBATE_ID
```

Same data via `check_demo.py`:

```bash
python scripts/check_demo.py kb --debate-session-id $DEBATE_ID --json
```

Example output (`inspect_kb.py`):

```json
{
  "debate_session_id": "debate-4383d7ca",
  "pro": [
    { "id": "tweet-123", "text": "E20 fuel prices are...", "ingested_at": "2026-06-14T12:00:00+00:00" },
    { "id": "tweet-122", "text": "...", "ingested_at": "2026-06-14T11:58:00+00:00" }
  ],
  "con": [
    { "id": "tweet-456", "text": "Actually subsidies...", "ingested_at": "2026-06-14T12:01:00+00:00" }
  ]
}
```

| Goal | Command |
|------|---------|
| Summary only (counts + latest) | `check_demo.py kb` |
| **All pro + con points** | `inspect_kb.py` or `check_demo.py kb --json` |
| Poll summary every 5s | `check_demo.py kb --watch 5` |

### Watch KB every 5 seconds (best for live demo)

Polls KB while the debate runs. Press `Ctrl+C` to stop.

```bash
python scripts/check_demo.py kb --debate-session-id $DEBATE_ID --watch 5
```

### Watch sessions + KB together every 5 seconds

```bash
python scripts/check_demo.py watch --debate-session-id $DEBATE_ID --interval 5
```

### One-liner without `export` (paste debate id directly)

```bash
python scripts/check_demo.py kb --debate-session-id debate-4383d7ca --watch 5
```

### What each id means

| Value | Where it comes from | Used for |
|-------|---------------------|----------|
| `debate_session_id` | Agora channel / debate app (`debate-xxxx`) | KB ingest, session list, HMAC session token |
| `session_id` (pro) | `GET /sessions` → `side=pro` | MLLM `POST /inject/{session_id}` for pro agent |
| `session_id` (con) | `GET /sessions` → `side=con` | MLLM `POST /inject/{session_id}` for con agent |

KB is **in-memory only** — it clears when you restart uvicorn. Run these commands against the **same** proxy instance that is serving the live debate.

---

**Smoke test script** (spawns pro+con sessions, injects sample tweets):

```bash
python scripts/smoke_inject.py --spawn --debate-session-id smoke-test-room
```

If Agora agents are already connected with the same `debate_session_id`, skip `--spawn`:

```bash
python scripts/smoke_inject.py --debate-session-id YOUR-ROOM-ID
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Address already in use` on 8081 | `kill $(lsof -t -i :8081)` then restart uvicorn |
| WebSocket **403/1008 Unauthorized** | Set matching `PROXY_MASTER_SECRET` and send HMAC Bearer (invite/scripts), or clear secret for auth-off local dev |
| Agora hits `/` not `/realtime` | URL must end with `/realtime` |
| ngrok URL changed | Free ngrok URLs change on restart — update debate app |
| `.env` changes not applied | Restart uvicorn (`--reload` does not re-read `.env`) |

---

## Tests

```bash
pytest
```

## Docker

```bash
docker build -t custom-xai-mllm .
docker run -p 8081:8081 --env-file .env custom-xai-mllm
```

## Milestones

| Milestone | Status | Description |
|-----------|--------|-------------|
| 0 | done | Scaffold + `/health` |
| 1 | done | Direct xAI smoke test |
| 2 | done | Transparent WebSocket proxy |
| 3 | in progress | Agora + ngrok E2E |
| 4 | in progress | `/inject` wired; Railway deploy |
