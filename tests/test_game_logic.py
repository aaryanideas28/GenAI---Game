"""Unit tests for game/logic.py (no window needed)."""

import random

from game import commands, logic
from game.config import DEFAULTS, load_config

CFG = dict(DEFAULTS)
LW = CFG["lane_width"]


def spec(kind, lane, z, length=None, moving=False):
    length = length if length is not None else (logic.BARRIER_LENGTH if kind != logic.KIND_TRAIN else 15.0)
    return logic.ObstacleSpec(kind, lane, z, length, moving)


def test_low_barrier_jump_clears_but_standing_hits():
    o = spec(logic.KIND_LOW, 0, -0.3)
    assert logic.overlaps(0.0, 0.0, logic.PLAYER_STAND_HEIGHT, o, LW)
    assert not logic.overlaps(0.0, 1.5, 1.5 + logic.PLAYER_STAND_HEIGHT, o, LW)


def test_high_barrier_roll_clears_but_jump_hits():
    o = spec(logic.KIND_HIGH, 0, -0.3)
    assert not logic.overlaps(0.0, 0.0, logic.PLAYER_ROLL_HEIGHT, o, LW)
    assert logic.overlaps(0.0, 0.0, logic.PLAYER_STAND_HEIGHT, o, LW)
    assert logic.overlaps(0.0, 2.0, 2.0 + logic.PLAYER_STAND_HEIGHT, o, LW)


def test_adjacent_lane_is_safe_mid_switch_is_not():
    o = spec(logic.KIND_TRAIN, 0, -5)
    assert not logic.overlaps(LW, 0.0, 1.9, o, LW)
    assert logic.overlaps(LW / 2, 0.0, 1.9, o, LW)


def test_obstacle_ahead_or_behind_no_hit():
    assert not logic.overlaps(0, 0, 1.9, spec(logic.KIND_TRAIN, 0, 5), LW)
    assert not logic.overlaps(0, 0, 1.9, spec(logic.KIND_TRAIN, 0, -30, 10), LW)


def test_side_hit_detection():
    assert logic.is_side_hit(spec(logic.KIND_TRAIN, 0, -5))
    assert not logic.is_side_hit(spec(logic.KIND_TRAIN, 0, 0.3))


def _blocked_at(obstacles, z):
    return {o.lane for o in obstacles if o.kind == logic.KIND_TRAIN and o.z_start <= z <= o.z_end}


def test_generated_rows_always_leave_an_escape_lane():
    rng = random.Random(1)
    cfg = dict(CFG, moving_train_chance=0.0)
    live: list[logic.ObstacleSpec] = []
    for _ in range(3000):
        row = logic.generate_row(rng, 150.0, live, cfg)
        row_lanes = {o.lane for o in row.obstacles}
        assert len(row_lanes) <= 2, "a row may never block all three lanes"
        live.extend(row.obstacles)
        gap = logic.next_gap(rng, cfg["start_speed"], cfg)
        for o in live:
            o.z_start -= gap
        live = [o for o in live if o.z_end > -20]
        for z in range(-5, 150, 2):           # never 3 trains side by side
            assert len(_blocked_at(live, z)) < 3


def test_moving_train_rules():
    live = [spec(logic.KIND_TRAIN, -1, 50, 20), spec(logic.KIND_TRAIN, 1, 55, 20)]
    assert not logic.can_add_moving_train(0, live, 150)       # other two lanes overlap
    assert logic.can_add_moving_train(0, [spec(logic.KIND_TRAIN, -1, 50, 20)], 150)
    assert not logic.can_add_moving_train(-1, [spec(logic.KIND_LOW, -1, 80)], 150)  # own lane occupied


def test_command_queue_roundtrip():
    commands.drain()
    commands.push_lane("left")
    commands.push_action("jump")
    assert commands.drain() == [(commands.LANE, "LEFT"), (commands.ACTION, "JUMP")]
    assert commands.drain() == []


def test_config_file_loads_and_has_defaults():
    cfg = load_config()
    for key in DEFAULTS:
        assert key in cfg


def test_ramp_train_frontal_approach_clears_and_gives_surface_y():
    # Ramp train at front: player at z=0 is on the ramp slope
    ramp_obs = logic.ObstacleSpec(logic.KIND_TRAIN, 0, -1.0, 15.0, False, has_ramp=True)
    assert not logic.overlaps(0.0, 0.0, logic.PLAYER_STAND_HEIGHT, ramp_obs, LW)

    # Surface height ascends up the ramp
    surf_y = logic.get_surface_y(0.0, 0.0, LW, [ramp_obs])
    assert surf_y > 0.0 and surf_y < 2.80

    # On the roof: surface height is 2.80, standing on roof does not overlap
    roof_obs = logic.ObstacleSpec(logic.KIND_TRAIN, 0, -5.0, 15.0, False, has_ramp=True)
    surf_roof = logic.get_surface_y(0.0, 2.80, LW, [roof_obs])
    assert surf_roof == 2.80
    assert not logic.overlaps(0.0, 2.80, 2.80 + logic.PLAYER_STAND_HEIGHT, roof_obs, LW)

    # Standard non-ramp train hits player standing on ground
    standard_obs = logic.ObstacleSpec(logic.KIND_TRAIN, 0, -0.3, 15.0, False, has_ramp=False)
    assert logic.overlaps(0.0, 0.0, logic.PLAYER_STAND_HEIGHT, standard_obs, LW)


def test_standard_train_roof_walking_and_jumping():
    # Standard non-ramp train: standing on ground hits front face
    train_obs = logic.ObstacleSpec(logic.KIND_TRAIN, 0, -3.0, 15.0, False, has_ramp=False)
    assert logic.overlaps(0.0, 0.0, logic.PLAYER_STAND_HEIGHT, train_obs, LW)

    # Standing/walking on roof (y=2.80) does NOT crash
    assert not logic.overlaps(0.0, 2.80, 2.80 + logic.PLAYER_STAND_HEIGHT, train_obs, LW)

    # get_surface_y for player on/near roof returns 2.80
    assert logic.get_surface_y(0.0, 2.80, LW, [train_obs]) == 2.80
    assert logic.get_surface_y(0.0, 2.20, LW, [train_obs]) == 2.80

    # Player on ground (y=0.0) under non-ramp train gets surface_y=0.0
    assert logic.get_surface_y(0.0, 0.0, LW, [train_obs]) == 0.0


def test_runner_countdown_and_replay_lifecycle():
    """Verify that menu start triggers countdown above player's head and replay restarts immediately without countdown."""
    from unittest.mock import MagicMock
    from game.runner import STATE_MENU, STATE_COUNTDOWN, STATE_PLAYING, STATE_OVER, Game

    # Mock game object with methods bound
    mock_game = MagicMock()
    mock_game.obstacles = MagicMock()
    mock_game.player = MagicMock()
    mock_game.inspector = MagicMock()
    mock_game.hud = MagicMock()
    mock_game.cfg = {"start_speed": 12.0}
    mock_game.has_calibrated = False

    # 1. Start from menu triggers STATE_COUNTDOWN and shows "3"
    Game.start_from_menu(mock_game)
    assert mock_game.state == STATE_COUNTDOWN
    assert mock_game.speed == 0.0
    assert mock_game.hud.countdown.text == "3"

    # 2. Transition from countdown to playing
    Game.start_playing(mock_game)
    assert mock_game.state == STATE_PLAYING
    assert mock_game.speed == 12.0
    assert mock_game.hud.countdown.text == ""

    # 3. Crash replay immediately enters STATE_PLAYING without countdown or recalibration
    mock_game.state = STATE_OVER
    Game.restart_run(mock_game)
    assert mock_game.state == STATE_PLAYING
    assert mock_game.speed == 12.0
    assert mock_game.hud.countdown.text == ""

