#!/usr/bin/env python3
"""xAI Voice Agent smoke test — direct or via local proxy (Milestones 1 & 2)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.settings import settings  # noqa: E402


def _build_headers(via_proxy: bool) -> dict[str, str]:
    headers: dict[str, str] = {}
    if via_proxy and settings.proxy_auth_token:
        headers["Authorization"] = f"Bearer {settings.proxy_auth_token}"
    elif not via_proxy:
        headers["Authorization"] = f"Bearer {settings.xai_api_key}"
    return headers


def _resolve_url(via_proxy: bool, host: str, port: int) -> str:
    if via_proxy:
        return f"ws://{host}:{port}/realtime?provider=xai"
    return settings.xai_upstream_url


async def run_smoke_test(via_proxy: bool, host: str, port: int) -> int:
    if not settings.xai_api_key:
        print("ERROR: XAI_API_KEY is not set in .env", file=sys.stderr)
        return 1

    url = _resolve_url(via_proxy, host, port)
    headers = _build_headers(via_proxy)
    mode = "proxy" if via_proxy else "direct"

    print(f"Connecting ({mode}) to {url} ...")

    saw_audio_delta = False
    saw_response_done = False
    saw_error = False

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "voice": "eve",
                            "instructions": "You are a helpful assistant. Keep replies very brief.",
                            "turn_detection": {"type": "server_vad"},
                            "audio": {
                                "input": {"format": {"type": "audio/pcm", "rate": 24000}},
                                "output": {"format": {"type": "audio/pcm", "rate": 24000}},
                            },
                        },
                    }
                )
            )

            await ws.send(
                json.dumps(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Say hello in one short sentence.",
                                }
                            ],
                        },
                    }
                )
            )
            await ws.send(json.dumps({"type": "response.create"}))

            print("Waiting for events ...")

            async for raw in ws:
                event = json.loads(raw)
                event_type = event.get("type", "unknown")
                print(f"  <- {event_type}")

                if event_type == "response.output_audio.delta":
                    saw_audio_delta = True
                elif event_type == "response.done":
                    saw_response_done = True
                    break
                elif event_type == "error":
                    saw_error = True
                    print(f"  ERROR payload: {json.dumps(event, indent=2)}", file=sys.stderr)
                    break

    except websockets.InvalidStatus as exc:
        print(f"ERROR: WebSocket rejected (HTTP {exc.response.status_code})", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — smoke script
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print()
    print(f"  response.output_audio.delta : {'PASS' if saw_audio_delta else 'FAIL'}")
    print(f"  response.done               : {'PASS' if saw_response_done else 'FAIL'}")

    if saw_error:
        return 1
    if saw_audio_delta and saw_response_done:
        print(f"\nSmoke test PASSED ({mode})")
        return 0

    print("\nSmoke test FAILED", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="xAI Voice Agent smoke test")
    parser.add_argument(
        "--via-proxy",
        action="store_true",
        help="Connect through local proxy at ws://host:port/realtime",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Proxy host (with --via-proxy)")
    parser.add_argument("--port", type=int, default=8081, help="Proxy port (with --via-proxy)")
    args = parser.parse_args()
    return asyncio.run(run_smoke_test(args.via_proxy, args.host, args.port))


if __name__ == "__main__":
    raise SystemExit(main())
