from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Tuple

import pygame

GRAVITY = 1400.0

# (name, skin_color, flesh_color)
FRUIT_PALETTE: list[Tuple[str, Tuple[int,int,int], Tuple[int,int,int]]] = [
    ("watermelon", ( 45, 120,  45), (215,  40,  60)),
    ("orange",     (255, 130,  25), (255, 175,  60)),
    ("apple",      (205,  38,  42), (242, 222, 196)),
    ("lemon",      (240, 210,  40), (252, 245, 110)),
    ("kiwi",       ( 95,  65,  28), ( 60, 178,  60)),
]


# ── per-type drawing helpers ──────────────────────────────────────────────

def _draw_watermelon_whole(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (40, 110, 40), (cx, cy), r)
    # Lighter green base stripe field
    pygame.draw.circle(surf, (65, 145, 55), (cx, cy), r - 4)
    # Dark green radiating stripes (5)
    for i in range(5):
        a = math.radians(-90 + i * 36)
        for t in range(0, r - 6, 3):
            sx = int(cx + t * math.cos(a))
            sy = int(cy + t * math.sin(a))
            pygame.draw.circle(surf, (30, 88, 30), (sx, sy), 4)
    pygame.draw.circle(surf, (70, 155, 60), (cx, cy), r - 4, 2)


def _draw_watermelon_half(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (215, 40, 58), (cx, cy), r)          # red flesh
    pygame.draw.circle(surf, (240, 230, 220), (cx, cy), r - 2, 6) # white rind strip
    pygame.draw.circle(surf, (45, 118, 45), (cx, cy), r, 6)       # green outer edge
    # Seeds
    rng = random.Random(cx + cy)
    for _ in range(10):
        ang = rng.uniform(0, math.tau)
        dist = rng.uniform(r * 0.2, r * 0.72)
        sx = int(cx + math.cos(ang) * dist)
        sy = int(cy + math.sin(ang) * dist)
        pygame.draw.ellipse(surf, (18, 14, 12), (sx - 4, sy - 6, 8, 12))


def _draw_orange_whole(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (255, 128, 22), (cx, cy), r)
    pygame.draw.circle(surf, (255, 148, 45), (cx, cy), r - 3)
    # Segment lines visible through skin
    for i in range(8):
        a = math.radians(i * 45)
        ex = int(cx + (r - 4) * math.cos(a))
        ey = int(cy + (r - 4) * math.sin(a))
        pygame.draw.line(surf, (210, 100, 15), (cx, cy), (ex, ey), 1)
    # Stem nub
    pygame.draw.circle(surf, (90, 60, 20), (cx, cy - r + 4), 4)


def _draw_orange_half(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (255, 170, 55), (cx, cy), r)
    # 8 white pith dividers radiating from center
    for i in range(8):
        a = math.radians(i * 45)
        ex = int(cx + (r - 2) * math.cos(a))
        ey = int(cy + (r - 2) * math.sin(a))
        pygame.draw.line(surf, (255, 240, 210), (cx, cy), (ex, ey), 2)
    pygame.draw.circle(surf, (255, 240, 205), (cx, cy), 7)           # center pith
    pygame.draw.circle(surf, (210, 105, 20), (cx, cy), r, 5)         # skin ring


def _draw_apple_whole(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (200, 35, 40), (cx, cy), r)
    pygame.draw.circle(surf, (220, 50, 52), (cx, cy), r - 3)
    # Shine
    pygame.draw.ellipse(surf, (245, 175, 175), (cx - r//2, cy - r//2, r//2, r//3))
    # Stem
    pygame.draw.line(surf, (90, 58, 20), (cx, cy - r + 3), (cx + 4, cy - r - 8), 3)
    # Small leaf
    pts = [(cx + 4, cy - r - 6), (cx + 14, cy - r - 12), (cx + 7, cy - r - 2)]
    pygame.draw.polygon(surf, (55, 140, 45), pts)


def _draw_apple_half(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (242, 220, 192), (cx, cy), r)
    # Core lines
    for a in (math.radians(-70), math.radians(70)):
        ex = int(cx + (r * 0.5) * math.cos(a))
        ey = int(cy + (r * 0.5) * math.sin(a))
        pygame.draw.line(surf, (180, 120, 70), (cx, cy), (ex, ey), 2)
    # Seeds
    for i in range(4):
        a = math.radians(-45 + i * 30)
        sx = int(cx + r * 0.38 * math.cos(a))
        sy = int(cy + r * 0.38 * math.sin(a))
        pygame.draw.ellipse(surf, (55, 35, 15), (sx - 4, sy - 6, 8, 11))
    pygame.draw.circle(surf, (200, 35, 40), (cx, cy), r, 6)  # skin ring


def _draw_lemon_whole(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (240, 208, 38), (cx, cy), r)
    pygame.draw.circle(surf, (252, 228, 68), (cx, cy), r - 3)
    # Tiny nubs at poles
    pygame.draw.circle(surf, (210, 175, 25), (cx, cy - r + 2), 5)
    pygame.draw.circle(surf, (210, 175, 25), (cx, cy + r - 2), 4)
    # Highlight
    pygame.draw.ellipse(surf, (255, 248, 180), (cx - r//3, cy - r//2, r//3, r//4))


def _draw_lemon_half(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (252, 242, 100), (cx, cy), r)
    for i in range(8):
        a = math.radians(i * 45)
        ex = int(cx + (r - 2) * math.cos(a))
        ey = int(cy + (r - 2) * math.sin(a))
        pygame.draw.line(surf, (255, 255, 200), (cx, cy), (ex, ey), 2)
    pygame.draw.circle(surf, (255, 252, 180), (cx, cy), 6)
    pygame.draw.circle(surf, (218, 188, 32), (cx, cy), r, 5)


def _draw_kiwi_whole(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (88, 60, 24), (cx, cy), r)
    pygame.draw.circle(surf, (105, 72, 30), (cx, cy), r - 2)
    # Fuzzy texture dots
    rng = random.Random(r)
    for _ in range(28):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0, r - 5)
        dx = int(cx + d * math.cos(a))
        dy = int(cy + d * math.sin(a))
        col = (rng.randint(70, 95), rng.randint(48, 65), rng.randint(15, 28))
        pygame.draw.circle(surf, col, (dx, dy), rng.randint(2, 4))
    # Stem
    pygame.draw.circle(surf, (65, 42, 12), (cx, cy - r + 3), 5)


def _draw_kiwi_half(surf: pygame.Surface, r: int) -> None:
    cx = cy = r
    pygame.draw.circle(surf, (62, 175, 62), (cx, cy), r)
    # Cream center
    pygame.draw.circle(surf, (240, 235, 210), (cx, cy), r // 3)
    # White lines from center to edge
    for i in range(12):
        a = math.radians(i * 30)
        ex = int(cx + (r - 2) * math.cos(a))
        ey = int(cy + (r - 2) * math.sin(a))
        pygame.draw.line(surf, (210, 230, 205), (cx, cy), (ex, ey), 1)
    # Seeds in a ring
    for i in range(10):
        a = math.radians(i * 36)
        sx = int(cx + r * 0.6 * math.cos(a))
        sy = int(cy + r * 0.6 * math.sin(a))
        # Each seed is a small rotated teardrop approximated by an ellipse
        pygame.draw.ellipse(surf, (22, 16, 10), (sx - 3, sy - 5, 6, 10))
    pygame.draw.circle(surf, (88, 60, 24), (cx, cy), r, 5)  # outer skin


_WHOLE_DRAWERS = {
    "watermelon": _draw_watermelon_whole,
    "orange":     _draw_orange_whole,
    "apple":      _draw_apple_whole,
    "lemon":      _draw_lemon_whole,
    "kiwi":       _draw_kiwi_whole,
}

_HALF_DRAWERS = {
    "watermelon": _draw_watermelon_half,
    "orange":     _draw_orange_half,
    "apple":      _draw_apple_half,
    "lemon":      _draw_lemon_half,
    "kiwi":       _draw_kiwi_half,
}


# ── Fruit dataclass ───────────────────────────────────────────────────────

@dataclass
class Fruit:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    color: Tuple[int, int, int]   # skin
    rind: Tuple[int, int, int]    # unused legacy field kept for compat
    name: str
    spin: float = 0.0
    angle: float = 0.0
    is_bomb: bool = False
    sliced: bool = False
    half_dir: int = 0
    age: float = 0.0

    # Pre-rendered surface cache (built on first draw, invalidated if None).
    _surf_cache: object = field(default=None, repr=False, compare=False)

    def _make_surface(self) -> pygame.Surface:
        r = int(self.radius)
        size = r * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)

        if self.is_bomb:
            pygame.draw.circle(surf, (28, 28, 28), (r, r), r)
            pygame.draw.circle(surf, (75, 75, 75), (r, r), r, 3)
            pygame.draw.line(surf, (200, 80, 30), (r, r - r), (r + 5, r - r - 8), 3)
            return surf

        drawer = (_HALF_DRAWERS if self.sliced else _WHOLE_DRAWERS).get(self.name)
        if drawer:
            drawer(surf, r)
        else:
            pygame.draw.circle(surf, self.color, (r, r), r)
            pygame.draw.circle(surf, self.rind, (r, r), r, 4)

        if self.sliced:
            # Mask off one half to show only the cut face.
            mask_rect = (r, 0, r + 2, size) if self.half_dir < 0 else (0, 0, r, size)
            pygame.draw.rect(surf, (0, 0, 0, 0), mask_rect)

        return surf

    def update(self, dt: float) -> None:
        self.vy += GRAVITY * dt
        self.x  += self.vx * dt
        self.y  += self.vy * dt
        self.angle += self.spin * dt
        self.age   += dt

    def offscreen(self, screen_w: int, screen_h: int) -> bool:
        return (
            self.y - self.radius > screen_h + 80
            or self.x + self.radius < -120
            or self.x - self.radius > screen_w + 120
        )

    def draw(self, surf: pygame.Surface) -> None:
        if self._surf_cache is None:
            self._surf_cache = self._make_surface()
        rotated = pygame.transform.rotate(self._surf_cache, math.degrees(-self.angle))
        rect = rotated.get_rect(center=(int(self.x), int(self.y)))
        surf.blit(rotated, rect.topleft)


# ── Spawner ───────────────────────────────────────────────────────────────

@dataclass
class FruitSpawner:
    screen_w: int
    screen_h: int
    spawn_every: float = 0.9
    bomb_chance: float = 0.08
    _t: float = 0.0
    rng: random.Random = field(default_factory=random.Random)

    def update(self, dt: float, out: list[Fruit]) -> None:
        self._t -= dt
        if self._t > 0:
            return
        self._t = self.spawn_every * self.rng.uniform(0.7, 1.4)
        out.append(self._spawn())

    def _spawn(self) -> Fruit:
        x        = self.rng.uniform(0.1, 0.9) * self.screen_w
        target_x = self.rng.uniform(0.3, 0.7) * self.screen_w
        rise_h   = self.rng.uniform(0.45, 0.65) * self.screen_h
        vy       = -math.sqrt(2 * GRAVITY * rise_h)
        t_peak   = -vy / GRAVITY
        vx       = (target_x - x) / max(t_peak, 0.1)

        is_bomb = self.rng.random() < self.bomb_chance
        if is_bomb:
            return Fruit(
                x=x, y=self.screen_h + 40, vx=vx, vy=vy,
                radius=44, color=(40, 40, 40), rind=(80, 80, 80), name="bomb",
                spin=self.rng.uniform(-2.0, 2.0), is_bomb=True,
            )

        name, skin, flesh = self.rng.choice(FRUIT_PALETTE)
        return Fruit(
            x=x, y=self.screen_h + 40, vx=vx, vy=vy,
            radius=self.rng.uniform(40, 56),
            color=skin, rind=flesh, name=name,
            spin=self.rng.uniform(-3.0, 3.0),
        )


def split_fruit(f: Fruit) -> tuple[Fruit, Fruit]:
    """Return two half-fruit pieces drifting from the slice point."""
    drift = 220.0
    left = Fruit(
        x=f.x - 4, y=f.y, vx=f.vx - drift, vy=f.vy - 80,
        radius=f.radius, color=f.color, rind=f.rind, name=f.name,
        spin=f.spin - 4.0, angle=f.angle, sliced=True, half_dir=-1,
    )
    right = Fruit(
        x=f.x + 4, y=f.y, vx=f.vx + drift, vy=f.vy - 80,
        radius=f.radius, color=f.color, rind=f.rind, name=f.name,
        spin=f.spin + 4.0, angle=f.angle, sliced=True, half_dir=+1,
    )
    return left, right
