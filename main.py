from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np
import pygame

from game.camera_picker import detect_cameras, run_camera_picker
from game.fruit import Fruit, FruitSpawner, split_fruit
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


def cv2_frame_to_surface(frame_bgr: np.ndarray, target_w: int, target_h: int) -> pygame.Surface:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, (target_w, target_h))
    return pygame.image.frombuffer(rgb.tobytes(), (target_w, target_h), "RGB")


def draw_trail(surf: pygame.Surface, trail_points: list, color=(255, 255, 255)) -> None:
    if len(trail_points) < 2:
        return
    for i in range(1, len(trail_points)):
        a = trail_points[i - 1]
        b = trail_points[i]
        width = max(2, int(2 + i * 0.8))
        pygame.draw.line(surf, color, (a.x, a.y), (b.x, b.y), width)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracker", choices=["webcam", "kinect"], default="webcam")
    parser.add_argument("--lives", type=int, default=3)
    parser.add_argument("--cam", type=int, default=None,
                        help="Camera index to use (skips picker)")
    args = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Hand-tracked Fruit Ninja")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 32, bold=True)
    big_font = pygame.font.SysFont("arial", 64, bold=True)

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

    spawner = FruitSpawner(SCREEN_W, SCREEN_H)
    fruits: list[Fruit] = []
    trails = TrailStore()

    score = 0
    lives = args.lives
    game_over = False
    flash_until = 0.0  # red flash on bomb / miss
    last_t = time.monotonic()

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
                        score = 0
                        lives = args.lives
                        game_over = False

            now = time.monotonic()
            dt = min(now - last_t, 1 / 30.0)
            last_t = now

            samples = tracker.poll()
            trails.update(samples)

            if not game_over:
                spawner.update(dt, fruits)

                for f in fruits:
                    f.update(dt)

                # Slice detection: any active trail vs any non-sliced fruit.
                new_pieces: list[Fruit] = []
                consumed_indices: set[int] = set()
                for idx, f in enumerate(fruits):
                    if f.sliced:
                        continue
                    for trail in trails.trails().values():
                        if check_slice(trail, f.x, f.y, f.radius):
                            consumed_indices.add(idx)
                            if f.is_bomb:
                                lives = max(0, lives - 1)
                                flash_until = now + 0.25
                                if lives == 0:
                                    game_over = True
                            else:
                                score += 1
                                a, b = split_fruit(f)
                                new_pieces.append(a)
                                new_pieces.append(b)
                            break

                # Remove sliced wholes, add halves.
                if consumed_indices:
                    fruits = [f for i, f in enumerate(fruits) if i not in consumed_indices]
                    fruits.extend(new_pieces)

                # Cull offscreen and count misses for whole fruits.
                kept: list[Fruit] = []
                for f in fruits:
                    if f.offscreen(SCREEN_W, SCREEN_H):
                        if not f.sliced and not f.is_bomb and f.vy > 0:
                            lives = max(0, lives - 1)
                            flash_until = now + 0.15
                            if lives == 0:
                                game_over = True
                        continue
                    kept.append(f)
                fruits = kept

            # --- Render ---
            bg = tracker.background_frame()
            if bg is not None:
                surf = cv2_frame_to_surface(bg, SCREEN_W, SCREEN_H)
                surf.set_alpha(110)
                screen.fill((0, 0, 0))
                screen.blit(surf, (0, 0))
            else:
                screen.fill((15, 15, 25))

            for f in fruits:
                f.draw(screen)

            # Trails
            for hand_id, trail in trails.trails().items():
                pts = list(trail.points)
                color = (255, 240, 200) if hand_id == 0 else (200, 230, 255)
                draw_trail(screen, pts, color)
                if pts:
                    pygame.draw.circle(screen, color, (int(pts[-1].x), int(pts[-1].y)), 12, 2)

            # HUD
            screen.blit(font.render(f"Score: {score}", True, (255, 255, 255)), (20, 16))
            screen.blit(font.render(f"Lives: {lives}", True, (255, 120, 120)), (SCREEN_W - 160, 16))

            if now < flash_until:
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                overlay.fill((255, 50, 50, 90))
                screen.blit(overlay, (0, 0))

            if game_over:
                txt = big_font.render("GAME OVER", True, (255, 80, 80))
                sub = font.render("Press R to restart, Esc to quit", True, (230, 230, 230))
                screen.blit(txt, txt.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 30)))
                screen.blit(sub, sub.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 30)))

            pygame.display.flip()
            clock.tick(FPS)
    finally:
        tracker.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
