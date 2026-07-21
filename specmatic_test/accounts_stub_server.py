#!/usr/bin/env python3
"""
accounts_stub_server.py
-----------------------
A lightweight HTTP stub server that acts as a "Server Under Test" for
Specmatic contract testing in TEST mode.

Architecture:
    [specmatic test (Docker)] ──GET /v1/accounts──▶ [This server :3000]
                                                         ↓
                                              Responds with fixture data
                                                         ↓
                              [Specmatic validates response vs contract]

This is the OPPOSITE of the mock server in unit_tests/specmatic/server.py:
    - server.py    → Specmatic IS the server (mock mode, port 9000)
    - this file    → Python IS the server (test mode target, port 3000)

Usage:
    python specmatic_test/accounts_stub_server.py [--port 3000]

Then in a separate terminal run run_contract_test.ps1 or:
    docker run --rm \
      -v "${PWD}:/usr/src/app" \
      -v "${env:USERPROFILE}/.specmatic:/root/.specmatic" \
      -w /usr/src/app \
      specmatic/specmatic:2.50.1 test \
      --host=host.docker.internal --port=3000 \
      --config specmatic-accounts-test.yaml \
      --timeout=30
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Fixture data — mirrors test_accounts.py fixture data, but spec-compliant
# ---------------------------------------------------------------------------

_ACCOUNTS = [
    {
        "id": "acct_1G9HZLIEn49ers",
        "object": "account",
        "email": "test@example.com",
        "type": "standard",
        "created": 1580000000,
        "country": "US",
    },
    {
        "id": "acct_2H0IALJFo50fts",
        "object": "account",
        "email": "second@example.com",
        "type": "express",
        "created": 1581000000,
        "country": "GB",
    },
    {
        "id": "acct_3I1JBMKGp61gut",
        "object": "account",
        "email": "third@example.com",
        "type": "custom",
        "created": 1582000000,
        "country": "DE",
    },
]


def _build_list_response(data: list, has_more: bool, url: str) -> dict:
    return {
        "object": "list",
        "data": data,
        "has_more": has_more,
        "url": url,
    }


def _paginate(items: list, limit: int, starting_after: str | None):
    """Applies Stripe-style cursor pagination to a list of items."""
    if starting_after:
        # Find the index of the item whose id == starting_after, start after it
        start_idx = next(
            (i + 1 for i, item in enumerate(items) if item["id"] == starting_after),
            len(items),
        )
        items = items[start_idx:]

    page = items[:limit]
    has_more = len(items) > limit
    return page, has_more


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class AccountsStubHandler(BaseHTTPRequestHandler):
    """Handles all incoming HTTP requests from Specmatic test runner."""

    def log_message(self, fmt, *args):
        """Override to prefix log lines clearly."""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[stub-server {timestamp}] {fmt % args}")

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, status: int, error_type: str, message: str, code: str = None):
        body = {"error": {"type": error_type, "message": message}}
        if code:
            body["error"]["code"] = code
        self._send_json(status, body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # ------------------------------------------------------------------
        # GET /v1/accounts  — main endpoint under contract test
        # ------------------------------------------------------------------
        if path == "/v1/accounts":

            # ── 400: Invalid limit value ────────────────────────────────
            # Spec example "bad_limit" sends limit=0.
            # We check BEFORE auth so limit errors always return 400.
            raw_limit = params.get("limit", [None])[0]
            if raw_limit is not None:
                try:
                    limit_int = int(raw_limit)
                except ValueError:
                    self._send_error(400, "invalid_request_error",
                                     f"Invalid integer: '{raw_limit}' is not a valid integer.")
                    return
                if limit_int < 1 or limit_int > 100:
                    self._send_error(400, "invalid_request_error",
                                     f"Invalid integer: {limit_int} is not within the allowed range [1, 100].",
                                     code="parameter_invalid_integer")
                    return
                limit = limit_int
            else:
                limit = 100  # Stripe default

            # ── 401: Invalid / missing API key ──────────────────────────
            # Spec example "no_auth" sends Authorization: Bearer invalid_key_12345.
            auth_header = self.headers.get("Authorization", "")
            if auth_header == "Bearer invalid_key_12345":
                self._send_error(401, "invalid_request_error",
                                 f"No such API key: {auth_header}.",
                                 code="api_key_missing")
                return

            # ── 200: Successful paginated response ──────────────────────
            starting_after = params.get("starting_after", [None])[0]
            page, has_more = _paginate(_ACCOUNTS, limit, starting_after)

            self._send_json(200, _build_list_response(
                data=page,
                has_more=has_more,
                url="/v1/accounts",
            ))
            return

        # ------------------------------------------------------------------
        # Health check — used by run_contract_test.ps1 to know when ready
        # ------------------------------------------------------------------
        if path in ("/health", "/actuator/health"):
            self._send_json(200, {"status": "UP"})
            return

        if path == "/actuator/mappings":
            mappings = {
                "contexts": {
                    "application": {
                        "mappings": {
                            "dispatcherServlets": {
                                "dispatcherServlet": [
                                    {
                                        "handler": "AccountsController#getV1Accounts",
                                        "predicate": "{GET [/v1/accounts]}",
                                        "details": {
                                            "requestMappingConditions": {
                                                "methods": ["GET"],
                                                "patterns": ["/v1/accounts"]
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            }
            self._send_json(200, mappings)
            return

        # ------------------------------------------------------------------
        # Catch-all — return 404 for any other path
        # ------------------------------------------------------------------
        self._send_error(404, "resource_missing",
                         f"No stub defined for path '{path}'.")

    def do_OPTIONS(self):
        """Support CORS preflight for any browser-based tooling."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Accounts stub server for Specmatic contract tests.")
    parser.add_argument("--port", type=int, default=3000, help="Port to listen on (default: 3000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), AccountsStubHandler)

    print("=" * 60)
    print("  Accounts Stub Server — Specmatic Contract Test Target")
    print("=" * 60)
    print(f"  Listening on : http://{args.host}:{args.port}")
    print(f"  Endpoint     : GET /v1/accounts")
    print(f"  Health check : GET /health")
    print()
    print("  When this server is running, execute in another terminal:")
    print("  > .\\run_contract_test.ps1")
    print("=" * 60)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[stub-server] Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
