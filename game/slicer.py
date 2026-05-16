from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterable

from trackers.base import HandSample


# Minimum hand speed (px/s) for a movement to count as a slice.
SLICE_SPEED_THRESHOLD = 900.0
# How long a trail point stays visible (s).
TRAIL_LIFETIME = 0.25
# Cap trail length per hand.
TRAIL_MAX = 16


@dataclass
class TrailPoint:
    x: float
    y: float
    t: float


@dataclass
class HandTrail:
    points: Deque[TrailPoint] = field(default_factory=lambda: deque(maxlen=TRAIL_MAX))

    def push(self, s: HandSample) -> None:
        self.points.append(TrailPoint(s.x, s.y, s.timestamp))
        self._gc(s.timestamp)

    def _gc(self, now: float) -> None:
        while self.points and now - self.points[0].t > TRAIL_LIFETIME:
            self.points.popleft()

    def latest_segment(self) -> tuple[TrailPoint, TrailPoint] | None:
        if len(self.points) < 2:
            return None
        return self.points[-2], self.points[-1]

    def latest_speed(self) -> float:
        seg = self.latest_segment()
        if seg is None:
            return 0.0
        a, b = seg
        dt = max(b.t - a.t, 1e-3)
        return math.hypot(b.x - a.x, b.y - a.y) / dt


class TrailStore:
    """Per-hand trails keyed by hand_id."""

    def __init__(self) -> None:
        self._trails: dict[int, HandTrail] = {}

    def update(self, samples: Iterable[HandSample]) -> None:
        for s in samples:
            self._trails.setdefault(s.hand_id, HandTrail()).push(s)

    def trails(self) -> dict[int, HandTrail]:
        return self._trails


def _segment_circle_intersects(
    x1: float, y1: float, x2: float, y2: float,
    cx: float, cy: float, r: float,
) -> bool:
    """Standard segment-vs-circle test."""
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - cx, y1 - cy
    a = dx * dx + dy * dy
    if a == 0:
        return (fx * fx + fy * fy) <= r * r
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4 * a * c
    if disc < 0:
        return False
    disc_sqrt = math.sqrt(disc)
    t1 = (-b - disc_sqrt) / (2 * a)
    t2 = (-b + disc_sqrt) / (2 * a)
    return (0 <= t1 <= 1) or (0 <= t2 <= 1) or (t1 < 0 and t2 > 1)


def check_slice(trail: HandTrail, cx: float, cy: float, r: float) -> bool:
    """True if the most recent trail segment is fast AND intersects the circle."""
    seg = trail.latest_segment()
    if seg is None:
        return False
    a, b = seg
    dt = max(b.t - a.t, 1e-3)
    speed = math.hypot(b.x - a.x, b.y - a.y) / dt
    if speed < SLICE_SPEED_THRESHOLD:
        return False
    return _segment_circle_intersects(a.x, a.y, b.x, b.y, cx, cy, r)
