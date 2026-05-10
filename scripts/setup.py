"""Interactive setup wizard for whoop-mcp.

Walks the user through:
  1. Creating an OAuth app at developer.whoop.com (instructions printed)
  2. Pasting Client ID + Client Secret
  3. Authorization-code OAuth flow (browser + local callback on 127.0.0.1:53682)
  4. Token storage via the auth abstraction
  5. Smoke-test against /v2/user/profile/basic
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from typing import Any

import httpx

from whoop_mcp import auth
from whoop_mcp.client import (
    WHOOP_OAUTH_AUTH_URL,
    WHOOP_OAUTH_TOKEN_URL,
    WhoopClient,
)

REDIRECT_HOST = "127.0.0.1"
# Port 53682 chosen to match the gcloud / many-OAuth-CLI default. Uncommon enough
# to rarely collide with dev tools (vs the heavily-used 8080), high enough to
# avoid privileged-port issues, deterministic so it can be pre-registered as the
# Whoop OAuth app's redirect URI. Override with WHOOP_MCP_REDIRECT_PORT env var
# if the chosen port is in use locally; you must then add the corresponding
# http://127.0.0.1:<port>/callback URI to your Whoop OAuth app config.
REDIRECT_PORT = int(os.environ.get("WHOOP_MCP_REDIRECT_PORT", "53682"))
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

# Whoop API v2 read scopes.
SCOPES = [
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:profile",
    "read:body_measurement",
    "offline",
]


def _print_app_setup_instructions() -> None:
    print("=" * 72)
    print("STEP 1: Create your OAuth app at developer.whoop.com")
    print("=" * 72)
    print(
        "\n"
        "  1. Go to https://developer.whoop.com/ and sign in with your Whoop account.\n"
        "  2. Create a new app (any name, e.g. 'personal-mcp').\n"
        f"  3. Add this exact Redirect URI:  {REDIRECT_URI}\n"
        "  4. Request the following scopes:\n"
        f"       {', '.join(SCOPES)}\n"
        "  5. Save the app, then copy the Client ID and Client Secret below.\n"
    )


def _prompt(label: str, secret: bool = False) -> str:
    if secret:
        import getpass
        return getpass.getpass(f"{label}: ").strip()
    return input(f"{label}: ").strip()


def _make_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """One-shot HTTP handler that captures the OAuth redirect params."""

    captured: dict[str, Any] = {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return
        params = dict(urllib.parse.parse_qsl(parsed.query))
        _CallbackHandler.captured.update(params)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<html><body style='font-family:system-ui;padding:2rem;'>"
            "<h2>whoop-mcp authorized.</h2>"
            "<p>You can close this tab and return to your terminal.</p>"
            "</body></html>"
        )
        self.wfile.write(body.encode())

    def log_message(self, *_args: Any) -> None:  # noqa: ANN401
        return  # silence access log


def _wait_for_code(timeout: float = 300.0) -> dict[str, str]:
    server = http.server.HTTPServer((REDIRECT_HOST, REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while thread.is_alive() and time.time() < deadline:
        time.sleep(0.25)
    server.server_close()
    if not _CallbackHandler.captured:
        raise TimeoutError("OAuth callback never received.")
    return dict(_CallbackHandler.captured)


def _build_authorize_url(client_id: str, state: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{WHOOP_OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    code_verifier: str,
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            WHOOP_OAUTH_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def _smoke_test() -> None:
    async with WhoopClient() as client:
        profile = await client.get_profile()
    print("\nSmoke test passed.")
    basic = profile.get("profile") or {}
    name = " ".join(filter(None, [basic.get("first_name"), basic.get("last_name")])) or "(no name)"
    print(f"  Authenticated as: {name}")
    if email := basic.get("email"):
        print(f"  Email: {email}")
    if user_id := basic.get("user_id"):
        print(f"  User ID: {user_id}")


def main() -> None:
    print("\nwhoop-mcp setup wizard\n")
    _print_app_setup_instructions()

    client_id = _prompt("Paste your Whoop Client ID")
    client_secret = _prompt("Paste your Whoop Client Secret", secret=True)
    if not (client_id and client_secret):
        print("ERROR: Client ID and Client Secret are required.", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 72)
    print("STEP 2: Authorize the app in your browser")
    print("=" * 72)
    state = secrets.token_urlsafe(24)
    code_verifier, code_challenge = _make_pkce_pair()
    auth_url = _build_authorize_url(client_id, state, code_challenge)
    print(f"\n  Opening: {auth_url}\n")
    print(f"  If the browser does not open, copy that URL manually.\n")
    webbrowser.open(auth_url)

    try:
        params = _wait_for_code()
    except TimeoutError:
        print("ERROR: Timed out waiting for the OAuth callback.", file=sys.stderr)
        sys.exit(1)

    if params.get("state") != state:
        print("ERROR: OAuth state mismatch. Aborting.", file=sys.stderr)
        sys.exit(1)
    if "error" in params:
        print(f"ERROR from Whoop: {params['error']} {params.get('error_description', '')}", file=sys.stderr)
        sys.exit(1)
    code = params.get("code")
    if not code:
        print("ERROR: No authorization code returned.", file=sys.stderr)
        sys.exit(1)

    print("Exchanging code for tokens.")
    tokens = _exchange_code(code, client_id, client_secret, code_verifier)
    creds = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tokens["refresh_token"],
        "access_token": tokens["access_token"],
        "expires_at": time.time() + float(tokens.get("expires_in", 3600)),
    }
    backend = auth.save_credentials(creds)
    print(f"Credentials stored via backend: {backend}")

    print("\n" + "=" * 72)
    print("STEP 3: Smoke test")
    print("=" * 72)
    asyncio.run(_smoke_test())

    print("\nAll set. You can now register the MCP with Claude Code:\n")
    print('  claude mcp add whoop -- uvx --from rdco-whoop-mcp whoop-mcp-server\n')


if __name__ == "__main__":
    main()
