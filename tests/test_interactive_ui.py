"""Unit tests for Task 5:
  1. In-Game AI Prompt Console with Command Bar, Spinner & Real-Time Guardrail Feedback
  2. Mobile-style Power-Up Countdown HUD Badges with Bar Progress Indicators
  3. Student Name Submission on Game Over (Arcade Entry Dialog)
  4. Interactive Leaderboard Screen Modal (Ranked vs Sandbox) & Teacher CSV Export
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from game.interactive_ui import (
    InGamePromptConsole,
    PowerUpHudBadges,
    ArcadeEntryModal,
    LeaderboardModal,
    PRESETS_INGAME,
    POWERUP_CONFIGS,
)
from game.runner import (
    Game,
    STATE_PLAYING,
    STATE_PAUSED,
    STATE_OVER,
    STATE_CONSOLE,
    STATE_LEADERBOARD,
    STATE_ARCADE_ENTRY,
)


# =============================================================================
# 1. In-Game AI Prompt Console Tests
# =============================================================================
def test_ingame_prompt_console_presets():
    """Verify that InGamePromptConsole provides all required presets and updates feedback."""
    preset_dict = dict(PRESETS_INGAME)
    assert "Floor is Lava" in preset_dict
    assert "Jetpack Skyway" in preset_dict
    assert "Coin Magnet" in preset_dict
    assert "Default Rules" in preset_dict

    mock_game = SimpleNamespace(active_prompt_summary="Vanilla / Default Rules")
    applied = []

    def on_apply(p: str):
        applied.append(p)

    console = InGamePromptConsole(mock_game, on_apply=on_apply)
    console.is_active = True
    console.input_field = SimpleNamespace(text="")
    console.feedback_text = SimpleNamespace(text="", color=None)
    console.spinner_text = SimpleNamespace(text="")

    # Preset: Floor is Lava
    console._select_preset("floor is lava", "Floor is Lava")
    assert console.input_field.text == "floor is lava"
    assert "Floor is Lava" in console.feedback_text.text
    assert "Sandbox Mode flagged" in console.feedback_text.text

    # Preset: Default Rules
    console._select_preset("", "Default Rules")
    assert console.input_field.text == ""
    assert "Ranked Mode" in console.feedback_text.text

    # Submit
    console.input_field.text = "flying jetpack"
    console.submit()
    assert applied == ["flying jetpack"]
    assert console.is_active is False


def test_ingame_prompt_console_spinner_tick():
    """Verify loading spinner frames animate while logic is generating."""
    console = InGamePromptConsole(None, on_apply=lambda p: None)
    console.is_active = True
    console.is_loading = True
    console.spinner_text = SimpleNamespace(text="")
    console.spinner_frame_idx = 0
    console.spinner_timer = 0.0

    # Advance time past frame threshold (0.08s)
    console.tick(0.09)
    assert console.spinner_frame_idx == 1
    assert "Gemini AI" in console.spinner_text.text


def test_ingame_prompt_console_keyboard_handling():
    """Verify Enter submits and Escape closes console."""
    applied = []
    closed = []

    console = InGamePromptConsole(
        None,
        on_apply=lambda p: applied.append(p),
        on_close=lambda: closed.append(True),
    )
    console.is_active = True
    console.input_field = SimpleNamespace(text="coin magnet")
    console.feedback_text = SimpleNamespace(text="", color=None)
    console.spinner_text = SimpleNamespace(text="")

    handled = console.handle_input("enter")
    assert handled is True
    assert applied == ["coin magnet"]

    # Reopen and test Escape
    console.is_active = True
    handled = console.handle_input("escape")
    assert handled is True
    assert len(closed) == 2


# =============================================================================
# 2. Power-Up Countdown HUD Badges Tests
# =============================================================================
def test_powerup_hud_badges_formatting():
    """Verify power-up badges display countdowns (M:SS) and active status."""
    badges = PowerUpHudBadges(parent_ui=SimpleNamespace())
    badges.container = SimpleNamespace()

    # Active timers: Magnet at 8s, Jetpack at 11s, Hoverboard active
    timers = {
        "magnet": 8.0,
        "jetpack": 11.0,
        "sneakers": 0.0,
        "hoverboard": 12.0,
    }

    badges.update_badges(timers)

    assert "magnet" in badges.badge_entities
    assert "jetpack" in badges.badge_entities
    assert "hoverboard" in badges.badge_entities
    assert "sneakers" not in badges.badge_entities

    # Verify formatting
    assert badges.badge_entities["magnet"]["label"].text == "🧲 0:08"
    assert badges.badge_entities["jetpack"]["label"].text == "🚀 0:11"
    assert badges.badge_entities["hoverboard"]["label"].text == "🛹 Active"

    # Verify progress bar fill scaling
    assert badges.badge_entities["magnet"]["fill"].scale_x == pytest.approx(8.0 / 10.0, 0.01)
    assert badges.badge_entities["hoverboard"]["fill"].scale_x == 1.0


def test_powerup_hud_badges_expiration_and_clear():
    """Verify expired power-up badges are cleaned up and clear() empties all."""
    badges = PowerUpHudBadges(parent_ui=SimpleNamespace())
    badges.container = SimpleNamespace()

    timers = {"magnet": 5.0, "jetpack": 4.0}
    badges.update_badges(timers)
    assert len(badges.badge_entities) == 2

    # Expire magnet
    timers["magnet"] = 0.0
    badges.update_badges(timers)
    assert "magnet" not in badges.badge_entities
    assert "jetpack" in badges.badge_entities

    # Clear all
    badges.clear()
    assert len(badges.badge_entities) == 0


# =============================================================================
# 3. Arcade Name Entry Modal on Game Over Tests
# =============================================================================
def test_arcade_entry_modal_submission():
    """Verify arcade entry modal collects student details and submits."""
    submitted = []
    skipped = []

    def on_submit(name: str, roll: str):
        submitted.append((name, roll))

    def on_skip():
        skipped.append(True)

    modal = ArcadeEntryModal(None, on_submit=on_submit, on_skip=on_skip)
    modal.is_active = True
    modal.input_name = SimpleNamespace(text="Param Gosar", active=True)

    # Test Enter submits
    handled = modal.handle_input("enter")
    assert handled is True
    assert submitted == [("Param Gosar", "")]
    assert modal.is_active is False

    # Test Escape skips
    modal.is_active = True
    handled = modal.handle_input("escape")
    assert handled is True
    assert len(skipped) == 1

    # Test tick animation updates (rapid score roll, coin rotation, running frames)
    modal.is_active = True
    modal.target_score = 5000
    modal.displayed_score = 0
    modal.txt_score_num = SimpleNamespace(text="0")
    modal.coin_icon = SimpleNamespace(scale_x=0.18)
    modal.runner_icon = SimpleNamespace(text=modal.RUNNER_FRAMES[0])

    modal.tick(0.05)
    assert modal.displayed_score > 0
    assert modal.displayed_score <= 5000
    assert modal.txt_score_num.text != "0"

    # Tick to completion
    for _ in range(30):
        modal.tick(0.1)
    assert modal.displayed_score == 5000
    assert modal.txt_score_num.text == "5,000"


# =============================================================================
# 4. Interactive Leaderboard Screen Modal Tests
# =============================================================================
def test_leaderboard_modal_tabs_and_export(tmp_path):
    """Verify LeaderboardModal toggles Ranked and Sandbox boards and exports CSV."""
    from game.leaderboard import LeaderboardBackend

    db_path = tmp_path / "test_lb.json"
    backend = LeaderboardBackend(storage_path=db_path)

    # Seed 1 ranked and 1 sandbox record
    backend.record_run("Alice", "CS-01", 1000, 20, 300.0, is_sandbox=False)
    backend.record_run("Bob", "CS-02", 2000, 40, 500.0, active_prompt_summary="Floor is Lava", is_sandbox=True)

    mock_game = SimpleNamespace(leaderboard=backend, hud=SimpleNamespace(show_toast=MagicMock()))

    modal = LeaderboardModal(mock_game)
    modal.container = SimpleNamespace()
    modal.btn_tab_ranked = SimpleNamespace(color=None)
    modal.btn_tab_sandbox = SimpleNamespace(color=None)
    modal.txt_export_status = SimpleNamespace(text="", color=None)
    modal.is_active = True

    # Default to RANKED
    modal.switch_tab("RANKED")
    assert modal.active_tab == "RANKED"
    ranked_entries = backend.get_ranked_board()
    assert len(ranked_entries) == 1
    assert ranked_entries[0].student_name == "Alice"

    # Switch to SANDBOX
    modal.switch_tab("SANDBOX")
    assert modal.active_tab == "SANDBOX"
    sandbox_entries = backend.get_sandbox_board()
    assert len(sandbox_entries) == 1
    assert sandbox_entries[0].student_name == "Bob"

    # Tab shortcut toggles tab
    modal.handle_input("tab")
    assert modal.active_tab == "RANKED"

    # Teacher CSV export
    modal.export_csv()
    assert "✓ Exported" in modal.txt_export_status.text

    # Close shortcut
    handled = modal.handle_input("escape")
    assert handled is True
    assert modal.is_active is False


# =============================================================================
# 5. Game Integration Tests with Task 5 Flow
# =============================================================================
def test_game_open_and_close_console():
    """Verify Game opens in-game console, pauses state, and resumes upon applying."""
    game = Game.__new__(Game)
    game.state = STATE_PLAYING
    game.console = SimpleNamespace(
        is_active=False,
        show=MagicMock(),
        close=MagicMock(),
    )
    game.hud = SimpleNamespace(show_toast=MagicMock())
    game.apply_llm_prompt = MagicMock(return_value=SimpleNamespace(title="Floor is Lava", summary="Lava rules"))

    # Open console mid-game
    game.open_prompt_console()
    assert game.state == STATE_CONSOLE
    assert game._prev_state == STATE_PLAYING
    game.console.show.assert_called_once()

    # Apply prompt
    game._on_console_apply("floor is lava")
    game.apply_llm_prompt.assert_called_once_with("floor is lava")
    assert game.state == STATE_PLAYING
    game.hud.show_toast.assert_called_once()


def test_game_open_leaderboard_modal():
    """Verify Game opens leaderboard modal from keyboard shortcut and resumes upon close."""
    game = Game.__new__(Game)
    game.state = STATE_PLAYING
    game.leaderboard_modal = SimpleNamespace(
        is_active=False,
        show=MagicMock(),
        close=MagicMock(),
    )

    # Open leaderboard
    game.open_leaderboard_modal(initial_tab="SANDBOX")
    assert game.state == STATE_LEADERBOARD
    assert game._prev_state == STATE_PLAYING
    game.leaderboard_modal.show.assert_called_once_with(initial_tab="SANDBOX")

    # Close leaderboard
    game._on_leaderboard_close()
    assert game.state == STATE_PLAYING


def test_game_over_pops_arcade_modal(tmp_path):
    """Verify crash pops up arcade entry dialog and submitting records student score."""
    from game.leaderboard import LeaderboardBackend

    db_path = tmp_path / "test_student_leaderboard.json"
    backend = LeaderboardBackend(storage_path=db_path)

    game = Game.__new__(Game)
    game.state = STATE_PLAYING
    game.state_time = 0.0
    game.player = SimpleNamespace(alive=True)
    game.inspector = SimpleNamespace(catch=MagicMock())
    game.shake = 0.0
    game.distance = 450.0
    game.coin_count = 35
    game.bonus_score = 0
    game.powerup_timers = {}
    game.powerups_collected = {"magnet": 1}
    game._hoverboard_invincible_timer = 0.0
    game.best = 500
    game.cfg = {"score_per_meter": 1.0}
    game.hud = SimpleNamespace(
        countdown=SimpleNamespace(text=""),
        center=SimpleNamespace(text=""),
        sub=SimpleNamespace(text=""),
        powerup_hud_badges=SimpleNamespace(clear=MagicMock()),
    )
    game.student_name = "Charlie"
    game.roll_number = "STU-88"
    game.active_prompt_summary = "Vanilla / Default Rules"
    game.leaderboard = backend

    # Mock arcade modal
    arcade_mock = SimpleNamespace(is_active=False, show=MagicMock())
    game.arcade_modal = arcade_mock

    # Crash
    game.game_over()
    assert game.state == STATE_ARCADE_ENTRY
    arcade_mock.show.assert_called_once()

    # Submit arcade entry
    game._on_arcade_submit("Diana Prince")
    assert game.student_name == "Diana Prince"
    assert game.state == STATE_OVER

    # Verify score was recorded in backend with submitted student name
    ranked_entries = backend.get_ranked_board()
    assert len(ranked_entries) == 1
    assert ranked_entries[0].student_name == "Diana Prince"


def test_leaderboard_modal_combined_board_and_row_animation(tmp_path):
    """Verify combined leaderboard combines all modes and animates row insertion."""
    from game.leaderboard import LeaderboardBackend

    db_path = tmp_path / "test_combined_lb.json"
    backend = LeaderboardBackend(storage_path=db_path)

    # Seed ranked and sandbox records
    e1 = backend.record_run("Alice", "CS-01", 5000, 50, 400.0, is_sandbox=False)
    e2 = backend.record_run("Bob", "CS-02", 3000, 30, 200.0, active_prompt_summary="Lava Run", is_sandbox=True)
    e3 = backend.record_run("Charlie", "CS-03", 1000, 10, 100.0, is_sandbox=False)

    mock_game = SimpleNamespace(leaderboard=backend, hud=SimpleNamespace(show_toast=MagicMock()))

    modal = LeaderboardModal(mock_game)
    modal.container = SimpleNamespace()
    modal.is_active = True

    # Initial show: Combined board contains all 3 entries sorted by score
    modal.show(initial_tab="ALL")
    assert modal.active_tab == "ALL"
    assert not hasattr(modal, "sub") or modal.sub is None  # Subtitle removed
    assert len(modal.row_entities) == 3
    assert len(modal.row_anim_data) == 3

    # Now simulate a new player run inserting between Alice and Bob:
    e_new = backend.record_run("NewPlayer", "CS-99", 4000, 40, 300.0, active_prompt_summary="Jetpack", is_sandbox=True)
    modal.refresh_entries(new_entry_id=e_new.entry_id)

    # 4 entries now visible
    assert len(modal.row_entities) == 4
    assert len(modal.row_anim_data) == 4

    # Row 0 (Alice, 5000) was higher: stayed in place
    anim_0 = modal.row_anim_data[0]
    assert anim_0.is_new is False
    assert anim_0.start_y == anim_0.target_y

    # Row 1 (NewPlayer, 4000): new player climbing from bottom of board (-0.310)
    anim_1 = modal.row_anim_data[1]
    assert anim_1.is_new is True
    assert anim_1.start_y == -0.310
    assert anim_1.target_y > anim_1.start_y

    # Rows 2 and 3 (Bob, Charlie): shifted down by one slot
    anim_2 = modal.row_anim_data[2]
    assert anim_2.is_new is False
    assert anim_2.start_y > anim_2.target_y  # started higher (previous slot) and shifted down

    # Test frame-by-frame interpolation via tick
    assert modal.animating is True
    modal.tick(0.05)
    assert modal.animating is True

    # Complete the animation
    for _ in range(20):
        modal.tick(0.1)

    assert modal.animating is False
    for anim in modal.row_anim_data:
        assert anim.entity.y == anim.target_y

