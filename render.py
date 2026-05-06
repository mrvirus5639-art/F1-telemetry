"""Pygame renderer for the pit wall display.

Two screens, cycled with TAB:
  - FocusScreen     - driver-centric: position, tyre, gaps, lap time, sectors
  - StandingsScreen - top 5 with team colours and gaps

Drawing primitives map 1-to-1 to TFT_eSPI calls so the port to ESP32 is
straightforward. Coordinates are exact panel pixels (320x170).
"""
import pygame

W, H = 320, 170

# ---- Palette ----
BLACK     = (  0,   0,   0)
WHITE     = (255, 255, 255)
LIGHTGREY = (180, 180, 180)
DIM       = ( 95,  95,  95)
GREY_LINE = ( 40,  40,  40)
TEAL      = ( 93, 202, 165)
RED       = (255,  60,  60)
AMBER     = (250, 199, 117)
PURPLE    = (200, 100, 240)
GREEN     = ( 80, 220, 100)
YELLOW    = (250, 220,  80)
LIVE_RED  = (235,  50,  50)

COMPOUND_COLOR = {
    "SOFT":         (255,  60,  60),
    "MEDIUM":       (250, 199, 117),
    "HARD":         (240, 240, 240),
    "INTERMEDIATE": ( 93, 202, 165),
    "WET":          ( 55, 138, 221),
}

SECTOR_COLOR = {
    "purple": PURPLE,
    "green":  GREEN,
    "yellow": YELLOW,
    "grey":   DIM,
}


def parse_hex(s):
    if not s:
        return None
    s = s.strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def fmt_lap(seconds):
    """Format 83.456 -> '1:23.456'. Returns '--.---' for None."""
    if seconds is None:
        return "--.---"
    if seconds < 60:
        return f"{seconds:.3f}"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}"


class Fonts:
    def __init__(self):
        self.huge = pygame.font.SysFont("Consolas", 56, bold=True)
        self.lg   = pygame.font.SysFont("Consolas", 18, bold=True)
        self.md   = pygame.font.SysFont("Consolas", 13, bold=True)
        self.sm   = pygame.font.SysFont("Consolas", 11, bold=True)
        self.xs   = pygame.font.SysFont("Consolas", 9)


def draw_chrome(surf, fonts, snap, circuit, mode, screen_name, total_laps):
    """Top header (always visible across screens)."""
    # Circuit
    circuit_text = fonts.md.render(circuit.upper()[:14], True, LIGHTGREY)
    surf.blit(circuit_text, (8, 5))

    # Mode badge
    if mode == "live":
        pygame.draw.circle(surf, LIVE_RED, (132, 11), 4)
        live_text = fonts.sm.render("LIVE", True, LIVE_RED)
        surf.blit(live_text, (140, 5))
    else:
        replay_text = fonts.sm.render("REPLAY", True, DIM)
        surf.blit(replay_text, (130, 5))

    # Lap counter
    lap_str = f"L {snap['lap']}/{total_laps}" if total_laps else f"L {snap['lap']}"
    lap_text = fonts.md.render(lap_str, True, LIGHTGREY)
    surf.blit(lap_text, (W - lap_text.get_width() - 8, 5))

    pygame.draw.line(surf, GREY_LINE, (8, 22), (W - 8, 22))

    # Tiny screen name centered just below the rule
    name_text = fonts.xs.render(screen_name, True, DIM)
    surf.blit(name_text, ((W - name_text.get_width()) // 2, 24))


def draw_badge(surf, fonts, text, bg, fg, x, y):
    t = fonts.sm.render(text, True, fg)
    pad_x, pad_y = 4, 2
    rect = pygame.Rect(x, y, t.get_width() + pad_x * 2, t.get_height() + pad_y * 2)
    pygame.draw.rect(surf, bg, rect, border_radius=2)
    surf.blit(t, (x + pad_x, y + pad_y))
    return rect


class FocusScreen:
    NAME = "PIT WALL"

    def draw(self, surf, fonts, snap, circuit, mode, total_laps):
        surf.fill(BLACK)
        draw_chrome(surf, fonts, snap, circuit, mode, self.NAME, total_laps)

        # === Position (huge), with purple halo if this driver holds session FL ===
        pos_str = f"P{snap['position']}" if snap['position'] else "P-"
        if snap.get("has_fastest_lap"):
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                halo = fonts.huge.render(pos_str, True, PURPLE)
                surf.blit(halo, (10 + dx, 38 + dy))
        pos_text = fonts.huge.render(pos_str, True, WHITE)
        surf.blit(pos_text, (10, 38))

        # Driver code (team colored)
        team_color = parse_hex(snap.get("team_color")) or AMBER
        code_text = fonts.lg.render(snap.get("code", "?"), True, team_color)
        surf.blit(code_text, (12, 96))

        # === Tyre puck ===
        compound = snap.get("compound", "")
        col = COMPOUND_COLOR.get(compound, DIM)
        tyre_cx, tyre_cy, tyre_r = 138, 64, 22
        pygame.draw.circle(surf, col, (tyre_cx, tyre_cy), tyre_r)
        if compound:
            letter = fonts.lg.render(compound[0], True, BLACK)
            surf.blit(letter, letter.get_rect(center=(tyre_cx, tyre_cy)))
        # Stint lap label below tyre
        stint_label = fonts.sm.render(f"L{snap['stint_lap']}", True, col)
        surf.blit(stint_label, stint_label.get_rect(center=(tyre_cx, tyre_cy + tyre_r + 6)))

        # === Tyre wear bar ===
        bar_x, bar_y, bar_w, bar_h = 110, 104, 56, 5
        pygame.draw.rect(surf, GREY_LINE, (bar_x, bar_y, bar_w, bar_h))
        pct = snap.get("tyre_pct", 0)
        if pct > 0:
            wear_color = GREEN if pct < 0.6 else YELLOW if pct < 0.85 else RED
            fill_w = max(1, int(bar_w * pct))
            pygame.draw.rect(surf, wear_color, (bar_x, bar_y, fill_w, bar_h))
        wear_label = fonts.xs.render(f"{int(pct * 100)}%", True, DIM)
        surf.blit(wear_label, wear_label.get_rect(center=(tyre_cx, 117)))

        # === Right column: gaps ===
        ahead_lbl = fonts.xs.render("AHEAD", True, DIM)
        surf.blit(ahead_lbl, (200, 38))
        if snap.get("interval") is not None:
            ahead_text = fonts.lg.render(f"-{snap['interval']:.3f}", True, TEAL)
        else:
            ahead_text = fonts.lg.render("--.---", True, DIM)
        surf.blit(ahead_text, (200, 50))

        leader_lbl = fonts.xs.render("LEADER", True, DIM)
        surf.blit(leader_lbl, (200, 78))
        if snap.get("to_leader"):
            lead_text = fonts.lg.render(f"+{snap['to_leader']:.2f}", True, WHITE)
        else:
            lead_text = fonts.lg.render("--.--", True, DIM)
        surf.blit(lead_text, (200, 90))

        # === Bottom strip: lap time + delta + sectors + pit status ===
        pygame.draw.line(surf, GREY_LINE, (8, 128), (W - 8, 128))

        # Lap time (purple if session best, green if PB, white otherwise)
        lt = snap.get("lap_time")
        sb = snap.get("session_best")
        pb = snap.get("personal_best")
        lt_color = WHITE
        if lt is not None and sb is not None and abs(lt - sb) < 1e-3:
            lt_color = PURPLE
        elif lt is not None and pb is not None and abs(lt - pb) < 1e-3:
            lt_color = GREEN
        lt_text = fonts.md.render(fmt_lap(lt), True, lt_color)
        surf.blit(lt_text, (8, 134))

        # Delta to session best
        delta = snap.get("delta_to_best")
        if delta is not None:
            sign = "+" if delta >= 0 else ""
            d_color = WHITE if delta >= 0 else GREEN
            d_text = fonts.md.render(f"{sign}{delta:.3f}", True, d_color)
            surf.blit(d_text, (78, 134))

        # Sector dots + times
        sector_x = 152
        for i, s in enumerate(snap.get("sectors", [])):
            cx = sector_x + i * 50
            cy = 140
            col = SECTOR_COLOR.get(s["color"], DIM)
            pygame.draw.circle(surf, col, (cx, cy), 4)
            label = fonts.xs.render(f"S{i+1}", True, DIM)
            surf.blit(label, label.get_rect(midtop=(cx, cy + 6)))
            t = s.get("time")
            if t is not None:
                t_text = fonts.xs.render(f"{t:.2f}", True, col)
                surf.blit(t_text, t_text.get_rect(center=(cx + 22, cy)))

        # Pit / Out badge (overlays bottom-right when active)
        ps = snap.get("pit_status", "ON_TRACK")
        if ps == "IN_PIT":
            draw_badge(surf, fonts, "PIT", LIVE_RED, BLACK, x=W - 38, y=156)
        elif ps == "OUT_LAP":
            draw_badge(surf, fonts, "OUT", AMBER, BLACK, x=W - 38, y=156)


class StandingsScreen:
    NAME = "STANDINGS"

    def draw(self, surf, fonts, snap, circuit, mode, total_laps):
        surf.fill(BLACK)
        draw_chrome(surf, fonts, snap, circuit, mode, self.NAME, total_laps)

        rows = snap.get("standings", [])[:5]
        if not rows:
            txt = fonts.md.render("no standings yet", True, DIM)
            surf.blit(txt, txt.get_rect(center=(W // 2, H // 2)))
            return

        row_h = 25
        y0 = 40
        for idx, r in enumerate(rows):
            y = y0 + idx * row_h

            # Position
            pos_text = fonts.lg.render(f"P{r['position']}", True, WHITE)
            surf.blit(pos_text, (8, y + 2))

            # Team color stripe
            team_color = parse_hex(r.get("team_color")) or DIM
            pygame.draw.rect(surf, team_color, (54, y, 4, 22))

            # Driver code
            code = fonts.lg.render(r.get("code", "?"), True, WHITE)
            surf.blit(code, (66, y + 2))

            # Mini tyre puck
            comp = r.get("compound", "")
            col = COMPOUND_COLOR.get(comp, DIM)
            pygame.draw.circle(surf, col, (140, y + 11), 9)
            if comp:
                letter = fonts.sm.render(comp[0], True, BLACK)
                surf.blit(letter, letter.get_rect(center=(140, y + 11)))

            # Gap to leader
            gap = r.get("gap_to_leader")
            if idx == 0:
                gap_str = "LEADER"
                gap_color = AMBER
            elif gap is None:
                gap_str = "--.--"
                gap_color = DIM
            else:
                gap_str = f"+{gap:.3f}"
                gap_color = WHITE
            gap_text = fonts.lg.render(gap_str, True, gap_color)
            surf.blit(gap_text, (W - gap_text.get_width() - 8, y + 2))


class Compositor:
    """Holds the screen list and the active index."""

    def __init__(self):
        self.fonts = Fonts()
        self.screens = [FocusScreen(), StandingsScreen()]
        self.idx = 0

    def cycle(self):
        self.idx = (self.idx + 1) % len(self.screens)

    def set_index(self, i):
        if 0 <= i < len(self.screens):
            self.idx = i

    def draw(self, surf, snap, circuit, mode, total_laps):
        self.screens[self.idx].draw(surf, self.fonts, snap, circuit, mode, total_laps)
