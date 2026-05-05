"""Entry point for the laptop pit wall.

Usage:
    python main.py                     # replay the most recent race
    python main.py --driver 1          # follow a different driver (1=Verstappen)
    python main.py --speed 60          # 60x replay speed (default 30x)
    python main.py --session 9839      # specific OpenF1 session_key

Controls (window must have focus):
    SPACE       pause/resume
    LEFT/RIGHT  scrub one lap
    HOME/END    jump to first / last lap
    Q or ESC    quit
"""
import argparse
import sys
import time

import pygame

from data import (
    latest_race_session,
    session_by_key,
    race_data,
    snapshot_at_lap,
    max_lap,
)
from render import Renderer, W, H

SCALE = 3
WINDOW = (W * SCALE, H * SCALE)

# Approximate seconds per lap of real time. Doesn't have to be exact -
# `--speed` is the multiplier you actually feel.
REAL_LAP_SECONDS = 90.0


def parse_args():
    p = argparse.ArgumentParser(description="F1 pit wall - laptop edition")
    p.add_argument("--driver",  type=int,   default=4,
                   help="driver number (default 4=NOR)")
    p.add_argument("--speed",   type=float, default=30.0,
                   help="replay speed multiplier (default 30x)")
    p.add_argument("--session", type=int,
                   help="specific OpenF1 session_key (default: latest race)")
    return p.parse_args()


def main():
    args = parse_args()

    print("[1/2] resolving session...")
    session = session_by_key(args.session) if args.session else latest_race_session(args.driver)
    if not session:
        print(f"no session found for key {args.session}", file=sys.stderr)
        sys.exit(1)
    sk = session["session_key"]
    circuit = session["circuit_short_name"]
    print(f"      {session['session_name']} @ {circuit} {session['year']}  (key={sk})")

    print(f"[2/2] fetching driver #{args.driver} race data...")
    data = race_data(sk, args.driver)
    if not data["laps"]:
        print("no lap data - wrong driver number, or session not started?",
              file=sys.stderr)
        sys.exit(1)
    final_lap = max_lap(data)
    code = data["driver"].get("name_acronym", "?")
    print(f"      driver {code}, {final_lap} laps available")
    print()
    print("controls: SPACE pause | <-/-> scrub | HOME/END jump | Q quit")

    pygame.init()
    pygame.display.set_caption(f"F1 Pit Wall - {circuit} ({code})")
    screen = pygame.display.set_mode(WINDOW)
    canvas = pygame.Surface((W, H))
    renderer = Renderer()
    clock = pygame.time.Clock()

    lap = 1
    paused = False
    step_interval = REAL_LAP_SECONDS / args.speed
    last_step = time.time()

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_RIGHT:
                    lap = min(final_lap, lap + 1); last_step = time.time()
                elif ev.key == pygame.K_LEFT:
                    lap = max(1, lap - 1); last_step = time.time()
                elif ev.key == pygame.K_HOME:
                    lap = 1; last_step = time.time()
                elif ev.key == pygame.K_END:
                    lap = final_lap; last_step = time.time()

        # auto-advance one lap per step_interval seconds of wall clock
        if not paused and lap < final_lap and time.time() - last_step >= step_interval:
            lap += 1
            last_step = time.time()

        snap = snapshot_at_lap(data, lap)
        if snap:
            renderer.draw(canvas, snap, circuit)

        # Render at native 320x170, upscale 3x to the window.
        # This is what gives the chunky LCD-pixel look and keeps the
        # rendering code identical to what we'll port to the TFT.
        scaled = pygame.transform.scale(canvas, WINDOW)
        screen.blit(scaled, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()