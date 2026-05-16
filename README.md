# Hand-Tracked Fruit Ninja

A real-time Fruit Ninja clone controlled entirely by hand gestures via webcam (or Kinect v2). No mouse or keyboard needed during gameplay — just wave your hands in front of the camera.

## Features

- **Hand tracking** via MediaPipe (webcam) or Kinect v2
- **5 fruit types** — watermelon, orange, apple, lemon, kiwi — each with unique whole and sliced sprites drawn in pygame
- **Bombs** with animated fire — slice one and lose a life
- **Juice layer** that accumulates splats and drips across the screen
- **3 solo difficulties** — Easy, Medium, Hard — with tunable lives, spawn rate, and required slice speed
- **2 vs 2 multiplayer** — 90-second timed team battle; first two detected hands are Team A (red), next two are Team B (blue)
- **Japanese dusk background** — gradient sky, layered mountains, moon glow, bamboo silhouettes

## Requirements

- Python 3.10+
- Webcam (built-in or USB); Kinect v2 on Windows is also supported

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The MediaPipe hand landmark model (`hand_landmarker.task`, ~25 MB) is downloaded automatically on first run.

## Running

```bash
python main.py
```

This opens the device picker, then the difficulty/mode selector. Use your mouse to click through the UI, then raise your hands in front of the camera to play.

### CLI flags (skip the UI)

```bash
python main.py --tracker webcam --cam 0   # use webcam index 0
python main.py --tracker kinect           # use Kinect v2
```

## Controls

| Action | Input |
|---|---|
| Slice a fruit | Swipe your hand quickly through it |
| Navigate menus | Mouse click |
| Select difficulty by keyboard | `1` / `2` / `3` / `4` |
| Restart after game over | `R` |
| Quit | `Esc` |

## Game Modes

### Solo (Easy / Medium / Hard)

| Mode | Lives | Spawn rate | Bomb chance | Required speed |
|---|---|---|---|---|
| Easy | 5 | Slow | 4% | 700 px/s |
| Medium | 3 | Normal | 8% | 900 px/s |
| Hard | 2 | Fast | 15% | 1100 px/s |

- Missing a fruit costs one life. Running out ends the game.
- Slicing a bomb costs one life and triggers a red flash.
- Press `R` on the game-over screen to return to the mode selector.

### 2 vs 2 Multiplayer

- **4 players** stand in front of one camera; MediaPipe tracks up to 4 hands simultaneously.
- Hand IDs 0 & 1 → **Team A** (red/orange trails); hand IDs 2 & 3 → **Team B** (blue/cyan trails).
- Each team scores points only for the fruits their own hands slice.
- Slicing a bomb deducts 1 point from the responsible team (minimum 0).
- Missing fruits carries no penalty.
- The team with the higher score when the **90-second timer** expires wins.

## Project Structure

```
main.py              # Game loop, HUD, background, entry point
game/
  camera_picker.py   # Device selection screen; opens cameras once
  welcome.py         # Difficulty/mode selection screen; Difficulty dataclass
  fruit.py           # Fruit dataclass, per-type draw helpers, FruitSpawner
  slicer.py          # TrailStore, HandTrail, segment-circle slice detection
  juice.py           # JuiceLayer — persistent splat surface
trackers/
  base.py            # HandTracker ABC, HandSample dataclass
  webcam.py          # MediaPipe Tasks VIDEO-mode tracker
  kinect.py          # Kinect v2 tracker (Windows only)
```

## Kinect v2 (Windows only)

Uncomment `pykinect2` and `comtypes` in `requirements.txt`, install them, then run:

```bash
python main.py --tracker kinect
```
