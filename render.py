"""Pygame renderer for the pit wall display.

The drawing logic here uses the same coordinates and primitives we'll
port to TFT_eSPI on the ESP32:
    pygame.draw.circle  ->  tft.fillCircle
    surf.blit(text)     ->  tft.setCursor + tft.print
    pygame.draw.line    ->  tft.drawFastHLine

So when we move to hardware, this is the file we 'translate' to C++.
"""
import pygame

# These match the LilyGO T-Display-S3 panel exactly.
W, H = 320, 170

# F1 tyre compound colors (RGB)
COMPOUND_COLOR = {
    "SOFT":         (255,  60,  60),
    "MEDIUM":       (250, 199, 117),
    "HARD":         (240, 240, 240),
    "INTERMEDIATE": ( 93, 202, 165),
    "WET":          ( 55, 138, 221),
}

WHITE     = (255, 255, 255)
LIGHTGREY = (180, 180, 180)
DIM       = ( 95,  95,  95)
GREY_LINE = ( 40,  40,  40)
BLACK     = (  0,   0,   0)
TEAL      = ( 93, 202, 165)


class Renderer:
    """Draws a pit-wall snapshot onto a 320x170 surface."""

    def __init__(self):
        # SysFont falls back to a system mono if Consolas is missing.
        self.font_huge = pygame.font.SysFont("Consolas", 64, bold=True)
        self.font_lg   = pygame.font.SysFont("Consolas", 22, bold=True)
        self.font_md   = pygame.font.SysFont("Consolas", 16, bold=True)
        self.font_sm   = pygame.font.SysFont("Consolas", 11, bold=True)
        self.font_xs   = pygame.font.SysFont("Consolas", 10)

    def draw(self, surf: pygame.Surface, snap: dict, circuit: str) -> None:
        surf.fill(BLACK)

        # ---- Header strip ----
        circuit_text = self.font_md.render(circuit.upper()[:12], True, LIGHTGREY)
        lap_text     = self.font_md.render(f"L {snap['lap']}", True, LIGHTGREY)
        surf.blit(circuit_text, (8, 6))
        surf.blit(lap_text, (W - lap_text.get_width() - 8, 6))
        pygame.draw.line(surf, GREY_LINE, (8, 26), (W - 8, 26))

        # ---- Position (huge) + driver code ----
        if snap["position"]:
            pos_text = self.font_huge.render(f"P{snap['position']}", True, WHITE)
            surf.blit(pos_text, (10, 36))
        if snap["code"]:
            team_color = self._parse_hex(snap.get("team_color")) or (250, 199, 117)
            code_text = self.font_lg.render(snap["code"], True, team_color)
            surf.blit(code_text, (12, 102))

        # ---- Tyre puck ----
        compound = snap.get("compound", "")
        col = COMPOUND_COLOR.get(compound, (60, 60, 60))
        pygame.draw.circle(surf, col, (252, 78), 28)
        if compound:
            letter = self.font_lg.render(compound[0], True, BLACK)
            surf.blit(letter, letter.get_rect(center=(252, 78)))
        if snap["stint_lap"]:
            sl = self.font_sm.render(f"L {snap['stint_lap']}", True, col)
            surf.blit(sl, sl.get_rect(center=(252, 116)))

        # ---- Footer ----
        pygame.draw.line(surf, GREY_LINE, (8, 138), (W - 8, 138))
        ahead_lbl  = self.font_xs.render("AHEAD", True, DIM)
        leader_lbl = self.font_xs.render("LEADER", True, DIM)
        surf.blit(ahead_lbl, (8, 142))
        surf.blit(leader_lbl, (W - leader_lbl.get_width() - 8, 142))

        if snap["interval"] is not None:
            iv = self.font_md.render(f"-{snap['interval']:.3f}", True, TEAL)
        else:
            iv = self.font_md.render("--.---", True, DIM)
        surf.blit(iv, (8, 154))

        if snap["to_leader"]:
            tl = self.font_md.render(f"+{snap['to_leader']:.2f}", True, WHITE)
            surf.blit(tl, (W - tl.get_width() - 8, 154))

    @staticmethod
    def _parse_hex(s: str | None):
        """OpenF1 returns team colours as 6-char hex without the '#'."""
        if not s:
            return None
        s = s.strip().lstrip("#")
        if len(s) != 6:
            return None
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None
