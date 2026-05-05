"""OpenF1 client + snapshot extraction.

This module is the part that *stays the same* when we move to hardware.
Right now it's called by main.py to render locally. Later, a tiny daemon
will call the same functions and POST the resulting snapshot dict over
WiFi to the ESP32.
"""
from datetime import datetime, timezone

import requests

OPENF1 = "https://api.openf1.org/v1"


def _get(endpoint: str, **params) -> list[dict]:
    """Fetch a JSON list from an OpenF1 endpoint.

    OpenF1 quirk: a query that matches zero rows returns HTTP 404 instead
    of an empty array. We normalize that to [] so callers can just check
    list length.
    """
    r = requests.get(f"{OPENF1}/{endpoint}", params=params, timeout=15)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


def _safe_float(v) -> float | None:
    """OpenF1 sometimes returns 'interval' as a string like '+1 LAP'."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_iso(s: str) -> datetime | None:
    """Parse an OpenF1 ISO timestamp (handles both 'Z' and '+00:00')."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _has_lap_data(session_key: int, driver_number: int | None = None) -> bool:
    """Cheap probe: is there lap data for this session (and optionally driver)?"""
    params = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    return len(_get("laps", **params)) > 0


def latest_race_session(driver_number: int | None = None) -> dict:
    """Most recently completed race session that actually has data.

    OpenF1 returns scheduled-but-not-yet-run sessions too, and recent
    races often take hours/days to fully populate per-driver telemetry.
    We walk backwards from the newest race until we find one with real
    lap data for the driver we care about.
    """
    sessions = _get("sessions", session_type="Race")
    now = datetime.now(timezone.utc)

    # Keep only races whose scheduled end is in the past, sorted newest first.
    completed = [
        s for s in sessions
        if (end := _parse_iso(s.get("date_end"))) and end < now
    ]
    completed.sort(key=lambda s: s["date_start"], reverse=True)

    for s in completed:
        if _has_lap_data(s["session_key"], driver_number):
            return s
        who = f"driver #{driver_number}" if driver_number else "any driver"
        print(f"      skipping {s['circuit_short_name']} {s['year']} (no data for {who} yet)")

    raise RuntimeError("no completed race session with lap data found")


def session_by_key(session_key: int) -> dict | None:
    """Look up a specific session by its OpenF1 key."""
    sessions = _get("sessions", session_key=session_key)
    return sessions[0] if sessions else None


def driver_info(session_key: int, driver_number: int) -> dict:
    """3-letter code, team name, team colour."""
    drivers = _get("drivers", session_key=session_key, driver_number=driver_number)
    return drivers[0] if drivers else {}


def race_data(session_key: int, driver_number: int) -> dict:
    """Pre-fetch everything we need to replay this driver's race.

    Bundling all calls up front means the render loop never blocks on the
    network — a pattern that'll matter even more on a tiny ESP32.
    """
    return {
        "laps":      _get("laps",      session_key=session_key, driver_number=driver_number),
        "intervals": _get("intervals", session_key=session_key, driver_number=driver_number),
        "stints":    _get("stints",    session_key=session_key, driver_number=driver_number),
        "position":  _get("position",  session_key=session_key, driver_number=driver_number),
        "driver":    driver_info(session_key, driver_number),
    }


def max_lap(data: dict) -> int:
    """Highest lap number we have data for."""
    return max(
        (l["lap_number"] for l in data["laps"] if l.get("lap_number")),
        default=0,
    )


def snapshot_at_lap(data: dict, lap: int) -> dict | None:
    """Build a 'pit-wall snapshot' for a given lap number.

    The dict returned here is exactly what we'll later POST as JSON to the
    ESP32 — keep it small and primitive-typed.
    """
    laps_for_n = [l for l in data["laps"] if l.get("lap_number") == lap]
    if not laps_for_n:
        return None
    lap_row = laps_for_n[0]
    cutoff = lap_row.get("date_start")

    # Tyre stint covering this lap
    stint = next(
        (s for s in data["stints"] if s["lap_start"] <= lap <= s["lap_end"]),
        None,
    )

    # Latest interval entry at or before this lap began
    interval_entry = None
    if cutoff:
        prior = [i for i in data["intervals"] if i.get("date") and i["date"] <= cutoff]
        if prior:
            interval_entry = max(prior, key=lambda x: x["date"])

    # Latest position entry at or before this lap began
    position_entry = None
    if cutoff:
        prior = [p for p in data["position"] if p.get("date") and p["date"] <= cutoff]
        if prior:
            position_entry = max(prior, key=lambda x: x["date"])

    return {
        "lap":        lap,
        "position":   position_entry["position"] if position_entry else 0,
        "interval":   _safe_float(interval_entry.get("interval"))      if interval_entry else None,
        "to_leader":  _safe_float(interval_entry.get("gap_to_leader")) if interval_entry else 0,
        "compound":   stint["compound"] if stint else "",
        "stint_lap":  (lap - stint["lap_start"] + 1) if stint else 0,
        "code":       data["driver"].get("name_acronym", ""),
        "team_color": data["driver"].get("team_colour", ""),
    }