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

import numpy as np

from .base import HandSample, HandTracker

_kinect_import_error = ""
try:
    from pykinect2 import PyKinectV2, PyKinectRuntime
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


_STATE_NAMES = {0: "NotTracked", 1: "Inferred", 2: "Tracked"}


class KinectTracker(HandTracker):
    def __init__(self, screen_w: int, screen_h: int):
        if not _KINECT_AVAILABLE:
            raise RuntimeError(
                f"pykinect2 failed to load: {_kinect_import_error}\n"
                "Make sure the Kinect for Windows SDK 2.0 is installed: "
                "https://www.microsoft.com/en-us/download/details.aspx?id=44561"
            )
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._kinect = None
        self._dbg_last_print = 0.0   # throttle console output to 1 Hz
        self._dbg_frames     = 0
        self._dbg_no_body    = 0

    def start(self) -> None:
        self._kinect = PyKinectRuntime.PyKinectRuntime(
            PyKinectV2.FrameSourceTypes_Body | PyKinectV2.FrameSourceTypes_Depth
        )
        self._prev_depth: Optional[np.ndarray] = None

    def stop(self) -> None:
        if self._kinect is not None:
            self._kinect.close()
            self._kinect = None

    def _check_depth(self) -> None:
        """Print depth-stream diagnostics: confirms sensor is live and sees objects."""
        if not self._kinect.has_new_depth_frame():
            return
        raw = self._kinect.get_last_depth_frame()
        if raw is None:
            return
        frame = raw.reshape((KINECT_DEPTH_H, KINECT_DEPTH_W)).astype(np.int32)
        # Valid pixels have depth > 0 (0 = no return / too close).
        valid = frame[frame > 0]
        if valid.size == 0:
            print("[Kinect][depth] all pixels invalid — sensor may be obstructed")
            return
        closest_mm  = int(valid.min())
        median_mm   = int(np.median(valid))
        print(f"[Kinect][depth] live — closest={closest_mm} mm  median={median_mm} mm  valid_px={valid.size}")
        if self._prev_depth is not None:
            changed = int(np.sum(np.abs(frame - self._prev_depth) > 50))
            print(f"[Kinect][depth] motion pixels (>50 mm change): {changed}")
        self._prev_depth = frame

    def poll(self) -> list[HandSample]:
        if self._kinect is None:
            return []

        self._check_depth()

        if not self._kinect.has_new_body_frame():
            return []

        bodies = self._kinect.get_last_body_frame()
        if bodies is None:
            return []

        t = time.monotonic()
        samples: list[HandSample] = []
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
                # Mirror horizontally for selfie view, scale to screen space.
                sx = (1.0 - pt.x / KINECT_DEPTH_W) * self.screen_w
                sy = pt.y / KINECT_DEPTH_H * self.screen_h
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
            # Only first tracked body — multi-player is a follow-up.
            break

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
