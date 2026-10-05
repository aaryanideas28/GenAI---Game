"""
Unit tests for Task 1: LLM Game Logic Synthesizer & Rule Generator
====================================================================
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from game.llm_synthesizer import (
    LLMGameLogicSynthesizer,
    LogicRuleExecutor,
    BehavioralLogicPackage,
    RuleHook,
    _safe_compile_lambda,
)


def test_safe_compile_lambda():
    """Verify safe lambda compilation for condition and action strings."""
    cond = _safe_compile_lambda("lambda ctx: ctx['val'] > 5", is_condition=True)
    act = _safe_compile_lambda("lambda ctx: ctx['val'] * 2", is_condition=False)

    assert cond({"val": 10}) is True
    assert cond({"val": 2}) is False
    assert act({"val": 7}) == 14


def test_synthesizer_shockwave_prompt():
    """Verify synthesis of Shockwave Roll mode from prompt."""
    synth = LLMGameLogicSynthesizer()
    package = synth.synthesize("Every time Jake rolls, emit a shockwave that clears the lane")

    assert package.mode_type == "shockwave"
    assert len(package.hooks) >= 1
    roll_hook = package.hooks[0]
    assert roll_hook.event_type == "on_roll"

    mock_game = MagicMock()
    mock_game.player.lane = 1
    mock_obstacles = MagicMock()
    mock_game.obstacles = mock_obstacles
    mock_game.hud = MagicMock()

    executor = LogicRuleExecutor(mock_game, package)
    executor.trigger_event("on_roll")

    mock_obstacles.clear_lane.assert_called_with(1)


def test_synthesizer_train_reversal():
    """Verify synthesis and execution of Train Reversal on jump."""
    synth = LLMGameLogicSynthesizer()
    package = synth.synthesize("trains reverse direction when Jake jumps")

    assert len(package.hooks) >= 1
    mock_game = MagicMock()
    mock_obstacles = MagicMock()
    mock_game.obstacles = mock_obstacles
    mock_game.hud = MagicMock()

    executor = LogicRuleExecutor(mock_game, package)
    executor.trigger_event("on_jump")

    mock_obstacles.reverse_trains.assert_called_once()


def test_synthesizer_inverted_controls():
    """Verify inverted controls mode triggering."""
    synth = LLMGameLogicSynthesizer()
    package = synth.synthesize("controls invert on the outer lanes")

    mock_game = MagicMock()
    mock_game.player.lane = -1  # Left outer lane
    mock_game.hud = MagicMock()

    executor = LogicRuleExecutor(mock_game, package)
    executor.trigger_event("on_lane_change")

    mock_game.set_inverted_controls.assert_called_with(True)


def test_synthesizer_survival_mode():
    """Verify score decay and coin recovery in Survival Mode."""
    synth = LLMGameLogicSynthesizer()
    package = synth.synthesize("survival mode where Jake loses score every second unless collecting coins")

    assert package.mode_type == "survival"
    mock_game = MagicMock()
    mock_game.state = "playing"
    mock_game.hud = MagicMock()

    executor = LogicRuleExecutor(mock_game, package)

    # Tick event deducts score
    executor.trigger_event("on_tick", dt=0.5)
    mock_game.apply_score_penalty.assert_called()

    # Coin collect restores score
    executor.trigger_event("on_coin_collect")
    mock_game.add_bonus_score.assert_called_with(60)


def test_synthesizer_floor_is_lava():
    """Verify Floor is Lava mode triggers crash if ground timer exceeds threshold."""
    synth = LLMGameLogicSynthesizer()
    package = synth.synthesize("floor is lava mode where jumping onto train roofs is mandatory")

    assert package.mode_type == "floor_is_lava"
    mock_game = MagicMock()
    mock_game.state = "playing"
    mock_game.player.y = 0.0  # On ground
    mock_game.hud = MagicMock()

    executor = LogicRuleExecutor(mock_game, package)

    # Accumulate lava timer beyond 1.5s
    for _ in range(4):
        executor.trigger_event("on_tick", dt=0.5)

    mock_game.game_over.assert_called()


def test_synthesizer_powerup_magnet():
    """Verify dynamic Coin Magnet power-up attraction."""
    synth = LLMGameLogicSynthesizer()
    package = synth.synthesize("activating Jetpack, Magnet, or custom powers")

    mock_game = MagicMock()
    mock_game.state = "playing"
    mock_game.player.x = 2.0
    mock_obstacles = MagicMock()
    mock_game.obstacles = mock_obstacles
    mock_game.hud = MagicMock()

    executor = LogicRuleExecutor(mock_game, package)
    executor.trigger_event("on_tick", dt=0.1)

    mock_obstacles.attract_coins.assert_called_with(2.0, 0.0, 8.0)
