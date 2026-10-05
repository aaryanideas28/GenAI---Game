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
  --llm-prompt   Pass any natural language prompt to synthesize custom game rules on top of normal game

---

## 🤖 Task 1: LLM Game Logic Synthesizer Framework (For Student Innovation)

By default, the game runs as the **normal Subway Surfers game**. However, the codebase is structured as an **open-source playground** where junior students can enter any text prompt to dynamically innovate and test new gameplay mechanics on top of the game!

### How Juniors / Students Can Innovate with Prompts:

Pass any text prompt using `--llm-prompt` when launching:

```bash
# Example 1: Custom Gameplay Rule
python run_game.py --llm-prompt "every time Jake rolls emit a shockwave that clears the lane"

# Example 2: Train Dynamics
python run_game.py --llm-prompt "trains reverse direction when Jake jumps"

# Example 3: Mandatory Challenge Mechanics
python run_game.py --llm-prompt "floor is lava mode where jumping onto train roofs is mandatory"

# Example 4: Survival Mode
python run_game.py --llm-prompt "survival mode where score decays every second unless collecting coins"
```

### Direct Frontier LLM API Integration (Gemini / OpenAI):
Students can supply their API key via environment variable:
```bash
# Windows PowerShell:
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
python run_game.py --llm-prompt "coins spawn in zigzag formations and collecting magnet activates jetpack hover"
```

### How the Framework Synthesizes Rules:
1. **Prompt Parsing & Synthesizer (`LLMGameLogicSynthesizer`)**:
   Sends specialized system prompts & few-shot game design contexts to Gemini API / OpenAI API.
2. **Deliverable Package (`BehavioralLogicPackage`)**:
   Produces executable Python condition-action lambdas, event triggers, and state dictionaries.
3. **Live Rule Execution (`LogicRuleExecutor`)**:
   Binds condition-action hooks to game events (`on_roll`, `on_jump`, `on_lane_change`, `on_tick`, `on_coin_collect`, `on_spawn`) seamlessly on top of the normal engine.

---

## 🧪 Testing & Verification

The project includes an extensive test suite verifying coordinate transforms, gesture thresholds, depth guards, game logic, and LLM rule synthesis:

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
- `test_llm_synthesizer.py`: Direct LLM rule synthesis, condition-action lambda compilation, and dynamic event hook execution.

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
│   ├── llm_synthesizer.py # Task 1: LLM Game Logic Synthesizer & Rule Executor
│   ├── player.py        # 3D Jake model, animations, physics & collision
│   ├── world.py         # Track generation, wrapping chunks & tunnels
│   ├── obstacles.py     # 3D Trains, ramps, barriers, coins & inspector
│   ├── logic.py         # Pure math, lanes, AABB bounding boxes & ramp profiles
│   ├── textures.py      # Procedural & custom textures
│   └── commands.py      # Thread-safe gesture command queue
└── tests/               # Comprehensive unit test suite (68 tests)
```

---

## 📜 License
MIT License. Built for educational and interactive gaming purposes.

