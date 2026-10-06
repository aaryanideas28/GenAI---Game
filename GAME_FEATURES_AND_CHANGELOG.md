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

## 🤖 Dynamic LLM Prompt Innovation Framework & Start UI

The codebase includes an interactive **Prompt UI** and open-ended LLM rule synthesizer (`game/llm_synthesizer.py` & `game/prompt_ui.py`):

### Start Prompt UI Dialog:
- **Interactive Start Overlay**: Appears at launch before countdown. Jake jogs smoothly in the background while the UI is open.
- **Large Typographic Input Box**: Type any custom prompt (e.g. `"make coin give 500 point"`).
- **One-Click Quick Presets**:
  - `Shockwave Roll` (`shockwave on roll`)
  - `Reverse Trains` (`trains reverse on jump`)
  - `Floor is Lava` (`floor is lava`)
  - `Survival Mode` (`survival mode`)
  - `Jetpack Flying` (`flying jetpack`)
  - `Normal Mode` (clears for vanilla play)
- **Keybindings**: <kbd>Enter</kbd> to apply and start, <kbd>Esc</kbd> to play vanilla, <kbd>Tab</kbd> to reopen prompt dialog from menu or game-over screen.
- **API Configuration**: Reads `GEMINI_API_KEY` automatically from `secure.env` using `google-genai` with automatic local fallback if offline.

### Supported Dynamic Event Hooks:
- `on_roll`: Triggers custom actions when Jake rolls (e.g. shockwaves, lane clearing, speed boosts).
- `on_jump`: Triggers custom actions when Jake jumps (e.g. reversing trains, spawning coins).
- `on_lane_change`: Triggers custom actions when Jake switches lanes.
- `on_coin_collect`: Triggers custom actions upon collecting coins (e.g. dynamic bonus score).
- `on_powerup`: Triggers custom actions upon picking up power-up tokens.
- `on_tick`: Executes continuous per-frame logic (e.g. score multipliers, floor is lava timers).

---

## 🛡️ Task 2: Safety Guardrails System (`game/guardrails.py`)

A multi-layer security and stability system protecting LLM rule generation:

1. **`PromptGuard`**:
   - Defends against jailbreak / prompt injection attacks (`ignore previous instructions`, `system override`, `eval(`, etc.).
   - Enforces length limits ($\le 250$ chars) and strips non-printable characters.
   - Triggers HUD toast warnings when invalid prompts are rejected.
2. **`ASTValidator`**:
   - Statically parses synthesized Python condition/action strings with `ast.parse`.
   - Blocks dunder attribute inspection (`__class__`, `__subclasses__`, `__globals__`).
   - Restricts execution strictly to whitelisted methods (`add_bonus_score`, `add_score`, `clear_lane`, `show_toast`, etc.).
3. **`SafetyClamps`**:
   - Anti-cheat score capping ($\le 1000$ points per event).
   - Bounds speed to $[5.0, 35.0]\text{ m/s}$ and jump velocity to $[8.0, 25.0]\text{ m/s}$.
   - Sanitizes `NaN` and `infinite` floating-point values.
4. **`RuntimeGuard`**:
   - Isolates execution errors inside `LogicRuleExecutor.trigger_event()`.
   - Prevents frame drops or crashes if an LLM rule fails at runtime.
   - Automatically revokes rules that fail 3 consecutive times.

---

## 🔧 Bug Fixes & Stability Enhancements

1. **Tunnel Wall Crash Restart Fix**:
   - Implemented `World.reset()` to reset track chunks and push tunnel portals forward ($z = 160, 360$) on restart.
   - Added frame-0 spawn protection buffer (`distance > 2.0`) preventing instant-crash loops.
2. **Score Method Aliasing**:
   - Supported `add_score` and `add_points` aliases for `add_bonus_score` to maintain compatibility with varying LLM code outputs.

---

## 🏆 Task 4: Track Collectibles Spawner & Student Leaderboard Backend (`game/leaderboard.py`)

A persistent database backend, spawner, and anti-tamper security architecture:

1. **3D Power-Up Collectibles Spawner (`game/obstacles.py` & `game/models3d.py`)**:
   - Dedicated 3D procedural collectible models for all 6 items:
     - **Magnet Horseshoe**: 3D U-curved red magnet with dual silver pole caps.
     - **Jetpack Rocket Cylinder**: Twin booster cylinders, metal nose cones, and exhaust thrusters.
     - **Super Sneaker Shoe**: 3D high-top sneaker with rubber sole, shoe upper, and ankle collar.
     - **2X Multiplier Star**: 3D 5-pointed star token with golden halo and red accent disc.
     - **Hoverboard Box / Deck**: Aerodynamic hover deck with neon blue edge rails and repulsor pads.
     - **Shield / Headstart**: Cyan energy aegis with protective boss.
   - Dynamic floating bobbing oscillation and pulsing aura rings.
   - Collision detection triggers expanding 3D visual burst cues (`PickupVisualCue`), audio cues, informs Task 3 (`activate_powerup`), and increments session power-up tallies.

2. **Student Score Persistence & Atomic I/O**:
   - Persists student name, roll number, score, coins, distance, detailed power-up breakdown, active prompt summary, and timestamps.
   - **Atomic Write Strategy**: Uses temporary files with filesystem flush and atomic `os.replace` to prevent corruption during unexpected game closures.
   - Automatic `.bak` backup creation before write commits with automatic corruption recovery.

3. **Dual Leaderboard Segregation**:
   - **Ranked Board**: Verified scores from fair skill, unmodded gameplay.
   - **Sandbox Board**: Creative, AI-synthesized rule runs (e.g. Shockwave roll, Floor is lava).

4. **Anti-Tamper Verification & Checksum Security**:
   - Computes HMAC-SHA256 signatures for every record to prevent manual file tampering.
   - Validates physics plausibility against distance and coin limits. Demotes or flags suspicious submissions.

5. **Teacher Export Tools**:
   - One-click CSV export (`export_to_csv()`) for grading with ranking, student name, roll number, and power-up tallies.
   - Aggregated Class Roster Summary (`export_roster_summary_csv()`) providing single-entry-per-student views with personal bests.
   - Class statistics reporting (`get_class_statistics()`) with averages, high scores, and popular power-ups.
   - In-game keyboard shortcut <kbd>E</kbd> or CLI flag `--export-leaderboard` for instant CSV export.

---

## 🧪 Automated Unit Test Suite

The project features **114 passing unit tests** across 12 specialized test modules:

To execute tests:
```bash
python -m pytest tests/
```

### Key Test Files:
- `tests/test_leaderboard_and_spawner.py`: Verified atomic persistence, dual board segregation, anti-tamper HMAC verification, CSV teacher exports, class metrics, and 3D collectible spawner/pickup cues.
- `tests/test_powerups_and_guardrail.py`: Verified all 6 power-ups, stackability, event hooks, and Pydantic parameter guardrails.
- `tests/test_guardrails.py`: Verified prompt injection defense, AST dunder validation, safety clamping, and runtime revocation.
- `tests/test_prompt_ui.py`: Verified start Prompt UI layout, preset selection, submission, and game start transitions.
- `tests/test_world_reset.py`: Verified track chunk and tunnel portal position resets on restart.
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
- **`W` / `Up Arrow` / `Space`**: Jump / Start
- **`S` / `Down Arrow`**: Roll
- **`P`**: Pause / Resume
- **`C`**: Calibrate Posture
- **`R`**: Quick Restart after Crash
- **`Tab`**: Reopen AI Prompt Modifier Dialog
- **`L`**: In-Game Leaderboard Preview (Ranked & Sandbox)
- **`E`**: One-Click Export Leaderboard to CSV
