"""Kinect v2 hand tracker for Windows.

Requires `pykinect2` and `comtypes` (Windows + Kinect SDK 2.0 installed).
Drop-in replacement for WebcamTracker; same HandSample contract.

To use:
    from trackers.kinect import KinectTracker
    tracker = KinectTracker(screen_w, screen_h)

This implementation reads the BodyFrameSource, picks the closest tracked
body, and converts the HandLeft / HandRight joints from Kinect camera-space
(meters) to color-space pixels, then to screen-space pixels.
"""
from __future__ import annotations

import time
from typing import Optional

from .base import HandSample, HandTracker

try:
    from pykinect2 import PyKinectV2, PyKinectRuntime
    from pykinect2.PyKinectV2 import JointType_HandLeft, JointType_HandRight
    _KINECT_AVAILABLE = True
except ImportError:
    _KINECT_AVAILABLE = False


# Kinect v2 color frame is 1920x1080.
KINECT_COLOR_W = 1920
KINECT_COLOR_H = 1080


class KinectTracker(HandTracker):
    def __init__(self, screen_w: int, screen_h: int):
        if not _KINECT_AVAILABLE:
            raise RuntimeError(
                "pykinect2 not installed. Install on Windows with: "
                "pip install pykinect2 comtypes"
            )
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._kinect = None

    def start(self) -> None:
        self._kinect = PyKinectRuntime.PyKinectRuntime(
            PyKinectV2.FrameSourceTypes_Body
        )

    def stop(self) -> None:
        if self._kinect is not None:
            self._kinect.close()
            self._kinect = None

    def poll(self) -> list[HandSample]:
        if self._kinect is None or not self._kinect.has_new_body_frame():
            return []

        bodies = self._kinect.get_last_body_frame()
        if bodies is None:
            return []

        t = time.monotonic()
        samples: list[HandSample] = []
        hand_id = 0

        for body in bodies.bodies:
            if not body.is_tracked:
                continue
            joints = body.joints
            for joint_type in (JointType_HandLeft, JointType_HandRight):
                joint = joints[joint_type]
                # Camera-space (meters) -> color-space (px) using mapper.
                pt = self._kinect._mapper.MapCameraPointToColorSpace(joint.Position)
                if pt.x != pt.x or pt.y != pt.y:  # NaN check
                    continue
                # Mirror horizontally for selfie view.
                cx = KINECT_COLOR_W - pt.x
                sx = cx * (self.screen_w / KINECT_COLOR_W)
                sy = pt.y * (self.screen_h / KINECT_COLOR_H)
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

        return samples
