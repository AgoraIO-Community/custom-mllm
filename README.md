# custom-xAI-mllm

Transparent WebSocket proxy between [Agora Conversational AI](https://docs.agora.io/en/conversational-ai/models/mllm/xai) and the [xAI Grok Voice Agent API](https://docs.x.ai/developers/model-capabilities/audio/voice-agent).

## Docs

- [prd.md](./prd.md) — product requirements
- [spec.md](./spec.md) — implementation spec
- [debate-architcture.md](./debate-architcture.md) — debate demo architecture (consumer app)

## Milestone 0 (done)

- Python project scaffold
- `GET /health` endpoint
- Module stubs for relay, inject, sessions (Milestones 2–4)

## Milestone 1 (done)

Direct xAI smoke test — verifies your API key and voice pipeline:

```bash
python scripts/smoke_xai.py
```

## Milestone 2 (done)

Transparent WebSocket proxy at `/realtime`:

```bash
# Terminal 1
uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload

# Terminal 2 — smoke test through proxy
python scripts/smoke_xai.py --via-proxy
```

## Quick start

> **Note:** Default port is **8081** (8080 is often taken by Docker on macOS).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set XAI_API_KEY when running Milestone 1+

uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload
```

Health check:

```bash
curl http://localhost:8081/health
```

Expected:

```json
{"status":"ok","version":"0.1.0","active_sessions":0}
```

## Tests

```bash
pytest
```

## Docker

```bash
docker build -t custom-xai-mllm .
docker run -p 8081:8081 --env-file .env custom-xai-mllm
```

## Agora integration (later)

Point the debate app `mllm.url` at this proxy:

```
wss://<your-host>/realtime?model=grok-voice-latest
```

Keep `vendor: "xai"`. Set `XAI_API_KEY` only in this proxy's environment.
