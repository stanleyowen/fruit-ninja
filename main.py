from __future__ import annotations

import argparse
import math
import random
import sys
import time

import pygame

from game.camera_picker import detect_cameras, run_camera_picker
from game.fruit import Fruit, FruitSpawner, split_fruit
from game.juice import JuiceLayer
from game.slicer import TrailStore, check_slice
from trackers.base import HandTracker


SCREEN_W = 1280
SCREEN_H = 720
FPS = 60


def build_tracker(kind: str, cam_index: int = 0) -> HandTracker:
    if kind == "webcam":
        from trackers.webcam import WebcamTracker
        return WebcamTracker(SCREEN_W, SCREEN_H, cam_index=cam_index)
    if kind == "kinect":
        from trackers.kinect import KinectTracker
        return KinectTracker(SCREEN_W, SCREEN_H)
    raise ValueError(f"unknown tracker: {kind}")


# ── Background ────────────────────────────────────────────────────────────

def build_background(w: int, h: int) -> pygame.Surface:
    """Bamboo-dojo background: vertical stalks over a dark gradient sky."""
    rng  = random.Random(7)
    surf = pygame.Surface((w, h))

    # Deep navy-indigo gradient sky.
    for y in range(h):
        t = y / h
        r = int(12  + 8  * t)
        g = int(8   + 6  * t)
        b = int(38  + 22 * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))

    # Bamboo stalks.
    x = rng.randint(-30, 0)
    while x < w + 60:
        sw = rng.randint(44, 74)
        base = (
            rng.randint(130, 168),
            rng.randint(158, 200),
            rng.randint(42,  75),
        )
        # Cylindrical highlight: brighter at centre, darker at edges.
        for px in range(x, min(x + sw, w)):
            t = (px - x) / sw
            bright = 0.72 + 0.38 * math.exp(-((t - 0.5) ** 2) / 0.07)
            col = tuple(min(255, int(c * bright)) for c in base)
            pygame.draw.line(surf, col, (px, 0), (px, h))

        # Edge shadows.
        for i in range(5):
            a  = int(190 * (1 - i / 5))
            sl = pygame.Surface((1, h), pygame.SRCALPHA)
            sl.fill((0, 0, 0, a))
            surf.blit(sl, (x + i, 0))
            if x + sw - 1 - i < w:
                surf.blit(sl, (x + sw - 1 - i, 0))

        # Bamboo nodes.
        ny = rng.randint(50, 115)
        while ny < h:
            node = tuple(max(0, c - 28) for c in base)
            pygame.draw.rect(surf, node, (x, ny, sw, 8))
            hl = tuple(min(255, c + 22) for c in base)
            pygame.draw.rect(surf, hl, (x + 2, ny + 1, sw - 4, 3))
            ny += rng.randint(80, 148)

        x += sw + rng.randint(2, 6)

    # Light dim (keeps bamboo clearly visible).
    dim = pygame.Surface((w, h), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 72))
    surf.blit(dim, (0, 0))

    # Vignette corners.
    vig = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(90):
        a  = int(200 * ((90 - i) / 90) ** 2.4)
        vs = pygame.Surface((1, h), pygame.SRCALPHA)
        vs.fill((0, 0, 0, a))
        vig.blit(vs, (i, 0))
        vig.blit(vs, (w - 1 - i, 0))
    for i in range(55):
        a  = int(160 * ((55 - i) / 55) ** 2.4)
        hs = pygame.Surface((w, 1), pygame.SRCALPHA)
        hs.fill((0, 0, 0, a))
        vig.blit(hs, (0, i))
        vig.blit(hs, (0, h - 1 - i))
    surf.blit(vig, (0, 0))
    return surf


# ── Text helpers (avoids macOS font-background rendering quirk) ───────────

def _txt(font: pygame.font.Font, text: str, color: tuple) -> pygame.Surface:
    """Render text onto a transparent surface so no font-bg bleeds through."""
    raw = font.render(text, True, color)
    out = pygame.Surface(raw.get_size(), pygame.SRCALPHA)
    out.blit(raw, (0, 0))
    return out


def _txt_shadow(font: pygame.font.Font, text: str, color: tuple,
                shadow: tuple = (0, 0, 0), offset: int = 2) -> pygame.Surface:
    raw_s = font.render(text, True, shadow)
    raw_c = font.render(text, True, color)
    w = raw_c.get_width() + offset
    h = raw_c.get_height() + offset
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    sh = pygame.Surface(raw_s.get_size(), pygame.SRCALPHA)
    sh.blit(raw_s, (0, 0))
    sh.set_alpha(180)
    out.blit(sh, (offset, offset))
    out.blit(raw_c, (0, 0))
    return out


# ── HUD drawing ───────────────────────────────────────────────────────────

def draw_score_badge(surf: pygame.Surface, small_font, big_font,
                     score: int, x: int, y: int) -> None:
    W, H = 170, 68
    badge = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(badge, (0, 0, 0, 170), (0, 0, W, H), border_radius=14)
    pygame.draw.rect(badge, (255, 215, 80, 60), (0, 0, W, H), 2, border_radius=14)

    lbl = _txt(small_font, "SCORE", (200, 185, 100))
    badge.blit(lbl, (W // 2 - lbl.get_width() // 2, 7))

    val = _txt(big_font, str(score), (255, 255, 255))
    badge.blit(val, (W // 2 - val.get_width() // 2, 28))
    surf.blit(badge, (x, y))


def draw_lives_badge(surf: pygame.Surface, small_font, heart_font,
                     lives: int, max_lives: int, x: int, y: int) -> None:
    heart_w  = heart_font.size("♥")[0]
    W = max(140, max_lives * (heart_w + 6) + 24)
    H = 68
    badge = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(badge, (0, 0, 0, 170), (0, 0, W, H), border_radius=14)
    pygame.draw.rect(badge, (220, 80, 80, 60), (0, 0, W, H), 2, border_radius=14)

    lbl = _txt(small_font, "LIVES", (200, 120, 120))
    badge.blit(lbl, (W // 2 - lbl.get_width() // 2, 7))

    total_hw = max_lives * (heart_w + 6) - 6
    hx = W // 2 - total_hw // 2
    for i in range(max_lives):
        col = (220, 55, 55) if i < lives else (70, 55, 55)
        h_surf = _txt(heart_font, "♥", col)
        badge.blit(h_surf, (hx + i * (heart_w + 6), 30))

    surf.blit(badge, (x - W, y))


def draw_game_over(surf: pygame.Surface, big_font, med_font, sm_font,
                   score: int) -> None:
    # Full-screen dim.
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 190))
    surf.blit(overlay, (0, 0))

    PW, PH = 520, 280
    px = SCREEN_W // 2 - PW // 2
    py = SCREEN_H // 2 - PH // 2

    panel = pygame.Surface((PW, PH), pygame.SRCALPHA)
    pygame.draw.rect(panel, (18, 12, 32, 230), (0, 0, PW, PH), border_radius=22)
    pygame.draw.rect(panel, (220, 60, 60, 140), (0, 0, PW, PH), 3, border_radius=22)
    surf.blit(panel, (px, py))

    # "GAME OVER"
    go  = _txt_shadow(big_font, "GAME OVER", (255, 75, 75), (80, 0, 0), offset=3)
    surf.blit(go, go.get_rect(centerx=SCREEN_W // 2, top=py + 30))

    # Final score line
    sc  = _txt_shadow(med_font, f"Score: {score}", (255, 220, 80), offset=2)
    surf.blit(sc, sc.get_rect(centerx=SCREEN_W // 2, top=py + 130))

    # Restart hint
    hint = _txt_shadow(sm_font, "Press  R  to restart   •   Esc  to quit",
                       (200, 200, 210), offset=1)
    surf.blit(hint, hint.get_rect(centerx=SCREEN_W // 2, top=py + 200))


def draw_warning(surf: pygame.Surface, font, now: float, last_hand_t: float) -> None:
    absent = now - last_hand_t
    if absent <= 1.0:
        return
    pulse = abs(math.sin((absent - 1.0) * math.pi * 1.4))
    alpha = int(80 + 175 * pulse)

    msg = "✋  No hand detected — raise your hand in front of the camera"
    txt = _txt_shadow(font, msg, (255, 220, 80))
    txt.set_alpha(alpha)

    tw, th = txt.get_size()
    wx = SCREEN_W // 2 - tw // 2
    wy = SCREEN_H - 58

    pill = pygame.Surface((tw + 28, th + 14), pygame.SRCALPHA)
    pygame.draw.rect(pill, (0, 0, 0, int(alpha * 0.6)), (0, 0, tw + 28, th + 14),
                     border_radius=10)
    surf.blit(pill, (wx - 14, wy - 7))
    surf.blit(txt,  (wx, wy))


# ── Slash trail ───────────────────────────────────────────────────────────

def draw_trail(surf: pygame.Surface, points: list, color: tuple) -> None:
    n = len(points)
    if n < 2:
        return
    # Glow pass (thick, dimmer).
    glow = tuple(min(255, c + 60) for c in color)
    for i in range(1, n):
        t = i / n
        w = max(1, int(t * 10))
        a, b = points[i - 1], points[i]
        pygame.draw.line(surf, glow, (int(a.x), int(a.y)), (int(b.x), int(b.y)), w + 4)
    # White core pass.
    for i in range(1, n):
        t = i / n
        w = max(1, int(t * 5))
        a, b = points[i - 1], points[i]
        pygame.draw.line(surf, (255, 255, 255), (int(a.x), int(a.y)), (int(b.x), int(b.y)), w)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracker", choices=["webcam", "kinect"], default="webcam")
    parser.add_argument("--lives", type=int, default=3)
    parser.add_argument("--cam", type=int, default=None, help="Camera index (skips picker)")
    args = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Hand-tracked Fruit Ninja")
    clock = pygame.time.Clock()

    # Fonts — SysFont can have bg-colour artefacts on macOS; we always render
    # onto transparent surfaces via _txt() / _txt_shadow() to avoid this.
    f_small  = pygame.font.SysFont("arial", 18, bold=True)
    f_hud    = pygame.font.SysFont("arial", 30, bold=True)
    f_heart  = pygame.font.SysFont("arial", 26)
    f_big    = pygame.font.SysFont("arial", 64, bold=True)
    f_med    = pygame.font.SysFont("arial", 36, bold=True)
    f_warn   = pygame.font.SysFont("arial", 24, bold=True)

    # Camera selection (webcam mode only).
    cam_index = 0
    if args.tracker == "webcam":
        if args.cam is not None:
            cam_index = args.cam
        else:
            cameras = detect_cameras()
            if not cameras:
                print("ERROR: No cameras detected.")
                pygame.quit()
                return 1
            cam_index = run_camera_picker(screen, cameras)

    tracker = build_tracker(args.tracker, cam_index=cam_index)
    tracker.start()

    bg_surf     = build_background(SCREEN_W, SCREEN_H)
    juice_layer = JuiceLayer(SCREEN_W, SCREEN_H)
    spawner     = FruitSpawner(SCREEN_W, SCREEN_H)
    fruits: list[Fruit] = []
    trails      = TrailStore()

    MAX_LIVES   = args.lives
    score       = 0
    lives       = MAX_LIVES
    game_over   = False
    flash_until = 0.0
    last_hand_t = time.monotonic()
    last_t      = time.monotonic()

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return 0
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return 0
                    if event.key == pygame.K_r and game_over:
                        fruits.clear()
                        juice_layer.clear()
                        score     = 0
                        lives     = MAX_LIVES
                        game_over = False

            now = time.monotonic()
            dt  = min(now - last_t, 1 / 30.0)
            last_t = now

            samples = tracker.poll()
            trails.update(samples)
            if samples:
                last_hand_t = now

            if not game_over:
                spawner.update(dt, fruits)
                for f in fruits:
                    f.update(dt)

                # Slice detection.
                new_pieces: list[Fruit] = []
                consumed:   set[int]   = set()
                for idx, f in enumerate(fruits):
                    if f.sliced:
                        continue
                    for trail in trails.trails().values():
                        if check_slice(trail, f.x, f.y, f.radius):
                            consumed.add(idx)
                            if f.is_bomb:
                                lives = max(0, lives - 1)
                                flash_until = now + 0.3
                                juice_layer.splat(f.x, f.y, "bomb", f.radius)
                                if lives == 0:
                                    game_over = True
                            else:
                                score += 1
                                juice_layer.splat(f.x, f.y, f.name, f.radius)
                                a, b = split_fruit(f)
                                new_pieces.append(a)
                                new_pieces.append(b)
                            break

                if consumed:
                    fruits = [f for i, f in enumerate(fruits) if i not in consumed]
                    fruits.extend(new_pieces)

                kept: list[Fruit] = []
                for f in fruits:
                    if f.offscreen(SCREEN_W, SCREEN_H):
                        if not f.sliced and not f.is_bomb and f.vy > 0:
                            lives = max(0, lives - 1)
                            flash_until = now + 0.18
                            if lives == 0:
                                game_over = True
                        continue
                    kept.append(f)
                fruits = kept

            # ── Render ────────────────────────────────────────────────────

            screen.blit(bg_surf, (0, 0))       # 1. Bamboo background
            juice_layer.draw(screen)            # 2. Juice stains

            for f in fruits:                    # 3. Fruits
                f.draw(screen)

            for hand_id, trail in trails.trails().items():   # 4. Slash trails
                pts   = list(trail.points)
                color = (255, 200, 80) if hand_id == 0 else (120, 200, 255)
                draw_trail(screen, pts, color)
                if pts:
                    cx, cy = int(pts[-1].x), int(pts[-1].y)
                    pygame.draw.circle(screen, color, (cx, cy), 14, 2)
                    pygame.draw.circle(screen, (255, 255, 255), (cx, cy), 6)

            if now < flash_until:               # 5. Hit flash
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                overlay.fill((255, 50, 50, 100))
                screen.blit(overlay, (0, 0))

            draw_score_badge(screen, f_small, f_hud, score, 18, 14)
            draw_lives_badge(screen, f_small, f_heart, lives, MAX_LIVES,
                             SCREEN_W - 18, 14)

            draw_warning(screen, f_warn, now, last_hand_t)

            if game_over:
                draw_game_over(screen, f_big, f_med, f_hud, score)

            pygame.display.flip()
            clock.tick(FPS)
    finally:
        tracker.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
