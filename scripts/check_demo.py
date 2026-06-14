#!/usr/bin/env python3
"""Monitor live debate sessions and in-memory KB during a demo.

Examples:
  python scripts/check_demo.py sessions --debate-session-id debate-4383d7ca
  python scripts/check_demo.py kb --debate-session-id debate-4383d7ca
  python scripts/check_demo.py kb --debate-session-id debate-4383d7ca --watch 5
  python scripts/check_demo.py watch --debate-session-id debate-4383d7ca --interval 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.proxy_auth import proxy_auth_headers  # noqa: E402
from src.settings import settings  # noqa: E402


def _base_url(host: str) -> str:
    return f"http://{host}"


def _session_headers(debate_session_id: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        **proxy_auth_headers(debate_session_id=debate_session_id),
    }


def fetch_sessions(host: str, debate_session_id: str) -> tuple[int, dict | str]:
    url = f"{_base_url(host)}/sessions"
    response = httpx.get(
        url,
        params={"debate_session_id": debate_session_id},
        headers=_session_headers(debate_session_id),
        timeout=15.0,
    )
    try:
        return response.status_code, response.json()
    except Exception:
        return response.status_code, response.text


def fetch_kb(host: str, debate_session_id: str) -> tuple[int, dict | str]:
    url = f"{_base_url(host)}/kb"
    response = httpx.get(
        url,
        params={"debate_session_id": debate_session_id},
        headers=_session_headers(debate_session_id),
        timeout=15.0,
    )
    try:
        return response.status_code, response.json()
    except Exception:
        return response.status_code, response.text


def print_sessions(debate_session_id: str, data: dict) -> None:
    sessions = data.get("sessions") or []
    pro = [s for s in sessions if s.get("side") == "pro"]
    con = [s for s in sessions if s.get("side") == "con"]

    print(f"\n=== Sessions for {debate_session_id} ===")
    print(f"  active: {len(sessions)} (pro={len(pro)}, con={len(con)})")

    for side, items in (("pro", pro), ("con", con)):
        if not items:
            print(f"  {side}: (none connected)")
            continue
        for session in items:
            print(
                f"  {side}: session_id={session['session_id']} "
                f"upstream={session.get('upstream_connected')} "
                f"provider={session.get('provider')}"
            )


def _truncate(text: str, limit: int = 100) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def print_kb_summary(debate_session_id: str, data: dict) -> None:
    pro = data.get("pro") or []
    con = data.get("con") or []

    print(f"\n=== KB for {debate_session_id} ===")
    print(f"  pro points: {len(pro)}")
    print(f"  con points: {len(con)}")

    if pro:
        latest = pro[0]
        print(f"  latest pro [{latest['id']}]: {_truncate(latest['text'])}")
    else:
        print("  latest pro: (none yet)")

    if con:
        latest = con[0]
        print(f"  latest con [{latest['id']}]: {_truncate(latest['text'])}")
    else:
        print("  latest con: (none yet)")

    print("  (LLM mode injects latest pro/con point per side on each turn)")


def cmd_sessions(host: str, debate_session_id: str, as_json: bool) -> int:
    status, body = fetch_sessions(host, debate_session_id)
    print(f"GET /sessions?debate_session_id={debate_session_id} -> {status}")
    if status != 200:
        print(body)
        return 1
    if as_json:
        print(json.dumps(body, indent=2))
    else:
        print_sessions(debate_session_id, body)
    return 0


def cmd_kb(
    host: str,
    debate_session_id: str,
    *,
    as_json: bool,
    watch: int,
) -> int:
    def run_once() -> int:
        status, body = fetch_kb(host, debate_session_id)
        print(f"GET /kb?debate_session_id={debate_session_id} -> {status}")
        if status != 200:
            print(body)
            return 1
        if as_json:
            print(json.dumps(body, indent=2))
        else:
            print_kb_summary(debate_session_id, body)
        return 0

    if watch <= 0:
        return run_once()

    try:
        while True:
            print(f"\n--- {time.strftime('%H:%M:%S')} ---")
            code = run_once()
            if code != 0:
                return code
            time.sleep(watch)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def cmd_watch(host: str, debate_session_id: str, interval: int, as_json: bool) -> int:
    try:
        while True:
            print(f"\n========== {time.strftime('%H:%M:%S')} ==========")
            sessions_code = cmd_sessions(host, debate_session_id, as_json)
            kb_code = cmd_kb(host, debate_session_id, as_json=as_json, watch=0)
            if sessions_code != 0 or kb_code != 0:
                return 1
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor proxy sessions and in-memory KB during a live debate demo"
    )
    parser.add_argument(
        "command",
        choices=["sessions", "kb", "watch"],
        help="sessions=list pro/con WS UUIDs; kb=ingested points; watch=both on interval",
    )
    parser.add_argument(
        "--debate-session-id",
        required=True,
        help="Debate room id from Agora channel, e.g. debate-4383d7ca",
    )
    parser.add_argument("--host", default=f"localhost:{settings.port}")
    parser.add_argument(
        "--watch",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Poll kb every N seconds (kb command only)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        metavar="SECONDS",
        help="Poll sessions+kb every N seconds (watch command only)",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON responses")
    args = parser.parse_args()

    if args.command == "sessions":
        return cmd_sessions(args.host, args.debate_session_id, args.json)
    if args.command == "kb":
        return cmd_kb(
            args.host,
            args.debate_session_id,
            as_json=args.json,
            watch=args.watch,
        )
    return cmd_watch(args.host, args.debate_session_id, args.interval, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
