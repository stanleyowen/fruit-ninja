from __future__ import annotations

import argparse
import math
import random
import sys
import time
import time as _time

# 💡 預防 Python 3.10+ 的 time.clock 崩潰
if not hasattr(time, 'clock'):
    time.clock = _time.perf_counter
    
import pygame

from game.camera_picker import TrackerChoice, run_tracker_picker
from game.fruit import Fruit, FruitSpawner, split_fruit
from game.juice import JuiceLayer
from game.slicer import TrailStore, check_slice
from game.welcome import run_welcome_screen
from trackers.base import HandTracker


SCREEN_W = 1280
SCREEN_H = 720
FPS = 60


def build_tracker(choice: TrackerChoice, max_hands: int = 2,
                  kinect_sensitivity: float = 1.5) -> HandTracker:
    if choice.tracker_type == "webcam":
        from trackers.webcam import WebcamTracker
        return WebcamTracker(SCREEN_W, SCREEN_H, cam_index=choice.cam_index,
                             existing_cap=choice.cap, max_hands=max_hands)
    if choice.tracker_type == "kinect":
        from trackers.kinect import KinectTracker
        return KinectTracker(SCREEN_W, SCREEN_H, sensitivity=kinect_sensitivity)
    raise ValueError(f"unknown tracker: {choice.tracker_type}")


# ── Background ────────────────────────────────────────────────────────────

def _lerp_color(c0: tuple, c1: tuple, t: float) -> tuple:
    return tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))


def build_background(w: int, h: int) -> pygame.Surface:
    """Japanese-dusk scene: warm sunset sky, layered mountains, bamboo silhouettes."""
    rng  = random.Random(17)
    surf = pygame.Surface((w, h))

    # ── Gradient sky (vivid dusk palette) ────────────────────────────────
    stops = [
        (0.00, ( 52,  28, 115)),  # rich indigo at top
        (0.20, ( 98,  38, 148)),  # vivid purple
        (0.44, (188,  62, 112)),  # strong rose
        (0.64, (232, 100,  58)),  # warm amber
        (0.82, (252, 165,  65)),  # bright orange-gold
        (1.00, (218, 105,  48)),  # deep amber
    ]
    for y in range(h):
        t = y / h
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                col = _lerp_color(c0, c1, (t - t0) / (t1 - t0))
                pygame.draw.line(surf, col, (0, y), (w, y))
                break

    # ── Moon glow ─────────────────────────────────────────────────────────
    mx, my = int(w * 0.74), int(h * 0.17)
    for gr in range(110, 0, -4):
        a = int(22 * (1 - gr / 110) ** 0.45)
        gs = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(gs, (255, 238, 195, a), (gr, gr), gr)
        surf.blit(gs, (mx - gr, my - gr))
    pygame.draw.circle(surf, (255, 248, 215), (mx, my), 40)
    pygame.draw.circle(surf, (248, 238, 200), (mx, my), 37)

    # ── Stars (faint dots above the mountain line) ────────────────────────
    for _ in range(80):
        sx = rng.randint(0, w)
        sy = rng.randint(0, int(h * 0.52))
        br = rng.randint(140, 230)
        pygame.draw.circle(surf, (br, br, br), (sx, sy), rng.randint(0, 1))

    # ── Far mountains (purple-haze silhouette) ────────────────────────────
    pts = [(0, h)]
    x = 0
    while x < w:
        x += rng.randint(55, 165)
        pts.append((min(x, w), int(h * rng.uniform(0.52, 0.66))))
    pts += [(w, h)]
    pygame.draw.polygon(surf, (72, 32, 108), pts)
    for i in range(1, len(pts) - 1):
        pygame.draw.line(surf, (110, 55, 145), pts[i-1], pts[i], 2)

    # ── Near mountains (dark, close) ──────────────────────────────────────
    pts2 = [(0, h)]
    x = 0
    while x < w:
        x += rng.randint(40, 120)
        pts2.append((min(x, w), int(h * rng.uniform(0.66, 0.80))))
    pts2 += [(w, h)]
    pygame.draw.polygon(surf, (32, 15, 55), pts2)
    for i in range(1, len(pts2) - 1):
        pygame.draw.line(surf, (62, 28, 88), pts2[i-1], pts2[i], 2)

    # ── Bamboo silhouettes (left & right edges) ───────────────────────────
    for side_x in [rng.randint(30, 90), rng.randint(55, 110),
                   w - rng.randint(30, 90), w - rng.randint(55, 110)]:
        sw  = rng.randint(7, 14)
        col = (14, 8, 26)
        pygame.draw.rect(surf, col, (side_x, 0, sw, h))
        ny = rng.randint(40, 100)
        while ny < h:
            pygame.draw.rect(surf, (22, 12, 38), (side_x - 3, ny, sw + 6, 8))
            ny += rng.randint(80, 145)

    # ── Vignette ──────────────────────────────────────────────────────────
    vig = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(80):
        a  = int(190 * ((80 - i) / 80) ** 2.3)
        vs = pygame.Surface((1, h), pygame.SRCALPHA)
        vs.fill((0, 0, 0, a))
        vig.blit(vs, (i, 0))
        vig.blit(vs, (w - 1 - i, 0))
    for i in range(50):
        a  = int(150 * ((50 - i) / 50) ** 2.3)
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

def draw_score_badge(small_font, big_font, score: int) -> pygame.Surface:
    W, H = 170, 68
    badge = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(badge, (0, 0, 0, 170), (0, 0, W, H), border_radius=14)
    pygame.draw.rect(badge, (255, 215, 80, 60), (0, 0, W, H), 2, border_radius=14)

    lbl = _txt(small_font, "SCORE", (200, 185, 100))
    badge.blit(lbl, (W // 2 - lbl.get_width() // 2, 7))

    val = _txt(big_font, str(score), (255, 255, 255))
    badge.blit(val, (W // 2 - val.get_width() // 2, 28))
    return badge


def draw_lives_badge(small_font, heart_font, lives: int, max_lives: int) -> pygame.Surface:
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

    return badge


def draw_game_over(surf: pygame.Surface, big_font, med_font, sm_font,
                   score: int, diff_label: str = "", diff_color: tuple = (220, 60, 60)) -> None:
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 195))
    surf.blit(overlay, (0, 0))

    PW, PH = 540, 300
    px = SCREEN_W // 2 - PW // 2
    py = SCREEN_H // 2 - PH // 2

    panel = pygame.Surface((PW, PH), pygame.SRCALPHA)
    pygame.draw.rect(panel, (18, 12, 32, 235), (0, 0, PW, PH), border_radius=22)
    pygame.draw.rect(panel, (*diff_color, 160), (0, 0, PW, PH), 3, border_radius=22)
    surf.blit(panel, (px, py))

    go = _txt_shadow(big_font, "GAME OVER", (255, 75, 75), (80, 0, 0), offset=3)
    surf.blit(go, go.get_rect(centerx=SCREEN_W // 2, top=py + 24))

    if diff_label:
        dl = _txt_shadow(sm_font, f"Difficulty: {diff_label}", diff_color, offset=1)
        surf.blit(dl, dl.get_rect(centerx=SCREEN_W // 2, top=py + 110))

    sc = _txt_shadow(med_font, f"Score: {score}", (255, 220, 80), offset=2)
    surf.blit(sc, sc.get_rect(centerx=SCREEN_W // 2, top=py + 150))

    hint = _txt_shadow(sm_font, "Press  R  to choose difficulty   •   Esc  to quit",
                       (200, 200, 210), offset=1)
    surf.blit(hint, hint.get_rect(centerx=SCREEN_W // 2, top=py + 240))


# ── Multiplayer HUD ───────────────────────────────────────────────────────

_MP_TRAIL_COLORS: dict[int, tuple] = {
    0: (255,  90,  90),   # Team A hand 1 — red
    1: (255, 160,  60),   # Team A hand 2 — orange
    2: ( 80, 180, 255),   # Team B hand 1 — blue
    3: (100, 255, 200),   # Team B hand 2 — cyan
}


def draw_mp_team_badge(small_font, big_font, team: int, score: int) -> pygame.Surface:
    W, H = 170, 68
    badge = pygame.Surface((W, H), pygame.SRCALPHA)
    color = (220, 60, 60) if team == 0 else (60, 140, 220)
    label = "TEAM  A" if team == 0 else "TEAM  B"
    pygame.draw.rect(badge, (0, 0, 0, 170), (0, 0, W, H), border_radius=14)
    pygame.draw.rect(badge, (*color, 100), (0, 0, W, H), 2, border_radius=14)
    lbl = _txt(small_font, label, color)
    badge.blit(lbl, (W // 2 - lbl.get_width() // 2, 7))
    val = _txt(big_font, str(score), (255, 255, 255))
    badge.blit(val, (W // 2 - val.get_width() // 2, 28))
    return badge


def draw_mp_timer_badge(small_font, big_font, time_left: float) -> pygame.Surface:
    W, H = 170, 68
    badge = pygame.Surface((W, H), pygame.SRCALPHA)
    secs  = int(math.ceil(time_left))
    color = (220, 60, 60) if secs <= 10 else (200, 185, 100)
    pygame.draw.rect(badge, (0, 0, 0, 170), (0, 0, W, H), border_radius=14)
    pygame.draw.rect(badge, (*color, 60), (0, 0, W, H), 2, border_radius=14)
    lbl = _txt(small_font, "TIME LEFT", (200, 185, 100))
    badge.blit(lbl, (W // 2 - lbl.get_width() // 2, 7))
    mins, sec_r = divmod(max(secs, 0), 60)
    val = _txt(big_font, f"{mins}:{sec_r:02d}", color)
    badge.blit(val, (W // 2 - val.get_width() // 2, 28))
    return badge


def draw_mp_game_over(surf: pygame.Surface, big_font, med_font, sm_font,
                      team_scores: list[int]) -> None:
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 195))
    surf.blit(overlay, (0, 0))

    a, b = team_scores
    if a > b:
        winner, color = "TEAM A WINS!", (220, 60, 60)
    elif b > a:
        winner, color = "TEAM B WINS!", (60, 140, 220)
    else:
        winner, color = "IT'S A DRAW!", (200, 185, 100)

    PW, PH = 560, 320
    px = SCREEN_W // 2 - PW // 2
    py = SCREEN_H // 2 - PH // 2

    panel = pygame.Surface((PW, PH), pygame.SRCALPHA)
    pygame.draw.rect(panel, (18, 12, 32, 235), (0, 0, PW, PH), border_radius=22)
    pygame.draw.rect(panel, (*color, 160), (0, 0, PW, PH), 3, border_radius=22)
    surf.blit(panel, (px, py))

    go = _txt_shadow(big_font, winner, color, (40, 0, 40), offset=3)
    surf.blit(go, go.get_rect(centerx=SCREEN_W // 2, top=py + 28))

    sc_a = _txt_shadow(med_font, f"Team A:  {a}", (220, 80, 80), offset=2)
    sc_b = _txt_shadow(med_font, f"Team B:  {b}", (80, 160, 255), offset=2)
    surf.blit(sc_a, sc_a.get_rect(centerx=SCREEN_W // 2, top=py + 130))
    surf.blit(sc_b, sc_b.get_rect(centerx=SCREEN_W // 2, top=py + 182))

    hint = _txt_shadow(sm_font, "Press  R  to choose difficulty   •   Esc  to quit",
                       (200, 200, 210), offset=1)
    surf.blit(hint, hint.get_rect(centerx=SCREEN_W // 2, top=py + 262))


def _build_warn_surf(font: pygame.font.Font) -> tuple[pygame.Surface, int, int]:
    """Pre-render the warning banner into a single composite surface."""
    msg = "✋  No hand detected — raise your hand in front of the camera"
    txt = _txt_shadow(font, msg, (255, 220, 80))
    tw, th = txt.get_size()
    W, H = tw + 28, th + 14
    composite = pygame.Surface((W, H), pygame.SRCALPHA)
    # Fill pill at 60% opacity (153 = round(255 * 0.6)); set_alpha later scales both together.
    pygame.draw.rect(composite, (0, 0, 0, 153), (0, 0, W, H), border_radius=10)
    composite.blit(txt, (14, 7))
    x = SCREEN_W // 2 - W // 2
    y = SCREEN_H - 58 - 7
    return composite, x, y


def draw_warning(surf: pygame.Surface, warn_surf: pygame.Surface,
                 wx: int, wy: int, now: float, last_hand_t: float) -> None:
    absent = now - last_hand_t
    if absent <= 1.0:
        return
    pulse = abs(math.sin((absent - 1.0) * math.pi * 1.4))
    warn_surf.set_alpha(int(80 + 175 * pulse))
    surf.blit(warn_surf, (wx, wy))


# ── Bomb fire ────────────────────────────────────────────────────────────

def draw_bomb_fire(surf: pygame.Surface, f: "Fruit", now: float) -> None:
    """Animated flame tongues drawn above a live bomb."""
    cx, cy = int(f.x), int(f.y)
    r      = int(f.radius)

    FW = r * 2 + 8
    FH = r * 4
    fs = pygame.Surface((FW, FH), pygame.SRCALPHA)
    lx = FW // 2

    # 3 flame tongues with staggered phases.
    for i in range(3):
        phase  = now * 8.5 + i * (math.tau / 3)
        lean   = int(math.sin(phase) * r * 0.30)
        height = int(r * (1.1 + 0.55 * abs(math.sin(phase * 0.72 + 0.4))))

        base_y = FH - 2
        # Draw 6 circles stacked bottom-to-tip, transitioning dark-red → yellow → white.
        for s in range(6):
            t  = s / 5
            px = lx + lean + int(math.sin(phase + t * 1.4) * r * 0.09)
            py = base_y - int(height * t)
            pr = max(1, int(r * 0.26 * (1 - t * 0.70)))

            if t < 0.33:
                col = (215, int(38  + 145 * (t / 0.33)), 0)
            elif t < 0.66:
                tt  = (t - 0.33) / 0.33
                col = (255, int(183 + 60  * tt), int(18 * tt))
            else:
                tt  = (t - 0.66) / 0.34
                col = (255, int(243 + 12  * tt), int(18 + 210 * tt))

            alpha = int(215 * (1 - t * 0.52))
            pygame.draw.circle(fs, (*col, alpha), (px, py), pr)

    # Bright core flicker at the very base of each tongue.
    for i in range(3):
        phase = now * 12.0 + i * (math.tau / 3)
        px = lx + int(math.sin(phase) * r * 0.18)
        py = FH - 4
        pr = max(2, int(r * 0.14))
        pygame.draw.circle(fs, (255, 255, 180, 240), (px, py), pr)

    surf.blit(fs, (cx - FW // 2, cy - r - FH + 10))


# ── Bomb explosion ────────────────────────────────────────────────────────

EXPLOSION_DURATION = 0.65

def draw_explosion(surf: pygame.Surface, x: float, y: float, elapsed: float) -> None:
    """Animated shockwave + sparks drawn at (x, y). elapsed = seconds since detonation."""
    t = min(elapsed / EXPLOSION_DURATION, 1.0)
    cx, cy = int(x), int(y)
    MAX_R = 160
    size  = MAX_R * 2 + 20
    ov    = pygame.Surface((size, size), pygame.SRCALPHA)
    ox = oy = size // 2

    # Central flash — bright burst that fades in the first 40 % of lifetime.
    if t < 0.40:
        ft      = t / 0.40
        flash_r = int(30 + 80 * ft)
        flash_a = int(220 * (1.0 - ft))
        pygame.draw.circle(ov, (255, 230, 100, flash_a), (ox, oy), flash_r)

    # Expanding shockwave ring.
    ring_r = int(12 + t * (MAX_R - 12))
    ring_a = int(255 * (1.0 - t * t))
    ring_w = max(2, int(14 * (1.0 - t)))
    pygame.draw.circle(ov, (255, 110, 20, ring_a), (ox, oy), ring_r, ring_w)
    # Inner softer ring for volume.
    inner_r = max(1, ring_r - ring_w - 2)
    pygame.draw.circle(ov, (255, 200, 80, ring_a // 3), (ox, oy), inner_r, max(1, ring_w // 2))

    # Flying sparks — deterministic per position so they don't jitter frame to frame.
    rng = random.Random(int(x) ^ (int(y) << 16))
    et  = t * EXPLOSION_DURATION          # real seconds elapsed
    for _ in range(16):
        angle = rng.uniform(0, math.tau)
        speed = rng.uniform(130, 300)
        sx    = int(ox + math.cos(angle) * speed * et)
        sy    = int(oy + math.sin(angle) * speed * et + 180 * et * et)  # gravity
        sr    = max(1, int(5 * (1.0 - t * 0.85)))
        sa    = int(255 * (1.0 - t))
        gc    = int(max(0, 150 - 150 * t))
        pygame.draw.circle(ov, (255, gc, 0, sa), (sx, sy), sr)

    surf.blit(ov, (cx - ox, cy - oy))


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
    parser.add_argument("--tracker", choices=["webcam", "kinect"], default=None,
                        help="Skip picker and force tracker type")
    parser.add_argument("--cam", type=int, default=None,
                        help="Skip picker and use this camera index")
    parser.add_argument("--kinect-sensitivity", type=float, default=0.5,
                        help="Kinect motion amplification (default 1.5). "
                             "Higher = less hand travel needed (e.g. 2.0 = half the movement).")
    args = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Hand-tracked Fruit Ninja")
    clock = pygame.time.Clock()

    f_small  = pygame.font.SysFont("arial", 18, bold=True)
    f_hud    = pygame.font.SysFont("arial", 30, bold=True)
    f_heart  = pygame.font.SysFont("arial", 26)
    f_big    = pygame.font.SysFont("arial", 64, bold=True)
    f_med    = pygame.font.SysFont("arial", 36, bold=True)
    f_warn   = pygame.font.SysFont("arial", 24, bold=True)

    # Background built once; shared by all screens.
    bg_surf = build_background(SCREEN_W, SCREEN_H)

    # Cached single-color overlay — reused every flash frame instead of re-allocated.
    flash_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    flash_overlay.fill((255, 50, 50, 100))

    # Warning banner built once; set_alpha() animates it each frame.
    warn_surf, warn_x, warn_y = _build_warn_surf(f_warn)

    # ── Step 1: device / tracker selection ───────────────────────────────
    if args.tracker == "webcam" and args.cam is not None:
        tracker_choice = TrackerChoice("webcam", args.cam)
    elif args.tracker == "kinect":
        from game.camera_picker import _kinect_status
        ok, _msg = _kinect_status()
        if ok:
            tracker_choice = TrackerChoice("kinect", 0)
        else:
            print(f"Kinect unavailable ({_msg}); opening device picker.", file=sys.stderr)
            tracker_choice = run_tracker_picker(screen, bg_surf)
    else:
        tracker_choice = run_tracker_picker(screen, bg_surf)

    # ── Step 2: difficulty selection ──────────────────────────────────────
    difficulty = run_welcome_screen(screen, bg_surf)

    # ── Step 3: start tracking ────────────────────────────────────────────
    mp        = difficulty.multiplayer
    max_hands = 4 if mp else 2
    tracker   = build_tracker(tracker_choice, max_hands=max_hands,
                              kinect_sensitivity=args.kinect_sensitivity)
    tracker.start()

    juice_layer = JuiceLayer(SCREEN_W, SCREEN_H)
    spawner     = FruitSpawner(SCREEN_W, SCREEN_H,
                               spawn_every=difficulty.spawn_every,
                               bomb_chance=difficulty.bomb_chance)
    fruits: list[Fruit] = []
    trails      = TrailStore()

    MAX_LIVES   = difficulty.lives
    score       = 0
    lives       = MAX_LIVES
    team_scores = [0, 0]       # only used in 2v2 mode
    time_left   = difficulty.time_limit
    game_over   = False
    flash_until = 0.0
    explosions: list[tuple[float, float, float]] = []   # (x, y, start_time)
    last_hand_t = time.monotonic()
    last_t      = time.monotonic()

    # Solo HUD badge caches — rebuilt only when the displayed value changes.
    _score_surf: pygame.Surface | None = None
    _score_val  = -1
    _lives_surf: pygame.Surface | None = None
    _lives_key: tuple[int, int] = (-1, -1)

    # Multiplayer HUD badge caches.
    _mp_a_surf:     pygame.Surface | None = None
    _mp_a_val       = -1
    _mp_b_surf:     pygame.Surface | None = None
    _mp_b_val       = -1
    _mp_timer_surf: pygame.Surface | None = None
    _mp_timer_secs  = -1

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return 0
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return 0
                    if event.key == pygame.K_r and game_over:
                        difficulty = run_welcome_screen(screen, bg_surf)
                        new_mp        = difficulty.multiplayer
                        new_max_hands = 4 if new_mp else 2
                        if new_max_hands != max_hands:
                            tracker.stop()
                            tracker   = build_tracker(tracker_choice, max_hands=new_max_hands,
                                                      kinect_sensitivity=args.kinect_sensitivity)
                            tracker.start()
                            max_hands = new_max_hands
                        mp = new_mp
                        trails = TrailStore()
                        spawner = FruitSpawner(SCREEN_W, SCREEN_H,
                                               spawn_every=difficulty.spawn_every,
                                               bomb_chance=difficulty.bomb_chance)
                        MAX_LIVES   = difficulty.lives
                        fruits.clear()
                        juice_layer.clear()
                        score       = 0
                        lives       = MAX_LIVES
                        team_scores = [0, 0]
                        time_left   = difficulty.time_limit
                        game_over   = False
                        explosions.clear()
                        # Invalidate all caches.
                        _score_val = -1;  _lives_key = (-1, -1)
                        _mp_a_val = _mp_b_val = _mp_timer_secs = -1

            now = time.monotonic()
            dt  = min(now - last_t, 1 / 30.0)
            last_t = now

            samples = tracker.poll()
            trails.update(samples)
            if samples:
                last_hand_t = now

            if not game_over:
                if mp:
                    time_left = max(0.0, time_left - dt)
                    if time_left <= 0:
                        game_over = True

                spawner.update(dt, fruits)
                for f in fruits:
                    f.update(dt)

                # Slice detection — iterate items() to know which hand sliced.
                new_pieces: list[Fruit] = []
                consumed:   set[int]   = set()
                for idx, f in enumerate(fruits):
                    if f.sliced:
                        continue
                    for trail_id, trail in trails.trails().items():
                        if check_slice(trail, f.x, f.y, f.radius,
                                       difficulty.slice_speed):
                            consumed.add(idx)
                            if f.is_bomb:
                                juice_layer.splat(f.x, f.y, "bomb", f.radius)
                                explosions.append((f.x, f.y, now))
                                if mp:
                                    team = trail_id // 2
                                    team_scores[team] = max(0, team_scores[team] - 1)
                                else:
                                    lives = max(0, lives - 1)
                                    flash_until = now + 0.3
                                    if lives == 0:
                                        game_over = True
                            else:
                                juice_layer.splat(f.x, f.y, f.name, f.radius)
                                if mp:
                                    team_scores[trail_id // 2] += 1
                                else:
                                    score += 1
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
                        if not mp and not f.sliced and not f.is_bomb and f.vy > 0:
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

            for f in fruits:                    # 3. Fruits + bomb fire
                f.draw(screen)
                if f.is_bomb and not f.sliced:
                    draw_bomb_fire(screen, f, now)

            explosions = [(ex, ey, et) for ex, ey, et in explosions  # 4. Explosions
                          if now - et < EXPLOSION_DURATION]
            for ex, ey, et in explosions:
                draw_explosion(screen, ex, ey, now - et)

            for hand_id, trail in trails.trails().items():   # 5. Slash trails
                pts   = list(trail.points)
                color = (_MP_TRAIL_COLORS.get(hand_id, (255, 200, 80)) if mp
                         else ((255, 200, 80) if hand_id == 0 else (120, 200, 255)))
                draw_trail(screen, pts, color)
                if pts:
                    cx, cy = int(pts[-1].x), int(pts[-1].y)
                    pygame.draw.circle(screen, color, (cx, cy), 14, 2)
                    pygame.draw.circle(screen, (255, 255, 255), (cx, cy), 6)

            if now < flash_until:               # 6. Hit flash
                screen.blit(flash_overlay, (0, 0))

            if mp:                              # 7. HUD
                if team_scores[0] != _mp_a_val:
                    _mp_a_surf = draw_mp_team_badge(f_small, f_hud, 0, team_scores[0])
                    _mp_a_val  = team_scores[0]
                screen.blit(_mp_a_surf, (18, 14))

                timer_secs = int(math.ceil(time_left))
                if timer_secs != _mp_timer_secs:
                    _mp_timer_surf = draw_mp_timer_badge(f_small, f_hud, time_left)
                    _mp_timer_secs = timer_secs
                screen.blit(_mp_timer_surf,
                            (SCREEN_W // 2 - _mp_timer_surf.get_width() // 2, 14))

                if team_scores[1] != _mp_b_val:
                    _mp_b_surf = draw_mp_team_badge(f_small, f_hud, 1, team_scores[1])
                    _mp_b_val  = team_scores[1]
                screen.blit(_mp_b_surf, (SCREEN_W - 18 - _mp_b_surf.get_width(), 14))
            else:
                if score != _score_val:
                    _score_surf = draw_score_badge(f_small, f_hud, score)
                    _score_val  = score
                screen.blit(_score_surf, (18, 14))

                lives_key = (lives, MAX_LIVES)
                if lives_key != _lives_key:
                    _lives_surf = draw_lives_badge(f_small, f_heart, lives, MAX_LIVES)
                    _lives_key  = lives_key
                screen.blit(_lives_surf, (SCREEN_W - 18 - _lives_surf.get_width(), 14))

            draw_warning(screen, warn_surf, warn_x, warn_y, now, last_hand_t)

            if game_over:
                if mp:
                    draw_mp_game_over(screen, f_big, f_med, f_hud, team_scores)
                else:
                    draw_game_over(screen, f_big, f_med, f_hud, score,
                                   difficulty.label, difficulty.color)

            pygame.display.flip()
            clock.tick(FPS)
    finally:
        tracker.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
