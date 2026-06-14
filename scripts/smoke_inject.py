#!/usr/bin/env python3
"""Smoke test for GET /sessions and POST /inject/{session_id}."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.proxy_auth import proxy_auth_headers  # noqa: E402
from src.settings import settings  # noqa: E402

PRO_TEXT = "[LIVE X - PRO] @user_pro: AI regulation will boost innovation."
CON_TEXT = "[LIVE X - CON] @user_con: AI regulation will stifle startups."


def _http_headers(debate_session_id: str, *, side: str | None = None) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        **proxy_auth_headers(debate_session_id=debate_session_id, side=side),
    }


def _ws_headers(debate_session_id: str, side: str) -> dict[str, str]:
    return proxy_auth_headers(debate_session_id=debate_session_id, side=side)


async def _hold_session(
    base_url: str,
    debate_session_id: str,
    side: str,
    stop: asyncio.Event,
) -> None:
    ws_url = (
        f"ws://{base_url}/realtime"
        f"?pipeline_mode=mllm&debate_session_id={debate_session_id}&side={side}"
        f"&provider=xai"
    )
    async with websockets.connect(
        ws_url, additional_headers=_ws_headers(debate_session_id, side)
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "voice": "eve",
                        "instructions": f"You are the {side} debate agent. Keep replies brief.",
                        "turn_detection": {"type": "server_vad"},
                    },
                }
            )
        )

        async def _drain() -> None:
            async for _ in ws:
                if stop.is_set():
                    break

        drain_task = asyncio.create_task(_drain())
        await stop.wait()
        drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass


async def _wait_for_sessions(
    http_base: str,
    debate_session_id: str,
    timeout: float,
) -> list[dict]:
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(
        base_url=http_base, headers=_http_headers(debate_session_id)
    ) as client:
        while asyncio.get_event_loop().time() < deadline:
            response = await client.get(
                "/sessions",
                params={"debate_session_id": debate_session_id},
            )
            response.raise_for_status()
            sessions = response.json()["sessions"]
            sides = {s["side"] for s in sessions if s.get("upstream_connected")}
            if {"pro", "con"}.issubset(sides):
                return sessions
            await asyncio.sleep(0.5)
    raise TimeoutError(
        f"Timed out waiting for pro+con upstream_connected sessions "
        f"(debate_session_id={debate_session_id})"
    )


async def _inject(
    http_base: str,
    session_id: str,
    text: str,
    *,
    debate_session_id: str,
    side: str,
    trigger_response: bool,
) -> dict:
    async with httpx.AsyncClient(
        base_url=http_base,
        headers=_http_headers(debate_session_id, side=side),
    ) as client:
        response = await client.post(
            f"/inject/{session_id}",
            json={"text": text, "trigger_response": trigger_response},
        )
        print(f"  POST /inject/{session_id} -> {response.status_code}")
        if response.status_code != 200:
            print(f"  body: {response.text}", file=sys.stderr)
            response.raise_for_status()
        data = response.json()
        print(f"  injected side={data.get('side')} trigger_response={data.get('trigger_response')}")
        return data


async def run(args: argparse.Namespace) -> int:
    if not settings.xai_api_key:
        print("ERROR: XAI_API_KEY is not set in .env", file=sys.stderr)
        return 1

    http_base = f"http://{args.host}:{args.port}"
    ws_host = f"{args.host}:{args.port}"
    debate_session_id = args.debate_session_id
    stop = asyncio.Event()
    hold_tasks: list[asyncio.Task] = []

    print(f"Proxy HTTP: {http_base}")
    print(f"Debate session: {debate_session_id}")

    try:
        async with httpx.AsyncClient(
        base_url=http_base, headers=_http_headers(debate_session_id)
    ) as client:
            health = await client.get("/health")
            health.raise_for_status()
            print(f"Health: {health.json()}")

        if args.spawn:
            print("Spawning pro + con WebSocket sessions ...")
            hold_tasks = [
                asyncio.create_task(_hold_session(ws_host, debate_session_id, "pro", stop)),
                asyncio.create_task(_hold_session(ws_host, debate_session_id, "con", stop)),
            ]
            sessions = await _wait_for_sessions(http_base, debate_session_id, args.timeout)
        else:
            print("Using existing sessions (pass --spawn to create pro+con automatically) ...")
            async with httpx.AsyncClient(
        base_url=http_base, headers=_http_headers(debate_session_id)
    ) as client:
                response = await client.get(
                    "/sessions",
                    params={"debate_session_id": debate_session_id},
                )
                response.raise_for_status()
                sessions = response.json()["sessions"]

        by_side = {s["side"]: s for s in sessions if s.get("side")}
        missing = [side for side in ("pro", "con") if side not in by_side]
        if missing:
            print(
                f"ERROR: missing sessions for sides: {missing}. "
                "Start Agora agents or re-run with --spawn",
                file=sys.stderr,
            )
            return 1

        for side, session in by_side.items():
            status = "connected" if session.get("upstream_connected") else "NOT connected"
            print(f"  {side}: session_id={session['session_id']} ({status})")

        if not all(s.get("upstream_connected") for s in by_side.values()):
            print("ERROR: upstream not connected for all sessions", file=sys.stderr)
            return 1

        print("Injecting live context ...")
        await _inject(
            http_base,
            by_side["pro"]["session_id"],
            args.pro_text or PRO_TEXT,
            debate_session_id=debate_session_id,
            side="pro",
            trigger_response=args.trigger_response,
        )
        await _inject(
            http_base,
            by_side["con"]["session_id"],
            args.con_text or CON_TEXT,
            debate_session_id=debate_session_id,
            side="con",
            trigger_response=args.trigger_response,
        )

        print("\nInject smoke test PASSED")
        print("Check proxy logs for inject.sent and upstream conversation.item.create")
        return 0

    except Exception as exc:  # noqa: BLE001 — smoke script
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        stop.set()
        for task in hold_tasks:
            task.cancel()
        if hold_tasks:
            await asyncio.gather(*hold_tasks, return_exceptions=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject endpoint smoke test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument(
        "--debate-session-id",
        default="smoke-test-room",
        help="debate_session_id scope (must match Agora mllm.url if not using --spawn)",
    )
    parser.add_argument(
        "--spawn",
        action="store_true",
        help="Open pro+con WebSocket sessions to the proxy before injecting",
    )
    parser.add_argument(
        "--trigger-response",
        action="store_true",
        help="Set trigger_response=true (agent responds immediately)",
    )
    parser.add_argument("--pro-text", default="", help="Override pro inject text")
    parser.add_argument("--con-text", default="", help="Override con inject text")
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait for sessions")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
