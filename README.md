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
PROXY_AUTH_TOKEN=
```

Leave `PROXY_AUTH_TOKEN` **empty** for local/Agora testing. The real xAI key stays in this proxy only — not in the debate app.

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
wss://sensationally-unpeppered-eleanor.ngrok-free.dev/realtime
```

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
    "url": "wss://YOUR-NGROK-SUBDOMAIN.ngrok-free.dev/realtime",
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

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Address already in use` on 8081 | `kill $(lsof -t -i :8081)` then restart uvicorn |
| WebSocket **403 Forbidden** | Clear `PROXY_AUTH_TOKEN` in `.env` and **restart** uvicorn |
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
| 4 | pending | `/inject`, Railway deploy |
