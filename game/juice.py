from __future__ import annotations

import math
import random

import pygame

# Juice colour per fruit name (RGB).
JUICE_COLORS: dict[str, tuple[int, int, int]] = {
    "watermelon": (210,  25,  55),
    "orange":     (255, 125,  20),
    "apple":      (195,  25,  35),
    "lemon":      (240, 215,  30),
    "kiwi":       ( 50, 185,  50),
    "bomb":       ( 70,  70,  70),
}


class JuiceLayer:
    """Persistent RGBA surface that accumulates juice splats over the game."""

    def __init__(self, w: int, h: int) -> None:
        self._surf = pygame.Surface((w, h), pygame.SRCALPHA)
        self._rng  = random.Random()

    def splat(self, x: float, y: float, fruit_name: str, radius: float = 48.0) -> None:
        color = JUICE_COLORS.get(fruit_name, (200, 50, 50))
        rng   = self._rng
        s     = radius / 48.0   # scale relative to default fruit size

        # Central splat blob.
        pygame.draw.circle(self._surf, (*color, 180), (int(x), int(y)), int(20 * s))

        # Scattered blobs.
        for _ in range(rng.randint(9, 15)):
            angle = rng.uniform(0, math.tau)
            dist  = rng.uniform(5, 80 * s)
            bx    = int(x + math.cos(angle) * dist)
            by    = int(y + math.sin(angle) * dist)
            br    = int(rng.uniform(7, 20) * s)
            alpha = rng.randint(110, 200)
            pygame.draw.circle(self._surf, (*color, alpha), (bx, by), br)

        # Drip streaks shooting outward.
        for _ in range(rng.randint(5, 9)):
            angle  = rng.uniform(0, math.tau)
            dist   = rng.uniform(35 * s, 100 * s)
            bx     = int(x + math.cos(angle) * dist)
            by     = int(y + math.sin(angle) * dist)
            length = int(rng.uniform(14, 38) * s)
            width  = max(2, int(rng.uniform(3, 7) * s))
            alpha  = rng.randint(85, 160)
            ex     = int(bx + math.cos(angle) * length)
            ey     = int(by + math.sin(angle) * length)
            pygame.draw.line(self._surf, (*color, alpha), (bx, by), (ex, ey), width)
            pygame.draw.circle(self._surf, (*color, alpha), (ex, ey), max(1, width // 2))

        # Fine spray dots.
        for _ in range(rng.randint(12, 22)):
            angle = rng.uniform(0, math.tau)
            dist  = rng.uniform(20 * s, 120 * s)
            bx    = int(x + math.cos(angle) * dist)
            by    = int(y + math.sin(angle) * dist)
            alpha = rng.randint(50, 120)
            pygame.draw.circle(self._surf, (*color, alpha), (bx, by), rng.randint(1, 3))

    def draw(self, target: pygame.Surface) -> None:
        target.blit(self._surf, (0, 0))

    def clear(self) -> None:
        self._surf.fill((0, 0, 0, 0))
