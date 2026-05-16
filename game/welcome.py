from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

import pygame

from game.fruit import (
    FRUIT_PALETTE, GRAVITY, Fruit,
    _draw_watermelon_whole, _draw_orange_whole, _draw_apple_whole,
)


# ── Difficulty presets ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Difficulty:
    key:         str
    label:       str
    tagline:     str
    desc:        list   # two short lines
    lives:       int
    spawn_every: float
    bomb_chance: float
    slice_speed: float
    color:       tuple  # accent (R,G,B)
    fruit_name:  str    # which fruit sprite to show on the card


DIFFICULTIES: list[Difficulty] = [
    Difficulty(
        key="easy",   label="EASY",
        tagline="Relaxed",
        desc=["More lives, slower fruits", "Perfect for beginners"],
        lives=5, spawn_every=1.3, bomb_chance=0.04, slice_speed=700,
        color=(65, 200, 80), fruit_name="watermelon",
    ),
    Difficulty(
        key="medium", label="MEDIUM",
        tagline="Classic",
        desc=["Balanced speed and chaos", "The true Fruit Ninja feel"],
        lives=3, spawn_every=0.9, bomb_chance=0.08, slice_speed=900,
        color=(240, 158, 38), fruit_name="orange",
    ),
    Difficulty(
        key="hard",   label="HARD",
        tagline="Brutal",
        desc=["Fast fruits, many bombs", "Only 2 lives — good luck"],
        lives=2, spawn_every=0.55, bomb_chance=0.15, slice_speed=1100,
        color=(220, 52, 48), fruit_name="apple",
    ),
]


# ── Text helpers ──────────────────────────────────────────────────────────

def _surf(font, text, color):
    raw = font.render(text, True, color)
    out = pygame.Surface(raw.get_size(), pygame.SRCALPHA)
    out.blit(raw, (0, 0))
    return out


def _outlined(surf, font, text, color, outline, cx, cy, ow=3):
    """Blit outlined text centred at (cx, cy)."""
    r  = font.render(text, True, outline)
    sr = pygame.Surface(r.get_size(), pygame.SRCALPHA)
    sr.blit(r, (0, 0))
    for dx, dy in [(ow,0),(-ow,0),(0,ow),(0,-ow),
                   (ow,ow),(-ow,ow),(ow,-ow),(-ow,-ow)]:
        surf.blit(sr, sr.get_rect(centerx=cx+dx, centery=cy+dy))
    rc = font.render(text, True, color)
    sc = pygame.Surface(rc.get_size(), pygame.SRCALPHA)
    sc.blit(rc, (0, 0))
    surf.blit(sc, sc.get_rect(centerx=cx, centery=cy))


# ── Custom mini icons (drawn with pygame.draw, no unicode needed) ─────────

def _icon_heart(surf, cx, cy, sz, color):
    r = max(1, sz // 3)
    pygame.draw.circle(surf, color, (cx - r // 2, cy - r // 3), r)
    pygame.draw.circle(surf, color, (cx + r // 2, cy - r // 3), r)
    pts = [(cx - sz//2+1, cy - r//3),
           (cx + sz//2-1, cy - r//3),
           (cx,           cy + sz//2)]
    pygame.draw.polygon(surf, color, pts)


def _icon_bolt(surf, cx, cy, sz, color):
    # Zig-zag lightning bolt
    pts = [
        (cx + sz//3,  cy - sz//2),
        (cx - sz//8,  cy - sz//8),
        (cx + sz//5,  cy - sz//8),
        (cx - sz//3,  cy + sz//2),
        (cx + sz//8,  cy + sz//8),
        (cx - sz//5,  cy + sz//8),
    ]
    pygame.draw.polygon(surf, color, pts)


def _icon_bomb(surf, cx, cy, sz, color):
    r = sz // 2 - 1
    pygame.draw.circle(surf, color, (cx, cy + sz//8), r)
    # Highlight
    pygame.draw.circle(surf, tuple(min(255, c+60) for c in color),
                       (cx - r//3, cy - r//3 + sz//8), max(1, r//3))
    # Fuse
    pygame.draw.line(surf, (200, 180, 60),
                     (cx, cy - r + sz//8), (cx + r//2, cy - r - sz//5), 2)
    pygame.draw.circle(surf, (255, 240, 80), (cx + r//2, cy - r - sz//5), 3)


# ── Fruit icon surface ────────────────────────────────────────────────────

_ICON_DRAWERS = {
    "watermelon": _draw_watermelon_whole,
    "orange":     _draw_orange_whole,
    "apple":      _draw_apple_whole,
}

def _make_fruit_icon(name: str, size: int) -> pygame.Surface:
    raw = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
    draw = _ICON_DRAWERS.get(name)
    if draw:
        draw(raw, size)
    return pygame.transform.smoothscale(raw, (size, size))


# ── Decorative helpers ────────────────────────────────────────────────────

def _katana_line(surf, x1, y, x2, color=(180, 160, 100)):
    """Draw a horizontal sword / divider line with diamond accent."""
    pygame.draw.line(surf, color, (x1, y), (x2, y), 1)
    cx = (x1 + x2) // 2
    diamond = [(cx, y-5), (cx+8, y), (cx, y+5), (cx-8, y)]
    pygame.draw.polygon(surf, color, diamond)
    for dx in [-30, 30]:
        small = [(cx+dx, y-3), (cx+dx+5, y), (cx+dx, y+3), (cx+dx-5, y)]
        pygame.draw.polygon(surf, color, small)


# ── Demo fruits ───────────────────────────────────────────────────────────

def _spawn_demo(w, h, rng):
    name, skin, flesh = rng.choice(FRUIT_PALETTE)
    r   = rng.uniform(34, 50)
    x   = rng.uniform(0.06, 0.94) * w
    tx  = rng.uniform(0.2,  0.80) * w
    rh  = rng.uniform(0.30, 0.58) * h
    vy  = -math.sqrt(2 * GRAVITY * rh)
    tp  = -vy / GRAVITY
    vx  = (tx - x) / max(tp, 0.1)
    f   = Fruit(x=x, y=h+50, vx=vx, vy=vy, radius=r,
                color=skin, rind=flesh, name=name,
                spin=rng.uniform(-3.5, 3.5))
    return f


# ── Card geometry ─────────────────────────────────────────────────────────

_CW, _CH = 330, 310
_GAP      = 38


# ── Main ──────────────────────────────────────────────────────────────────

def run_welcome_screen(screen: pygame.Surface, bg_surf: pygame.Surface) -> Difficulty:
    """Blocking welcome screen — returns the chosen Difficulty."""
    SW, SH = screen.get_size()
    rng    = random.Random()
    clock  = pygame.time.Clock()

    try:
        f_title  = pygame.font.SysFont("arial", 78, bold=True)
        f_sub    = pygame.font.SysFont("arial", 20)
        f_tag    = pygame.font.SysFont("arial", 14, bold=True)
        f_label  = pygame.font.SysFont("arial", 34, bold=True)
        f_desc   = pygame.font.SysFont("arial", 16)
        f_stat   = pygame.font.SysFont("arial", 15, bold=True)
        f_key    = pygame.font.SysFont("arial", 19, bold=True)
        f_hint   = pygame.font.SysFont("arial", 19)
    except Exception:
        f_title = f_sub = f_tag = f_label = f_desc = f_stat = f_key = f_hint = \
            pygame.font.Font(None, 26)

    # Pre-build fruit icons (60 px).
    icons = {d.fruit_name: _make_fruit_icon(d.fruit_name, 60) for d in DIFFICULTIES}

    total_w = len(DIFFICULTIES) * _CW + (len(DIFFICULTIES)-1) * _GAP
    cx0     = SW // 2 - total_w // 2
    card_y  = SH // 2 - _CH // 2 + 55

    card_rects = [
        pygame.Rect(cx0 + i * (_CW + _GAP), card_y, _CW, _CH)
        for i in range(len(DIFFICULTIES))
    ]

    demos: list[Fruit] = []
    spawn_t = 0.0
    last_t  = time.monotonic()
    hovered = -1

    while True:
        now = time.monotonic()
        dt  = min(now - last_t, 1/30.0)
        last_t = now

        spawn_t -= dt
        if spawn_t <= 0:
            demos.append(_spawn_demo(SW, SH, rng))
            spawn_t = rng.uniform(0.55, 1.05)
        for f in demos:
            f.update(dt)
        demos = [f for f in demos if not f.offscreen(SW, SH)]

        mx, my = pygame.mouse.get_pos()
        hovered = next((i for i, r in enumerate(card_rects)
                        if r.collidepoint(mx, my)), -1)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); raise SystemExit
                if event.key == pygame.K_1: return DIFFICULTIES[0]
                if event.key == pygame.K_2: return DIFFICULTIES[1]
                if event.key == pygame.K_3: return DIFFICULTIES[2]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hovered >= 0:
                    return DIFFICULTIES[hovered]

        # ── Render ────────────────────────────────────────────────────────
        screen.blit(bg_surf, (0, 0))

        # Subtle dark fog only in the card region so background sky shows.
        fog = pygame.Surface((SW, _CH + 80), pygame.SRCALPHA)
        fog.fill((0, 0, 0, 55))
        screen.blit(fog, (0, card_y - 40))

        # Demo fruits behind everything.
        for f in demos:
            f.draw(screen)

        # ── Title ─────────────────────────────────────────────────────────
        ty = SH // 4 - 10
        pulse = 0.5 + 0.5 * math.sin(now * 2.0)

        # Warm glow behind text.
        for gr in (55, 42, 28, 14):
            a  = int(28 * pulse * (1 - gr/60))
            gs = pygame.Surface((gr*2, gr*2), pygame.SRCALPHA)
            pygame.draw.circle(gs, (255, 195, 50, a), (gr, gr), gr)
            screen.blit(gs, (SW//2 - gr, ty - gr + 6))

        _outlined(screen, f_title, "FRUIT NINJA",
                  (255, 218, 60), (90, 40, 0), SW//2, ty, ow=4)

        sub = _surf(f_sub, "Hand-Tracked Edition", (210, 195, 155))
        screen.blit(sub, sub.get_rect(centerx=SW//2, top=ty+52))

        _katana_line(screen, SW//2 - 160, ty+80, SW//2 + 160, (165, 145, 90))

        # ── Cards ─────────────────────────────────────────────────────────
        for i, (diff, base_rect) in enumerate(zip(DIFFICULTIES, card_rects)):
            is_hov = (i == hovered)
            lift   = 12 if is_hov else 0
            rect   = base_rect.move(0, -lift)

            # Outer glow on hover.
            if is_hov:
                for gl in (22, 14, 7):
                    gs2 = pygame.Surface((rect.w + gl*2, rect.h + gl*2), pygame.SRCALPHA)
                    a2  = int(80 * (1 - gl/24))
                    pygame.draw.rect(gs2, (*diff.color, a2),
                                     (0, 0, rect.w+gl*2, rect.h+gl*2),
                                     border_radius=22+gl)
                    screen.blit(gs2, (rect.x - gl, rect.y - gl))

            # Card face.
            card = pygame.Surface((_CW, _CH), pygame.SRCALPHA)
            bg_a = 225 if is_hov else 185
            pygame.draw.rect(card, (14, 9, 28, bg_a),
                             (0, 0, _CW, _CH), border_radius=20)

            # Colored top strip.
            strip_a = 240 if is_hov else 180
            strip   = pygame.Surface((_CW, 10), pygame.SRCALPHA)
            strip.fill((*diff.color, strip_a))
            card.blit(strip, (0, 0))

            # Border.
            bw = 3 if is_hov else 2
            ba = 255 if is_hov else 120
            pygame.draw.rect(card, (*diff.color, ba),
                             (0, 0, _CW, _CH), bw, border_radius=20)

            # -- Fruit icon --
            icon = icons[diff.fruit_name]
            ix   = _CW//2 - icon.get_width()//2
            card.blit(icon, (ix, 18))

            # -- Tagline pill --
            tag_txt  = _surf(f_tag, diff.tagline.upper(), diff.color)
            pill_w   = tag_txt.get_width() + 20
            pill_h   = tag_txt.get_height() + 8
            pill_x   = _CW//2 - pill_w//2
            pill_y   = 86
            pill_s   = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
            pygame.draw.rect(pill_s, (*diff.color, 50),
                             (0, 0, pill_w, pill_h), border_radius=8)
            pygame.draw.rect(pill_s, (*diff.color, 160),
                             (0, 0, pill_w, pill_h), 1, border_radius=8)
            pill_s.blit(tag_txt, (10, 4))
            card.blit(pill_s, (pill_x, pill_y))

            # -- Difficulty label --
            lbl = _surf(f_label, diff.label, diff.color)
            card.blit(lbl, lbl.get_rect(centerx=_CW//2, top=110))

            # -- Description --
            for li, line in enumerate(diff.desc):
                dl = _surf(f_desc, line, (185, 180, 200))
                card.blit(dl, dl.get_rect(centerx=_CW//2, top=152 + li*20))

            # -- Divider --
            pygame.draw.line(card, (*diff.color, 60),
                             (24, 198), (_CW-24, 198), 1)

            # -- Stats (icon + text, stacked vertically) --
            stats = [
                (_icon_heart, diff.color,         f"Lives:  {diff.lives}"),
                (_icon_bolt,  (120, 200, 255),
                 f"Speed:  {'Normal' if diff.spawn_every > 1.0 else 'Fast' if diff.spawn_every > 0.65 else 'Blazing'}"),
                (_icon_bomb,  (240, 155, 40),
                 f"Bombs: {'Few' if diff.bomb_chance < 0.07 else 'Some' if diff.bomb_chance < 0.12 else 'Many'}"),
            ]
            for si, (icon_fn, icol, stxt) in enumerate(stats):
                sy = 206 + si * 22
                tmp = pygame.Surface((18, 18), pygame.SRCALPHA)
                icon_fn(tmp, 9, 9, 14, icol)
                card.blit(tmp, (28, sy))
                st = _surf(f_stat, stxt, (210, 205, 220))
                card.blit(st, (50, sy + 1))

            # -- Keyboard shortcut --
            kb = _surf(f_key, f"[ {i+1} ]",
                       diff.color if is_hov else (140, 135, 160))
            card.blit(kb, kb.get_rect(centerx=_CW//2, bottom=_CH-14))

            screen.blit(card, rect.topleft)

        # ── Bottom hint ───────────────────────────────────────────────────
        hint = _surf(f_hint, "Click a card  or  press  1 / 2 / 3  to begin",
                     (175, 170, 195))
        screen.blit(hint, hint.get_rect(centerx=SW//2, bottom=SH-20))

        pygame.display.flip()
        clock.tick(60)
