#!/usr/bin/env python3
"""Run proxy unit tests and smoke scripts from one place.

Usage:
  python scripts/run_tests.py              # list available tests
  python scripts/run_tests.py unit         # pytest (no server required)
  python scripts/run_tests.py smoke-llm    # cascade LLM smoke (server + keys)
  python scripts/run_tests.py all-unit     # alias for unit
  python scripts/run_tests.py all-smoke    # all smoke tests (server must be running)

Prerequisites:
  - source .venv/bin/activate
  - .env with XAI_API_KEY (and OPENAI_API_KEY for cascade LLM smoke)
  - PROXY_MASTER_SECRET set if auth is enabled on the proxy
  - uvicorn running on port 8081 for smoke tests:
      uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

TESTS: dict[str, dict[str, str]] = {
    "unit": {
        "title": "Unit tests (pytest)",
        "requires": "None — no running server",
        "command": f"{PYTHON} -m pytest tests/ -q",
        "cwd": str(ROOT),
    },
    "auth-vector": {
        "title": "HMAC cross-language vector (proxy_auth)",
        "requires": "None",
        "command": f"{PYTHON} -m pytest tests/test_proxy_auth.py -q -v",
        "cwd": str(ROOT),
    },
    "health": {
        "title": "Health check (GET /health)",
        "requires": "Proxy running on :8081",
        "command": "curl -s http://localhost:8081/health",
        "cwd": str(ROOT),
        "shell": True,
    },
    "smoke-xai-direct": {
        "title": "xAI voice smoke — direct to xAI (no proxy)",
        "requires": "XAI_API_KEY in .env",
        "command": f"{PYTHON} scripts/smoke_xai.py",
        "cwd": str(ROOT),
    },
    "smoke-xai-proxy": {
        "title": "xAI voice smoke — via proxy WebSocket /realtime",
        "requires": "Proxy on :8081, XAI_API_KEY, PROXY_MASTER_SECRET if auth on",
        "command": (
            f"{PYTHON} scripts/smoke_xai.py --via-proxy "
            "--debate-session-id debate-smoke-test --side pro"
        ),
        "cwd": str(ROOT),
    },
    "smoke-llm": {
        "title": "Cascade LLM smoke — /kb/ingest + /v1/chat/completions",
        "requires": "Proxy on :8081, OPENAI_API_KEY or XAI_API_KEY, PROXY_MASTER_SECRET if auth on",
        "command": (
            f"{PYTHON} scripts/smoke_llm.py "
            "--debate-session-id debate-smoke-test --provider openai"
        ),
        "cwd": str(ROOT),
    },
    "smoke-inject": {
        "title": "MLLM inject smoke — /sessions + /inject (spawns pro+con WS)",
        "requires": "Proxy on :8081, XAI_API_KEY, PROXY_MASTER_SECRET if auth on",
        "command": (
            f"{PYTHON} scripts/smoke_inject.py --spawn "
            "--debate-session-id debate-smoke-test"
        ),
        "cwd": str(ROOT),
    },
    "inspect-kb": {
        "title": "Inspect KB (GET /kb) after ingest",
        "requires": "Proxy on :8081, debate_session_id, PROXY_MASTER_SECRET if auth on",
        "command": (
            f"{PYTHON} scripts/inspect_kb.py --debate-session-id debate-smoke-test"
        ),
        "cwd": str(ROOT),
    },
    "check-demo-sessions": {
        "title": "Live demo — list pro/con proxy sessions",
        "requires": "Proxy on :8081, live debate_session_id, PROXY_MASTER_SECRET if auth on",
        "command": (
            f"{PYTHON} scripts/check_demo.py sessions "
            "--debate-session-id debate-smoke-test"
        ),
        "cwd": str(ROOT),
    },
    "check-demo-kb": {
        "title": "Live demo — KB summary (ingested live-X points)",
        "requires": "Proxy on :8081, live debate_session_id, PROXY_MASTER_SECRET if auth on",
        "command": (
            f"{PYTHON} scripts/check_demo.py kb "
            "--debate-session-id debate-smoke-test --watch 5"
        ),
        "cwd": str(ROOT),
    },
}

GROUPS: dict[str, list[str]] = {
    "all-unit": ["unit", "auth-vector"],
    "all-smoke": [
        "health",
        "smoke-xai-proxy",
        "smoke-llm",
        "smoke-inject",
        "inspect-kb",
    ],
    "all": ["unit", "auth-vector", "health", "smoke-xai-direct", "smoke-xai-proxy", "smoke-llm", "smoke-inject"],
}


def print_catalog() -> None:
    print("Available tests\n")
    for name, info in TESTS.items():
        print(f"  {name}")
        print(f"    {info['title']}")
        print(f"    Requires: {info['requires']}")
        print(f"    Run:      python scripts/run_tests.py {name}")
        print()
    print("Groups\n")
    for group, members in GROUPS.items():
        print(f"  {group}: {', '.join(members)}")
        print(f"    Run: python scripts/run_tests.py {group}")
        print()
    print("Examples")
    print("  python scripts/run_tests.py unit")
    print("  python scripts/run_tests.py smoke-llm")
    print("  python scripts/run_tests.py all-smoke")
    print()
    print("Manual one-liners (copy/paste)")
    print("  source .venv/bin/activate && python -m pytest tests/ -q")
    print("  python scripts/smoke_xai.py --via-proxy --debate-session-id debate-abc --side pro")
    print("  python scripts/smoke_llm.py --debate-session-id debate-abc --provider openai")
    print("  python scripts/smoke_inject.py --spawn --debate-session-id debate-abc")
    print("  python scripts/inspect_kb.py --debate-session-id debate-abc")


def run_one(name: str) -> int:
    if name not in TESTS:
        print(f"Unknown test: {name}", file=sys.stderr)
        print("Run without arguments to list available tests.", file=sys.stderr)
        return 1

    info = TESTS[name]
    print(f"\n=== {info['title']} ===")
    print(f"Requires: {info['requires']}")
    print(f"Command:  {info['command']}\n")

    result = subprocess.run(
        info["command"],
        cwd=info["cwd"],
        shell=info.get("shell", False),
    )
    if result.returncode != 0:
        print(f"\nFAILED: {name} (exit {result.returncode})", file=sys.stderr)
        return result.returncode
    print(f"\nPASSED: {name}")
    return 0


def run_group(group: str) -> int:
    if group not in GROUPS:
        return 1
    exit_code = 0
    for name in GROUPS[group]:
        code = run_one(name)
        if code != 0:
            exit_code = code
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run proxy unit tests and smoke scripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run with no test name to print the full catalog.",
    )
    parser.add_argument(
        "test",
        nargs="?",
        default="list",
        help="Test name or group (unit, smoke-llm, all-smoke, ...)",
    )
    args = parser.parse_args()

    if args.test in ("list", "help", "-h", "--help"):
        print_catalog()
        return 0

    if args.test in GROUPS:
        return run_group(args.test)

    return run_one(args.test)


if __name__ == "__main__":
    raise SystemExit(main())
