"""
Comprehensive unit tests for Task 4:
  1. 3D Power-Up Collectibles Spawner & Pickup Cues
  2. Student Score Persistence & Atomic I/O
  3. Dual Leaderboard Segregation (Ranked vs Sandbox)
  4. Anti-Tamper Verification & Checksum Security
  5. Teacher Export Tools (CSV & Roster Reports)
"""

import csv
import json
import os
from pathlib import Path
import tempfile
import time
import pytest

from game.leaderboard import (
    BOARD_RANKED,
    BOARD_SANDBOX,
    AntiTamperVerifier,
    LeaderboardBackend,
    LeaderboardEntry,
)
from game.obstacles import (
    POWERUP_HOVERBOARD,
    POWERUP_JETPACK,
    POWERUP_MAGNET,
    POWERUP_MULTIPLIER,
    POWERUP_SHIELD,
    POWERUP_SNEAKERS,
    POWERUPS,
    ObstacleManager,
    PickupVisualCue,
    PowerUpToken,
    play_pickup_sound,
)


@pytest.fixture
def temp_db_path(tmp_path):
    return tmp_path / "test_student_leaderboard.json"


# ---------------------------------------------------------------------------
# 1. Student Score Persistence & Atomic I/O Tests
# ---------------------------------------------------------------------------
def test_record_run_persistence(temp_db_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)

    pu_collected = {"magnet": 2, "jetpack": 1}
    entry = backend.record_run(
        student_name="Alex Chen",
        roll_number="CS-101",
        score=1450,
        coins=45,
        distance=620.5,
        powerups_collected=pu_collected,
        active_prompt_summary="Vanilla / Default Rules",
        is_sandbox=False,
    )

    assert entry.student_name == "Alex Chen"
    assert entry.roll_number == "CS-101"
    assert entry.score == 1450
    assert entry.coins == 45
    assert entry.distance == 620.5
    assert entry.total_powerups == 3
    assert entry.powerups_collected == pu_collected
    assert entry.board_type == BOARD_RANKED
    assert entry.verified is True
    assert entry.checksum != ""
    assert temp_db_path.is_file()

    # Reload from disk into a fresh backend instance
    reloaded = LeaderboardBackend(storage_path=temp_db_path)
    all_runs = reloaded.get_all_entries()
    assert len(all_runs) == 1
    loaded = all_runs[0]
    assert loaded.student_name == "Alex Chen"
    assert loaded.roll_number == "CS-101"
    assert loaded.score == 1450
    assert loaded.coins == 45
    assert loaded.distance == 620.5
    assert loaded.total_powerups == 3


def test_atomic_write_creates_backup(temp_db_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)
    backend.record_run("Student 1", "R01", 100, 5, 50.0)
    assert temp_db_path.is_file()

    # Second write should create .bak backup
    backend.record_run("Student 2", "R02", 200, 10, 100.0)
    bak_file = temp_db_path.with_suffix(".json.bak")
    assert bak_file.is_file()


def test_corrupted_db_recovery(temp_db_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)
    backend.record_run("Safe Student", "R99", 500, 20, 250.0)

    # Trigger second save so .bak is populated
    backend.record_run("Safe Student 2", "R99", 600, 25, 300.0)
    assert temp_db_path.with_suffix(".json.bak").is_file()

    # Corrupt main file
    temp_db_path.write_text("{CORRUPTED_JSON_TRUNCATED", encoding="utf-8")

    # Reload should fall back to backup
    recovered = LeaderboardBackend(storage_path=temp_db_path)
    entries = recovered.get_all_entries()
    assert len(entries) >= 1
    assert any(e.student_name == "Safe Student" for e in entries)


# ---------------------------------------------------------------------------
# 2. Dual Leaderboard Segregation Tests
# ---------------------------------------------------------------------------
def test_dual_board_segregation(temp_db_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)

    # 1. Vanilla run -> Ranked
    backend.record_run(
        student_name="Ranked Player",
        roll_number="RP-01",
        score=2500,
        coins=50,
        distance=800.0,
        active_prompt_summary="Vanilla / Default Rules",
        is_sandbox=False,
    )

    # 2. AI Modded run -> Sandbox
    backend.record_run(
        student_name="Modded Player",
        roll_number="MP-01",
        score=9900,
        coins=200,
        distance=1200.0,
        active_prompt_summary="Shockwave Roll: clears lane on roll",
        is_sandbox=True,
    )

    # 3. Auto-detected sandbox run from prompt summary
    backend.record_run(
        student_name="Lava Player",
        roll_number="LP-01",
        score=3200,
        coins=80,
        distance=600.0,
        active_prompt_summary="Floor is Lava Mode",
        is_sandbox=None,  # Should infer SANDBOX
    )

    ranked_list = backend.get_ranked_board()
    sandbox_list = backend.get_sandbox_board()

    assert len(ranked_list) == 1
    assert ranked_list[0].student_name == "Ranked Player"
    assert ranked_list[0].board_type == BOARD_RANKED

    assert len(sandbox_list) == 2
    sandbox_names = [e.student_name for e in sandbox_list]
    assert "Modded Player" in sandbox_names
    assert "Lava Player" in sandbox_names


def test_student_history_and_best(temp_db_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)

    backend.record_run("Samantha", "ROLL-07", 800, 20, 300.0)
    backend.record_run("Samantha", "ROLL-07", 1500, 40, 600.0)
    backend.record_run("Samantha", "ROLL-07", 1200, 30, 500.0)
    backend.record_run("Bob", "ROLL-08", 900, 25, 350.0)

    history = backend.get_student_history("ROLL-07")
    assert len(history) == 3

    best = backend.get_student_best("ROLL-07")
    assert best is not None
    assert best.score == 1500


# ---------------------------------------------------------------------------
# 3. Anti-Tamper Verification & Checksum Security Tests
# ---------------------------------------------------------------------------
def test_anti_tamper_flags_impossible_score(temp_db_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)

    # Physically impossible: ran 3 meters, collected 0 coins, but got 80,000 score
    entry = backend.record_run(
        student_name="Suspicious Student",
        roll_number="CHEAT-01",
        score=80000,
        coins=0,
        distance=3.0,
        active_prompt_summary="Vanilla / Default Rules",
        is_sandbox=False,
    )

    assert entry.verified is False
    assert "FLAGGED" in entry.verification_status
    # Demoted from ranked to sandbox
    assert entry.board_type == BOARD_SANDBOX


def test_anti_tamper_checksum_validation():
    entry = LeaderboardEntry(
        entry_id="TEST-1",
        student_name="Alice",
        roll_number="A1",
        score=1000,
        coins=20,
        distance=400.0,
        board_type=BOARD_RANKED,
        timestamp="2026-10-06T10:00:00Z",
    )
    entry.checksum = AntiTamperVerifier.compute_checksum(
        entry.student_name, entry.roll_number, entry.score,
        entry.coins, entry.distance, entry.board_type, entry.timestamp
    )

    # Valid check
    is_valid, _ = AntiTamperVerifier.verify_record(entry)
    assert is_valid is True

    # Tampered score in memory without updating checksum
    entry.score = 99999
    is_valid, reason = AntiTamperVerifier.verify_record(entry)
    assert is_valid is False
    assert "mismatch" in reason or "exceeds" in reason


# ---------------------------------------------------------------------------
# 4. Teacher Export Tools (CSV & Roster Reports)
# ---------------------------------------------------------------------------
def test_export_to_csv(temp_db_path, tmp_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)
    backend.record_run("Zara Khan", "ZK-99", 2400, 60, 900.0, {"magnet": 1, "jetpack": 2})
    backend.record_run("Liam Smith", "LS-12", 1800, 45, 700.0, {"sneakers": 1})

    export_file = tmp_path / "exported_leaderboard.csv"
    res_path = backend.export_to_csv(export_file)

    assert res_path.is_file()
    with open(res_path, encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 2
        assert reader[0]["Student Name"] == "Zara Khan"
        assert int(reader[0]["Final Score"]) == 2400
        assert "magnet: 1" in reader[0]["Power-Ups Breakdown"]
        assert reader[1]["Student Name"] == "Liam Smith"


def test_export_roster_summary_csv(temp_db_path, tmp_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)
    # Student with multiple runs
    backend.record_run("Maya Lin", "ML-01", 1000, 20, 400.0)
    backend.record_run("Maya Lin", "ML-01", 3200, 75, 1100.0)

    # Another student
    backend.record_run("David K", "DK-02", 2100, 50, 800.0)

    roster_file = tmp_path / "roster_summary.csv"
    res_path = backend.export_roster_summary_csv(roster_file)

    assert res_path.is_file()
    with open(res_path, encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        # Unique students in roster = 2
        assert len(reader) == 2
        maya = next(r for r in reader if r["Student Name"] == "Maya Lin")
        assert int(maya["Total Runs"]) == 2
        assert int(maya["Highest Score"]) == 3200


def test_class_statistics(temp_db_path):
    backend = LeaderboardBackend(storage_path=temp_db_path)
    backend.record_run("Student A", "A1", 1000, 25, 400.0, {"jetpack": 2})
    backend.record_run("Student B", "B1", 2000, 50, 800.0, {"jetpack": 1, "magnet": 3})

    stats = backend.get_class_statistics()
    assert stats["total_runs"] == 2
    assert stats["unique_students"] == 2
    assert stats["average_score"] == 1500.0
    assert stats["total_coins_collected"] == 75
    assert stats["most_popular_powerup"] in ("jetpack", "magnet")


# ---------------------------------------------------------------------------
# 5. 3D Collectibles Spawner & Power-Up Token Tests
# ---------------------------------------------------------------------------
def test_all_six_powerups_present():
    expected = {
        POWERUP_MAGNET,
        POWERUP_JETPACK,
        POWERUP_SNEAKERS,
        POWERUP_MULTIPLIER,
        POWERUP_HOVERBOARD,
        POWERUP_SHIELD,
    }
    assert set(POWERUPS) == expected


def test_powerup_token_instantiation():
    cfg = {"lane_width": 2.2}
    for kind in POWERUPS:
        token = PowerUpToken(kind=kind, lane=0, cfg=cfg, z=50.0)
        assert token.kind == kind
        assert token.lane == 0
        assert token.base_y > 0.0
        assert hasattr(token, "ring")
        # Verify tick function (advances z, rotation, bobbing, and ring pulse)
        initial_z = token.z
        token.tick(dt=0.05, speed=10.0)
        assert token.z < initial_z
        assert token.bob_timer > 0.0


def test_obstacle_manager_spawns_cues():
    cfg = {"lane_width": 2.2, "moving_train_extra_speed": 4.0}
    manager = ObstacleManager(cfg=cfg, seed=42)

    assert len(manager.cues) == 0
    manager.spawn_pickup_cue((0.0, 1.2, 10.0), POWERUP_MAGNET)
    assert len(manager.cues) == 1

    # Ticking should update cue and eventually expire
    manager.tick(dt=0.1, speed=10.0)
    assert len(manager.cues) == 1

    # Safe audio playback check
    play_pickup_sound(POWERUP_JETPACK)


def test_pickup_visual_cue_animation():
    cue = PickupVisualCue(position=(0.0, 1.0, 5.0), kind=POWERUP_MULTIPLIER)
    initial_y = cue.y
    expired = cue.tick(dt=0.2)
    assert cue.y > initial_y
    assert expired is False

    # After full lifetime
    expired = cue.tick(dt=1.0)
    assert expired is True


def test_lava_train_highway_continuity():
    """Verify that spawn_lava_train_highway creates continuous, unbroken roof coverage from z=6 to >160."""
    from game import logic
    cfg = {"lane_width": 2.2, "moving_train_extra_speed": 4.0}
    manager = ObstacleManager(cfg=cfg, seed=42)

    manager.spawn_lava_train_highway()
    assert len(manager.obstacles) >= 7
    assert len(manager.coins) >= 20

    # All obstacles must be static trains with ramps
    for o in manager.obstacles:
        assert o.spec.kind == logic.KIND_TRAIN
        assert o.spec.has_ramp is True
        assert o.spec.moving is False

    # Check continuous rooftop coverage at every meter from z=10 to z=160
    for z_probe in range(10, 161, 2):
        has_roof = any(o.spec.z_start <= z_probe <= o.spec.z_end for o in manager.obstacles)
        assert has_roof, f"Gap in roof coverage at z={z_probe}m in Floor is Lava highway!"

