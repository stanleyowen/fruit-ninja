from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
import pygame


# ── Return type ───────────────────────────────────────────────────────────

@dataclass
class TrackerChoice:
    tracker_type: str              # "webcam" or "kinect"
    cam_index:    int = 0
    # Pre-opened cap handed to WebcamTracker so the camera is NEVER re-negotiated.
    cap: Optional[cv2.VideoCapture] = field(default=None, repr=False)


# ── Stderr suppressor (quiets AVFoundation/FFmpeg noise) ──────────────────

@contextlib.contextmanager
def _silence_stderr():
    fd    = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    os.dup2(fd, 2)
    try:
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(fd)


# ── Camera info ───────────────────────────────────────────────────────────

@dataclass
class CameraInfo:
    index:  int
    label:  str
    width:  int
    height: int


# ── Single-pass detect + open ─────────────────────────────────────────────
# Opens each candidate index ONCE, keeps successful caps alive.
# Caller is responsible for releasing caps it no longer needs.

def _open_cameras(max_probe: int = 8) -> tuple[list[CameraInfo], dict[int, cv2.VideoCapture]]:
    infos: list[CameraInfo] = []
    caps:  dict[int, cv2.VideoCapture] = {}
    for i in range(max_probe):
        with _silence_stderr():
            cap = cv2.VideoCapture(i)
        if not cap.isOpened():
            cap.release()
            continue
        ok, _ = cap.read()
        if not ok:
            cap.release()
            continue
        # Two more warm-up reads so Continuity Camera flushes its init frames.
        cap.read(); cap.read()
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        label = "Built-in Camera" if i == 0 else f"Camera {i}"
        infos.append(CameraInfo(i, label, w, h))
        caps[i] = cap
    return infos, caps


# Keep the old name available for any code that calls it directly.
def detect_cameras(max_probe: int = 8) -> list[CameraInfo]:
    infos, caps = _open_cameras(max_probe)
    for c in caps.values():
        c.release()
    return infos


# ── Kinect probe ──────────────────────────────────────────────────────────

def _kinect_status() -> tuple[bool, str]:
    try:
        from pykinect2 import PyKinectV2  # noqa: F401
        return True, "Driver ready"
    except ImportError:
        return False, "pykinect2 not installed"
    except Exception as e:
        return False, str(e)


# ── Device list (cameras + kinect entry) ──────────────────────────────────

@dataclass
class DeviceEntry:
    dtype:      str   # "webcam" | "kinect"
    cam_index:  int
    label:      str
    sublabel:   str
    resolution: str
    available:  bool


def _build_entries(infos: list[CameraInfo]) -> list[DeviceEntry]:
    entries = [
        DeviceEntry("webcam", c.index, c.label,
                    f"Index {c.index}", f"{c.width} × {c.height}", True)
        for c in infos
    ]
    ok, msg = _kinect_status()
    entries.append(DeviceEntry(
        "kinect", 0, "Kinect v2", msg,
        "1920 × 1080  (depth + RGB)", ok,
    ))
    return entries


# ── Text helpers ──────────────────────────────────────────────────────────

def _surf(font, text, color):
    raw = font.render(text, True, color)
    out = pygame.Surface(raw.get_size(), pygame.SRCALPHA)
    out.blit(raw, (0, 0))
    return out


def _outlined(surf, font, text, color, outline, cx, cy, ow=2):
    r  = font.render(text, True, outline)
    sr = pygame.Surface(r.get_size(), pygame.SRCALPHA)
    sr.blit(r, (0, 0))
    for dx, dy in [(ow,0),(-ow,0),(0,ow),(0,-ow)]:
        surf.blit(sr, sr.get_rect(centerx=cx+dx, centery=cy+dy))
    rc = font.render(text, True, color)
    sc = pygame.Surface(rc.get_size(), pygame.SRCALPHA)
    sc.blit(rc, (0, 0))
    surf.blit(sc, sc.get_rect(centerx=cx, centery=cy))


def _bgr_to_surface(frame: np.ndarray, w: int, h: int) -> pygame.Surface:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, (w, h))
    return pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")


# ── Layout ────────────────────────────────────────────────────────────────

_ITEM_H = 88
_ITEM_G = 10
_LX, _LW = 55, 300
_LY      = 110
_PX, _PW, _PH = 415, 520, 292
_PY      = 130
_ACCENT  = (240, 165, 45)
_KC      = (80, 180, 240)


# ── Picker ────────────────────────────────────────────────────────────────

def run_tracker_picker(
    screen: pygame.Surface,
    bg_surf: pygame.Surface,
) -> TrackerChoice:
    """
    Show the device-selection screen.

    Cameras are opened ONCE here and the chosen cap is handed directly to
    the returned TrackerChoice — WebcamTracker will reuse it without a
    second VideoCapture() call, eliminating the reconnect flicker.
    """
    SW, SH = screen.get_size()

    try:
        f_title = pygame.font.SysFont("arial", 36, bold=True)
        f_label = pygame.font.SysFont("arial", 20, bold=True)
        f_sub   = pygame.font.SysFont("arial", 15)
        f_res   = pygame.font.SysFont("arial", 13)
        f_btn   = pygame.font.SysFont("arial", 22, bold=True)
        f_hint  = pygame.font.SysFont("arial", 17)
        f_err   = pygame.font.SysFont("arial", 19, bold=True)
    except Exception:
        f_title = f_label = f_sub = f_res = f_btn = f_hint = f_err = \
            pygame.font.Font(None, 24)

    # ── Open cameras ONCE ────────────────────────────────────────────────
    infos, caps = _open_cameras()
    entries     = _build_entries(infos)
    selected    = next((i for i, e in enumerate(entries) if e.available), 0)
    prev_surfs: dict[int, Optional[pygame.Surface]] = {i: None for i in range(len(entries))}

    def _confirm(idx: int) -> TrackerChoice:
        """Release every cap except the chosen one, return TrackerChoice."""
        entry = entries[idx]
        if entry.dtype == "webcam":
            keep = entry.cam_index
            for ci, c in list(caps.items()):
                if ci != keep:
                    c.release()
            return TrackerChoice("webcam", keep, caps.get(keep))
        else:   # kinect
            for c in caps.values():
                c.release()
            return TrackerChoice("kinect", 0, None)

    def _release_all():
        for c in caps.values():
            c.release()
        caps.clear()

    def _retry():
        nonlocal infos, entries, selected
        _release_all()
        new_infos, new_caps = _open_cameras()
        caps.update(new_caps)
        infos   = new_infos
        entries = _build_entries(infos)
        selected = next((i for i, e in enumerate(entries) if e.available), 0)
        prev_surfs.clear()
        prev_surfs.update({i: None for i in range(len(entries))})

    clock   = pygame.time.Clock()
    hovered = -1

    btn_w, btn_h = 260, 52
    btn_rect   = pygame.Rect(SW // 2 - btn_w // 2, SH - btn_h - 24, btn_w, btn_h)
    retry_rect = pygame.Rect(SW // 2 - 120, SH // 2 + 30, 240, 48)

    def item_rect(i: int) -> pygame.Rect:
        return pygame.Rect(_LX, _LY + i * (_ITEM_H + _ITEM_G), _LW, _ITEM_H)

    try:
        while True:
            mx, my    = pygame.mouse.get_pos()
            hovered   = next((i for i in range(len(entries))
                              if item_rect(i).collidepoint(mx, my)), -1)
            btn_hov   = btn_rect.collidepoint(mx, my)
            retry_hov = retry_rect.collidepoint(mx, my)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    _release_all(); pygame.quit(); raise SystemExit
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        _release_all(); pygame.quit(); raise SystemExit
                    if event.key in (pygame.K_UP,   pygame.K_w):
                        selected = (selected - 1) % len(entries)
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        selected = (selected + 1) % len(entries)
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if entries[selected].available:
                            return _confirm(selected)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if hovered >= 0:
                        selected = hovered
                    if btn_hov and entries[selected].available:
                        return _confirm(selected)
                    if retry_hov:
                        _retry()

            # Read one frame from every open webcam cap (keeps them alive).
            for i, entry in enumerate(entries):
                if entry.dtype != "webcam":
                    continue
                cap = caps.get(entry.cam_index)
                if cap is None or not cap.isOpened():
                    continue
                ok, frame = cap.read()
                if ok and frame is not None:
                    frame = cv2.flip(frame, 1)
                    prev_surfs[i] = _bgr_to_surface(frame, _PW, _PH)

            # ── Draw ──────────────────────────────────────────────────
            screen.blit(bg_surf, (0, 0))
            ov = pygame.Surface((SW, SH), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 110))
            screen.blit(ov, (0, 0))

            _outlined(screen, f_title, "Select Input Device",
                      (255, 218, 60), (80, 40, 0), SW // 2, 62)

            has_webcam = any(e.dtype == "webcam" and e.available for e in entries)
            if not has_webcam:
                for dy, (msg, col) in enumerate([
                    ("No cameras detected",               (255, 120, 100)),
                    ("Check your camera and press Retry", (190, 185, 210)),
                    ("Kinect v2 is still selectable below", (150, 145, 165)),
                ]):
                    s = _surf(f_err if dy == 0 else f_hint, msg, col)
                    screen.blit(s, s.get_rect(centerx=SW//2,
                                              top=SH//2 - 70 + dy * 34))
                rc = (70, 200, 90) if retry_hov else (50, 155, 65)
                pygame.draw.rect(screen, rc,           retry_rect, border_radius=12)
                pygame.draw.rect(screen, (120, 255, 140), retry_rect, 2, border_radius=12)
                rt = _surf(f_btn, "Retry Scan", (255, 255, 255))
                screen.blit(rt, rt.get_rect(center=retry_rect.center))

            # Device list.
            for i, entry in enumerate(entries):
                r      = item_rect(i)
                is_sel = (i == selected)
                is_hov = (i == hovered)
                avail  = entry.available
                accent = (_KC if entry.dtype == "kinect" else _ACCENT) if avail else (80, 78, 88)

                card = pygame.Surface((_LW, _ITEM_H), pygame.SRCALPHA)
                pygame.draw.rect(card,
                                 (14, 10, 28, 230 if is_sel else (185 if is_hov else 150)),
                                 (0, 0, _LW, _ITEM_H), border_radius=14)
                pygame.draw.rect(card,
                                 (*accent, 255 if is_sel else (160 if is_hov else 70)),
                                 (0, 0, _LW, _ITEM_H),
                                 3 if is_sel else (2 if is_hov else 1), border_radius=14)

                pygame.draw.circle(card,
                                   (80, 220, 90) if avail else (200, 70, 60),
                                   (_LW - 18, 18), 6)

                ic = accent
                if entry.dtype == "kinect":
                    pygame.draw.rect(card, (*ic, 140), (12, _ITEM_H//2-16, 32, 32), border_radius=6)
                    card.blit(_surf(f_label, "K", (255,255,255)),
                              _surf(f_label,"K",(0,0,0)).get_rect(centerx=28, centery=_ITEM_H//2))
                else:
                    pygame.draw.circle(card, (*ic, 140), (28, _ITEM_H//2), 16)
                    pygame.draw.circle(card, (255,255,255),  (28, _ITEM_H//2), 8)
                    pygame.draw.circle(card, (*ic, 200),     (28, _ITEM_H//2), 5)

                tc = (230, 225, 240) if avail else (120, 115, 130)
                sc = (160, 155, 175) if avail else (90, 88, 98)
                card.blit(_surf(f_label, entry.label,      tc), (52, 12))
                card.blit(_surf(f_sub,   entry.sublabel,   sc), (52, 36))
                card.blit(_surf(f_res,   entry.resolution, sc), (52, 56))
                screen.blit(card, r.topleft)

            # Preview pane.
            prev_rect = pygame.Rect(_PX, _PY, _PW, _PH)
            panel = pygame.Surface((_PW, _PH), pygame.SRCALPHA)
            pygame.draw.rect(panel, (14, 10, 28, 200), (0, 0, _PW, _PH), border_radius=14)
            screen.blit(panel, prev_rect.topleft)

            ps = prev_surfs.get(selected)
            if ps is not None:
                screen.blit(ps, prev_rect.topleft)
                pygame.draw.rect(screen, (255,255,255,40), prev_rect, 2, border_radius=14)
            else:
                e = entries[selected]
                msg = ("Kinect preview unavailable in picker" if e.dtype == "kinect"
                       else "Device not available" if not e.available
                       else "Warming up...")
                screen.blit(_surf(f_hint, msg, (140,135,160)),
                            _surf(f_hint, msg, (0,0,0)).get_rect(center=prev_rect.center))

            slbl = _surf(f_sub, f"Preview: {entries[selected].label}", (200,195,215))
            screen.blit(slbl, slbl.get_rect(centerx=_PX+_PW//2, top=_PY+_PH+10))

            # Start button.
            avail_sel = entries[selected].available
            bc = (65, 185, 80) if (btn_hov and avail_sel) else \
                 (45, 150, 60) if avail_sel else (55, 50, 65)
            border = (120,255,140) if avail_sel else (90,85,100)
            pygame.draw.rect(screen, bc,     btn_rect, border_radius=14)
            pygame.draw.rect(screen, border, btn_rect, 2, border_radius=14)
            bt = _surf(f_btn, f"Use  {entries[selected].label}",
                       (255,255,255) if avail_sel else (110,105,120))
            screen.blit(bt, bt.get_rect(center=btn_rect.center))

            screen.blit(
                _surf(f_hint, "Click a device or use Up/Down then Enter", (150,145,165)),
                _surf(f_hint, "", (0,0,0)).get_rect(centerx=SW//2, bottom=SH-5),
            )

            pygame.display.flip()
            clock.tick(30)

    except Exception:
        _release_all()
        raise
