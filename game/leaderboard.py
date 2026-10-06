"""
STUDENT LEADERBOARD BACKEND & ANTI-TAMPER PERSISTENCE
=====================================================

Task 4 (Teammate 4: World Spawner & Database Architect)

Scope & Responsibilities:
  1. Student Score Persistence:
     - Persists student name, roll number, score, coins, distance,
       power-ups collected, active prompt logic summary, and timestamps.
     - Atomic write operations with temporary files and filesystem replace
       to guarantee zero data corruption during unexpected game closures.
  2. Dual Leaderboard Segregation:
     - Maintains separate RANKED (fair skill) and SANDBOX (AI-generated custom logic) boards.
     - Anti-tamper verification confirming score consistency with distance and coins.
     - HMAC/SHA-256 cryptographic signature verification.
  3. Teacher Export Tools:
     - One-click function to export complete class roster and scores into spreadsheet/CSV
       with rank positions, detailed power-up breakdown, and grading summaries.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("leaderboard")

# Cryptographic salt for anti-tamper signature generation
_INTEGRITY_SALT = b"SubwaySurfers-GenAI-AntiTamper-Task4-2026"

BOARD_RANKED = "RANKED"
BOARD_SANDBOX = "SANDBOX"


@dataclass
class LeaderboardEntry:
    """Represents a persisted student game run record."""
    entry_id: str
    student_name: str
    roll_number: str
    score: int
    coins: int
    distance: float
    powerups_collected: Dict[str, int] = field(default_factory=dict)
    total_powerups: int = 0
    active_prompt_summary: str = "Vanilla / Default Rules"
    board_type: str = BOARD_RANKED     # RANKED or SANDBOX
    timestamp: str = ""
    verified: bool = True
    verification_status: str = "VERIFIED"   # VERIFIED, UNVERIFIED, TAMPERED, FLAGGED
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeaderboardEntry":
        # Handle backward compatibility / missing fields gracefully
        pu = data.get("powerups_collected", {})
        if not isinstance(pu, dict):
            pu = {}
        total_pu = data.get("total_powerups", sum(pu.values()) if pu else 0)
        return cls(
            entry_id=str(data.get("entry_id", "")),
            student_name=str(data.get("student_name", "Anonymous")),
            roll_number=str(data.get("roll_number", "N/A")),
            score=int(data.get("score", 0)),
            coins=int(data.get("coins", 0)),
            distance=round(float(data.get("distance", 0.0)), 1),
            powerups_collected=pu,
            total_powerups=total_pu,
            active_prompt_summary=str(data.get("active_prompt_summary", "Default Rules")),
            board_type=str(data.get("board_type", BOARD_RANKED)),
            timestamp=str(data.get("timestamp", "")),
            verified=bool(data.get("verified", True)),
            verification_status=str(data.get("verification_status", "VERIFIED")),
            checksum=str(data.get("checksum", "")),
        )


class AntiTamperVerifier:
    """Validates game score authenticity, physics plausibility, and record checksums."""

    @staticmethod
    def compute_checksum(student_name: str, roll_number: str, score: int,
                         coins: int, distance: float, board_type: str,
                         timestamp: str) -> str:
        """Computes HMAC-SHA256 signature for score record to detect file tampering."""
        payload = f"{student_name.strip()}|{roll_number.strip()}|{score}|{coins}|{distance:.1f}|{board_type}|{timestamp}".encode("utf-8")
        return hmac.new(_INTEGRITY_SALT, payload, hashlib.sha256).hexdigest()

    @staticmethod
    def verify_record(entry: LeaderboardEntry, cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """Validates score plausibility against distance and coin limits.

        Returns (is_valid, reason).
        """
        # 1. Non-negative bounds
        if entry.score < 0:
            return False, "Negative score detected"
        if entry.coins < 0:
            return False, "Negative coin count detected"
        if entry.distance < 0.0:
            return False, "Negative distance detected"

        # 2. Physics consistency check:
        # In Subway Surfers, score = (distance * score_per_meter * multiplier) + (coins * coin_val) + bonus
        # Default: 1 meter = 1 score point (x2 multiplier = 2), 1 coin = 10 score points.
        score_per_m = float(cfg.get("score_per_meter", 1.0)) if cfg else 1.0
        max_multiplier = 4.0      # generous ceiling for stacked multipliers
        max_coin_val = 100        # generous ceiling for coin bonuses
        bonus_cap_per_meter = 50  # generous ceiling for dynamic event bonuses

        # Calculate theoretical ceiling
        max_dist_score = entry.distance * score_per_m * max_multiplier
        max_coin_score = entry.coins * max_coin_val
        max_bonus = max(500.0, entry.distance * bonus_cap_per_meter)
        theoretical_ceiling = max_dist_score + max_coin_score + max_bonus + 1000

        # Impossible score check: e.g. 5 meters ran, 0 coins, but 50,000 score
        if entry.distance < 20.0 and entry.coins < 5 and entry.score > 2500:
            return False, f"Impossible score ({entry.score}) for distance ({entry.distance:.1f}m)"

        if entry.score > theoretical_ceiling:
            return False, f"Score ({entry.score}) exceeds physical ceiling ({int(theoretical_ceiling)})"

        # 3. Checksum verification if record already has a checksum
        if entry.checksum:
            expected = AntiTamperVerifier.compute_checksum(
                entry.student_name, entry.roll_number, entry.score,
                entry.coins, entry.distance, entry.board_type, entry.timestamp
            )
            if not hmac.compare_digest(entry.checksum, expected):
                return False, "Checksum mismatch: entry was altered after creation"

        return True, "Verified Authentic Run"


class LeaderboardBackend:
    """Thread-safe student leaderboard database manager with atomic file I/O."""

    DEFAULT_DB_FILENAME = "student_leaderboard.json"

    def __init__(self, storage_path: Optional[Union[str, Path]] = None,
                 cfg: Optional[Dict[str, Any]] = None) -> None:
        if storage_path is None:
            storage_path = Path(__file__).resolve().parent / self.DEFAULT_DB_FILENAME
        self.storage_path = Path(storage_path).resolve()
        self.cfg = cfg or {}
        self._lock = threading.RLock()
        self._entries: List[LeaderboardEntry] = []
        self._load()

    # -------------------------------------------------------------------------
    # Core Persistence & Atomic Operations
    # -------------------------------------------------------------------------
    def _load(self) -> None:
        """Loads records from disk with automatic corruption recovery."""
        with self._lock:
            self._entries.clear()
            if not self.storage_path.is_file():
                return

            try:
                content = self.storage_path.read_text(encoding="utf-8")
                if not content.strip():
                    return
                data = json.loads(content)
                raw_list = data if isinstance(data, list) else data.get("entries", [])
                for item in raw_list:
                    try:
                        self._entries.append(LeaderboardEntry.from_dict(item))
                    except Exception as ex:
                        logger.warning("Skipping corrupted leaderboard record: %s", ex)
            except Exception as e:
                logger.error("Failed to read leaderboard at %s: %s", self.storage_path, e)
                # Check for backup file
                bak = self.storage_path.with_suffix(".json.bak")
                if bak.is_file():
                    try:
                        logger.info("Restoring leaderboard from backup %s", bak)
                        data = json.loads(bak.read_text(encoding="utf-8"))
                        raw_list = data if isinstance(data, list) else data.get("entries", [])
                        self._entries = [LeaderboardEntry.from_dict(item) for item in raw_list]
                    except Exception as bak_err:
                        logger.error("Backup restoration also failed: %s", bak_err)

    def save(self) -> bool:
        """Atomically saves all entries to disk with zero-corruption guarantees."""
        with self._lock:
            # Create parent directories if they don't exist
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            payload = {
                "version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_records": len(self._entries),
                "entries": [entry.to_dict() for entry in self._entries],
            }
            serialized = json.dumps(payload, indent=2, ensure_ascii=False)

            # Atomic write pattern:
            # 1. Write to temporary file in the exact same directory
            # 2. Flush and fsync
            # 3. Create backup of current file
            # 4. Atomically rename/replace temp file to target file
            temp_file = None
            try:
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.storage_path.parent,
                    prefix=f"{self.storage_path.stem}_tmp_",
                    suffix=".tmp"
                )
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(serialized)
                    f.flush()
                    os.fsync(f.fileno())

                # Create backup if current file exists
                if self.storage_path.is_file():
                    bak_path = self.storage_path.with_suffix(".json.bak")
                    try:
                        bak_path.write_bytes(self.storage_path.read_bytes())
                    except Exception:
                        pass

                # Atomic replace (atomic on Windows and Unix for same volume)
                os.replace(temp_path, self.storage_path)
                return True
            except Exception as e:
                logger.error("Atomic write failed for leaderboard: %s", e)
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                return False

    # -------------------------------------------------------------------------
    # Record Ingestion & Segregation
    # -------------------------------------------------------------------------
    def record_run(self, student_name: str, roll_number: str,
                   score: int, coins: int, distance: float,
                   powerups_collected: Optional[Dict[str, int]] = None,
                   active_prompt_summary: str = "Vanilla / Default Rules",
                   is_sandbox: Optional[bool] = None) -> LeaderboardEntry:
        """Validates, classifies, signs, and persists a completed student game run.

        Parameters:
          student_name: Full name of student
          roll_number: Student school ID or roll number
          score: Total run score
          coins: Total coins collected
          distance: Distance ran in meters
          powerups_collected: Dict of power-up kinds and count collected
          active_prompt_summary: Summary of AI prompt rule package
          is_sandbox: Explicit flag. If None, automatically inferred from prompt summary.
        """
        with self._lock:
            pu = powerups_collected or {}
            total_pu = sum(pu.values())

            # Infer board type if not explicitly supplied
            if is_sandbox is None:
                summary_lower = active_prompt_summary.lower()
                is_custom = not (
                    "default" in summary_lower or
                    "vanilla" in summary_lower or
                    "normal" in summary_lower or
                    not active_prompt_summary.strip()
                )
                board_type = BOARD_SANDBOX if is_custom else BOARD_RANKED
            else:
                board_type = BOARD_SANDBOX if is_sandbox else BOARD_RANKED

            # Generate unique entry ID and timestamp
            entry_id = f"RUN-{int(time.time()*1000)}-{os.urandom(3).hex()}"
            ts = datetime.now(timezone.utc).isoformat()

            # Pre-compute signature
            checksum = AntiTamperVerifier.compute_checksum(
                student_name, roll_number, score, coins, distance, board_type, ts
            )

            entry = LeaderboardEntry(
                entry_id=entry_id,
                student_name=student_name.strip() or "Anonymous",
                roll_number=roll_number.strip() or "N/A",
                score=max(0, int(score)),
                coins=max(0, int(coins)),
                distance=max(0.0, round(float(distance), 1)),
                powerups_collected=pu,
                total_powerups=total_pu,
                active_prompt_summary=active_prompt_summary.strip() or "Vanilla / Default Rules",
                board_type=board_type,
                timestamp=ts,
                verified=True,
                verification_status="VERIFIED",
                checksum=checksum,
            )

            # Perform anti-tamper verification
            is_valid, reason = AntiTamperVerifier.verify_record(entry, self.cfg)
            if not is_valid:
                logger.warning("Anti-tamper flagged run for %s (%s): %s",
                               student_name, roll_number, reason)
                entry.verified = False
                entry.verification_status = f"FLAGGED: {reason}"
                # If flagged and was ranked, demote to sandbox so ranked stays fair
                if entry.board_type == BOARD_RANKED:
                    entry.board_type = BOARD_SANDBOX
                    # Recompute checksum for new board type
                    entry.checksum = AntiTamperVerifier.compute_checksum(
                        entry.student_name, entry.roll_number, entry.score,
                        entry.coins, entry.distance, entry.board_type, entry.timestamp
                    )

            self._entries.append(entry)
            self.save()
            return entry

    # -------------------------------------------------------------------------
    # Dual Board Query APIs
    # -------------------------------------------------------------------------
    def get_ranked_board(self, limit: int = 100, verified_only: bool = True) -> List[LeaderboardEntry]:
        """Returns top scores for fair, competitive, unmodded gameplay."""
        with self._lock:
            ranked = [e for e in self._entries if e.board_type == BOARD_RANKED]
            if verified_only:
                ranked = [e for e in ranked if e.verified]
            ranked.sort(key=lambda x: x.score, reverse=True)
            return ranked[:limit]

    def get_sandbox_board(self, limit: int = 100) -> List[LeaderboardEntry]:
        """Returns top scores for creative, AI-synthesized custom rule runs."""
        with self._lock:
            sandbox = [e for e in self._entries if e.board_type == BOARD_SANDBOX]
            sandbox.sort(key=lambda x: x.score, reverse=True)
            return sandbox[:limit]

    def get_all_entries(self) -> List[LeaderboardEntry]:
        """Returns all entries sorted by score descending."""
        with self._lock:
            return sorted(self._entries, key=lambda x: x.score, reverse=True)

    def get_student_history(self, roll_number: str) -> List[LeaderboardEntry]:
        """Retrieves all attempts by a specific student roll number."""
        with self._lock:
            rn = roll_number.strip().lower()
            return [e for e in self._entries if e.roll_number.strip().lower() == rn]

    def get_student_best(self, roll_number: str, board_type: Optional[str] = None) -> Optional[LeaderboardEntry]:
        """Retrieves the personal best run for a student."""
        history = self.get_student_history(roll_number)
        if board_type:
            history = [e for e in history if e.board_type == board_type]
        if not history:
            return None
        return max(history, key=lambda x: x.score)

    def clear(self) -> None:
        """Clears all records in memory and saves."""
        with self._lock:
            self._entries.clear()
            self.save()

    # -------------------------------------------------------------------------
    # Teacher Export Tools (CSV & Grading Reports)
    # -------------------------------------------------------------------------
    def export_to_csv(self, filepath: Optional[Union[str, Path]] = None,
                      board_type: Optional[str] = None) -> Path:
        """One-click export of complete leaderboard into CSV for teachers.

        Parameters:
          filepath: Destination file path. If None, generates timestamped file.
          board_type: Optional filter (RANKED, SANDBOX, or None for all).
        """
        with self._lock:
            if filepath is None:
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = self.storage_path.parent / f"student_scores_export_{ts_str}.csv"
            out_path = Path(filepath).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)

            entries = self._entries
            if board_type:
                entries = [e for e in entries if e.board_type == board_type]
            # Sort by score descending
            entries = sorted(entries, key=lambda x: x.score, reverse=True)

            fieldnames = [
                "Rank",
                "Student Name",
                "Roll Number",
                "Board Type",
                "Final Score",
                "Coins Collected",
                "Distance (m)",
                "Total Power-Ups",
                "Power-Ups Breakdown",
                "Active AI Prompt / Rules",
                "Submission Timestamp",
                "Integrity Status",
                "Run ID",
            ]

            with open(out_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for rank, e in enumerate(entries, start=1):
                    pu_str = ", ".join(f"{k}: {v}" for k, v in e.powerups_collected.items() if v > 0)
                    writer.writerow({
                        "Rank": rank,
                        "Student Name": e.student_name,
                        "Roll Number": e.roll_number,
                        "Board Type": e.board_type,
                        "Final Score": e.score,
                        "Coins Collected": e.coins,
                        "Distance (m)": f"{e.distance:.1f}",
                        "Total Power-Ups": e.total_powerups,
                        "Power-Ups Breakdown": pu_str or "None",
                        "Active AI Prompt / Rules": e.active_prompt_summary,
                        "Submission Timestamp": e.timestamp,
                        "Integrity Status": e.verification_status,
                        "Run ID": e.entry_id,
                    })

            logger.info("Exported %d student leaderboard records to %s", len(entries), out_path)
            return out_path

    def export_roster_summary_csv(self, filepath: Optional[Union[str, Path]] = None) -> Path:
        """Exports aggregated class roster where each student appears once with their best score."""
        with self._lock:
            if filepath is None:
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = self.storage_path.parent / f"class_roster_summary_{ts_str}.csv"
            out_path = Path(filepath).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Group by roll number
            roster: Dict[str, Dict[str, Any]] = {}
            for e in self._entries:
                key = e.roll_number.strip().upper() or e.student_name.strip().upper()
                if key not in roster:
                    roster[key] = {
                        "student_name": e.student_name,
                        "roll_number": e.roll_number,
                        "total_attempts": 0,
                        "best_ranked_score": 0,
                        "best_sandbox_score": 0,
                        "total_coins": 0,
                        "total_distance": 0.0,
                        "total_powerups": 0,
                        "last_active": e.timestamp,
                    }
                r = roster[key]
                r["total_attempts"] += 1
                if e.board_type == BOARD_RANKED:
                    r["best_ranked_score"] = max(r["best_ranked_score"], e.score)
                else:
                    r["best_sandbox_score"] = max(r["best_sandbox_score"], e.score)
                r["total_coins"] += e.coins
                r["total_distance"] += e.distance
                r["total_powerups"] += e.total_powerups
                if e.timestamp > r["last_active"]:
                    r["last_active"] = e.timestamp

            # Sort students by highest overall score
            students = sorted(roster.values(),
                              key=lambda s: max(s["best_ranked_score"], s["best_sandbox_score"]),
                              reverse=True)

            fieldnames = [
                "Rank",
                "Student Name",
                "Roll Number",
                "Best Ranked Score",
                "Best Sandbox Score",
                "Highest Score",
                "Total Runs",
                "Lifetime Coins",
                "Total Distance (m)",
                "Total Power-Ups",
                "Last Active",
            ]

            with open(out_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for rank, s in enumerate(students, start=1):
                    highest = max(s["best_ranked_score"], s["best_sandbox_score"])
                    writer.writerow({
                        "Rank": rank,
                        "Student Name": s["student_name"],
                        "Roll Number": s["roll_number"],
                        "Best Ranked Score": s["best_ranked_score"],
                        "Best Sandbox Score": s["best_sandbox_score"],
                        "Highest Score": highest,
                        "Total Runs": s["total_attempts"],
                        "Lifetime Coins": s["total_coins"],
                        "Total Distance (m)": f"{s['total_distance']:.1f}",
                        "Total Power-Ups": s["total_powerups"],
                        "Last Active": s["last_active"],
                    })

            logger.info("Exported %d student roster summaries to %s", len(students), out_path)
            return out_path

    def get_class_statistics(self) -> Dict[str, Any]:
        """Calculates key class metrics for teacher dashboard / grading."""
        with self._lock:
            if not self._entries:
                return {
                    "total_runs": 0,
                    "unique_students": 0,
                    "ranked_runs": 0,
                    "sandbox_runs": 0,
                    "highest_ranked_score": 0,
                    "highest_sandbox_score": 0,
                    "average_score": 0.0,
                    "total_coins_collected": 0,
                    "total_distance_m": 0.0,
                    "most_popular_powerup": "None",
                }

            unique_rolls = {e.roll_number.strip().upper() for e in self._entries}
            ranked = [e for e in self._entries if e.board_type == BOARD_RANKED]
            sandbox = [e for e in self._entries if e.board_type == BOARD_SANDBOX]

            pu_totals: Dict[str, int] = {}
            for e in self._entries:
                for k, v in e.powerups_collected.items():
                    pu_totals[k] = pu_totals.get(k, 0) + v

            top_pu = max(pu_totals.items(), key=lambda x: x[1])[0] if pu_totals else "None"

            return {
                "total_runs": len(self._entries),
                "unique_students": len(unique_rolls),
                "ranked_runs": len(ranked),
                "sandbox_runs": len(sandbox),
                "highest_ranked_score": max((e.score for e in ranked), default=0),
                "highest_sandbox_score": max((e.score for e in sandbox), default=0),
                "average_score": round(sum(e.score for e in self._entries) / len(self._entries), 1),
                "total_coins_collected": sum(e.coins for e in self._entries),
                "total_distance_m": round(sum(e.distance for e in self._entries), 1),
                "most_popular_powerup": top_pu,
            }
