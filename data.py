"""OpenF1 client + snapshot extraction.

This module is the part that *stays the same* when we move to hardware.
The snapshot dict is small and primitive-typed by design so it later
serializes cleanly to JSON for the laptop -> ESP32 push.
"""
from datetime import datetime, timezone

import requests

OPENF1 = "https://api.openf1.org/v1"

# Rough typical compound life in laps. Used for the tyre wear bar.
# Real-world life varies a lot with track and conditions; these are sensible
# averages based on dry-race stints across recent seasons.
COMPOUND_LIFE = {
    "SOFT":         18,
    "MEDIUM":       28,
    "HARD":         40,
    "INTERMEDIATE": 30,
    "WET":          22,
}


# ---------- low-level HTTP ----------

def _get(endpoint: str, **params) -> list[dict]:
    """Fetch a JSON list from an OpenF1 endpoint.

    OpenF1 quirk: a query that matches zero rows returns HTTP 404 instead
    of an empty array. We normalize to [].
    """
    r = requests.get(f"{OPENF1}/{endpoint}", params=params, timeout=15)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _has_lap_data(session_key: int, driver_number: int | None = None) -> bool:
    params = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    return len(_get("laps", **params)) > 0


# ---------- session resolution ----------

def latest_race_session(driver_number: int | None = None) -> dict:
    """Most recently completed race session that actually has data."""
    sessions = _get("sessions", session_type="Race")
    now = datetime.now(timezone.utc)
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
    sessions = _get("sessions", session_key=session_key)
    return sessions[0] if sessions else None


def live_session() -> dict | None:
    """Find a currently-running session (any type), if any."""
    now = datetime.now(timezone.utc)
    sessions = _get("sessions")
    for s in sessions:
        start = _parse_iso(s.get("date_start"))
        end   = _parse_iso(s.get("date_end"))
        if start and end and start <= now <= end:
            return s
    return None


# ---------- bulk fetch ----------

def race_data(session_key: int, driver_number: int) -> dict:
    """Pre-fetch everything we need.

    Includes per-driver and session-wide data so the render loop never
    blocks on the network.
    """
    return {
        # Per-driver
        "laps":          _get("laps",      session_key=session_key, driver_number=driver_number),
        "intervals":     _get("intervals", session_key=session_key, driver_number=driver_number),
        "stints":        _get("stints",    session_key=session_key, driver_number=driver_number),
        "position":      _get("position",  session_key=session_key, driver_number=driver_number),
        "driver":        _driver_info(session_key, driver_number),
        # Session-wide (for fastest-lap halo, sector colors, standings)
        "all_laps":      _get("laps",      session_key=session_key),
        "all_position":  _get("position",  session_key=session_key),
        "all_intervals": _get("intervals", session_key=session_key),
        "all_stints":    _get("stints",    session_key=session_key),
        "all_drivers":   _get("drivers",   session_key=session_key),
        "all_pit":       _get("pit",       session_key=session_key),
    }


def _driver_info(session_key: int, driver_number: int) -> dict:
    drivers = _get("drivers", session_key=session_key, driver_number=driver_number)
    return drivers[0] if drivers else {}


def max_lap(data: dict) -> int:
    return max(
        (l["lap_number"] for l in data["laps"] if l.get("lap_number")),
        default=0,
    )


# ---------- session-wide computed values ----------

def _fastest_lap(laps: list[dict]) -> dict | None:
    valid = [l for l in laps if l.get("lap_duration") and not l.get("is_pit_out_lap")]
    return min(valid, key=lambda l: l["lap_duration"]) if valid else None


def _fastest_sector(laps: list[dict], sector: int) -> float | None:
    key = f"duration_sector_{sector}"
    times = [l[key] for l in laps if l.get(key) and not l.get("is_pit_out_lap")]
    return min(times) if times else None


# ---------- snapshot ----------

def snapshot_at_lap(data: dict, lap: int) -> dict | None:
    """Build a comprehensive pit-wall snapshot for a given lap number."""
    laps_for_n = [l for l in data["laps"] if l.get("lap_number") == lap]
    if not laps_for_n:
        return None
    lap_row = laps_for_n[0]
    cutoff = lap_row.get("date_start")
    driver_no = data["driver"].get("driver_number")

    # ---- Tyre / stint ----
    stint = next(
        (s for s in data["stints"] if s["lap_start"] <= lap <= s["lap_end"]),
        None,
    )
    compound  = stint["compound"] if stint else ""
    stint_lap = (lap - stint["lap_start"] + 1) if stint else 0
    tyre_life = COMPOUND_LIFE.get(compound, 30)
    tyre_pct  = min(1.0, stint_lap / tyre_life) if compound else 0.0

    # ---- Gaps ----
    interval_entry = _latest_before(data["intervals"], cutoff)
    position_entry = _latest_before(data["position"], cutoff)

    # ---- Lap time + bests (computed up to and including this lap, so as
    #      we scrub backwards the bests reflect what was known at that moment) ----
    lap_time = lap_row.get("lap_duration")

    all_laps_so_far = [
        l for l in data["all_laps"]
        if l.get("lap_number") and l["lap_number"] <= lap
    ]
    driver_laps_so_far = [
        l for l in data["laps"]
        if l.get("lap_number") and l["lap_number"] <= lap
    ]

    sess_fl = _fastest_lap(all_laps_so_far)
    sess_best = sess_fl["lap_duration"] if sess_fl else None
    has_fl = bool(sess_fl and sess_fl.get("driver_number") == driver_no)

    pb_lap = _fastest_lap(driver_laps_so_far)
    pb_time = pb_lap["lap_duration"] if pb_lap else None

    # ---- Sectors with colors ----
    sectors = []
    for n in (1, 2, 3):
        key = f"duration_sector_{n}"
        t = lap_row.get(key)
        col = "grey"
        if t:
            sb = _fastest_sector(all_laps_so_far, n)
            pb = _fastest_sector(driver_laps_so_far, n)
            # 1ms tolerance so floating-point edge cases don't miss the highlight
            if sb is not None and t <= sb + 1e-3:
                col = "purple"
            elif pb is not None and t <= pb + 1e-3:
                col = "green"
            else:
                col = "yellow"
        sectors.append({"time": t, "color": col})

    # ---- Pit status ----
    pit_status = "ON_TRACK"
    if lap_row.get("is_pit_out_lap"):
        pit_status = "OUT_LAP"
    pit_this_lap = next(
        (p for p in data["all_pit"]
         if p.get("driver_number") == driver_no and p.get("lap_number") == lap),
        None,
    )
    if pit_this_lap:
        pit_status = "IN_PIT"

    # ---- Standings ----
    standings = _standings_at_cutoff(
        data["all_position"],
        data["all_intervals"],
        data["all_stints"],
        data["all_drivers"],
        lap,
        cutoff,
    )

    return {
        "lap":             lap,
        "position":        position_entry["position"] if position_entry else 0,
        "interval":        _safe_float(interval_entry.get("interval"))      if interval_entry else None,
        "to_leader":       _safe_float(interval_entry.get("gap_to_leader")) if interval_entry else 0,
        "compound":        compound,
        "stint_lap":       stint_lap,
        "tyre_pct":        tyre_pct,
        "code":            data["driver"].get("name_acronym", ""),
        "team_color":      data["driver"].get("team_colour", ""),
        "lap_time":        lap_time,
        "session_best":    sess_best,
        "personal_best":   pb_time,
        "delta_to_best":   (lap_time - sess_best) if (lap_time and sess_best) else None,
        "sectors":         sectors,
        "pit_status":      pit_status,
        "has_fastest_lap": has_fl,
        "standings":       standings,
    }


def _latest_before(rows: list[dict], cutoff: str | None) -> dict | None:
    if not cutoff:
        return None
    prior = [r for r in rows if r.get("date") and r["date"] <= cutoff]
    return max(prior, key=lambda x: x["date"]) if prior else None


def _standings_at_cutoff(all_position, all_intervals, all_stints, all_drivers, lap, cutoff):
    """Top-N standings at this moment in the race."""
    if not cutoff:
        return []

    # Latest position per driver before cutoff
    by_driver_pos: dict[int, dict] = {}
    for p in all_position:
        if not (p.get("date") and p["date"] <= cutoff):
            continue
        dn = p.get("driver_number")
        if dn is None:
            continue
        existing = by_driver_pos.get(dn)
        if existing is None or p["date"] > existing["date"]:
            by_driver_pos[dn] = p

    # Latest interval per driver before cutoff
    by_driver_int: dict[int, dict] = {}
    for i in all_intervals:
        if not (i.get("date") and i["date"] <= cutoff):
            continue
        dn = i.get("driver_number")
        if dn is None:
            continue
        existing = by_driver_int.get(dn)
        if existing is None or i["date"] > existing["date"]:
            by_driver_int[dn] = i

    drivers_by_no = {d["driver_number"]: d for d in all_drivers if "driver_number" in d}

    rows = []
    for dn, p in by_driver_pos.items():
        d = drivers_by_no.get(dn, {})
        stints_d = [s for s in all_stints if s.get("driver_number") == dn]
        stint = next(
            (s for s in stints_d if s["lap_start"] <= lap <= s["lap_end"]),
            None,
        )
        ivl = by_driver_int.get(dn)
        rows.append({
            "position":      p["position"],
            "code":          d.get("name_acronym", ""),
            "team_color":    d.get("team_colour", ""),
            "compound":      stint["compound"] if stint else "",
            "gap_to_leader": _safe_float(ivl.get("gap_to_leader")) if ivl else None,
        })

    rows.sort(key=lambda r: r["position"])
    return rows[:6]
