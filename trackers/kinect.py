"""Kinect v2 hand tracker for Windows.

Requires `pykinect2` and `comtypes` (Windows + Kinect SDK 2.0 installed).
Drop-in replacement for WebcamTracker; same HandSample contract.

To use:
    from trackers.kinect import KinectTracker
    tracker = KinectTracker(screen_w, screen_h)

This implementation reads the BodyFrameSource, picks the closest tracked
body, and converts the HandLeft / HandRight joints to depth-space pixels
(512×424) via the public body_joints_to_depth_space API, then scales to
screen-space pixels.
"""
from __future__ import annotations

import math
import time
from typing import Optional

import cv2
import numpy as np

from .base import HandSample, HandTracker

_kinect_import_error = ""
try:
    from pykinect2 import PyKinectV2

    from pykinect2 import PyKinectRuntime
    if not hasattr(PyKinectRuntime.PyKinectRuntime, 'body_joints_to_depth_space'):
        PyKinectRuntime.PyKinectRuntime.body_joints_to_depth_space = PyKinectRuntime.PyKinectRuntime.body_joints_to_depth

    from pykinect2.PyKinectV2 import (
        JointType_HandLeft, JointType_HandRight,
        TrackingState_NotTracked,
    )
    _KINECT_AVAILABLE = True
except Exception as e:
    _KINECT_AVAILABLE = False
    _kinect_import_error = str(e)


# Kinect v2 depth frame dimensions.
KINECT_DEPTH_W = 512
KINECT_DEPTH_H = 424

_PREVIEW_WIN = "Kinect Preview"

_STATE_NAMES = {0: "NotTracked", 1: "Inferred", 2: "Tracked"}


class KinectTracker(HandTracker):
    def __init__(self, screen_w: int, screen_h: int, sensitivity: float = 0.5):
        """
        sensitivity > 1.0 zooms in on the center of the depth frame so you
        need less hand travel to cover the full screen.  1.0 = raw mapping,
        2.0 = half the physical movement covers the full screen.
        """
        if not _KINECT_AVAILABLE:
            raise RuntimeError(
                f"pykinect2 failed to load: {_kinect_import_error}\n"
                "Make sure the Kinect for Windows SDK 2.0 is installed: "
                "https://www.microsoft.com/en-us/download/details.aspx?id=44561"
            )
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.sensitivity = sensitivity
        self._kinect = None
        self._dbg_last_print = 0.0   # throttle console output to 1 Hz
        self._dbg_frames     = 0
        self._dbg_no_body    = 0

    def start(self) -> None:
        self._kinect = PyKinectRuntime.PyKinectRuntime(
            PyKinectV2.FrameSourceTypes_Body | PyKinectV2.FrameSourceTypes_Depth
        )
        cv2.namedWindow(_PREVIEW_WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(_PREVIEW_WIN, KINECT_DEPTH_W, KINECT_DEPTH_H)

    def stop(self) -> None:
        if self._kinect is not None:
            self._kinect.close()
            self._kinect = None
        cv2.destroyWindow(_PREVIEW_WIN)

    def _draw_preview(self, hand_depth_pts: list[tuple[float, float]]) -> None:
        """Grab the latest depth frame, colorize it, overlay hand dots, show it."""
        if not self._kinect.has_new_depth_frame():
            return
        raw = self._kinect.get_last_depth_frame()
        if raw is None:
            return

        # raw is a flat uint16 array; reshape and normalize 500–5000 mm → 0–255.
        depth = raw.reshape((KINECT_DEPTH_H, KINECT_DEPTH_W)).astype(np.float32)
        depth_u8 = np.clip((depth - 500) / 4500 * 255, 0, 255).astype(np.uint8)
        preview = cv2.applyColorMap(depth_u8, cv2.COLORMAP_TURBO)

        # Draw a circle for each tracked hand in depth-space.
        for (dx, dy) in hand_depth_pts:
            ix, iy = int(dx), int(dy)
            cv2.circle(preview, (ix, iy), 18, (255, 255, 255), 3)
            cv2.circle(preview, (ix, iy), 6,  (255, 255, 255), -1)

        cv2.imshow(_PREVIEW_WIN, preview)
        cv2.waitKey(1)

    def poll(self) -> list[HandSample]:
        if self._kinect is None or not self._kinect.has_new_body_frame():
            return []

        bodies = self._kinect.get_last_body_frame()
        if bodies is None:
            return []

        t = time.monotonic()
        samples: list[HandSample] = []
        hand_depth_pts: list[tuple[float, float]] = []
        hand_id = 0

        tracked_bodies = 0
        for body in bodies.bodies:
            if not body.is_tracked:
                continue
            tracked_bodies += 1
            joints = body.joints
            # Public API: maps all joints to depth-space (512×424) in one call.
            # Avoids the private _mapper which needs the color stream open.
            depth_pts = self._kinect.body_joints_to_depth_space(joints)
            for joint_type in (JointType_HandLeft, JointType_HandRight):
                joint = joints[joint_type]
                name  = "L" if joint_type == JointType_HandLeft else "R"
                state = _STATE_NAMES.get(joint.TrackingState, str(joint.TrackingState))
                if joint.TrackingState == TrackingState_NotTracked:
                    print(f"[Kinect] hand {name}: {state} — skipped")
                    continue
                pt = depth_pts[joint_type]
                if not math.isfinite(pt.x) or not math.isfinite(pt.y):
                    print(f"[Kinect] hand {name}: non-finite depth coords ({pt.x}, {pt.y}) — skipped")
                    continue
                if not (0 <= pt.x <= KINECT_DEPTH_W and 0 <= pt.y <= KINECT_DEPTH_H):
                    print(f"[Kinect] hand {name}: out-of-bounds depth ({pt.x:.0f}, {pt.y:.0f}) — skipped")
                    continue
                hand_depth_pts.append((pt.x, pt.y))
                # Normalize to 0..1, zoom in around center, scale to screen.
                nx = (pt.x / KINECT_DEPTH_W - 0.5) / self.sensitivity + 0.5
                ny = (pt.y / KINECT_DEPTH_H - 0.5) / self.sensitivity + 0.5
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))
                sx = nx * self.screen_w
                sy = ny * self.screen_h
                print(f"[Kinect] hand {name}: {state}  depth=({pt.x:.0f},{pt.y:.0f})  screen=({sx:.0f},{sy:.0f})  z={joint.Position.z:.2f}m")
                samples.append(
                    HandSample(
                        hand_id=hand_id,
                        x=sx,
                        y=sy,
                        z=joint.Position.z,  # meters from sensor
                        timestamp=t,
                    )
                )
                hand_id += 1

        self._draw_preview(hand_depth_pts)

        # Throttled summary: once per second show frame + body count.
        self._dbg_frames += 1
        if tracked_bodies == 0:
            self._dbg_no_body += 1
        now = time.monotonic()
        if now - self._dbg_last_print >= 1.0:
            print(
                f"[Kinect] frames={self._dbg_frames}  tracked_bodies={tracked_bodies}"
                f"  no_body_frames={self._dbg_no_body}  hands_emitted={len(samples)}"
            )
            self._dbg_frames  = 0
            self._dbg_no_body = 0
            self._dbg_last_print = now

        return samples
