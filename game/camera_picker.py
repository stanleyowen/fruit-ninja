from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import pygame


# ── stderr suppression ────────────────────────────────────────────────────
# OpenCV / AVFoundation prints native-level errors to file descriptor 2 when
# probing missing camera indices.  Redirect at the OS level so they stay off
# the terminal.

@contextlib.contextmanager
def _silence_stderr():
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    os.dup2(devnull_fd, 2)
    try:
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull_fd)


# ── camera detection ──────────────────────────────────────────────────────

@dataclass
class CameraInfo:
    index: int
    label: str
    width: int
    height: int


def detect_cameras(max_probe: int = 8) -> list[CameraInfo]:
    """Probe camera indices 0..max_probe-1, return those that deliver frames.

    Uses a read() check (not just isOpened()) so devices like iPhone Continuity
    Camera that need a moment to activate are validated properly.
    Stderr is suppressed to hide AVFoundation 'out of bound' noise.
    """
    found: list[CameraInfo] = []
    for i in range(max_probe):
        with _silence_stderr():
            cap = cv2.VideoCapture(i)
            ok = cap.isOpened()
            if ok:
                ok, _ = cap.read()   # confirm it actually delivers frames
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
        if ok:
            label = f"Camera {i}"
            if i == 0:
                label = "Camera 0 (built-in)"
            found.append(CameraInfo(index=i, label=label, width=w, height=h))
    return found


# ── colours & layout ──────────────────────────────────────────────────────

_BG          = (15,  15,  25)
_CARD        = (30,  35,  55)
_CARD_HOV    = (45,  55,  85)
_CARD_SEL    = (60, 100, 200)
_TEXT        = (235, 235, 245)
_SUBTEXT     = (160, 165, 185)
_BTN_START   = (50,  170,  80)
_BTN_START_H = (70,  210, 100)

_PREVIEW_W = 480
_PREVIEW_H = 270
_CARD_W    = 240
_CARD_H    = 80
_CARD_GAP  = 16
_MARGIN    = 48


def _bgr_to_surface(frame: np.ndarray, w: int, h: int) -> pygame.Surface:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, (w, h))
    return pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")


def _rounded_rect(surf: pygame.Surface, color: tuple, rect: pygame.Rect, radius: int) -> None:
    pygame.draw.rect(surf, color, rect, border_radius=radius)


# ── picker UI ────────────────────────────────────────────────────────────

def run_camera_picker(
    screen: pygame.Surface,
    cameras: list[CameraInfo],
) -> int:
    """Blocking camera-selection screen.  Returns chosen camera index.

    All cameras are opened upfront and kept open for the duration so that
    devices like iPhone Continuity Camera don't time out between detection
    and the game starting.
    """
    if not cameras:
        raise RuntimeError("No cameras detected.")
    if len(cameras) == 1:
        return cameras[0].index

    SW, SH = screen.get_size()

    try:
        title_font = pygame.font.SysFont("arial", 38, bold=True)
        label_font = pygame.font.SysFont("arial", 22, bold=True)
        sub_font   = pygame.font.SysFont("arial", 18)
        btn_font   = pygame.font.SysFont("arial", 26, bold=True)
    except Exception:
        title_font = label_font = sub_font = btn_font = pygame.font.Font(None, 28)

    # Open every detected camera now and keep it open.
    caps: dict[int, cv2.VideoCapture] = {}
    for cam in cameras:
        with _silence_stderr():
            cap = cv2.VideoCapture(cam.index)
        if cap.isOpened():
            # Drain a few frames so the camera warms up (needed for
            # Continuity Camera which delivers black/stale frames at first).
            for _ in range(4):
                cap.read()
            caps[cam.index] = cap

    def release_all() -> None:
        for c in caps.values():
            c.release()
        caps.clear()

    # Per-camera last-good frame surface.
    surfaces: dict[int, Optional[pygame.Surface]] = {cam.index: None for cam in cameras}

    selected      = 0
    hovered       = -1
    start_hovered = False

    list_x    = _MARGIN
    list_top  = 140
    preview_x = list_x + _CARD_W + _MARGIN * 2
    preview_y = list_top

    start_btn = pygame.Rect(SW // 2 - 120, SH - 90, 240, 56)
    clock     = pygame.time.Clock()

    try:
        while True:
            mx, my = pygame.mouse.get_pos()

            card_rects = [
                pygame.Rect(list_x, list_top + i * (_CARD_H + _CARD_GAP), _CARD_W, _CARD_H)
                for i in range(len(cameras))
            ]
            hovered       = next((i for i, r in enumerate(card_rects) if r.collidepoint(mx, my)), -1)
            start_hovered = start_btn.collidepoint(mx, my)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    release_all()
                    pygame.quit()
                    raise SystemExit
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        release_all()
                        pygame.quit()
                        raise SystemExit
                    if event.key in (pygame.K_UP, pygame.K_w):
                        selected = (selected - 1) % len(cameras)
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        selected = (selected + 1) % len(cameras)
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        chosen = cameras[selected].index
                        # Release all except the chosen one — WebcamTracker will
                        # reopen it; releasing them all here is safest.
                        release_all()
                        return chosen
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if hovered >= 0:
                        selected = hovered
                    elif start_hovered:
                        chosen = cameras[selected].index
                        release_all()
                        return chosen

            # Grab a frame from every open camera so they all stay active.
            for cam in cameras:
                cap = caps.get(cam.index)
                if cap is None or not cap.isOpened():
                    continue
                ok, frame = cap.read()
                if ok and frame is not None:
                    frame = cv2.flip(frame, 1)
                    surfaces[cam.index] = _bgr_to_surface(frame, _PREVIEW_W, _PREVIEW_H)

            # ── Draw ──────────────────────────────────────────────────────
            screen.fill(_BG)

            title = title_font.render("Select Camera", True, _TEXT)
            screen.blit(title, (SW // 2 - title.get_width() // 2, 52))
            hint = sub_font.render(
                "Click a camera or use ↑ ↓, then press Start / Enter", True, _SUBTEXT
            )
            screen.blit(hint, (SW // 2 - hint.get_width() // 2, 100))

            # Camera cards (left panel).
            for i, (cam, rect) in enumerate(zip(cameras, card_rects)):
                color = _CARD_SEL if i == selected else (_CARD_HOV if i == hovered else _CARD)
                _rounded_rect(screen, color, rect, 10)
                screen.blit(label_font.render(cam.label, True, _TEXT), (rect.x + 16, rect.y + 14))
                screen.blit(sub_font.render(f"{cam.width}×{cam.height}", True, _SUBTEXT), (rect.x + 16, rect.y + 42))
                if i == selected:
                    pygame.draw.rect(screen, (150, 200, 255), rect, 2, border_radius=10)

            # Preview pane (right panel) — always shows selected camera.
            preview_rect = pygame.Rect(preview_x, preview_y, _PREVIEW_W, _PREVIEW_H)
            _rounded_rect(screen, _CARD, preview_rect, 8)
            sel_surf = surfaces.get(cameras[selected].index)
            if sel_surf is not None:
                screen.blit(sel_surf, preview_rect.topleft)
                pygame.draw.rect(screen, (80, 90, 120), preview_rect, 2, border_radius=8)
            else:
                warming = sub_font.render("Warming up…", True, _SUBTEXT)
                screen.blit(warming, warming.get_rect(center=preview_rect.center))

            sel_label_surf = label_font.render(f"Selected: {cameras[selected].label}", True, _TEXT)
            screen.blit(sel_label_surf, sel_label_surf.get_rect(
                centerx=preview_rect.centerx, top=preview_rect.bottom + 12
            ))

            # Start button.
            _rounded_rect(screen, _BTN_START_H if start_hovered else _BTN_START, start_btn, 12)
            btn_txt = btn_font.render("Start Game", True, (255, 255, 255))
            screen.blit(btn_txt, btn_txt.get_rect(center=start_btn.center))

            pygame.display.flip()
            clock.tick(30)
    except Exception:
        release_all()
        raise
