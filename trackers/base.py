from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HandSample:
    """One hand observation in screen-space pixel coordinates."""
    hand_id: int           # 0 = first hand, 1 = second hand
    x: float               # px, 0..screen_w
    y: float               # px, 0..screen_h
    z: float               # depth (m for Kinect; relative for webcam)
    timestamp: float       # seconds, monotonic


class HandTracker(ABC):
    """Source-agnostic hand tracker. Yields HandSample per hand per frame."""

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def poll(self) -> list[HandSample]:
        """Return the latest hand samples (one per visible hand). Non-blocking."""

    def background_frame(self) -> Optional["any"]:
        """Optional: BGR image to draw as a faded background. None if unavailable."""
        return None
