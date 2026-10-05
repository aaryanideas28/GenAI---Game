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
from game.obstacles import ObstacleManager
from game.player import Player
from game.world import World
from game.llm_synthesizer import LLMGameLogicSynthesizer, LogicRuleExecutor, BehavioralLogicPackage


logger = logging.getLogger("game")

TITLE = "RAIL RUSH"
SAVE_PATH = Path(__file__).with_name("save.json")
CAMERA_OFFSET = (0, 3.4, -4.5)
CAMERA_PITCH = 16

STATE_MENU, STATE_COUNTDOWN, STATE_PLAYING, STATE_PAUSED, STATE_OVER = "menu", "countdown", "playing", "paused", "over"


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
    """Mobile Subway Surfers style HUD with pause button, multiplier, score, and coins."""
    def __init__(self) -> None:
        # Yellow pause button (top-left)
        self.pause_bg = Entity(parent=camera.ui, model="quad", color=color.hex("#f6a800"),
                               scale=(0.07, 0.07), position=(-0.42, 0.44))
        self.pause_icon = Text("||", parent=self.pause_bg, origin=(0, 0), scale=18.0, color=color.black)

        # Multiplier badge + Score (top-center)
        self.multiplier = Text("x1", origin=(1, 0), position=(-0.04, 0.44), scale=2.4, color=color.hex("#38e028"))
        self.score = Text("000000", origin=(-1, 0), position=(-0.02, 0.44), scale=2.4, color=color.white)

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

        # 3-second countdown counter centered directly above player's head (scale ~6.5 = 1/8 screen height)
        self.countdown = Text("", origin=(0, 0), y=0.22, scale=6.5, color=color.white)

        for t in (self.score, self.multiplier, self.coins, self.center, self.sub, self.toast, self.powerup_badge, self.countdown):
            t.background = False


    def show_toast(self, msg: str, seconds: float = 2.5) -> None:
        self.toast.text = msg
        self.toast_timer = seconds

    def tick(self, dt: float) -> None:
        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast.text = ""


class Game(Entity):
    def __init__(self, seed: int | None = None, llm_prompt: str | None = None) -> None:
        super().__init__()
        self.cfg = load_config()
        self.watcher = ConfigWatcher()
        self.watch_timer = 0.0

        self.world = World(self.cfg)
        self.player = Player(self.cfg)
        self.inspector = Inspector(self.player)
        self.obstacles = ObstacleManager(self.cfg, seed)
        self.hud = Hud()
        self.rng = random.Random(seed)

        self.synthesizer = LLMGameLogicSynthesizer()
        self.rule_executor = LogicRuleExecutor(self)
        self.bonus_score = 0
        self.inverted_controls = False
        self.powerup_timers: dict[str, float] = {
            "jetpack": 0.0, "magnet": 0.0, "sneakers": 0.0,
            "multiplier": 0.0, "hoverboard": 0.0
        }

        self.best = _load_best()
        self.state = STATE_MENU
        self.speed = 0.0
        self.distance = 0.0
        self.coin_count = 0
        self.shake = 0.0
        self.prev_lane = 0
        self.state_time = 0.0
        self.has_calibrated = False

        if llm_prompt:
            self.apply_llm_prompt(llm_prompt)

        camera.position = CAMERA_OFFSET
        camera.rotation_x = CAMERA_PITCH
        camera.fov = 70
        self._show_menu()

    def activate_powerup(self, kind: str) -> None:
        """Triggers dynamic Subway Surfers Power-Up item (Jetpack, Magnet, Super Sneakers, 2X Multiplier, Hoverboard)."""
        from game.obstacles import (
            POWERUP_JETPACK, POWERUP_MAGNET, POWERUP_SNEAKERS,
            POWERUP_MULTIPLIER, POWERUP_HOVERBOARD
        )
        if kind == POWERUP_JETPACK:
            self.powerup_timers[POWERUP_JETPACK] = 8.0
            self.player.set_jetpack_active(True)
            self.hud.show_toast("🚀 JETPACK FLYING!", 2.5)
            self.obstacles.spawn_sky_coins(self.distance + 15.0)
        elif kind == POWERUP_MAGNET:
            self.powerup_timers[POWERUP_MAGNET] = 10.0
            self.hud.show_toast("🧲 COIN MAGNET!", 2.5)
        elif kind == POWERUP_SNEAKERS:
            self.powerup_timers[POWERUP_SNEAKERS] = 8.0
            self.hud.show_toast("👟 SUPER SNEAKERS!", 2.5)
        elif kind == POWERUP_MULTIPLIER:
            self.powerup_timers[POWERUP_MULTIPLIER] = 12.0
            self.hud.show_toast("✖️2 MULTIPLIER!", 2.5)
        elif kind == POWERUP_HOVERBOARD:
            self.powerup_timers[POWERUP_HOVERBOARD] = 12.0
            self.player.set_hoverboard_active(True)
            self.hud.show_toast("🛹 HOVERBOARD SHIELD!", 2.5)


    def apply_llm_prompt(self, prompt: str, api_key: str | None = None) -> BehavioralLogicPackage:
        """Synthesizes dynamic gameplay rules via LLM Game Logic Synthesizer and applies them."""
        package = self.synthesizer.synthesize(prompt)
        self.rule_executor.set_package(package)
        self.hud.show_toast(f"AI Mode Loaded: {package.title}", 3.0)
        return package


    def set_inverted_controls(self, inverted: bool) -> None:
        self.inverted_controls = inverted

    def apply_score_penalty(self, amount: int) -> None:
        self.bonus_score -= amount

    def add_bonus_score(self, amount: int) -> None:
        self.bonus_score += amount


    # --- states --------------------------------------------------------------
    def _show_menu(self) -> None:
        self.state = STATE_MENU
        self.state_time = 0.0
        self.hud.countdown.text = ""
        self.hud.center.text = TITLE
        self.hud.sub.text = "SPACE / JUMP to start   ('C' to calibrate posture)\n\nArrows or WASD: move   Up / Space: jump   Down: roll   P: pause"

    def start_from_menu(self) -> None:
        """Triggered from menu by SPACE / JUMP: starts 3s countdown with one-time posture calibration."""
        self.obstacles.clear()
        self.player.reset()
        self.inspector.reset()
        self.prev_lane = 0
        self.speed = 0.0
        self.distance = 0.0
        self.coin_count = 0
        self.state = STATE_COUNTDOWN
        self.state_time = 0.0
        self.hud.center.text = ""
        self.hud.sub.text = ""
        self.hud.countdown.text = "3"

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
        self.obstacles.clear()
        self.player.reset()
        self.inspector.reset()
        self.prev_lane = 0
        self.speed = self.cfg["start_speed"]
        self.distance = 0.0
        self.coin_count = 0
        self.state = STATE_PLAYING
        self.state_time = 0.0
        self.hud.center.text = ""
        self.hud.sub.text = ""
        self.hud.countdown.text = ""

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
        self.hud.sub.text = f"Score {score}    Coins {self.coin_count}    Best {self.best}\n\nSPACE / JUMP to run again"

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
        raw_score = int(self.distance * self.cfg["score_per_meter"]) * mult + self.coin_count * 10 + self.bonus_score
        return max(0, raw_score)

    # --- commands (keyboard + gesture queue share these) ---------------------
    def cmd_move(self, direction: int) -> None:
        if self.state == STATE_PLAYING:
            eff_dir = -direction if self.inverted_controls else direction
            self.prev_lane = self.player.lane
            self.player.move(eff_dir)
            self.rule_executor.trigger_event("on_lane_change")

    def cmd_set_lane(self, lane: int) -> None:
        if self.state == STATE_PLAYING:
            eff_lane = -lane if self.inverted_controls else lane
            self.prev_lane = self.player.lane
            self.player.set_lane(eff_lane)
            self.rule_executor.trigger_event("on_lane_change")

    def cmd_jump(self) -> None:
        if self.state == STATE_PLAYING:
            self.player.jump()
            self.rule_executor.trigger_event("on_jump")
        elif self.state == STATE_MENU:
            self.start_from_menu()
        elif self.state == STATE_OVER and self.state_time > 0.8:
            self.restart_run()

    def cmd_roll(self) -> None:
        if self.state == STATE_PLAYING:
            self.player.roll()
            self.rule_executor.trigger_event("on_roll")


    def input(self, key: str) -> None:
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
        elif key in ("space", "r") and self.state == STATE_OVER and self.state_time > 0.8:
            self.restart_run()
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

            if self.state == STATE_MENU:
                if (kind == commands.ACTION and value == "JUMP") or (kind == commands.LANE):
                    self.start_from_menu()
            elif self.state == STATE_OVER:
                if kind == commands.ACTION and value == "JUMP" and self.state_time > 0.8:
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

        if self.state == STATE_PLAYING:
            # Tick active power-up timers
            for k in list(self.powerup_timers.keys()):
                if self.powerup_timers[k] > 0:
                    self.powerup_timers[k] -= dt
                    if self.powerup_timers[k] <= 0:
                        self.powerup_timers[k] = 0.0
                        if k == "hoverboard":
                            self.player.set_hoverboard_active(False)
                        elif k == "jetpack":
                            self.player.set_jetpack_active(False)
                        self.hud.show_toast(f"{k.upper()} EXPIRED", 1.5)

            # Active power-up behaviors
            if self.powerup_timers["jetpack"] > 0:
                target_sky_y = 6.2
                self.player.y = lerp(self.player.y, target_sky_y, min(1, dt * 5))
                self.player.grounded = True
                self.player.vy = 0.0


            if self.powerup_timers["magnet"] > 0:
                self.obstacles.attract_coins(self.player.x, 0.0, range_dist=12.0)

            if self.powerup_timers["sneakers"] > 0:
                self.player.cfg["jump_velocity"] = 26.0
            else:
                self.player.cfg["jump_velocity"] = self.cfg.get("jump_velocity", 15.0)


            mult_val = 2 if self.powerup_timers["multiplier"] > 0 else 1
            self.hud.multiplier.text = f"x{mult_val}"

            active_names = [k.upper() for k, v in self.powerup_timers.items() if v > 0]
            if active_names:
                self.hud.powerup_badge.text = "⚡ " + " | ".join(active_names)
            else:
                self.hud.powerup_badge.text = ""

            self.speed = min(self.cfg["max_speed"], self.speed + self.cfg["speed_increase_per_second"] * dt)
            self.distance += self.speed * dt
            self.world.tick(dt, self.speed)
            self.obstacles.tick(dt, self.speed, world=self.world)
            support_y = logic.get_surface_y(self.player.x, self.player.y, self.cfg["lane_width"], self.obstacles.live_specs())
            self.player.tick(dt, self.speed, support_y)
            self.inspector.tick(dt, self.speed, True)
            self._collide()
            self.rule_executor.trigger_event("on_tick", dt)
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
        elif self.state == STATE_MENU:
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
                self.activate_powerup(p_up.kind)
                self.obstacles.powerups.remove(p_up)
                from ursina import destroy
                destroy(p_up)
                self.rule_executor.trigger_event("on_powerup", payload={"kind": p_up.kind})

        for o in list(self.obstacles.obstacles):
            # Jetpack allows flying safely above obstacles
            if self.powerup_timers.get("jetpack", 0.0) > 0:
                continue

            if logic.overlaps(p.x, p.bottom, p.top, o.spec, lw):
                # Hoverboard crash shield protection
                if self.powerup_timers.get("hoverboard", 0.0) > 0:
                    self.powerup_timers["hoverboard"] = 0.0
                    self.player.set_hoverboard_active(False)
                    self.shake = 0.4
                    self.hud.show_toast("🛹 HOVERBOARD SAVED YOU!", 2.0)
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
        if hasattr(self.world, "tunnels"):
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
    args, _ = parser.parse_known_args(argv)

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

    Game(seed=args.seed, llm_prompt=args.llm_prompt)
    app.run()

