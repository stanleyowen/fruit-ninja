from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Tuple

import pygame

GRAVITY = 1400.0  # px/s^2


FRUIT_PALETTE: list[Tuple[str, Tuple[int, int, int], Tuple[int, int, int]]] = [
    # (name, fill, rind)
    ("watermelon", (220, 60, 80), (40, 140, 60)),
    ("orange",     (255, 150, 50), (200, 110, 30)),
    ("apple",      (220, 40, 60),  (130, 30, 40)),
    ("lemon",      (245, 220, 80), (200, 180, 60)),
    ("kiwi",       (130, 200, 90), (90, 70, 30)),
]


@dataclass
class Fruit:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    color: Tuple[int, int, int]
    rind: Tuple[int, int, int]
    name: str
    spin: float = 0.0           # rad/s
    angle: float = 0.0          # rad
    is_bomb: bool = False
    sliced: bool = False
    half_dir: int = 0           # -1 or +1 for sliced halves; 0 for whole fruit
    age: float = 0.0

    def update(self, dt: float) -> None:
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        self.age += dt

    def offscreen(self, screen_w: int, screen_h: int) -> bool:
        return (
            self.y - self.radius > screen_h + 80
            or self.x + self.radius < -120
            or self.x - self.radius > screen_w + 120
        )

    def draw(self, surf: pygame.Surface) -> None:
        if self.is_bomb:
            pygame.draw.circle(surf, (30, 30, 30), (int(self.x), int(self.y)), int(self.radius))
            pygame.draw.circle(surf, (80, 80, 80), (int(self.x), int(self.y)), int(self.radius), 3)
            # Fuse
            fx = int(self.x + math.cos(self.angle) * self.radius)
            fy = int(self.y - self.radius - 6)
            pygame.draw.line(surf, (200, 80, 30), (int(self.x), int(self.y - self.radius)), (fx, fy), 3)
            return

        if self.sliced:
            # Render a half-disc, offset along its drift direction.
            self._draw_half(surf)
            return

        pygame.draw.circle(surf, self.rind, (int(self.x), int(self.y)), int(self.radius))
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), int(self.radius - 5))

    def _draw_half(self, surf: pygame.Surface) -> None:
        r = int(self.radius)
        size = r * 2 + 2
        tmp = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(tmp, self.rind, (r, r), r)
        pygame.draw.circle(tmp, self.color, (r, r), r - 5)
        # Mask off one side based on half_dir.
        mask_rect = (r, 0, r + 2, size) if self.half_dir < 0 else (0, 0, r, size)
        pygame.draw.rect(tmp, (0, 0, 0, 0), mask_rect)
        rotated = pygame.transform.rotate(tmp, math.degrees(self.angle))
        rect = rotated.get_rect(center=(int(self.x), int(self.y)))
        surf.blit(rotated, rect.topleft)


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
        # Spawn from bottom 30% with upward velocity biased toward the center.
        x = self.rng.uniform(0.1, 0.9) * self.screen_w
        target_x = self.rng.uniform(0.3, 0.7) * self.screen_w
        # We want fruit to rise to ~30% screen height before falling.
        rise_h = self.rng.uniform(0.45, 0.65) * self.screen_h
        vy = -math.sqrt(2 * GRAVITY * rise_h)
        # Time-to-peak; aim vx so x reaches target_x at peak.
        t_peak = -vy / GRAVITY
        vx = (target_x - x) / max(t_peak, 0.1)

        is_bomb = self.rng.random() < self.bomb_chance
        if is_bomb:
            return Fruit(
                x=x, y=self.screen_h + 40,
                vx=vx, vy=vy,
                radius=44,
                color=(40, 40, 40), rind=(80, 80, 80), name="bomb",
                spin=self.rng.uniform(-2.0, 2.0), is_bomb=True,
            )

        name, color, rind = self.rng.choice(FRUIT_PALETTE)
        return Fruit(
            x=x, y=self.screen_h + 40,
            vx=vx, vy=vy,
            radius=self.rng.uniform(40, 56),
            color=color, rind=rind, name=name,
            spin=self.rng.uniform(-3.0, 3.0),
        )


def split_fruit(f: Fruit) -> tuple[Fruit, Fruit]:
    """Replace a sliced whole fruit with two halves drifting apart."""
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
