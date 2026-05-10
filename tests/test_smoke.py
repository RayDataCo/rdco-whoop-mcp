"""Smoke tests for whoop-mcp.

The integration test hits the live Whoop API and is gated by:
    WHOOP_INTEGRATION_TEST=1

Run with:
    WHOOP_INTEGRATION_TEST=1 pytest tests/test_smoke.py -s
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest

from whoop_mcp.tools import (
    _to_rfc3339_end,
    _to_rfc3339_start,
    _validate_date_range,
    whoop_get_profile,
    whoop_get_recovery,
)


# Unit tests (always run) ----------------------------------------------------


def test_iso_to_rfc3339_start():
    assert _to_rfc3339_start("2026-05-10") == "2026-05-10T00:00:00.000Z"


def test_iso_to_rfc3339_end():
    assert _to_rfc3339_end("2026-05-10") == "2026-05-10T23:59:59.999Z"


def test_validate_rejects_bad_date():
    with pytest.raises(ValueError):
        _validate_date_range("2026/05/10", "2026-05-11")


def test_validate_rejects_inverted_range():
    with pytest.raises(ValueError):
        _validate_date_range("2026-05-11", "2026-05-10")


def test_validate_accepts_single_day():
    start, end = _validate_date_range("2026-05-10", "2026-05-10")
    assert start.startswith("2026-05-10T00:00:00")
    assert end.startswith("2026-05-10T23:59:59")


# Integration tests (live API) ----------------------------------------------

INTEGRATION = os.environ.get("WHOOP_INTEGRATION_TEST") == "1"
skip_unless_integration = pytest.mark.skipif(
    not INTEGRATION,
    reason="Set WHOOP_INTEGRATION_TEST=1 to run live API smoke tests.",
)


@skip_unless_integration
@pytest.mark.asyncio
async def test_smoke_profile():
    raw = await whoop_get_profile()
    payload = json.loads(raw)
    assert "profile" in payload
    profile = payload["profile"] or {}
    # Whoop profile API returns at minimum a user_id.
    assert profile.get("user_id") is not None
    print(f"\nProfile: {profile}")


@skip_unless_integration
@pytest.mark.asyncio
async def test_smoke_recovery_last_30_days():
    today = date.today()
    start = (today - timedelta(days=30)).isoformat()
    end = today.isoformat()
    raw = await whoop_get_recovery(start, end)
    payload = json.loads(raw)
    assert "records" in payload
    print(f"\nRecovery records in last 30 days: {payload['count']}")
    assert payload["count"] > 0, "Expected at least one recovery record in the last 30 days."
