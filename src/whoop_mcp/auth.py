"""OAuth2 credential storage with tiered backend.

Resolution order:
  1. 1Password CLI (`op read 'op://Personal/whoop-mcp/<field>'`)
  2. System keyring (macOS Keychain, Linux secret-service, Windows Credential Manager)
  3. JSON file at ~/.config/whoop-mcp/credentials.json (0700 dir, 0600 file) with warning

Credentials dict shape:
{
    "client_id": str,
    "client_secret": str,
    "refresh_token": str,
    "access_token": str | None,
    "expires_at": float | None,  # unix timestamp
}
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "rdco-whoop-mcp"
KEYRING_USERNAME = "default"

# 1Password vault + item are configurable so users whose vault is not named
# "Personal" (e.g. "Private", a shared vault, or a per-project vault) don't
# have to fork the package. Override via env vars before running setup or the
# server.
OP_VAULT_DEFAULT = "Personal"
OP_ITEM_DEFAULT = "whoop-mcp"


def _op_vault() -> str:
    return os.environ.get("WHOOP_MCP_OP_VAULT") or OP_VAULT_DEFAULT


def _op_item() -> str:
    return os.environ.get("WHOOP_MCP_OP_ITEM") or OP_ITEM_DEFAULT

CONFIG_DIR = Path.home() / ".config" / "whoop-mcp"
CREDS_FILE = CONFIG_DIR / "credentials.json"


def _have_op() -> bool:
    """Detect 1Password CLI availability and active session."""
    if shutil.which("op") is None:
        return False
    try:
        # `op whoami` exits non-zero if not signed in.
        result = subprocess.run(
            ["op", "whoami"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _op_read(field: str) -> str | None:
    """Read a single field from the configured 1Password item."""
    vault = _op_vault()
    item = _op_item()
    ref = f"op://{vault}/{item}/{field}"
    try:
        result = subprocess.run(
            ["op", "read", ref],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("op read %s failed: %s", ref, e)
    return None


def _op_write(field: str, value: str) -> bool:
    """Write a single field to the configured 1Password item.

    Creates the item if absent. Best-effort. Returns True on success.
    """
    vault = _op_vault()
    item = _op_item()
    ref = f"{item}.{field}"
    try:
        edit = subprocess.run(
            ["op", "item", "edit", item, f"{field}={value}", "--vault", vault],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if edit.returncode == 0:
            return True
        # Try create.
        create = subprocess.run(
            [
                "op", "item", "create",
                "--category", "API Credential",
                "--title", item,
                "--vault", vault,
                f"{field}={value}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return create.returncode == 0
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("op write %s failed: %s", ref, e)
        return False


def _have_keyring() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


def _keyring_read() -> dict[str, Any] | None:
    try:
        import keyring
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if raw:
            return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        logger.debug("keyring read failed: %s", e)
    return None


def _keyring_write(creds: dict[str, Any]) -> bool:
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, json.dumps(creds))
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("keyring write failed: %s", e)
        return False


def _file_read() -> dict[str, Any] | None:
    if not CREDS_FILE.exists():
        return None
    try:
        with CREDS_FILE.open("r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("credentials file unreadable: %s", e)
        return None


def _file_write(creds: dict[str, Any]) -> bool:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(CONFIG_DIR, 0o700)
        with CREDS_FILE.open("w") as f:
            json.dump(creds, f, indent=2)
        os.chmod(CREDS_FILE, 0o600)
        print(
            "WARNING: Credentials stored in ~/.config/whoop-mcp/credentials.json. "
            "Consider installing 1Password CLI or system keyring for stronger isolation.",
            file=sys.stderr,
        )
        return True
    except OSError as e:
        logger.error("file write failed: %s", e)
        return False


# Public API ----------------------------------------------------------------

CRED_FIELDS = ("client_id", "client_secret", "refresh_token", "access_token", "expires_at")


def get_credentials() -> dict[str, Any] | None:
    """Return the stored credentials dict, or None if nothing is configured."""
    if _have_op():
        creds: dict[str, Any] = {}
        for field in CRED_FIELDS:
            val = _op_read(field)
            if val is not None:
                if field == "expires_at":
                    try:
                        creds[field] = float(val)
                    except ValueError:
                        creds[field] = None
                else:
                    creds[field] = val
        # Require client_id + refresh_token at minimum for a usable backend.
        if creds.get("client_id") and creds.get("refresh_token"):
            return creds

    if _have_keyring():
        kr = _keyring_read()
        if kr and kr.get("client_id") and kr.get("refresh_token"):
            return kr

    fr = _file_read()
    if fr and fr.get("client_id") and fr.get("refresh_token"):
        return fr

    return None


def save_credentials(creds: dict[str, Any]) -> str:
    """Persist credentials to the highest-priority backend available.

    Returns the backend name used: "1password", "keyring", or "file".
    """
    if _have_op():
        ok = True
        for field in CRED_FIELDS:
            val = creds.get(field)
            if val is None:
                continue
            if not _op_write(field, str(val)):
                ok = False
                break
        if ok:
            return "1password"
        logger.warning("1Password write failed; falling through to keyring.")

    if _have_keyring():
        if _keyring_write(creds):
            return "keyring"
        logger.warning("keyring write failed; falling through to file.")

    if _file_write(creds):
        return "file"

    raise RuntimeError("All credential backends failed to write.")


def update_tokens(access_token: str, refresh_token: str, expires_at: float) -> str:
    """Update only the refreshed token fields, preserving client credentials."""
    creds = get_credentials() or {}
    creds["access_token"] = access_token
    creds["refresh_token"] = refresh_token
    creds["expires_at"] = expires_at
    return save_credentials(creds)
