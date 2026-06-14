Per-debate HMAC proxy authentication

Goal

Protect all debate proxy routes so a leaked ngrok/Railway URL is not enough. Use one shared master secret in env (PROXY_MASTER_SECRET) on Next.js and Python proxy; derive per-debate (and per-side) tokens with HMAC-SHA256. Vendor keys (OPENAI_API_KEY, XAI_API_KEY) stay on the proxy only.

sequenceDiagram
  participant Next as NextJS_invite
  participant Agora as Agora_ConvEngine
  participant Proxy as Python_proxy

  Next->>Next: tokenSide=HMAC(secret, debate_id:pro)
  Next->>Agora: join llm.api_key=tokenSide
  Agora->>Proxy: POST /v1/chat/completions?debate_session_id&side=pro
  Note over Agora,Proxy: Authorization Bearer tokenSide
  Proxy->>Proxy: recompute HMAC compare_digest
  Proxy->>Proxy: upstream with OPENAI_API_KEY

  Next->>Proxy: POST /kb/ingest debate_session_id
  Note over Next,Proxy: Authorization Bearer HMAC(secret, debate_id)

Shared contract (both repos must match exactly)







Item



Value





Env var



PROXY_MASTER_SECRET (same string on Next.js + Python)





Side token message



{debate_session_id}:{side} e.g. debate-abc123:pro





Debate token message



{debate_session_id} only (for /kb/ingest, GET /sessions)





Algorithm



HMAC-SHA256, output hex





Header



Authorization: Bearer <token>





Dev



Empty/unset secret → skip auth (both sides)

Side values: lowercase pro | con (matches [buildLlmProxyUrl](src/lib/mllm-proxy.ts) query params).

Debate session id: debate-{sessionId} from [getDebateSessionId()](src/lib/mllm-proxy.ts) — same as Agora channel [debate-{sessionId}](app/api/podcast/start/route.ts).



Phase 1 — Next.js app (this repo)

1. Add token helpers in [src/lib/mllm-proxy.ts](src/lib/mllm-proxy.ts)

New exports:





getProxyMasterSecret(): string | undefined — reads PROXY_MASTER_SECRET (trimmed)



isProxyAuthEnabled(): boolean — secret non-empty



deriveDebateProxySideToken(debateSessionId, side) — HMAC hex for Agora + side-scoped routes



deriveDebateProxySessionToken(debateSessionId) — HMAC hex for debate-scoped routes



isDebateProxyUrl(url: string): boolean — host matches MLLM_PROXY_HTTP_URL / LLM_PROXY_HTTP_URL / derived WS host



parseDebateSessionIdFromChannel(channelName) — if channelName.startsWith("debate-"), return as-is



parseDebateProxySide(agentName?) — debate-host-* → pro, debate-guest-* → con

Replace static [proxyHeaders()](src/lib/mllm-proxy.ts) with:





proxyHeadersForSide(debateSessionId, side) → side token



proxyHeadersForSession(debateSessionId) → debate token

Migration: If PROXY_MASTER_SECRET unset but MLLM_PROXY_AUTH_TOKEN set, fall back to static Bearer (existing behavior) so local setups do not break until Phase 2 ships.

Update callers:





[postKbIngest](src/lib/mllm-proxy.ts) → proxyHeadersForSession(debateSessionId)



[getProxySessions](src/lib/mllm-proxy.ts) → proxyHeadersForSession(debateSessionId)



[injectContext](src/lib/mllm-proxy.ts) → needs debateSessionId + side (already in log context / session lookup path via injectToProxySide)

2. Invite route — inject derived tokens for debate + proxy only

File: [app/api/agent/invite/route.ts](app/api/agent/invite/route.ts)

When to apply HMAC (all must be true):





isProxyAuthEnabled() OR legacy static token path for non-HMAC fallback



URL is debate proxy (isDebateProxyUrl(llm.url) or isDebateProxyUrl(mllm.url))



Debate context: channelName like debate-* or agent name debate-host-* / debate-guest-*

Cascade LLM branch (~line 659): when proxy + HMAC enabled:





Do not inject LLM_API_KEY



Set llm.api_key = deriveDebateProxySideToken(debateSessionId, side)



Ensure llm.vendor = "custom" is forwarded (currently set in agent settings but not copied into llmPayload)

MLLM branch (~line 864): when mllmStyleUsesProxy(style) + HMAC:





Override payload.api_key with side token after buildMllmInvitePayload



Skip 400 when upstream XAI_MLLM_API_KEY / OPENAI_MLLM_API_KEY missing (proxy holds upstream keys)



Still require PROXY_MASTER_SECRET in prod when proxy URLs are used

Non-debate flows (1:1 meetings, direct OpenAI URL): unchanged — keep injecting LLM_API_KEY / upstream MLLM keys.

Custom payload join (handleCustomPayloadJoin, ~line 187): same proxy detection + side token logic for llm / mllm.

Logging: continue masking api_key in sanitized logs; never log derived tokens when verbose.

3. Agent settings — no client secrets

[src/utils/podcastAgentSettings.ts](src/utils/podcastAgentSettings.ts) stays with api_key: "***MASKED***" / "" — server resolves at invite. No change to client-visible shape.

4. Env and docs

Update [.env.example](.env.example):

# Shared with Python proxy — HMAC per-debate auth (empty = dev open)
# PROXY_MASTER_SECRET=
# Legacy static Bearer (fallback when PROXY_MASTER_SECRET unset):
# MLLM_PROXY_AUTH_TOKEN=

Add short section to [docs/debate/architecture.md](docs/debate/architecture.md) API keys table: PROXY_MASTER_SECRET, token derivation, Phase 2 proxy requirement.

5. Unit tests

Add src/lib/mllm-proxy.auth.test.ts (or similar):





Fixed secret + inputs → expected hex (document vector for Python cross-check)



deriveDebateProxySideToken("debate-abc", "pro") !== deriveDebateProxySideToken("debate-abc", "con")



proxyHeadersForSession includes Bearer when secret set



Phase 2 — Python proxy (separate repo)

You implement in your Python server; Next.js Phase 1 can ship first only if proxy still accepts legacy static MLLM_PROXY_AUTH_TOKEN until Phase 2 is deployed.

Env

PROXY_MASTER_SECRET = os.environ.get("PROXY_MASTER_SECRET", "").strip()
# Optional legacy: PROXY_AUTH_TOKEN for static Bearer during migration

Empty secret → skip verify (dev). Non-empty → require valid HMAC on all routes.

Shared module (proxy_auth.py)

def derive_side_token(debate_session_id: str, side: str) -> str: ...
def derive_session_token(debate_session_id: str) -> str: ...
def verify_bearer(auth_header, debate_session_id, side=None) -> bool:
    # side set → compare side token; side None → session token
    # hmac.compare_digest only

Middleware / per-route checks







Route



Validate with





POST /v1/chat/completions



query debate_session_id + side → side token





WS /realtime



query debate_session_id + side → side token





POST /kb/ingest



body debate_session_id → session token





GET /sessions



query debate_session_id → session token





POST /inject/{session_id}



lookup session’s debate_session_id + side → side token

After auth: forward upstream using OPENAI_API_KEY / XAI_API_KEY from proxy env only.

Logging

Redact Authorization in all access/error logs.

Verification checklist





curl proxy URL without Bearer → 401 (prod secret set)



Wrong token → 401



curl with Bearer $(python -c "derive_side_token(...)") → not 401



Start debate → agents speak (Agora path)



Live X ingest/inject works (Next.js path)



Cross-lang: run same inputs in Node test + Python one-liner → identical hex



Rollout order





Deploy Phase 2 proxy with dual auth: accept either legacy static Bearer or HMAC (optional, simplifies cutover).



Deploy Phase 1 Next.js with PROXY_MASTER_SECRET set.



Remove legacy static PROXY_AUTH_TOKEN / MLLM_PROXY_AUTH_TOKEN once both sides verified.

Files touched (Phase 1)







File



Change





[src/lib/mllm-proxy.ts](src/lib/mllm-proxy.ts)



HMAC helpers, scoped proxyHeaders, update fetch callers





[app/api/agent/invite/route.ts](app/api/agent/invite/route.ts)



Inject side token for debate proxy; skip upstream keys





[.env.example](.env.example)



Document PROXY_MASTER_SECRET





[docs/debate/architecture.md](docs/debate/architecture.md)



Auth section update





New test file



Cross-lang HMAC vector

Phase 2 is not in this repo — deliver as Python module + route middleware in your proxy project using the same env var and message formats above.