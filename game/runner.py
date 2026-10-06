"""Main game: state machine, input, collisions, HUD. Entry point: ``main()``."""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path

from panda3d.core import loadPrcFileData
loadPrcFileData("", "model-cache-dir")

from ursina import Entity, Text, Ursina, Vec2, application, camera, color, held_keys, lerp, time, window  # noqa: F401
from ursina.shaders import basic_lighting_shader

application.asset_folder = Path(__file__).resolve().parent.parent

from game import commands, logic
from game.config import ConfigWatcher, load_config
from game.inspector import Inspector
from game.obstacles import (
    ObstacleManager,
    POWERUP_JETPACK, POWERUP_MAGNET, POWERUP_SNEAKERS,
    POWERUP_MULTIPLIER, POWERUP_HOVERBOARD, POWERUP_SHIELD,
)
from game.player import Player
from game.world import World
from game.llm_synthesizer import LLMGameLogicSynthesizer, LogicRuleExecutor, BehavioralLogicPackage
from game.prompt_ui import PromptUI
from game.interactive_ui import (
    InGamePromptConsole,
    PowerUpHudBadges,
    ArcadeEntryModal,
    LeaderboardModal,
    PRESETS_INGAME,
)

# --------------------------------------------------------------------------
# Game Event Dispatcher — typed on_jump / on_roll / on_frame / on_coin hooks
# --------------------------------------------------------------------------
try:
    from game_events import (
        GameEventDispatcher,
        EVENT_JUMP, EVENT_ROLL, EVENT_COIN_COLLECT,
        EVENT_LANE_CHANGE, EVENT_FRAME, EVENT_POWERUP_START, EVENT_POWERUP_END,
        JumpEvent, RollEvent, CoinEvent, FrameEvent, LaneChangeEvent, PowerUpEvent,
    )
    import time as _time
    _GAME_EVENTS_AVAILABLE = True
except ImportError:
    _GAME_EVENTS_AVAILABLE = False

# --------------------------------------------------------------------------
# Gemini Guardrail Engine — validates LLM prompts with Pydantic safety schema
# --------------------------------------------------------------------------
try:
    from guardrail import GuardrailEngine
    _GUARDRAIL_ENGINE: "GuardrailEngine | None" = GuardrailEngine()
except Exception:
    _GUARDRAIL_ENGINE = None


logger = logging.getLogger("game")

TITLE = "RAIL RUSH"
SAVE_PATH = Path(__file__).with_name("save.json")
CAMERA_OFFSET = (0, 3.4, -4.5)
CAMERA_PITCH = 16

STATE_PROMPT, STATE_MENU, STATE_COUNTDOWN, STATE_PLAYING, STATE_PAUSED, STATE_OVER = "prompt", "menu", "countdown", "playing", "paused", "over"
STATE_CONSOLE, STATE_LEADERBOARD, STATE_ARCADE_ENTRY = "console", "leaderboard", "arcade_entry"


def _load_best() -> int:
    try:
        return int(json.loads(SAVE_PATH.read_text())["best"])
    except Exception:  # noqa: BLE001
        return 0


def _save_best(best: int) -> None:
    try:
        SAVE_PATH.write_text(json.dumps({"best": best}))
    except OSError:
        pass


class Hud:
    """Mobile Subway Surfers style HUD with pause button, multiplier, score, coins, and Task 5 interactive badges."""
    def __init__(self, game_ref: Any = None) -> None:
        self.game = game_ref

        # Yellow pause button (top-left)
        from ursina import Button
        self.pause_bg = Button(
            text="||",
            parent=camera.ui,
            scale=(0.065, 0.065),
            position=(-0.42, 0.44),
            color=color.hex("#f6a800"),
            highlight_color=color.hex("#ffb81a"),
            text_color=color.black,
        )
        self.pause_bg.on_click = self._on_pause_click
        self.pause_icon = None

        # Task 5: In-Game AI Prompt Console HUD Button (top-left next to pause)
        self.ai_btn = Button(
            text="⚡ AI [/]",
            parent=camera.ui,
            scale=(0.11, 0.045),
            position=(-0.29, 0.44),
            color=color.hex("#7c3aed"),
            highlight_color=color.hex("#8b5cf6"),
        )
        self.ai_btn.on_click = self._on_ai_click

        # Multiplier badge + Score (top-center)
        self.multiplier = Text("x1", origin=(1, 0), position=(-0.04, 0.44), scale=2.4, color=color.hex("#38e028"))
        self.score = Text("000000", origin=(-1, 0), position=(-0.02, 0.44), scale=2.4, color=color.white)

        # Task 5: Interactive Leaderboard HUD Button (top-right before coins)
        self.lb_btn = Button(
            text="🏆 [L]",
            parent=camera.ui,
            scale=(0.09, 0.045),
            position=(0.20, 0.44),
            color=color.hex("#2563eb"),
            highlight_color=color.hex("#3b82f6"),
        )
        self.lb_btn.on_click = self._on_lb_click

        # Coins badge (top-right)
        self.coin_bg = Entity(parent=camera.ui, model="circle", color=color.hex("#ffc400"),
                              scale=(0.04, 0.04), position=(0.34, 0.44))
        self.coins = Text("0", origin=(-1, 0), position=(0.37, 0.44), scale=1.8, color=color.hex("#ffd21a"))

        # Center announcement & toasts
        self.center = Text("", origin=(0, 0), y=0.08, scale=3.2, color=color.white)
        self.sub = Text("", origin=(0, 0), y=-0.06, scale=1.3, color=color.white)
        self.toast = Text("", origin=(0, 0), y=0.35, scale=1.4, color=color.hex("#7dffb2"))
        self.powerup_badge = Text("", origin=(-1, 0), position=(-0.44, -0.42), scale=1.4, color=color.hex("#ffea00"))
        self.toast_timer = 0.0

        # Task 5: Mobile-style Power-up countdown badges with bar progress indicators
        self.powerup_hud_badges = PowerUpHudBadges(parent_ui=camera.ui)

        # 3-second countdown counter centered directly above player's head (scale ~6.5 = 1/8 screen height)
        self.countdown = Text("", origin=(0, 0), y=0.22, scale=6.5, color=color.white)

        for t in (self.score, self.multiplier, self.coins, self.center, self.sub, self.toast, self.powerup_badge, self.countdown):
            t.background = False

    def _on_pause_click(self) -> None:
        if self.game and hasattr(self.game, "toggle_pause"):
            self.game.toggle_pause()

    def _on_ai_click(self) -> None:
        if self.game and hasattr(self.game, "open_prompt_console"):
            self.game.open_prompt_console()

    def _on_lb_click(self) -> None:
        if self.game and hasattr(self.game, "open_leaderboard_modal"):
            self.game.open_leaderboard_modal()

    def update_powerups(self, powerup_timers: dict[str, float], invincible_timer: float = 0.0) -> None:
        if hasattr(self, "powerup_hud_badges") and self.powerup_hud_badges:
            self.powerup_hud_badges.update_badges(powerup_timers, invincible_timer)

    def show_toast(self, msg: str, seconds: float = 2.5) -> None:
        self.toast.text = msg
        self.toast_timer = seconds

    def tick(self, dt: float) -> None:
        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast.text = ""


class Game(Entity):
    def __init__(self, seed: int | None = None, llm_prompt: str | None = None,
                 student_name: str = "Jake", roll_number: str = "SUB-001") -> None:
        super().__init__()
        self.cfg = load_config()
        self.watcher = ConfigWatcher()
        self.watch_timer = 0.0

        self.student_name = student_name
        self.roll_number = roll_number
        from game.leaderboard import LeaderboardBackend
        self.leaderboard = LeaderboardBackend(cfg=self.cfg)
        self.powerups_collected: dict[str, int] = {
            "jetpack": 0, "magnet": 0, "sneakers": 0,
            "multiplier": 0, "hoverboard": 0, "shield": 0,
        }
        self.active_prompt_summary = "Vanilla / Default Rules"

        self.world = World(self.cfg)
        self.player = Player(self.cfg)
        self.inspector = Inspector(self.player)
        self.obstacles = ObstacleManager(self.cfg, seed)
        self.hud = Hud(self)
        self.rng = random.Random(seed)

        self.synthesizer = LLMGameLogicSynthesizer()
        self.rule_executor = LogicRuleExecutor(self)
        self.bonus_score = 0
        self.inverted_controls = False
        self.powerup_timers: dict[str, float] = {
            "jetpack": 0.0, "magnet": 0.0, "sneakers": 0.0,
            "multiplier": 0.0, "hoverboard": 0.0, "shield": 0.0,
        }
        # Hoverboard post-crash invincibility window (seconds; set on absorb-hit)
        self._hoverboard_invincible_timer: float = 0.0
        _HOVERBOARD_INVINC_S = 2.5
        self._HOVERBOARD_INVINC_S = _HOVERBOARD_INVINC_S

        # Game-event dispatcher — emits typed on_jump/on_roll/on_frame/on_coin hooks
        if _GAME_EVENTS_AVAILABLE:
            from event_bus import EventBus as _EventBus
            self._event_bus = _EventBus()
            self._game_dispatcher = GameEventDispatcher()
            self._frame_count = 0
        else:
            self._game_dispatcher = None

        self.best = _load_best()
        self.state = STATE_PROMPT
        self.speed = 0.0
        self.distance = 0.0
        self.coin_count = 0
        self.shake = 0.0
        self.prev_lane = 0
        self.state_time = 0.0
        self.has_calibrated = False

        camera.position = CAMERA_OFFSET
        camera.rotation_x = CAMERA_PITCH
        camera.fov = 70

        # Task 1 Start Prompt UI
        self.prompt_ui = PromptUI(self, on_start=self._on_prompt_start)

        # Task 5 Interactive Modals:
        self.console = InGamePromptConsole(
            self,
            on_apply=self._on_console_apply,
            on_close=self._on_console_close,
        )
        self.leaderboard_modal = LeaderboardModal(
            self,
            on_close=self._on_leaderboard_close,
        )
        self.arcade_modal = ArcadeEntryModal(
            self,
            on_submit=self._on_arcade_submit,
            on_skip=self._on_arcade_skip,
        )

        self.show_prompt_ui(default_prompt=llm_prompt)

    def activate_powerup(self, kind: str) -> None:
        """Triggers all 6 Subway Surfers Power-Ups: Jetpack, Magnet, Super Sneakers,
        2X Multiplier, Hoverboard, and Shield/Headstart. Supports stackability."""
        from game.obstacles import (
            POWERUP_JETPACK, POWERUP_MAGNET, POWERUP_SNEAKERS,
            POWERUP_MULTIPLIER, POWERUP_HOVERBOARD, POWERUP_SHIELD
        )
        is_stacked = self.powerup_timers.get(kind, 0.0) > 0
        self.powerups_collected[kind] = self.powerups_collected.get(kind, 0) + 1

        if kind == POWERUP_JETPACK:
            self.powerup_timers[POWERUP_JETPACK] = self.powerup_timers.get(POWERUP_JETPACK, 0.0) + 8.0 if is_stacked else 8.0
            self._jetpack_descending = False
            if hasattr(self.player, "set_jetpack_active"):
                self.player.set_jetpack_active(True)
            self.speed = max(self.speed, 16.0)
            self.hud.show_toast("🚀 JETPACK FLYING!" if not is_stacked else "🚀 JETPACK EXTENDED!", 2.5)
            self.obstacles.spawn_sky_coins(self.distance + 15.0)
        elif kind == POWERUP_MAGNET:
            self.powerup_timers[POWERUP_MAGNET] = self.powerup_timers.get(POWERUP_MAGNET, 0.0) + 10.0 if is_stacked else 10.0
            self.hud.show_toast("🧲 COIN MAGNET!" if not is_stacked else "🧲 MAGNET EXTENDED!", 2.5)
        elif kind == POWERUP_SNEAKERS:
            self.powerup_timers[POWERUP_SNEAKERS] = self.powerup_timers.get(POWERUP_SNEAKERS, 0.0) + 10.0 if is_stacked else 10.0
            if hasattr(self.player, "cfg") and isinstance(self.player.cfg, dict):
                self.player.cfg["jump_velocity"] = 22.5
                self.player.cfg["gravity"] = self.cfg.get("gravity", 55.0)
            self.hud.show_toast("[SNEAKERS] SUPER JUMP ACTIVE!" if not is_stacked else "[SNEAKERS] EXTENDED!", 2.5)
        elif kind == POWERUP_MULTIPLIER:
            self.powerup_timers[POWERUP_MULTIPLIER] = self.powerup_timers.get(POWERUP_MULTIPLIER, 0.0) + 12.0 if is_stacked else 12.0
            self.hud.show_toast("✖️2 MULTIPLIER!" if not is_stacked else "✖️2 MULTIPLIER EXTENDED!", 2.5)
        elif kind == POWERUP_HOVERBOARD:
            self.powerup_timers[POWERUP_HOVERBOARD] = self.powerup_timers.get(POWERUP_HOVERBOARD, 0.0) + 12.0 if is_stacked else 12.0
            self._hoverboard_invincible_timer = 0.0   # reset invincibility
            if hasattr(self.player, "set_hoverboard_active"):
                self.player.set_hoverboard_active(True)
            self.hud.show_toast("🛹 HOVERBOARD SHIELD!" if not is_stacked else "🛹 HOVERBOARD EXTENDED!", 2.5)
        elif kind == POWERUP_SHIELD:
            self.powerup_timers[POWERUP_SHIELD] = self.powerup_timers.get(POWERUP_SHIELD, 0.0) + 8.0 if is_stacked else 8.0
            self.hud.show_toast("🛡️ SHIELD ACTIVE!" if not is_stacked else "🛡️ SHIELD EXTENDED!", 2.5)

        # Emit power-up start event to game_events dispatcher
        if self._game_dispatcher and _GAME_EVENTS_AVAILABLE:
            dur = self.powerup_timers.get(kind, 0.0)
            self._game_dispatcher.emit_powerup(kind, dur, started=True, stacked=is_stacked)


    def apply_llm_prompt(self, prompt: str, api_key: str | None = None) -> BehavioralLogicPackage:
        """Synthesizes dynamic gameplay rules via LLM Game Logic Synthesizer and applies them.

        Layer 1: Gemini GuardrailEngine validates parameters with Pydantic schema.
        Layer 2: PromptGuard checks for injections / dangerous commands.
        Layer 3: LLMGameLogicSynthesizer synthesizes executable rule hooks.
        """
        # --- Layer 1: Gemini-backed parameter guardrail -----------------------
        if _GUARDRAIL_ENGINE is not None:
            guardrail_result = _GUARDRAIL_ENGINE.evaluate(prompt)
            if not guardrail_result.allowed:
                # Visual CAUTION/WARNING banner on screen
                self._show_guardrail_banner(
                    f"⚠ CAUTION [{guardrail_result.threat_level}]: {guardrail_result.reason}"
                )
                # Return a blocked package so caller knows
                return BehavioralLogicPackage(
                    title="Prompt Blocked by Guardrail",
                    summary=guardrail_result.reason,
                    mode_type="custom_rules",
                    hooks=[],
                    state={},
                    raw_prompt=prompt,
                    json_response="",
                )
            else:
                # Apply validated numeric game parameters directly
                p = guardrail_result.params
                if p.game_speed is not None:
                    self.cfg["start_speed"] = p.game_speed
                if p.jump_height is not None:
                    self.player.cfg["jump_velocity"] = p.jump_height * 15.0
                if p.score_multiplier is not None:
                    self.powerup_timers["multiplier"] = 12.0 if p.score_multiplier >= 2.0 else 0.0
                if p.powerup:
                    _pu_map = {
                        "Jetpack": "jetpack", "CoinMagnet": "magnet",
                        "SuperSneakers": "sneakers", "ScoreMultiplier": "multiplier",
                        "Hoverboard": "hoverboard", "Shield": "shield",
                    }
                    mapped = _pu_map.get(p.powerup, p.powerup.lower())
                    self.activate_powerup(mapped)

        # --- Layer 2 + 3: LLM rule synthesis ---------------------------------
        package = self.synthesizer.synthesize(prompt)
        self.rule_executor.set_package(package)
        if package.title in ("Prompt Blocked", "Prompt Blocked by Guardrail"):
            self.hud.show_toast(f"Guardrail: {package.summary}", 3.5)
            self.active_prompt_summary = "Vanilla / Default Rules"
        else:
            self.hud.show_toast(f"AI Mode Loaded: {package.title}", 3.0)
            self.active_prompt_summary = f"{package.title}: {package.summary}" if package.summary else package.title
        return package

    def _show_guardrail_banner(self, message: str, duration: float = 4.0) -> None:
        """Displays a flashing red CAUTION/WARNING banner on the HUD when a prompt is blocked."""
        # Use HUD toast with extended duration and warning formatting
        self.hud.show_toast(message, duration)
        # Additional high-visibility center text for 2s
        self.hud.center.text = "⚠ PROMPT BLOCKED"
        from ursina import invoke
        invoke(self._clear_warning_banner, delay=2.0)

    def _clear_warning_banner(self) -> None:
        if self.state not in (STATE_MENU, STATE_PROMPT):
            self.hud.center.text = ""


    def set_inverted_controls(self, inverted: bool) -> None:
        self.inverted_controls = inverted

    def apply_score_penalty(self, amount: int) -> None:
        from game.guardrails import SafetyClamps
        self.bonus_score -= SafetyClamps.clamp_score_penalty(amount)

    def add_bonus_score(self, amount: int) -> None:
        from game.guardrails import SafetyClamps
        self.bonus_score += SafetyClamps.clamp_bonus_score(amount)

    add_score = add_bonus_score
    add_points = add_bonus_score
    deduct_score = apply_score_penalty


    # --- states --------------------------------------------------------------
    def show_prompt_ui(self, default_prompt: str | None = None) -> None:
        """Displays the start prompt configuration dialog."""
        self.state = STATE_PROMPT
        self.state_time = 0.0
        self.hud.center.text = ""
        self.hud.sub.text = ""
        self.hud.countdown.text = ""
        if not hasattr(self, "prompt_ui") or self.prompt_ui is None:
            self.prompt_ui = PromptUI(self, on_start=self._on_prompt_start)
        self.prompt_ui.show(default_prompt=default_prompt)

    def _on_prompt_start(self, prompt: str) -> None:
        """Called when user submits prompt or clicks start from prompt UI."""
        if prompt:
            self.apply_llm_prompt(prompt)
        else:
            self.active_prompt_summary = "Vanilla / Default Rules"
        self.start_from_menu()

    def _show_menu(self) -> None:
        self.state = STATE_MENU
        self.state_time = 0.0
        self.hud.countdown.text = ""
        self.hud.center.text = TITLE
        self.hud.sub.text = "SPACE / JUMP to start   ('C' to calibrate posture)\n\nArrows or WASD: move   Up / Space: jump   Down: roll\nTAB: Change AI Prompt"

    def start_from_menu(self) -> None:
        """Triggered from menu by SPACE / JUMP: starts 3s countdown with one-time posture calibration."""
        if hasattr(self.world, "reset"):
            self.world.reset()
        self.obstacles.clear()
        self.player.reset()
        self.inspector.reset()
        self.prev_lane = 0
        self.speed = 0.0
        self.distance = 0.0
        self.coin_count = 0
        self.bonus_score = 0
        self.powerup_timers = {
            "jetpack": 0.0, "magnet": 0.0, "sneakers": 0.0,
            "multiplier": 0.0, "hoverboard": 0.0, "shield": 0.0,
        }
        self.powerups_collected = {
            "jetpack": 0, "magnet": 0, "sneakers": 0,
            "multiplier": 0, "hoverboard": 0, "shield": 0,
        }
        self._hoverboard_invincible_timer = 0.0
        if hasattr(self.player, "set_hoverboard_active"):
            self.player.set_hoverboard_active(False)
        if hasattr(self.player, "set_jetpack_active"):
            self.player.set_jetpack_active(False)
        self._jetpack_descending = False
        if hasattr(self.player, "cfg") and isinstance(self.player.cfg, dict):
            self.player.cfg["jump_velocity"] = self.cfg.get("jump_velocity", 17.0)
            self.player.cfg["gravity"] = self.cfg.get("gravity", 55.0)
        self.state = STATE_COUNTDOWN
        self.state_time = 0.0
        self.hud.center.text = ""
        self.hud.sub.text = ""
        self.hud.countdown.text = "3"
        if hasattr(self.hud, "powerup_badge"):
            self.hud.powerup_badge.text = ""
        if hasattr(self.hud, "powerup_hud_badges"):
            self.hud.powerup_hud_badges.clear()

    def start(self) -> None:
        """Alias for start_from_menu."""
        self.start_from_menu()

    def start_playing(self) -> None:
        """Transition from countdown to actual running."""
        self.state = STATE_PLAYING
        self.state_time = 0.0
        self.speed = self.cfg["start_speed"]
        self.hud.center.text = ""
        self.hud.sub.text = ""
        self.hud.countdown.text = ""

    def restart_run(self) -> None:
        """Replay from game-over: restarts immediately from original position without recalibration or countdown."""
        if hasattr(self.world, "reset"):
            self.world.reset()
        self.obstacles.clear()
        self.player.reset()
        self.inspector.reset()
        self.prev_lane = 0
        self.speed = self.cfg["start_speed"]
        self.distance = 0.0
        self.coin_count = 0
        self.bonus_score = 0
        self.powerup_timers = {
            "jetpack": 0.0, "magnet": 0.0, "sneakers": 0.0,
            "multiplier": 0.0, "hoverboard": 0.0, "shield": 0.0,
        }
        self.powerups_collected = {
            "jetpack": 0, "magnet": 0, "sneakers": 0,
            "multiplier": 0, "hoverboard": 0, "shield": 0,
        }
        self._hoverboard_invincible_timer = 0.0
        if hasattr(self.player, "set_hoverboard_active"):
            self.player.set_hoverboard_active(False)
        if hasattr(self.player, "set_jetpack_active"):
            self.player.set_jetpack_active(False)
        self._jetpack_descending = False
        if hasattr(self.player, "cfg") and isinstance(self.player.cfg, dict):
            self.player.cfg["jump_velocity"] = self.cfg.get("jump_velocity", 17.0)
            self.player.cfg["gravity"] = self.cfg.get("gravity", 55.0)
        self.state = STATE_PLAYING
        self.state_time = 0.0
        self.hud.center.text = ""
        self.hud.sub.text = ""
        self.hud.countdown.text = ""
        if hasattr(self, "arcade_modal") and self.arcade_modal and self.arcade_modal.is_active:
            self.arcade_modal.hide()
        if hasattr(self, "console") and self.console and self.console.is_active:
            self.console.close()
        if hasattr(self, "leaderboard_modal") and self.leaderboard_modal and self.leaderboard_modal.is_active:
            self.leaderboard_modal.close()
        if hasattr(self.hud, "powerup_hud_badges"):
            self.hud.powerup_hud_badges.clear()
        if hasattr(self.hud, "powerup_badge"):
            self.hud.powerup_badge.text = ""
        if hasattr(self.hud, "toast"):
            self.hud.toast.text = ""

    def game_over(self) -> None:
        self.state = STATE_OVER
        self.state_time = 0.0
        self.player.alive = False
        self.inspector.catch()
        self.shake = 0.6
        score = self.score
        if score > self.best:
            self.best = score
            _save_best(score)
        self.hud.countdown.text = ""
        self.hud.center.text = "CRASHED!"

        # Reset active power-ups and revert physics immediately on death
        self.powerup_timers = {
            "jetpack": 0.0, "magnet": 0.0, "sneakers": 0.0,
            "multiplier": 0.0, "hoverboard": 0.0, "shield": 0.0,
        }
        self._hoverboard_invincible_timer = 0.0
        if hasattr(self.player, "set_hoverboard_active"):
            self.player.set_hoverboard_active(False)
        if hasattr(self.player, "set_jetpack_active"):
            self.player.set_jetpack_active(False)
        self._jetpack_descending = False
        if hasattr(self.player, "cfg") and isinstance(self.player.cfg, dict):
            self.player.cfg["jump_velocity"] = self.cfg.get("jump_velocity", 17.0)
            self.player.cfg["gravity"] = self.cfg.get("gravity", 55.0)
        if hasattr(self.hud, "powerup_badge"):
            self.hud.powerup_badge.text = ""
        if hasattr(self.hud, "powerup_hud_badges"):
            self.hud.powerup_hud_badges.clear()

        # Task 5: Pop up arcade entry dialog upon crashing
        if hasattr(self, "arcade_modal") and self.arcade_modal:
            try:
                self.state = STATE_ARCADE_ENTRY
                self.arcade_modal.show(
                    default_name=self.student_name,
                    score=score,
                    coins=self.coin_count,
                    distance=self.distance,
                    prompt_summary=self.active_prompt_summary,
                )
            except Exception as e:
                logger.error(f"Failed to display arcade modal: {e}", exc_info=True)
                self._record_run_and_display_results(self.student_name, "", score)
        else:
            self._record_run_and_display_results(self.student_name, "", score)

    def _on_arcade_submit(self, name: str, roll: str = "") -> None:
        """Called when student submits their details in the arcade entry dialog."""
        self.student_name = name
        entry = self._record_run_and_display_results(name, "", self.score)
        entry_id = getattr(entry, "entry_id", None) or (entry.get("entry_id") if isinstance(entry, dict) else None)
        if hasattr(self, "leaderboard_modal") and self.leaderboard_modal:
            self.open_leaderboard_modal(new_entry_id=entry_id)

    def _on_arcade_skip(self) -> None:
        """Called when student skips arcade submission."""
        self._record_run_and_display_results(self.student_name, "", self.score)

    def _record_run_and_display_results(self, name: str, roll: str, score: int) -> LeaderboardEntry:
        """Records run into leaderboard backend and updates Game Over HUD display."""
        self.state = STATE_OVER
        self.state_time = 0.0
        is_sandbox = not (
            self.active_prompt_summary.lower().startswith("vanilla") or
            "default" in self.active_prompt_summary.lower() or
            "normal" in self.active_prompt_summary.lower()
        )
        entry = self.leaderboard.record_run(
            student_name=name,
            roll_number=roll or "N/A",
            score=score,
            coins=self.coin_count,
            distance=self.distance,
            powerups_collected=dict(self.powerups_collected),
            active_prompt_summary=self.active_prompt_summary,
            is_sandbox=is_sandbox,
        )

        all_entries = (
            self.leaderboard.get_all_entries()
            if hasattr(self.leaderboard, "get_all_entries")
            else []
        )
        entry_id = getattr(entry, "entry_id", None) or (entry.get("entry_id") if isinstance(entry, dict) else None)
        rank = (entry.get("rank") if isinstance(entry, dict) and "rank" in entry else 1)
        for idx, e in enumerate(all_entries, start=1):
            e_id = getattr(e, "entry_id", None) or (e.get("entry_id") if isinstance(e, dict) else None)
            if e_id and e_id == entry_id:
                rank = idx
                break

        self.hud.sub.text = (
            f"SCORE {score:,}    COINS {self.coin_count}    BEST {self.best:,}\n"
            f"LEADERBOARD RANK: #{rank}  |  PLAYER: {name.upper()}\n\n"
            f"[SPACE / JUMP] RETRY          [L] LEADERBOARD\n\n"
            f"[/] AI PROMPT                [E] EXPORT CSV"
        )
        self.hud.sub.scale = 1.65
        self.hud.sub.y = -0.10
        self.hud.sub.font = "VeraMono.ttf" if hasattr(Text, "default_font") else None
        return entry

    # -------------------------------------------------------------------------
    # Task 5: In-Game AI Prompt Console & Interactive Leaderboard Openers
    # -------------------------------------------------------------------------
    def open_prompt_console(self) -> None:
        """Opens in-game AI prompt command bar console and pauses gameplay."""
        if hasattr(self, "console") and self.console:
            if not self.console.is_active:
                self._prev_state = self.state
                self.state = STATE_CONSOLE
                self.console.show()

    def _on_console_apply(self, prompt: str) -> None:
        """Called when user applies prompt from the in-game command bar."""
        package = self.apply_llm_prompt(prompt)
        if package.title in ("Prompt Blocked", "Prompt Blocked by Guardrail"):
            feedback = f"Guardrail: {package.summary}"
        elif "vanilla" in prompt.lower() or "default" in prompt.lower() or not prompt.strip():
            feedback = "Default Rules active — Fair Play (Ranked Mode)"
        else:
            feedback = f"Generated {package.title} logic active — Sandbox Mode flagged"
        self.hud.show_toast(feedback, 3.5)
        self.state = getattr(self, "_prev_state", STATE_PLAYING)

    def _on_console_close(self) -> None:
        """Resumes game or returns to previous screen after closing in-game console."""
        self.state = getattr(self, "_prev_state", STATE_PLAYING)

    def open_leaderboard_modal(self, initial_tab: str = "ALL", new_entry_id: Optional[str] = None) -> None:
        """Opens interactive unified leaderboard modal."""
        if hasattr(self, "leaderboard_modal") and self.leaderboard_modal:
            if not self.leaderboard_modal.is_active:
                self._prev_state = self.state
                self.state = STATE_LEADERBOARD
                if new_entry_id is not None:
                    self.leaderboard_modal.show(initial_tab=initial_tab, new_entry_id=new_entry_id)
                else:
                    self.leaderboard_modal.show(initial_tab=initial_tab)

    def _on_leaderboard_close(self) -> None:
        """Resumes game or returns to previous screen after closing leaderboard modal."""
        self.state = getattr(self, "_prev_state", STATE_PLAYING)

    def show_leaderboard_toast(self) -> None:
        """Displays quick preview of top Ranked and Sandbox leaderboard records."""
        ranked = self.leaderboard.get_ranked_board(limit=3)
        sandbox = self.leaderboard.get_sandbox_board(limit=3)
        r_str = " | ".join(f"#{i} {e.student_name}: {e.score}" for i, e in enumerate(ranked, 1)) or "No runs yet"
        s_str = " | ".join(f"#{i} {e.student_name}: {e.score}" for i, e in enumerate(sandbox, 1)) or "No runs yet"
        self.hud.show_toast(f"🏆 RANKED: {r_str}\n🧪 SANDBOX: {s_str}", 4.5)

    def export_leaderboard_csv(self) -> None:
        """Exports full class records and summaries to CSV."""
        try:
            csv_path = self.leaderboard.export_to_csv()
            roster_path = self.leaderboard.export_roster_summary_csv()
            self.hud.show_toast(f"Exported to {csv_path.name} & {roster_path.name}!", 3.5)
        except Exception as ex:
            self.hud.show_toast(f"Export failed: {ex}", 3.0)

    def toggle_pause(self) -> None:
        if self.state in (STATE_PLAYING, STATE_COUNTDOWN):
            self._prev_state = self.state
            self.state = STATE_PAUSED
            self.hud.center.text = "PAUSED"
            self.hud.sub.text = "P to continue"
        elif self.state == STATE_PAUSED:
            self.state = getattr(self, "_prev_state", STATE_PLAYING)
            self.hud.center.text = ""
            self.hud.sub.text = ""

    @property
    def score(self) -> int:
        mult = 2 if self.powerup_timers.get("multiplier", 0.0) > 0 else 1
        raw_score = int(self.distance * self.cfg.get("score_per_meter", 1.0)) * mult + self.coin_count * 10 + self.bonus_score
        return max(0, raw_score)

    # --- game_events dispatcher helpers (on_jump, on_roll, on_frame, on_lane_change) --
    def _emit_jump_event(self) -> None:
        if self._game_dispatcher and _GAME_EVENTS_AVAILABLE:
            self._game_dispatcher.emit(JumpEvent(
                name=EVENT_JUMP,
                timestamp=_time.time(),
                data={"lane": self.player.lane},
            ))

    def _emit_roll_event(self) -> None:
        if self._game_dispatcher and _GAME_EVENTS_AVAILABLE:
            self._game_dispatcher.emit(RollEvent(
                name=EVENT_ROLL,
                timestamp=_time.time(),
                data={"lane": self.player.lane},
            ))

    def _emit_coin_event(self, coin_x: float = 0.0, coin_z: float = 0.0) -> None:
        if self._game_dispatcher and _GAME_EVENTS_AVAILABLE:
            self._game_dispatcher.emit(CoinEvent(
                name=EVENT_COIN_COLLECT,
                timestamp=_time.time(),
                x_norm=coin_x,
                y_norm=coin_z,
                magnet_assisted=(self.powerup_timers.get("magnet", 0.0) > 0),
                data={"coin_x": coin_x, "coin_z": coin_z},
            ))

    def _emit_lane_event(self, lane: int) -> None:
        if self._game_dispatcher and _GAME_EVENTS_AVAILABLE:
            lane_str = {-1: "LEFT", 0: "CENTER", 1: "RIGHT"}.get(lane, "CENTER")
            self._game_dispatcher.emit(LaneChangeEvent(
                name=EVENT_LANE_CHANGE,
                timestamp=_time.time(),
                lane=lane_str,
                data={"lane": lane_str},
            ))

    def _emit_frame_event(self, dt: float) -> None:
        if self._game_dispatcher and _GAME_EVENTS_AVAILABLE:
            self._frame_count += 1
            fps = 1.0 / dt if dt > 0 else 0.0
            self._game_dispatcher.emit(FrameEvent(
                name=EVENT_FRAME,
                timestamp=_time.time(),
                fps=fps,
                data={"frame": self._frame_count, "dt": dt},
            ))

    # --- commands (keyboard + gesture queue share these) ---------------------
    def cmd_move(self, direction: int) -> None:
        if self.state == STATE_PLAYING:
            eff_dir = -direction if self.inverted_controls else direction
            self.prev_lane = self.player.lane
            self.player.move(eff_dir)
            self.rule_executor.trigger_event("on_lane_change")
            self._emit_lane_event(self.player.lane)   # game_events hook

    def cmd_set_lane(self, lane: int) -> None:
        if self.state == STATE_PLAYING:
            eff_lane = -lane if self.inverted_controls else lane
            self.prev_lane = self.player.lane
            self.player.set_lane(eff_lane)
            self.rule_executor.trigger_event("on_lane_change")
            self._emit_lane_event(self.player.lane)   # game_events hook

    def cmd_jump(self) -> None:
        if self.state == STATE_PLAYING:
            self.player.jump()
            self.rule_executor.trigger_event("on_jump")
            self._emit_jump_event()   # game_events hook
        elif self.state == STATE_MENU:
            self.start_from_menu()
        elif self.state == STATE_OVER and self.state_time > 0.2:
            self.restart_run()

    def cmd_roll(self) -> None:
        if self.state == STATE_PLAYING:
            self.player.roll()
            self.rule_executor.trigger_event("on_roll")
            self._emit_roll_event()   # game_events hook


    def input(self, key: str) -> None:
        # Route input to active modals
        if self.state == STATE_PROMPT:
            if hasattr(self, "prompt_ui") and self.prompt_ui and self.prompt_ui.is_active:
                self.prompt_ui.handle_input(key)
            return

        if self.state == STATE_CONSOLE:
            if hasattr(self, "console") and self.console and self.console.is_active:
                self.console.handle_input(key)
            return

        if self.state == STATE_LEADERBOARD:
            if hasattr(self, "leaderboard_modal") and self.leaderboard_modal and self.leaderboard_modal.is_active:
                self.leaderboard_modal.handle_input(key)
            return

        if self.state == STATE_ARCADE_ENTRY:
            if hasattr(self, "arcade_modal") and self.arcade_modal and self.arcade_modal.is_active:
                self.arcade_modal.handle_input(key)
            return

        # Task 5: In-Game AI Prompt Console shortcut (/ or T)
        if key in ("/", "t"):
            self.open_prompt_console()
            return

        # Task 5: Interactive Leaderboard shortcut (L)
        if key == "l":
            self.open_leaderboard_modal()
            return

        if key == "e":
            self.export_leaderboard_csv()
            return

        if self.state == STATE_OVER:
            if key == "tab":
                self.show_prompt_ui()
                return
            if self.state_time > 0.2 and key in ("space", "r", "enter", "up arrow", "w", "a", "d", "s", "down arrow", "left arrow", "right arrow"):
                self.restart_run()
            return

        if key == "tab" and self.state == STATE_MENU:
            self.show_prompt_ui()
            return

        if key in ("left arrow", "a"):
            self.cmd_move(-1)
        elif key in ("right arrow", "d"):
            self.cmd_move(1)
        elif key in ("up arrow", "w", "space"):
            self.cmd_jump()
        elif key in ("down arrow", "s"):
            self.cmd_roll()
        elif key == "p":
            self.toggle_pause()
        elif key == "c":
            try:
                import controller
                controller.trigger_calibration()
                self.hud.show_toast("Calibrating posture... Stand straight!", 2.0)
            except Exception:
                pass

    def _drain_commands(self) -> None:
        for kind, value in commands.drain():
            if kind == commands.ACTION and value == "CALIBRATED":
                self.hud.show_toast("Posture calibrated! Stand straight.", 2.0)
                continue

            if self.state == STATE_PROMPT:
                continue

            if self.state == STATE_MENU:
                if (kind == commands.ACTION and value == "JUMP") or (kind == commands.LANE):
                    self.start_from_menu()
            elif self.state == STATE_OVER:
                if self.state_time > 0.2:
                    self.restart_run()
            elif self.state == STATE_PLAYING:
                if kind == commands.LANE and value in logic.LANE_BY_NAME:
                    self.cmd_set_lane(logic.LANE_BY_NAME[value])
                    self.hud.show_toast(f"Gesture: {value}", 0.6)
                elif kind == commands.ACTION and value == "JUMP":
                    self.cmd_jump()
                    self.hud.show_toast("Gesture: JUMP", 0.6)
                elif kind == commands.ACTION and value in ("CROUCH", "ROLL"):
                    self.cmd_roll()
                    self.hud.show_toast("Gesture: ROLL", 0.6)

    # --- config hot reload ---------------------------------------------------
    def _check_config(self, dt: float) -> None:
        self.watch_timer += dt
        if self.watch_timer < 1.0:
            return
        self.watch_timer = 0.0
        new_cfg = self.watcher.poll()
        if new_cfg is None:
            return
        old_player = json.dumps(self.cfg.get("player"), sort_keys=True)
        self.cfg.clear()
        self.cfg.update(new_cfg)              # shared dict -> player/world/obstacles see it
        if json.dumps(self.cfg.get("player"), sort_keys=True) != old_player:
            self.player.apply_colors(self.cfg)
        if self.state == STATE_PLAYING:
            self.speed = max(min(self.speed, self.cfg["max_speed"]), self.cfg["start_speed"])
        self.hud.show_toast("Game updated from config.json!")

    # --- frame ---------------------------------------------------------------
    def update(self) -> None:
        dt = min(time.dt, 1 / 20)
        self.state_time += dt
        self._drain_commands()
        self._check_config(dt)
        self.hud.tick(dt)

        if self.state == STATE_CONSOLE and hasattr(self, "console") and self.console:
            self.console.tick(dt)

        if self.state == STATE_ARCADE_ENTRY and hasattr(self, "arcade_modal") and self.arcade_modal:
            self.arcade_modal.tick(dt)

        if self.state == STATE_LEADERBOARD and hasattr(self, "leaderboard_modal") and self.leaderboard_modal:
            self.leaderboard_modal.tick(dt)

        if self.state == STATE_PLAYING:
            # Tick hoverboard post-crash invincibility
            if self._hoverboard_invincible_timer > 0:
                self._hoverboard_invincible_timer = max(0.0, self._hoverboard_invincible_timer - dt)

            # Tick active power-up timers
            for k in list(self.powerup_timers.keys()):
                if self.powerup_timers[k] > 0:
                    self.powerup_timers[k] -= dt
                    if self.powerup_timers[k] <= 0:
                        self.powerup_timers[k] = 0.0
                        if k == "hoverboard":
                            if hasattr(self.player, "set_hoverboard_active"):
                                self.player.set_hoverboard_active(False)
                        elif k == "jetpack":
                            if hasattr(self.player, "set_jetpack_active"):
                                self.player.set_jetpack_active(False)
                            self._jetpack_descending = True
                        elif k == "sneakers":
                            if hasattr(self.player, "cfg") and isinstance(self.player.cfg, dict):
                                self.player.cfg["jump_velocity"] = self.cfg.get("jump_velocity", 17.0)
                                self.player.cfg["gravity"] = self.cfg.get("gravity", 55.0)
                        self.hud.show_toast(f"{k.upper()} EXPIRED", 1.5)
                        if self._game_dispatcher and _GAME_EVENTS_AVAILABLE:
                            self._game_dispatcher.emit_powerup(k, 0.0, started=False)

            # Active power-up behaviors
            if self.powerup_timers["jetpack"] > 0:
                target_sky_y = 6.2
                self.player.y = lerp(self.player.y, target_sky_y, min(1, dt * 5))
                self.player.grounded = True
                self.player.vy = 0.0
            elif getattr(self, "_jetpack_descending", False):
                # Smooth descent upon jetpack expiration
                support_y = logic.get_surface_y(self.player.x, self.player.y, self.cfg["lane_width"], self.obstacles.live_specs())
                self.player.y = lerp(self.player.y, support_y, min(1, dt * 4))
                if abs(self.player.y - support_y) < 0.15:
                    self.player.y = support_y
                    self._jetpack_descending = False

            if self.powerup_timers["magnet"] > 0:
                self.obstacles.attract_coins(self.player.x, 0.0, range_dist=14.0)

            if hasattr(self.player, "cfg") and isinstance(self.player.cfg, dict):
                if self.powerup_timers["sneakers"] > 0:
                    self.player.cfg["jump_velocity"] = 22.5
                    self.player.cfg["gravity"] = self.cfg.get("gravity", 55.0)
                else:
                    self.player.cfg["jump_velocity"] = self.cfg.get("jump_velocity", 17.0)
                    self.player.cfg["gravity"] = self.cfg.get("gravity", 55.0)

            mult_val = 2 if self.powerup_timers["multiplier"] > 0 else 1
            if hasattr(self.hud, "multiplier"):
                self.hud.multiplier.text = f"x{mult_val}"

            # Visual glow states & badges with countdown seconds
            if hasattr(self.hud, "powerup_badge"):
                active_badges = []
                for k, v in self.powerup_timers.items():
                    if v > 0:
                        icon = {
                            "jetpack": "[JETPACK]",
                            "magnet": "[MAGNET]",
                            "sneakers": "[SNEAKERS]",
                            "multiplier": "[2X]",
                            "hoverboard": "[HOVERBOARD]",
                            "shield": "[SHIELD]",
                        }.get(k, "[POWERUP]")
                        active_badges.append(f"{icon} {v:.0f}s")
                if self._hoverboard_invincible_timer > 0:
                    active_badges.append(f"[INVINCIBLE] {self._hoverboard_invincible_timer:.1f}s")
                if active_badges:
                    self.hud.powerup_badge.text = " | ".join(active_badges)
                else:
                    self.hud.powerup_badge.text = ""

            # Task 5: Mobile-style Power-up countdown badges with bar progress indicators
            if hasattr(self.hud, "update_powerups"):
                self.hud.update_powerups(self.powerup_timers, self._hoverboard_invincible_timer)

            self.speed = min(self.cfg["max_speed"], self.speed + self.cfg["speed_increase_per_second"] * dt)
            self.distance += self.speed * dt
            self.world.tick(dt, self.speed)
            self.obstacles.tick(dt, self.speed, world=self.world)
            support_y = logic.get_surface_y(self.player.x, self.player.y, self.cfg["lane_width"], self.obstacles.live_specs())
            self.player.tick(dt, self.speed, support_y)
            self.inspector.tick(dt, self.speed, True)
            self._collide()
            self.rule_executor.trigger_event("on_tick", dt)
            self._emit_frame_event(dt)   # game_events on_frame hook
        elif self.state == STATE_COUNTDOWN:
            self.world.tick(dt, 0.0)
            self.player.tick(dt, 0.0, 0.0)
            self.inspector.tick(dt, 0.0, False)

            # Posture calibration triggers ONLY ONCE during countdown (at 1.0s) while player stands on ground
            if not self.has_calibrated and self.state_time >= 1.0:
                self.has_calibrated = True
                try:
                    import controller
                    controller.trigger_calibration()
                except Exception:
                    pass

            if self.state_time < 1.0:
                self.hud.countdown.text = "3"
            elif self.state_time < 2.0:
                self.hud.countdown.text = "2"
            elif self.state_time < 3.0:
                self.hud.countdown.text = "1"
            elif self.state_time < 3.8:
                self.hud.countdown.text = "START!"
            else:
                self.start_playing()
        elif self.state in (STATE_MENU, STATE_PROMPT):
            self.world.tick(dt, 6.0)
            self.player.tick(dt, 6.0, 0.0)
            self.inspector.tick(dt, 6.0, False)
        elif self.state == STATE_OVER:
            self.inspector.tick(dt, 0.0, False)

        self._update_camera(dt)
        self.hud.score.text = f"{self.score:06d}"
        self.hud.coins.text = f"{self.coin_count}"

    def _collide(self) -> None:
        p = self.player
        lw = self.cfg["lane_width"]

        # Check collision with power-up tokens
        for p_up in list(self.obstacles.powerups):
            if abs(p_up.x - p.x) < 0.9 and abs(p_up.z) < 0.8 and p.bottom - 0.4 < p_up.y < p.top + 0.5:
                self.obstacles.spawn_pickup_cue((p_up.x, p_up.y, p_up.z), p_up.kind)
                self.activate_powerup(p_up.kind)
                self.obstacles.powerups.remove(p_up)
                from ursina import destroy
                destroy(p_up)
                self.rule_executor.trigger_event("on_powerup", payload={"kind": p_up.kind})

        for o in list(self.obstacles.obstacles):
            # Jetpack allows flying safely above obstacles
            if self.powerup_timers.get("jetpack", 0.0) > 0:
                continue

            # Shield / Headstart: smash safely through obstacles
            if self.powerup_timers.get("shield", 0.0) > 0:
                if logic.overlaps(p.x, p.bottom, p.top, o.spec, lw):
                    self.obstacles.obstacles.remove(o)
                    from ursina import destroy
                    destroy(o)
                    self.shake = 0.3
                    self.hud.show_toast("🛡️ SHIELD SMASH!", 0.8)
                continue

            # Hoverboard post-crash invincibility window
            if self._hoverboard_invincible_timer > 0:
                continue

            if logic.overlaps(p.x, p.bottom, p.top, o.spec, lw):
                # Hoverboard crash shield: absorb one fatal hit, trigger recovery stumble & grant post-crash invincibility
                if self.powerup_timers.get("hoverboard", 0.0) > 0:
                    self.powerup_timers["hoverboard"] = 0.0
                    self.player.set_hoverboard_active(False)
                    # Start post-crash invincibility window
                    self._hoverboard_invincible_timer = self._HOVERBOARD_INVINC_S
                    self.shake = 0.45
                    self.hud.show_toast(f"🛹 HOVERBOARD SAVED! Stumble & Invincible {self._HOVERBOARD_INVINC_S:.1f}s", 2.5)
                    self.obstacles.obstacles.remove(o)
                    from ursina import destroy
                    destroy(o)
                    return

                if o.spec.kind == logic.KIND_TRAIN and logic.is_side_hit(o.spec) and p.lane != self.prev_lane:
                    p.set_lane(self.prev_lane)           # stumble back like hitting a train's side
                    self.shake = 0.25
                    self.inspector.alert()
                    self.hud.show_toast("Ouch!", 0.8)
                    return
                self.game_over()
                return


        # Check collision with blocked tunnel facade / sawhorses
        if self.distance > 2.0 and hasattr(self.world, "tunnels"):
            for tun in self.world.tunnels:
                if -0.8 <= tun.z <= 1.2:
                    if p.lane != getattr(tun, "tunnel_lane", 1):
                        self.game_over()
                        return

        for c in list(self.obstacles.coins):
            if abs(c.x - p.x) < 0.8 and abs(c.z) < 0.7 and p.bottom - 0.3 < c.y < p.top + 0.3:
                coin_x, coin_z = c.x, c.z
                self.coin_count += 1
                self.obstacles.coins.remove(c)
                from ursina import destroy
                destroy(c)
                self.rule_executor.trigger_event("on_coin_collect", payload={"coin_x": coin_x, "coin_z": coin_z})
                self._emit_coin_event(coin_x, coin_z)   # game_events on_coin_collect hook


    def _update_camera(self, dt: float) -> None:
        target_x = self.player.x * 0.75
        target_y = CAMERA_OFFSET[1] + self.player.y * 0.70
        camera.x = lerp(camera.x, target_x, min(1, dt * 6))
        camera.y = lerp(camera.y, target_y, min(1, dt * 4))
        camera.z = CAMERA_OFFSET[2]
        if self.shake > 0:
            self.shake -= dt
            camera.x += self.rng.uniform(-0.15, 0.15)
            camera.y += self.rng.uniform(-0.15, 0.15)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=f"{TITLE} - 3D endless runner")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--windowed", action="store_true", help="smaller window instead of borderless")
    parser.add_argument("--cv-window", action="store_true", help="show OpenCV debug camera window alongside game")
    parser.add_argument("--no-vision", action="store_true", help="disable camera gesture tracking, play with keyboard only")
    parser.add_argument("--camera", type=int, default=0, help="camera device index")
    parser.add_argument("--llm-prompt", type=str, default=None, help="LLM Game Logic Synthesizer rule prompt (e.g. 'shockwave', 'reverse_trains', 'survival', 'floor_is_lava')")
    parser.add_argument("--student-name", type=str, default="Jake", help="student name for leaderboard persistence")
    parser.add_argument("--roll-number", type=str, default="SUB-001", help="student roll number for leaderboard persistence")
    parser.add_argument("--export-leaderboard", action="store_true", help="export complete student leaderboard to CSV and exit")
    args, _ = parser.parse_known_args(argv)

    if args.export_leaderboard:
        from game.leaderboard import LeaderboardBackend
        backend = LeaderboardBackend()
        csv_file = backend.export_to_csv()
        roster_file = backend.export_roster_summary_csv()
        print(f"Exported leaderboard files:\n  1. {csv_file}\n  2. {roster_file}")
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    app = Ursina(title=TITLE, borderless=False, size=(520, 920),
                 development_mode=False)
    window.color = color.hex("#9fd8ff")
    window.fps_counter.enabled = False
    Entity.default_shader = basic_lighting_shader

    from ursina.lights import DirectionalLight, AmbientLight
    sun = DirectionalLight(y=14, z=-10, x=8)
    sun.look_at((0, 0, 10))
    AmbientLight(color=color.rgb(195, 200, 215))

    Game(seed=args.seed, llm_prompt=args.llm_prompt,
         student_name=args.student_name, roll_number=args.roll_number)
    app.run()

