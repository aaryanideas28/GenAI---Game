# Subway Surfers 3D - OpenCV Motion-Controlled Runner

A full 3D **Subway Surfers** clone built with **Python**, **Ursina Engine**, and **MediaPipe / OpenCV** real-time computer vision motion tracking. Control Jake with your body movements via webcam (lean to switch lanes, jump to leap over barriers, crouch/squat to roll under obstacles) or with classic keyboard controls!

---

## 🎮 Features

### 3D Game Engine (Ursina)
- **Authentic Jake Model**: Custom 3D mesh with animated running bounces, athletic forward sprint lean, articulated leg swings, and smooth rolling barrel animations.
- **Dynamic Subway Environment**: Continuous wrapping tracks, city tunnels, and overhead wires with zero rendering seams.
- **Ramp & Subway Trains**: Authentic silver commuter trains, container freight cars, and sloped ramp trains that allow you to climb and run along train rooftops.
- **Obstacles & Pickups**: High barriers (roll under), low crossbuck barriers (jump over), spinning gold subway coins, and the Inspector chasing behind Jake.
- **HUD & Audio-Visual Feedback**: Live score, coin counter, real-time gesture toasts, and responsive crash camera shakes.

### Computer Vision Gesture Engine (MediaPipe + OpenCV)
- **Horizontal Lane Classification (`horizontal.py`)**: Real-time torso tracking classifies player position into **LEFT**, **CENTER**, or **RIGHT** lanes with hysteresis filtering.
- **Velocity-Aware Jump & Crouch Detection (`vertical.py`)**:
  - **Countermovement Jump Protection**: Distinguishes jump wind-up knee dips from intentional crouches using vertical velocity vectors ($dy/dt$), preventing false rolls when leaping.
  - **Natural Squat & Duck Support**: Accommodates natural forward torso leans (+35% shoulder width expansion) without falsely triggering depth guards.
  - **Adaptive Baseline Tracking**: Smoothly tracks natural standing height changes ($|raw| < 0.18$), preventing posture drift lockouts if you launch the game sitting down and then stand up.
  - **Instant One-Key Calibration**: Press **`C`** anytime (or start a game) to recalibrate your standing baseline instantly.
- **Live Visual Debugger (`--cv-window`)**:
  - Skeleton wireframe and landmark tracking.
  - Color-coded threshold guide lines: **Yellow (JUMP)**, **Cyan (STAND BASELINE)**, and **Orange (CROUCH/ROLL)**.
  - Real-time relative offset ($rel$) and depth status overlay.

---

## 🚀 Quick Start & Installation

### Requirements
- **Python 3.10+** (Tested on Python 3.11)
- Standard USB Webcam or Integrated Laptop Camera
- Windows / macOS / Linux

### 1. Clone & Setup Environment
```bash
# Clone the repository
git clone https://github.com/aaryanideas28/GenAI---Game.git
cd GenAI---Game

# Create and activate virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Game
```bash
# Run with webcam motion tracking + live gesture camera window:
python run_game.py --cv-window

# Run with motion tracking in background (headless webcam):
python run_game.py

# Run keyboard-only (webcam disabled):
python run_game.py --no-vision
```

---

## 🕹️ Controls

### Motion Controls (Webcam)
| Real-Life Gesture | Game Action | Notes |
|---|---|---|
| **Lean Left** | Switch to Left Lane | Move torso to your real-life left |
| **Lean Right** | Switch to Right Lane | Move torso to your real-life right |
| **Jump Up** | Jump / Leap | Jump into the air over low obstacles / trains |
| **Crouch / Squat** | Roll | Duck or bend knees to roll under high barriers |
| **Stand Straight** | Neutral Running | Running forward along current lane |

> [!TIP]
> **Posture Calibration**: Press **`C`** on your keyboard at any time while standing in your natural playing stance to recalibrate your baseline height!

### Keyboard Controls (Fallback & Debug)
| Key | Action |
|---|---|
| **`A` / `Left Arrow`** | Move Left |
| **`D` / `Right Arrow`** | Move Right |
| **`W` / `Up Arrow` / `Space`** | Jump / Start Game |
| **`S` / `Down Arrow`** | Roll / Dive Down |
| **`P`** | Pause / Resume |
| **`C`** | Calibrate Posture Baseline |
| **`R`** | Restart after Crash |

---

## 🛠️ CLI Options

```text
usage: run_game.py [-h] [--seed SEED] [--windowed] [--cv-window] [--no-vision] [--camera CAMERA]

Options:
  --cv-window    Open OpenCV debug window showing skeleton & gesture threshold lines
  --no-vision    Disable webcam pipeline (play purely with keyboard)
  --windowed     Run game in a window instead of borderless fullscreen
  --camera INT   Select camera device index (default: 0)
  --seed INT     Fixed procedural obstacle RNG seed
```

---

## 🧪 Testing & Verification

The project includes an extensive test suite verifying coordinate transforms, gesture thresholds, depth guards, and game logic:

```bash
# Run all unit tests
python -m pytest tests/
```

### Test Coverage Highlights:
- `test_vision.py`: Camera mirroring, landmark schemas, FPS benchmarking.
- `test_horizontal.py`: Lane boundaries, hysteresis bands, center calibration.
- `test_vertical.py`: Jump thresholds, countermovement dips, crouch hold frames, natural forward lean tolerance, and distance invariance.
- `test_controller.py`: Event bus dispatch and command queue routing.
- `test_game_logic.py`: Lane math, obstacle collisions, ramp surface climbing.

---

## 📂 Architecture Overview

```
GenAI---Game/
├── run_game.py          # Unified entry point (Ursina game + vision thread)
├── main.py              # Standalone OpenCV vision pipeline runner
├── event_bus.py         # Decoupled pub-sub event distribution
├── vision.py            # MediaPipe Pose capture & coordinate mirroring
├── horizontal.py        # Teammate 2: Torso X lane tracker (LEFT/CENTER/RIGHT)
├── vertical.py          # Teammate 3: Velocity-aware JUMP & CROUCH detector
├── controller.py        # Teammate 4: Bridge between OpenCV events and Ursina
├── game/                # 3D Ursina Game Implementation
│   ├── runner.py        # Main Ursina Game loop, state machine & HUD
│   ├── player.py        # 3D Jake model, animations, physics & collision
│   ├── world.py         # Track generation, wrapping chunks & tunnels
│   ├── obstacles.py     # 3D Trains, ramps, barriers, coins & inspector
│   ├── logic.py         # Pure math, lanes, AABB bounding boxes & ramp profiles
│   ├── textures.py      # Procedural & custom textures
│   └── commands.py      # Thread-safe gesture command queue
└── tests/               # Comprehensive unit test suite (53 tests)
```

---

## 📜 License
MIT License. Built for educational and interactive gaming purposes.
