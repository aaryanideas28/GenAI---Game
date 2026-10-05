# Subway Surfers 3D - OpenCV Motion-Controlled Runner

A full 3D **Subway Surfers** clone built with **Python**, **Ursina Engine**, and **MediaPipe / OpenCV** real-time computer vision motion tracking. Control Jake with your body movements via webcam (lean to switch lanes, jump to leap over barriers, crouch/squat to roll under obstacles) or with classic keyboard controls!

---

### ⚡ Authentic Subway Surfers Power-Ups
- 🚀 **Jetpack**: Sky flight mode ($y = 6.2\text{m}$), dual spray-can thrusters with multi-colored flame animations, and sky coin streaks.
- 🧲 **Coin Magnet**: Magnetic pulse pulling coins from all lanes towards Jake within range.
- 👟 **Super Sneakers**: High-jump velocity ($v = 26.0$), leaping over trains and high barriers with instant reversion on expiration.
- ✖️2 **2X Multiplier**: Doubled score gain indicator and rate.
- 🛹 **Hoverboard Shield**: 3D surfboard entity granting single-use crash shield protection.

### 🚂 Train Roof Navigation & Surface Collision Physics
- **Roof Walking & Jumping**: Jump onto, run along, and jump between subway train roofs (`player_bottom >= 2.4m`).
- **Ramp Climbing**: Ascend frontal ramp trains smoothly onto the roof ($y = 2.80\text{m}$).

### 🎮 Features & Architecture
- Detailed feature walkthrough and development log available in [GAME_FEATURES_AND_CHANGELOG.md](file:///c:/Users/Pinal%20Shah/Desktop/Subway%20Surfer/GenAI---Game/GAME_FEATURES_AND_CHANGELOG.md).

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
| **`Tab`** | Re-open AI Prompt Modifier Dialog |

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
  --llm-prompt   Pre-fill natural language prompt to modify game rules
```

---

## 🤖 GenAI Prompt System & Start UI (For Live Innovation)

At game launch, a **Prompt UI** dialog appears automatically before the run starts, allowing you to modify game mechanics via natural language prompts!

### Features of the Prompt UI:
- **Large Typographic Input Box**: Type any custom prompt (e.g. `"make coin give 500 point"`, `"jumping emits shockwave"`, `"floor is lava"`).
- **One-Click Presets**:
  - `Shockwave Roll`: Rolling clears all obstacles in Jake's current lane.
  - `Reverse Trains`: Trains reverse direction whenever Jake jumps.
  - `Floor is Lava`: Running on the ground for more than 1.5s triggers game over.
  - `Survival Mode`: Score constantly decays over time unless coins are collected.
  - `Jetpack Flying`: Fly freely with jetpack and high speed.
  - `Normal Mode`: Clears modifications for vanilla Subway Surfers play.
- **Controls**: Press <kbd>Enter</kbd> to apply and start; press <kbd>Esc</kbd> or click "Play Vanilla" for default gameplay. Press <kbd>Tab</kbd> anytime from the menu or game over to modify prompts.

### API Key Configuration (`secure.env`):
Add your Gemini API key to a `secure.env` file in the root folder (automatically protected by `.gitignore`):
```ini
GEMINI_API_KEY=your_api_key_here
```
The game automatically loads `secure.env` on startup using `google-genai`. If offline or without a key, a local dynamic fallback parser handles prompts locally.

---

## 🛡️ Task 2: Safety Guardrails System (`game/guardrails.py`)

A comprehensive multi-layer safety architecture protects the game against prompt injections, code exploits, physics anomalies, and runtime crashes:

1. **Prompt Injection & Adversarial Defense (`PromptGuard`)**:
   - Blocks prompt injection phrases (`ignore previous instructions`, `system override`, `eval(`, `__import__`, etc.).
   - Enforces length limits ($\le 250$ chars) and strips non-printable characters.
   - Displays in-game toast notification when an invalid prompt is rejected.

2. **AST Code Sandbox Validator (`ASTValidator`)**:
   - Statically parses and inspects Python lambdas before compilation using `ast.parse`.
   - Prevents dunder attribute leaks (`__class__`, `__subclasses__`, `__globals__`, `__dict__`).
   - Whitelists only permitted game methods (`add_bonus_score`, `add_score`, `clear_lane`, `reverse_trains`, `attract_coins`, `show_toast`, etc.).

3. **Anti-Cheat & Game Invariant Clamps (`SafetyClamps`)**:
   - Caps score bonuses to a safe maximum ($\le 1000$ points per event).
   - Bounds speed to $[5.0, 35.0]\text{ m/s}$ and jump velocity to $[8.0, 25.0]\text{ m/s}$.
   - Automatically sanitizes `NaN` and `infinite` values.

4. **Runtime Crash Isolation (`RuntimeGuard`)**:
   - Wraps rule execution with error containment. If a rule throws an exception, it is caught without dropping frames.
   - Automatically revokes malfunctioning rules if they fail 3 times consecutively.

---

## 🧪 Testing & Verification

The project includes an extensive test suite verifying coordinate transforms, gesture thresholds, depth guards, game logic, world resets, prompt UI, and guardrails:

```bash
# Run all unit tests
python -m pytest tests/
```

### Test Coverage (85 Passing Unit Tests):
- `test_guardrails.py` (10 tests): Prompt injection blocking, AST dunder validation, safety clamping, and runtime rule revocation.
- `test_prompt_ui.py` (4 tests): Prompt UI layout, preset population, submission, and game start transitions.
- `test_world_reset.py` (2 tests): Track chunk and tunnel portal position resets on restart.
- `test_llm_synthesizer.py` (7 tests): LLM prompt synthesis, condition-action lambdas, and rule execution.
- `test_game_logic.py` (12 tests): Lane math, obstacle collisions, ramp climbing, and roof walking.
- `test_vertical.py` (14 tests): Jump/crouch thresholds, countermovement dips, and adaptive standing baselines.
- `test_horizontal.py` (5 tests): Lane boundaries, hysteresis bands, and torso tracking.
- `test_vision.py` (20 tests): MediaPipe Pose landmark normalization, mirroring, and benchmark latency.
- `test_controller.py` (4 tests): Gesture queue event routing and dispatching.
- `test_hud.py` (7 tests): Camera overlays, status panels, and threshold line guides.

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
│   ├── prompt_ui.py     # Task 1: In-game Prompt Modifier UI dialog & presets
│   ├── guardrails.py    # Task 2: Safety Guardrails (Prompt, AST, Clamps, Runtime)
│   ├── llm_synthesizer.py # Task 1: Gemini LLM Game Logic Synthesizer & Rule Executor
│   ├── player.py        # 3D Jake model, animations, physics & collision
│   ├── world.py         # Track generation, wrapping chunks, tunnels & resets
│   ├── obstacles.py     # 3D Trains, ramps, barriers, coins & inspector
│   ├── logic.py         # Pure math, lanes, AABB bounding boxes & ramp profiles
│   ├── textures.py      # Procedural & custom textures
│   └── commands.py      # Thread-safe gesture command queue
└── tests/               # Comprehensive unit test suite (85 tests)
```

---

## 📜 License
MIT License. Built for educational and interactive gaming purposes.

