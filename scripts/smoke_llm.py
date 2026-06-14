#!/usr/bin/env python3
"""Smoke test for POST /kb/ingest and POST /v1/chat/completions (cascade LLM)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.proxy_auth import proxy_auth_headers  # noqa: E402
from src.settings import settings  # noqa: E402

PRO_SUMMARY = "AI regulation will boost innovation and safety standards."
CON_SUMMARY = "AI regulation will stifle startups and slow deployment."


def _http_headers(debate_session_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        **proxy_auth_headers(debate_session_id=debate_session_id),
    }


def _chat_path(debate_session_id: str, side: str, provider: str, model: str) -> str:
    params = {
        "pipeline_mode": "llm",
        "debate_session_id": debate_session_id,
        "side": side,
        "provider": provider,
        "model": model,
    }
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"/v1/chat/completions?{query}"


async def run_smoke(
    base_url: str,
    debate_session_id: str,
    provider: str,
    model: str,
) -> None:
    async with httpx.AsyncClient(base_url=f"http://{base_url}") as client:
        health = await client.get("/health")
        health.raise_for_status()
        print(f"health: {health.json()}")

        ingest = await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": debate_session_id,
                "pro": {"id": "smoke-tweet-pro", "text": PRO_SUMMARY},
                "con": {"id": "smoke-tweet-con", "text": CON_SUMMARY},
            },
            headers=_http_headers(debate_session_id),
        )
        ingest.raise_for_status()
        print(f"kb/ingest: {ingest.json()}")

        kb_get = await client.get(
            "/kb",
            params={"debate_session_id": debate_session_id},
            headers=proxy_auth_headers(debate_session_id=debate_session_id),
        )
        kb_get.raise_for_status()
        kb_data = kb_get.json()
        print(f"kb GET: {kb_data}")
        assert len(kb_data["pro"]) == 1, "expected one pro KB point after ingest"
        assert len(kb_data["con"]) == 1, "expected one con KB point after ingest"
        assert kb_data["pro"][0]["text"] == PRO_SUMMARY
        assert kb_data["con"][0]["text"] == CON_SUMMARY
        print("kb ingest + fetch OK")

        for side in ("pro", "con"):
            print(f"\n--- chat completions side={side} ---")
            async with client.stream(
                "POST",
                _chat_path(debate_session_id, side, provider, model),
                json={
                    "messages": [{"role": "user", "content": "What is happening on live X?"}],
                    "stream": True,
                    "turn_id": 0,
                    "timestamp": 1,
                },
                headers={
                    "Content-Type": "application/json",
                    **proxy_auth_headers(debate_session_id=debate_session_id, side=side),
                },
                timeout=120.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    print(line)
                    if line.strip() == "data: [DONE]":
                        break


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test cascade LLM proxy endpoints")
    parser.add_argument("--host", default=f"{settings.host}:{settings.port}")
    parser.add_argument("--debate-session-id", default="debate-smoke-test")
    parser.add_argument("--provider", default="openai", choices=["openai", "xai"])
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    model = args.model
    if model is None:
        model = settings.openai_chat_model if args.provider == "openai" else settings.xai_chat_model

    asyncio.run(
        run_smoke(
            base_url=args.host,
            debate_session_id=args.debate_session_id,
            provider=args.provider,
            model=model,
        )
    )


if __name__ == "__main__":
    main()
