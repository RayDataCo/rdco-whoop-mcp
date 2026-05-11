"""MCP tool definitions for the Whoop server."""

from __future__ import annotations

import json
from datetime import datetime, time, timezone
from typing import Any

from .client import WhoopClient

ISO_DATE_FMT = "%Y-%m-%d"


def _to_rfc3339_start(date_str: str) -> str:
    """YYYY-MM-DD -> 2026-05-10T00:00:00.000Z (UTC start of day)."""
    d = datetime.strptime(date_str, ISO_DATE_FMT).date()
    dt = datetime.combine(d, time.min, tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _to_rfc3339_end(date_str: str) -> str:
    """YYYY-MM-DD -> 2026-05-10T23:59:59.999Z (UTC end of day)."""
    d = datetime.strptime(date_str, ISO_DATE_FMT).date()
    dt = datetime.combine(d, time.max, tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.999Z")


def _validate_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    try:
        start_dt = datetime.strptime(start_date, ISO_DATE_FMT)
        end_dt = datetime.strptime(end_date, ISO_DATE_FMT)
    except ValueError as e:
        raise ValueError(
            f"Dates must be ISO YYYY-MM-DD. Got start={start_date!r}, end={end_date!r}: {e}"
        ) from e
    if end_dt < start_dt:
        raise ValueError(f"end_date {end_date} is before start_date {start_date}")
    return _to_rfc3339_start(start_date), _to_rfc3339_end(end_date)


# Tool implementations -------------------------------------------------------

async def whoop_get_recovery(start_date: str, end_date: str) -> str:
    """Recovery records (HRV, RHR, recovery score) for the date range."""
    start, end = _validate_date_range(start_date, end_date)
    async with WhoopClient() as client:
        records = await client.get_recovery(start, end)
    return json.dumps({"count": len(records), "records": records}, indent=2)


async def whoop_get_sleep(start_date: str, end_date: str) -> str:
    """Sleep records (stages, efficiency, debt, performance) for the date range."""
    start, end = _validate_date_range(start_date, end_date)
    async with WhoopClient() as client:
        records = await client.get_sleep(start, end)
    return json.dumps({"count": len(records), "records": records}, indent=2)


async def whoop_get_strain(start_date: str, end_date: str) -> str:
    """Day-strain cycle records (day strain, max HR, calories, average HR)."""
    start, end = _validate_date_range(start_date, end_date)
    async with WhoopClient() as client:
        records = await client.get_strain(start, end)
    return json.dumps({"count": len(records), "records": records}, indent=2)


async def whoop_get_workouts(start_date: str, end_date: str) -> str:
    """Workout records (sport, duration, strain, calories) for the date range."""
    start, end = _validate_date_range(start_date, end_date)
    async with WhoopClient() as client:
        records = await client.get_workouts(start, end)
    return json.dumps({"count": len(records), "records": records}, indent=2)


async def whoop_get_profile() -> str:
    """User profile: name, member-since, height, weight, baseline metrics."""
    async with WhoopClient() as client:
        profile = await client.get_profile()
    return json.dumps(profile, indent=2)


async def whoop_get_body_measurements(start_date: str, end_date: str) -> str:
    """Fetch historical body-composition measurements (height, weight,
    max_heart_rate) for the given date range. Returns JSON with paginated
    records. Date format: YYYY-MM-DD.

    Note: as of Whoop API v2, the body-measurement endpoint typically returns
    the latest single record rather than a true historical series. The date
    range is sent as a best-effort filter.
    """
    start, end = _validate_date_range(start_date, end_date)
    async with WhoopClient() as client:
        records = await client.get_body_measurements(start, end)
    return json.dumps({"count": len(records), "records": records}, indent=2)


# Tool registry consumed by server.py ---------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "whoop_get_recovery",
        "description": (
            "Fetch Whoop recovery records (HRV, resting heart rate, recovery score, "
            "associated sleep_id and cycle_id) for a date range. "
            "Dates are ISO YYYY-MM-DD and inclusive."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": whoop_get_recovery,
    },
    {
        "name": "whoop_get_sleep",
        "description": (
            "Fetch Whoop sleep records (stages breakdown, efficiency, sleep debt, "
            "sleep performance) for a date range. Dates are ISO YYYY-MM-DD."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": whoop_get_sleep,
    },
    {
        "name": "whoop_get_strain",
        "description": (
            "Fetch Whoop daily cycle records (day strain, max HR, average HR, calories) "
            "for a date range. Dates are ISO YYYY-MM-DD."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": whoop_get_strain,
    },
    {
        "name": "whoop_get_workouts",
        "description": (
            "Fetch Whoop workout records (sport, duration, strain, calories) "
            "for a date range. Dates are ISO YYYY-MM-DD."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": whoop_get_workouts,
    },
    {
        "name": "whoop_get_profile",
        "description": (
            "Fetch the authenticated Whoop user's profile and body measurements "
            "(name, email, height, weight, max heart rate)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "handler": whoop_get_profile,
    },
    {
        "name": "whoop_get_body_measurements",
        "description": (
            "Fetch historical body-composition measurements (height, weight, "
            "max_heart_rate) for a date range. Dates are ISO YYYY-MM-DD. "
            "Note: Whoop API v2 currently returns the latest record rather than "
            "a true series; the date range is a best-effort filter."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": whoop_get_body_measurements,
    },
]
