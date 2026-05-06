"""Entry point for the laptop pit wall.

Usage:
    python main.py                  # auto: live if a session is running, else replay
    python main.py --replay         # force replay
    python main.py --live           # force live (errors if no session running)
    python main.py --driver 4       # follow a specific driver (default 4 = NOR)
    python main.py --speed 30       # replay speed multiplier (default 30x)
    python main.py --session 9839   # specific session_key (replay)

Controls:
    SPACE       pause/resume (replay only)
    LEFT/RIGHT  scrub one lap (replay only)
    HOME/END    jump to first / last lap (replay only)
    TAB         cycle screens (PIT WALL <-> STANDINGS)
    1, 2        jump directly to screen 1 / 2
    Q or ESC    quit
"""
import argparse
import sys
import time

import pygame

from data import (
    latest_race_session,
    session_by_key,
    live_session,
    race_data,
    snapshot_at_lap,
    max_lap,
)
from render import Compositor, W, H

SCALE = 3
WINDOW = (W * SCALE, H * SCALE)

REAL_LAP_SECONDS = 90.0   # nominal; --speed scales how fast we step laps
LIVE_POLL_SEC    = 5.0    # don't hammer OpenF1 in live mode


def parse_args():
    p = argparse.ArgumentParser(description="F1 pit wall - laptop edition")
    p.add_argument("--driver",  type=int,   default=4)
    p.add_argument("--speed",   type=float, default=30.0)
    p.add_argument("--session", type=int)
    p.add_argument("--live",    action="store_true", help="force live mode")
    p.add_argument("--replay",  action="store_true", help="force replay mode")
    return p.parse_args()


def resolve_mode(args):
    """Decide live vs replay and pick the session."""
    if args.session:
        s = session_by_key(args.session)
        if not s:
            print(f"no session with key {args.session}", file=sys.stderr)
            sys.exit(1)
        print(f"      {s['session_name']} @ {s['circuit_short_name']} {s['year']}  (key={s['session_key']})")
        return "replay", s

    if args.live:
        s = live_session()
        if not s:
            print("--live requested but no session is currently running", file=sys.stderr)
            sys.exit(1)
        print(f"      LIVE: {s['session_name']} @ {s['circuit_short_name']} {s['year']}")
        return "live", s

    if not args.replay:
        # auto-detect: prefer live if available
        s = live_session()
        if s:
            print(f"      LIVE: {s['session_name']} @ {s['circuit_short_name']} {s['year']}")
            return "live", s

    s = latest_race_session(args.driver)
    print(f"      {s['session_name']} @ {s['circuit_short_name']} {s['year']}  (key={s['session_key']})")
    return "replay", s


def main():
    args = parse_args()

    print("[1/2] resolving session...")
    mode, session = resolve_mode(args)
    sk = session["session_key"]
    circuit = session["circuit_short_name"]

    print(f"[2/2] fetching driver #{args.driver} race data...")
    data = race_data(sk, args.driver)
    if not data["laps"]:
        print(f"no lap data for driver #{args.driver} in this session", file=sys.stderr)
        sys.exit(1)
    final_lap = max_lap(data)
    code = data["driver"].get("name_acronym", "?")
    total_laps = session.get("total_laps") or final_lap
    print(f"      driver {code}, {final_lap} laps available")
    print()
    print("controls: SPACE pause | <-/-> scrub | TAB cycle | 1/2 screen | Q quit")

    pygame.init()
    pygame.display.set_caption(f"F1 Pit Wall - {circuit} ({code}) [{mode.upper()}]")
    screen = pygame.display.set_mode(WINDOW)
    canvas = pygame.Surface((W, H))
    compositor = Compositor()
    clock = pygame.time.Clock()

    lap = 1 if mode == "replay" else final_lap
    paused = False
    step_interval = REAL_LAP_SECONDS / args.speed
    last_step = time.time()
    last_poll = time.time()

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif ev.key == pygame.K_TAB:
                    compositor.cycle()
                elif ev.key == pygame.K_1:
                    compositor.set_index(0)
                elif ev.key == pygame.K_2:
                    compositor.set_index(1)
                elif mode == "replay":
                    if ev.key == pygame.K_SPACE:
                        paused = not paused
                    elif ev.key == pygame.K_RIGHT:
                        lap = min(final_lap, lap + 1); last_step = time.time()
                    elif ev.key == pygame.K_LEFT:
                        lap = max(1, lap - 1); last_step = time.time()
                    elif ev.key == pygame.K_HOME:
                        lap = 1; last_step = time.time()
                    elif ev.key == pygame.K_END:
                        lap = final_lap; last_step = time.time()

        # Replay auto-advance
        if mode == "replay" and not paused and lap < final_lap:
            if time.time() - last_step >= step_interval:
                lap += 1
                last_step = time.time()

        # Live re-poll
        if mode == "live" and time.time() - last_poll >= LIVE_POLL_SEC:
            try:
                fresh = race_data(sk, args.driver)
                if fresh["laps"]:
                    data = fresh
                    final_lap = max_lap(data)
                    lap = final_lap
            except Exception as e:
                print(f"[live poll] {e}", file=sys.stderr)
            last_poll = time.time()

        snap = snapshot_at_lap(data, lap)
        if snap:
            compositor.draw(canvas, snap, circuit, mode, total_laps)

        scaled = pygame.transform.scale(canvas, WINDOW)
        screen.blit(scaled, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
