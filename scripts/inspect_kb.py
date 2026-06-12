#!/usr/bin/env python3
"""Fetch in-memory KB state from the proxy (GET /kb)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.settings import settings  # noqa: E402


def _http_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.proxy_auth_token:
        headers["Authorization"] = f"Bearer {settings.proxy_auth_token}"
    return headers


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect in-memory KB via GET /kb")
    parser.add_argument("--host", default=f"{settings.host}:{settings.port}")
    parser.add_argument(
        "--debate-session-id",
        default=None,
        help="Filter to one debate (e.g. debate-38dac621). Omit to list all debates.",
    )
    args = parser.parse_args()

    params = {}
    if args.debate_session_id:
        params["debate_session_id"] = args.debate_session_id

    url = f"http://{args.host}/kb"
    response = httpx.get(url, params=params, headers=_http_headers(), timeout=30.0)
    print(f"GET {response.request.url} -> {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)
        return 1

    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
