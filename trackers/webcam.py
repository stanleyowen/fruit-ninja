from __future__ import annotations

import os
import time
import urllib.request
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from .base import HandSample, HandTracker

_MODEL_FILENAME = "hand_landmarker.task"
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)


def _ensure_model(path: str) -> None:
    if os.path.exists(path):
        return
    print(f"[webcam tracker] Downloading hand landmark model to {path!r} …")
    urllib.request.urlretrieve(_MODEL_URL, path)
    print("[webcam tracker] Download complete.")


class WebcamTracker(HandTracker):
    """MediaPipe Tasks HandLandmarker tracker over a regular webcam.

    Coordinates are mapped to game-window pixels and mirrored horizontally
    so the player's movements feel natural (selfie / mirror view).
    """

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        cam_index: int = 0,
        max_hands: int = 2,
        cam_w: int = 1280,
        cam_h: int = 720,
        model_path: str = _MODEL_FILENAME,
        existing_cap: Optional[cv2.VideoCapture] = None,
    ):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.cam_index = cam_index
        self.cam_w = cam_w
        self.cam_h = cam_h
        self.model_path = model_path
        self.max_hands = max_hands
        self._existing_cap = existing_cap

        self._cap: Optional[cv2.VideoCapture] = None
        self._detector: Optional[vision.HandLandmarker] = None
        self._last_bgr: Optional[np.ndarray] = None
        self._start_time = 0.0

    def start(self) -> None:
        _ensure_model(self.model_path)

        opts = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=self.max_hands,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._detector = vision.HandLandmarker.create_from_options(opts)

        if self._existing_cap is not None and self._existing_cap.isOpened():
            # Reuse the cap that was already opened by the camera picker — no re-negotiate.
            self._cap = self._existing_cap
        else:
            self._cap = cv2.VideoCapture(self.cam_index)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cam_w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cam_h)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open webcam index {self.cam_index}")

        self._start_time = time.monotonic()

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._detector is not None:
            self._detector.close()
            self._detector = None

    def poll(self) -> list[HandSample]:
        if self._cap is None or self._detector is None:
            return []

        ok, frame = self._cap.read()
        if not ok:
            return []

        # Mirror so player's left/right matches screen left/right.
        frame = cv2.flip(frame, 1)
        self._last_bgr = frame

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # VIDEO mode requires a monotonically increasing ms timestamp.
        timestamp_ms = int((time.monotonic() - self._start_time) * 1000)
        result = self._detector.detect_for_video(mp_image, timestamp_ms)

        if not result.hand_landmarks:
            return []

        t = time.monotonic()
        h, w = frame.shape[:2]
        samples: list[HandSample] = []
        for i, landmarks in enumerate(result.hand_landmarks[: self.max_hands]):
            # Landmark 9 = middle-finger MCP (stable palm center).
            p = landmarks[9]
            sx = p.x * w * (self.screen_w / w)   # simplifies to p.x * screen_w
            sy = p.y * h * (self.screen_h / h)
            samples.append(HandSample(hand_id=i, x=sx, y=sy, z=p.z, timestamp=t))
        return samples

    def background_frame(self) -> Optional[np.ndarray]:
        return self._last_bgr
