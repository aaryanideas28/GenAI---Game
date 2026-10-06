"""
Root re-export for Student Leaderboard Backend (Task 4)
"""

from game.leaderboard import (
    BOARD_RANKED,
    BOARD_SANDBOX,
    AntiTamperVerifier,
    LeaderboardBackend,
    LeaderboardEntry,
)

__all__ = [
    "BOARD_RANKED",
    "BOARD_SANDBOX",
    "AntiTamperVerifier",
    "LeaderboardBackend",
    "LeaderboardEntry",
]
