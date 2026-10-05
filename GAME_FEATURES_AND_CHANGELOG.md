# Subway Surfers 3D - Comprehensive Feature & Development Guide

Welcome to the full documentation for **Subway Surfers 3D (OpenCV Motion-Controlled Runner)**. This document compiles all architecture, gameplay features, motion tracking calibrations, power-up systems, train roof physics, dynamic AI rule synthesis, and test suites.

---

## 🚀 Overview & Key Highlights

This project is an authentic 3D clone of **Subway Surfers** built using **Python**, **Ursina Engine**, and **MediaPipe / OpenCV** real-time computer vision motion tracking. 

It serves dual purposes:
1. **Interactive Motion-Controlled Game**: Playable via webcam (body gestures: lean left/right, jump up, crouch/roll) or keyboard.
2. **Open Innovation Base for AI Exhibitions & Workshops**: Includes an `LLMGameLogicSynthesizer` framework where participants can input natural language prompts on the spot to dynamically modify game rules, spawn mechanics, and player abilities during live gameplay.

---

## ⚡ Power-Up Systems

The game features 5 authentic Subway Surfers power-ups, complete with custom high-resolution logo badges, glowing 3D aura rings, and HUD status indicators:

| Power-Up | Duration | Visual Effect | Gameplay Functionality |
|---|---|---|---|
| 🚀 **Jetpack** | 8.0s | Mounted dual spray cans on Jake's back with animated multi-colored flame thrusters | Elevates Jake into sky flight ($y = 6.2\text{m}$), streams sky coins, tracks camera elevation, and bypasses ground obstacles. |
| 🧲 **Coin Magnet** | 10.0s | Magnet token with magnetic pulse range indicator | Pulls coins from all lanes towards Jake within a 12-meter radius. |
| 👟 **Super Sneakers** | 8.0s | Glowing sneaker badge on HUD & player state | Increases jump velocity ($v = 26.0$, height $\approx 6.15\text{m}$), allowing Jake to leap over high barriers ($3.2\text{m}$) and full trains ($3.4\text{m}$). Reverts immediately to normal jump ($v = 15.0$, height $\approx 2.05\text{m}$) upon expiration. |
| ✖️2 **2X Multiplier** | 12.0s | Active `x2` multiplier badge on HUD | Doubles distance and coin score gain. |
| 🛹 **Hoverboard** | 12.0s | 3D surfboard mesh attached beneath Jake's feet | Single-use crash shield. If Jake hits an obstacle while active, the board absorbs the hit and saves Jake. |

---

## 🚂 Train Roof Navigation & Collision Physics

### Physics & Collision Rules
- **Normal Jump (Without Power-Up)**:
  - Jump velocity: `15.0`, Gravity: `55.0` (Apex height $\approx 2.05\text{m}$).
  - Clears low barriers ($1.1\text{m}$).
  - Cannot jump over high barriers ($3.2\text{m}$) or trains ($3.4\text{m}$) from ground level without a ramp.
- **Super Sneakers Jump**:
  - Jump velocity: `26.0` (Apex height $\approx 6.15\text{m}$).
  - Leaps completely over high barriers and trains.
- **Train Roof Walking & Climbing**:
  - `overlaps()` in `game/logic.py` allows Jake to walk, run, and land on any train roof (`player_bottom >= 2.4m`) without triggering a crash.
  - `get_surface_y()` provides solid roof support ($y = 2.80\text{m}$) whenever Jake is near or on top of a train ($y \ge 2.0\text{m}$).
  - Jake can hop from train roof to train roof, ascend frontal ramps, and fall back down to ground level when running off the back of a train.
  - Front-face and side-impact collisions against trains at ground level properly result in crashes or stumbles.

---

## 📷 Computer Vision Motion Engine (MediaPipe + OpenCV)

### Real-Time Gesture Mapping
- **Horizontal Movement (`horizontal.py`)**: Torso X coordinate tracking classifies position into `LEFT` ($x < -0.15$), `CENTER` (neutral), or `RIGHT` ($x > 0.15$) lanes with hysteresis filtering.
- **Vertical Movement (`vertical.py`)**:
  - `JUMP_THRESHOLD`: Set to `0.28`.
  - `CROUCH_THRESHOLD`: Set to `0.28`.
  - `CROUCH_HOLD_FRAMES`: Set to `2` to prevent countermovement jump dips from triggering false rolls.
  - `DEPTH_TOLERANCE`: Set to `0.45` to accommodate forward torso leans.
  - **Adaptive Baseline**: Dynamically tracks player standing height changes while accommodating sit-to-stand recalibration.
- **One-Key Calibration**: Press **`C`** during countdown or gameplay to recalibrate standing posture instantly.

---

## 🤖 Dynamic LLM Prompt Innovation Framework

The codebase includes an open-ended LLM game rule synthesizer (`game/llm_synthesizer.py`) designed for interactive exhibition stalls:

### Usage Example:
```bash
python run_game.py --llm-prompt "every time Jake rolls emit a shockwave that clears the lane"
```

### Supported Dynamic Event Hooks:
- `on_roll`: Triggers custom actions when Jake rolls (e.g. shockwaves, lane clearing, speed boosts).
- `on_jump`: Triggers custom actions when Jake jumps (e.g. reversing trains, spawning coins).
- `on_lane_change`: Triggers custom actions when Jake switches lanes.
- `on_coin_collect`: Triggers custom actions upon collecting coins.
- `on_powerup`: Triggers custom actions upon picking up power-up tokens.
- `on_tick`: Executes continuous per-frame logic (e.g. score multipliers, floor is lava timers).

---

## 🧪 Automated Unit Test Suite

The project features **69 passing unit tests** covering pure logic, vision processing, HUD rendering, and LLM rule synthesis.

To execute tests:
```bash
py -3.9 -m pytest
```

### Key Test Files:
- `tests/test_game_logic.py`: Verified train roof climbing, ramp ascending, jump height clearing, and lane math.
- `tests/test_vertical.py`: Verified jump/crouch thresholds, countermovement protection, and posture adaptation.
- `tests/test_vision.py`: Verified camera transforms, coordinate normalization, and FPS stability.
- `tests/test_llm_synthesizer.py`: Verified dynamic rule synthesis and condition-action lambda execution.
- `tests/test_horizontal.py`: Verified torso X lane classification and hysteresis bands.
- `tests/test_controller.py`: Verified event bus dispatching and gesture command queues.
- `tests/test_hud.py`: Verified toast notifications and score/coin rendering.

---

## 🕹️ Controls Quick Reference

### Motion Controls (Webcam)
- **Lean Left/Right**: Change lane.
- **Jump**: Leap over low obstacles or onto train roofs.
- **Crouch/Squat**: Roll under high barriers.

### Keyboard Controls
- **`A` / `D` or Left / Right Arrows**: Switch Lanes
- **`W` / `Up Arrow` / `Space`**: Jump
- **`S` / `Down Arrow`**: Roll
- **`P`**: Pause / Resume
- **`C`**: Calibrate Posture
- **`R`**: Quick Restart after Crash
