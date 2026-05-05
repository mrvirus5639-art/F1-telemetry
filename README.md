# F1 Pit Wall — Laptop Edition

A small pygame app that replays an F1 race, showing one driver's position,
tyre, and gap data — pixel-mapped to the 320×170 ESP32 TFT we'll port this
to next.

## Setup (Windows / VS Code)

```powershell
cd pitwall
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
python main.py                  # latest race, driver 4 (Norris), 30x speed
python main.py --driver 1       # Verstappen
python main.py --speed 60       # faster replay
python main.py --session 9839   # specific OpenF1 session
```

First run takes a few seconds to fetch the race data, then the window opens
and the lap counter starts ticking.

## Controls

| Key             | Action                  |
| --------------- | ----------------------- |
| SPACE           | pause / resume          |
| ← / →           | scrub one lap           |
| HOME / END      | jump to lap 1 / final   |
| Q or ESC        | quit                    |

## File map (and why it's split this way)

- **`data.py`** — OpenF1 client. Stays the same when we move to ESP32; it
  becomes the heart of the laptop daemon that pushes data over WiFi.
- **`render.py`** — pygame renderer. Becomes the firmware. Every
  `pygame.draw.X` call has a 1-to-1 TFT_eSPI equivalent in C++.
- **`main.py`** — event loop and replay logic. The only file that gets
  thrown away on the hardware port (replaced by a tiny push loop on the
  laptop side and the firmware's web server on the ESP32 side).

## Common driver numbers

1 — Verstappen · 4 — Norris · 16 — Leclerc · 44 — Hamilton · 63 — Russell ·
81 — Piastri

## Finding session keys

Open any of these in a browser and grab a `session_key`:

- All 2025 races: `https://api.openf1.org/v1/sessions?year=2025&session_type=Race`
- All 2024 races: `https://api.openf1.org/v1/sessions?year=2024&session_type=Race`

## Notes

- Historical OpenF1 data is free and unauthenticated. Live timing now requires
  sponsoring the project for an OAuth2 token — we'll add that as an opt-in
  later. Replay covers everything you need for development.
- Some sessions don't have full `intervals` data (qualifying, sprints).
  The renderer falls back to `--.---` for the gap when that happens.
