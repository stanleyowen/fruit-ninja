# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the game

```bash
# Activate venv first
source .venv/bin/activate

# Run with interactive camera + difficulty pickers (normal path)
python main.py

# Skip both pickers via CLI
python main.py --tracker webcam --cam 0
python main.py --tracker kinect
```

`hand_landmarker.task` (MediaPipe model) is auto-downloaded on first run if missing.

## Dependencies

```bash
pip install -r requirements.txt
```

`pykinect2` and `comtypes` are commented out — they are Windows-only and only needed for Kinect. Uncomment when wiring up Kinect hardware.

## Architecture

The app runs three sequential screens before entering the game loop, all sharing one pre-built `bg_surf`:

```
build_background()
  → run_tracker_picker()   # game/camera_picker.py  → TrackerChoice
  → run_welcome_screen()   # game/welcome.py         → Difficulty
  → build_tracker()        # main.py                 → HandTracker
  → game loop (main.py)
```

**Tracker abstraction** (`trackers/`): `HandTracker` ABC in `base.py` exposes `start()`, `stop()`, `poll() → list[HandSample]`. `WebcamTracker` uses MediaPipe Tasks API (`RunningMode.VIDEO`); `KinectTracker` uses `pykinect2`. Both output `HandSample(hand_id, x, y, z, timestamp)` in screen-space pixels, mirrored horizontally for selfie view.

**Camera stability**: Cameras are opened exactly once. `_open_cameras()` in `camera_picker.py` opens all probed indices and returns the live `caps` dict. The chosen cap is passed through `TrackerChoice.cap` → `build_tracker()` → `WebcamTracker(existing_cap=...)`. `start()` reuses it directly instead of calling `cv2.VideoCapture()` again — this prevents the macOS Continuity Camera reconnect flicker.

**Slice detection** (`game/slicer.py`): `TrailStore` keeps a `HandTrail` per `hand_id`. Each trail stores a `deque` of `TrailPoint`. `check_slice(trail, cx, cy, r, speed_threshold)` tests the latest segment: speed ≥ threshold AND segment intersects the fruit's bounding circle. The threshold comes from the chosen `Difficulty.slice_speed`.

**Fruit rendering** (`game/fruit.py`): Each `Fruit` has a `_surf_cache` built once by `_make_surface()` using per-type `_draw_*_whole` / `_draw_*_half` functions on an SRCALPHA surface. The cached surface is rotated each frame. Halves clip one side to transparent via `pygame.draw.rect(..., (0,0,0,0), mask_rect)`. `split_fruit()` produces two half-Fruits with opposing lateral drift.

**Juice persistence** (`game/juice.py`): `JuiceLayer` owns a single persistent SRCALPHA surface. `splat()` draws blobs + drip streaks + spray dots in one call; results accumulate. `clear()` resets it on new game.

**macOS font bug**: `pygame.font.SysFont.render(text, True, color)` fills the surface background with the text color on macOS. All text rendering goes through `_txt()` / `_txt_shadow()` / `_outlined()` helpers in `main.py` and `game/welcome.py` that blit the raw render onto a fresh SRCALPHA surface.

**Difficulty** (`game/welcome.py`): `Difficulty` dataclass carries `lives`, `spawn_every`, `bomb_chance`, `slice_speed`. The game loop and `FruitSpawner` are parameterized from it. On game-over + R, `run_welcome_screen()` is called again; the tracker keeps running.
