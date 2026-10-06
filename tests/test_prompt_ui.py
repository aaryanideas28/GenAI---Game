"""Unit tests for start Prompt UI and game initialization with prompts."""

from __future__ import annotations

from unittest.mock import MagicMock
from types import SimpleNamespace

from game.prompt_ui import PromptUI, PRESETS


def test_prompt_ui_show_and_presets():
    """Verify that PromptUI creates container, updates preset values, and submits."""
    calls = []

    def on_start(prompt: str):
        calls.append(prompt)

    mock_game = MagicMock()
    ui = PromptUI(mock_game, on_start=on_start)

    # Mock container and input_field without requiring OpenGL window
    ui.container = SimpleNamespace()
    ui.input_field = SimpleNamespace(text="initial text")
    ui.status_text = SimpleNamespace(text="")
    ui.is_active = True

    # Test preset selection
    ui._select_preset("shockwave on roll")
    assert ui.input_field.text == "shockwave on roll"
    assert "shockwave" in ui.status_text.text.lower()

    # Test presets list contains valid options
    preset_dict = dict(PRESETS)
    assert "Shockwave Roll" in preset_dict
    assert "Reverse Trains" in preset_dict
    assert "Floor is Lava" in preset_dict
    assert "Survival Mode" in preset_dict

    # Test submit
    ui.submit()
    assert calls == ["shockwave on roll"]
    assert ui.is_active is False


def test_prompt_ui_skip():
    """Verify that skipping launches with empty prompt."""
    calls = []

    def on_start(prompt: str):
        calls.append(prompt)

    ui = PromptUI(None, on_start=on_start)
    ui.container = SimpleNamespace()
    ui.input_field = SimpleNamespace(text="some unused prompt")
    ui.is_active = True

    ui._skip()
    assert calls == [""]
    assert ui.is_active is False


def test_prompt_ui_keyboard_handling():
    """Verify that Enter submits and Escape skips."""
    calls = []

    def on_start(prompt: str):
        calls.append(prompt)

    ui = PromptUI(None, on_start=on_start)
    ui.container = SimpleNamespace()
    ui.input_field = SimpleNamespace(text="trains reverse on jump")
    ui.is_active = True

    handled = ui.handle_input("enter")
    assert handled is True
    assert calls == ["trains reverse on jump"]

    calls.clear()
    ui.is_active = True
    ui.input_field = SimpleNamespace(text="anything")
    handled = ui.handle_input("escape")
    assert handled is True
    assert calls == [""]


def test_game_on_prompt_start():
    """Verify that Game._on_prompt_start properly synthesizes rules and transitions to countdown."""
    from game.runner import Game, STATE_PROMPT, STATE_COUNTDOWN
    from game.llm_synthesizer import LLMGameLogicSynthesizer, LogicRuleExecutor

    game = Game.__new__(Game)
    game.state = STATE_PROMPT
    game.synthesizer = LLMGameLogicSynthesizer()
    game.rule_executor = LogicRuleExecutor(game)
    game.bonus_score = 0
    game.obstacles = SimpleNamespace(clear=MagicMock())
    game.player = SimpleNamespace(reset=MagicMock(), cfg={})
    game.inspector = SimpleNamespace(reset=MagicMock())
    game.world = SimpleNamespace(reset=MagicMock())
    game.hud = SimpleNamespace(
        center=SimpleNamespace(text=""),
        sub=SimpleNamespace(text=""),
        countdown=SimpleNamespace(text=""),
        show_toast=MagicMock(),
    )
    game.cfg = {"start_speed": 12.0}

    # Call _on_prompt_start with a prompt
    game._on_prompt_start("Every time Jake rolls, emit a shockwave that clears the lane")

    assert game.rule_executor.package is not None
    assert game.rule_executor.package.mode_type == "shockwave"
    assert game.state == STATE_COUNTDOWN
    assert game.hud.countdown.text == "3"
