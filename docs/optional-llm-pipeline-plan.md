---
name: Optional LLM (cascade) pipeline alongside MLLM
overview: Cascade LLM (ASR + proxy LLM + ElevenLabs TTS) is the default when MLLM is off. MLLM voice-to-voice path unchanged. Proxy `/v1/chat/completions` and `/kb/ingest` are implemented in a separate repo.
todos:
  - id: mode-config
    content: "Phase 1: pipelineMode, setup UI, resolvePipelineMode, LLM_PROXY_HTTP_URL — implemented in Next.js app"
    status: completed
  - id: proxy-llm-endpoints
    content: "Phase 2 (proxy service): POST /v1/chat/completions + POST /kb/ingest — separate repo (user)"
    status: pending
  - id: invite-branching
    content: "Phase 3: buildLlmPodcastAgentSettings with query-param llm.url — implemented"
    status: completed
  - id: feed-routing
    content: "Phase 4: LLM mode → /kb/ingest; MLLM → /inject — implemented"
    status: completed
  - id: prompts
    content: "Phase 5: buildHostLlmSystemPrompt / buildGuestLlmSystemPrompt — implemented"
    status: completed
  - id: ui-transcript
    content: "Phase 6: Setup LLM provider/model/voices, Think API panel KB ingest labels — implemented"
    status: completed
  - id: verify
    content: "Phase 7: npm run build passes; manual E2E with live proxy pending"
    status: pending
isProject: false
---

# Cascade LLM pipeline alongside MLLM

## Locked decisions (implemented)

| Item | Choice |
|------|--------|
| Default toggle | MLLM **off** → cascade LLM default |
| LLM providers | **OpenAI + xAI only** (no Gemini in cascade mode) |
| Default models | `gpt-4o-mini` / `grok-4.3` |
| Routing | **Query params** on `llm.url` (mirrors MLLM `buildMllmUrl` pattern) |
| API keys | Proxy only |
| TTS voices | `llmProVoiceId` / `llmConVoiceId` (decoupled from avatar presets) |
| KB ingest body | Optional `pro` and/or `con` objects per POST |

## Architecture

```
MLLM mode (unchanged):
  Agora mllm ──WS──> proxy /realtime?debate_session_id&side&provider
  Next.js ──POST──> proxy /inject/{session}

LLM mode (default when MLLM off):
  Agora: ASR ──> LLM ──> ElevenLabs TTS
  Agora llm.url ──POST──> proxy /v1/chat/completions?pipeline_mode=llm&debate_session_id&side&provider&model
  Next.js ──POST──> proxy /kb/ingest
```

Same proxy host, four paths. Session id: `getDebateSessionId(sessionId)` → `debate-{sessionId}`.

### Example LLM URLs (per agent)

```
https://<proxy>/v1/chat/completions?pipeline_mode=llm&debate_session_id=debate-eea3c9e5&side=pro&provider=openai&model=gpt-4o-mini
https://<proxy>/v1/chat/completions?pipeline_mode=llm&debate_session_id=debate-eea3c9e5&side=con&provider=xai&model=grok-4.3
```

## Next.js app — implemented files

| Area | Files |
|------|-------|
| Types / helpers | `src/types/podcast.ts`, `src/lib/mllm-proxy.ts` |
| Setup UI | `src/screens/podcast/PodcastSetupScreen.tsx`, `src/components/ElevenLabsVoicePicker.tsx` |
| Agent invite | `src/utils/podcastAgentSettings.ts` → `buildLlmPodcastAgentSettings()` |
| Prompts | `src/config/podcast/prompts.ts` → `buildHostLlmSystemPrompt`, `buildGuestLlmSystemPrompt` |
| Feed routing | `src/lib/podcastSearchFeed.ts`, `src/lib/podcastRealtimeFeed.ts`, API routes, hooks |
| Studio UI | `src/components/podcast/PodcastThinkApiPanel.tsx`, `src/utils/podcastThinkLog.ts` |
| Env | `.env.example` → `LLM_PROXY_HTTP_URL` |

## Proxy repo contract (user implements)

### `POST /kb/ingest`

```json
{
  "debate_session_id": "debate-{sessionId}",
  "pro": { "id": "<postId>", "text": "<pro summary>" },
  "con": { "id": "<postId>", "text": "<con summary>" }
}
```

Both `pro` and `con` are optional. One or both may be present per cycle.

```ts
if (body.pro) ingest(debate_session_id, "pro", body.pro.id, body.pro.text);
if (body.con) ingest(debate_session_id, "con", body.con.id, body.con.text);
```

### `POST /v1/chat/completions`

Read from **query string** (same pattern as MLLM WS):

- `pipeline_mode=llm`
- `debate_session_id`
- `side` (`pro` | `con`)
- `provider` (`openai` | `xai`)
- `model`

Pull KB point for side → append system message → forward upstream → stream OpenAI-compatible SSE.

## Env

```properties
MLLM_PROXY_HTTP_URL=https://<proxy-host>
MLLM_PROXY_WS_URL=wss://<proxy-host>/realtime
LLM_PROXY_HTTP_URL=https://<proxy-host>/v1/chat/completions
# /kb/ingest derived from MLLM_PROXY_HTTP_URL base + /kb/ingest
```

## Verification matrix

1. Fresh setup: MLLM off, OpenAI, `gpt-4o-mini`, Pro/Con voice pickers visible
2. Invite: `asr+llm+tts`, `llm.url` with query params, no `mllm` block
3. MLLM regression: WS `/realtime` + `/inject` unchanged
4. KB ingest: pro-only, con-only, both-side POSTs; `debate_session_id` matches `llm.url`
5. TTS uses `llmProVoiceId` / `llmConVoiceId`
6. Turn orchestrator inactive in LLM mode
7. xAI provider → `provider=xai&model=grok-4.3` in invite URL

`npm run build` passes. E2E requires live proxy with `/kb/ingest` and `/v1/chat/completions`.
