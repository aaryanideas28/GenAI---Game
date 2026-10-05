"""
Guardrails System for GenAI Game Logic Synthesizer - Task 2 (Teammate 2)
========================================================================

Comprehensive multi-layer safety guardrails protecting:
  1. Prompt Security (Jailbreak / Prompt Injection Defense & Sanitization)
  2. Code Sandbox & AST Validation (Stops dunder leaks, arbitrary imports, dangerous builtins)
  3. Game Invariants & Anti-Cheat Clamping (Score, Speed, Jump limits)
  4. Runtime Stability Guard (Error containment, fault-tolerant execution, crash prevention)
"""

from __future__ import annotations

import ast
import logging
import re
import time
from typing import Any, Callable, Dict, Optional, Set, Tuple

logger = logging.getLogger("guardrails")

# -----------------------------------------------------------------------------
# 1. Prompt Guard: Injection & Adversarial Content Filtering
# -----------------------------------------------------------------------------

MAX_PROMPT_LENGTH = 250

PROMPT_INJECTION_PATTERNS = [
    r"\b(ignore\s+(all\s+)?(previous|prior)\s+instructions)\b",
    r"\b(ignore\s+system\s+prompt)\b",
    r"\b(disregard\s+(all\s+)?instructions)\b",
    r"\b(output\s+only\s+python\s+code\s+without\s+json)\b",
    r"\b(system\s+override|jailbreak|developer\s+mode)\b",
    r"\b(delete\s+(all\s+)?files|rmdir|format\s+c:)\b",
    r"\b(__import__|subprocess|os\.system|shutil|eval\(|exec\()\b",
    r"\b(drop\s+database|truncate\s+table)\b",
]

COMPILED_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in PROMPT_INJECTION_PATTERNS]


class PromptGuard:
    """Sanitizes and validates incoming natural language prompts before LLM dispatch."""

    @staticmethod
    def validate_prompt(prompt: str) -> Tuple[bool, str]:
        """Validates that prompt is safe, within length, and free of adversarial injections.
        
        Returns:
            (is_safe, error_or_sanitized_text)
        """
        if not prompt or not prompt.strip():
            return False, "Prompt is empty."

        clean = prompt.strip()

        if len(clean) > MAX_PROMPT_LENGTH:
            return False, f"Prompt exceeds maximum allowed length of {MAX_PROMPT_LENGTH} characters."

        for pattern in COMPILED_INJECTION_RE:
            if pattern.search(clean):
                logger.warning("Guardrail blocked prompt injection attempt: %r", clean)
                return False, "Prompt rejected: Contains restricted prompt-injection or dangerous command patterns."

        # Strip unprintable or control characters
        sanitized = "".join(ch for ch in clean if ch.isprintable())
        return True, sanitized


# -----------------------------------------------------------------------------
# 2. AST Validator: Python Code Sandboxing
# -----------------------------------------------------------------------------

# Whitelist of permissible method names on game/player/obstacle entities
ALLOWED_CALL_NAMES: Set[str] = {
    # Game & Score
    "add_bonus_score", "add_score", "add_points", "deduct_score",
    "apply_score_penalty", "set_inverted_controls",
    "game_over", "activate_powerup",
    # Obstacles & World
    "clear_lane", "reverse_trains", "attract_coins", "spawn_zigzag_coins",
    "spawn_sky_coins", "live_specs",
    # Player & HUD
    "set_lane", "jump", "roll", "move", "show_toast",
    # Dict & State operations
    "get", "update", "clear", "items", "keys", "values",
    # Safe math / builtins
    "abs", "min", "max", "int", "float", "bool", "len", "str",
}

# Whitelist of allowed AST node types
ALLOWED_AST_NODES = (
    ast.Expression, ast.Lambda, ast.Call, ast.Attribute, ast.Name,
    ast.Constant, ast.UnaryOp, ast.BinOp, ast.Compare, ast.Subscript,
    ast.Tuple, ast.List, ast.Dict, ast.BoolOp, ast.IfExp,
    ast.FormattedValue, ast.JoinedStr, ast.Load, ast.Store,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot,
    ast.In, ast.NotIn, ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
    ast.arguments, ast.arg, ast.keyword, ast.Slice,
)


class ASTValidator:
    """Statically verifies executable Python rule lambdas to guarantee sandbox safety."""

    @classmethod
    def validate_code(cls, code_str: str) -> Tuple[bool, str]:
        """Parses and inspects code string using Python AST.
        
        Ensures:
          - No dunder attributes (__class__, __subclasses__, __globals__, etc.)
          - No imports, exec, eval, or OS access
          - Only whitelisted AST nodes and method invocations
        """
        code_str = code_str.strip()
        if not code_str:
            return False, "Code string is empty."

        # Auto-wrap naked expression in lambda ctx if needed
        test_str = code_str if code_str.startswith("lambda") else f"lambda ctx: {code_str}"

        try:
            tree = ast.parse(test_str, mode="eval")
        except SyntaxError as e:
            return False, f"Syntax error in synthesized rule: {e}"

        for node in ast.walk(tree):
            # Check 1: Enforce allowed node types
            if not isinstance(node, ALLOWED_AST_NODES):
                return False, f"Disallowed syntax structure: {type(node).__name__}"

            # Check 2: Block ALL dunder access (e.g. __class__, __subclasses__, __dict__)
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                logger.warning("Guardrail blocked dunder access attempt: %r", node.attr)
                return False, f"Restricted dunder attribute access: {node.attr}"

            if isinstance(node, ast.Name) and node.id.startswith("__"):
                logger.warning("Guardrail blocked dunder name attempt: %r", node.id)
                return False, f"Restricted dunder variable access: {node.id}"

            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("__"):
                logger.warning("Guardrail blocked dunder string attempt: %r", node.value)
                return False, f"Restricted dunder access: {node.value}"

            # Check 3: Method call whitelist validation
            if isinstance(node, ast.Call):
                func = node.func
                call_name = None
                if isinstance(func, ast.Name):
                    call_name = func.id
                elif isinstance(func, ast.Attribute):
                    call_name = func.attr

                if call_name:
                    if call_name.startswith("__"):
                        logger.warning("Guardrail blocked dunder method attempt: %r", call_name)
                        return False, f"Restricted dunder method call: {call_name}"
                    if call_name not in ALLOWED_CALL_NAMES:
                        logger.warning("Guardrail blocked unauthorized method invocation: %r", call_name)
                        return False, f"Unauthorized method call: {call_name}"

        return True, "Code passed AST sandbox validation."


# -----------------------------------------------------------------------------
# 3. Game Invariants & Anti-Cheat Safety Clamps
# -----------------------------------------------------------------------------

SCORE_BONUS_MAX = 1000
SCORE_PENALTY_MAX = 500
SPEED_MIN = 5.0
SPEED_MAX = 35.0
JUMP_VELOCITY_MIN = 8.0
JUMP_VELOCITY_MAX = 25.0


class SafetyClamps:
    """Guarantees fair play, leaderboard integrity, and physics stability."""

    @staticmethod
    def clamp_bonus_score(points: int) -> int:
        """Clamps bonus score to prevent leaderboard corruption."""
        try:
            p = int(points)
        except (ValueError, TypeError):
            return 0
        return max(0, min(SCORE_BONUS_MAX, p))

    @staticmethod
    def clamp_score_penalty(points: int) -> int:
        """Clamps score penalty to reasonable survival bounds."""
        try:
            p = int(points)
        except (ValueError, TypeError):
            return 0
        return max(0, min(SCORE_PENALTY_MAX, p))

    @staticmethod
    def clamp_speed(speed: float) -> float:
        """Prevents physics breakdowns, chunk tunneling, or frozen movement."""
        try:
            s = float(speed)
            if s != s or s == float("inf") or s == float("-inf"):  # NaN or Inf check
                return 12.0
            return max(SPEED_MIN, min(SPEED_MAX, s))
        except (ValueError, TypeError):
            return 12.0

    @staticmethod
    def clamp_jump_velocity(vel: float) -> float:
        """Keeps Jake within visible screen bounds and track geometry."""
        try:
            v = float(vel)
            if v != v:
                return 15.0
            return max(JUMP_VELOCITY_MIN, min(JUMP_VELOCITY_MAX, v))
        except (ValueError, TypeError):
            return 15.0


# -----------------------------------------------------------------------------
# 4. Runtime Guard: Error Containment & Fault-Tolerant Execution
# -----------------------------------------------------------------------------

MAX_RULE_FAILURES = 3
MAX_EXECUTION_MS = 10.0


class RuntimeGuard:
    """Executes rule callables inside a protective boundary to eliminate frame crashes."""

    def __init__(self, hud_ref: Optional[Any] = None) -> None:
        self.hud = hud_ref
        self.failure_counts: Dict[str, int] = {}
        self.disabled_rules: Set[str] = set()

    def is_rule_disabled(self, rule_id: str) -> bool:
        return rule_id in self.disabled_rules

    def execute_hook(self, hook: Any, ctx: Dict[str, Any]) -> Any:
        """Safely evaluates a rule's condition and action with crash isolation."""
        if not hook or hook.rule_id in self.disabled_rules:
            return None

        # Check condition
        try:
            if hook.condition is not None and not hook.condition(ctx):
                return None
        except Exception as exc:
            self._handle_failure(hook, exc, phase="condition")
            return None

        # Execute action with timing guard
        t0 = time.perf_counter()
        try:
            if hook.action is not None:
                result = hook.action(ctx)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if elapsed_ms > MAX_EXECUTION_MS:
                    logger.warning("Rule '%s' took %.2fms (exceeded %0.1fms limit)",
                                   hook.rule_id, elapsed_ms, MAX_EXECUTION_MS)
                return result
        except Exception as exc:
            self._handle_failure(hook, exc, phase="action")
            return None

    def _handle_failure(self, hook: Any, error: Exception, phase: str) -> None:
        """Isolates runtime errors and revokes broken rules to keep the game running."""
        rule_id = getattr(hook, "rule_id", "anon_rule")
        count = self.failure_counts.get(rule_id, 0) + 1
        self.failure_counts[rule_id] = count

        logger.error("Runtime error in rule '%s' during %s (%d/%d): %s",
                     rule_id, phase, count, MAX_RULE_FAILURES, error)

        if count >= MAX_RULE_FAILURES:
            self.disabled_rules.add(rule_id)
            logger.warning("Guardrail disabled malfunctioning rule '%s' to protect game loop.", rule_id)
            if self.hud and hasattr(self.hud, "show_toast"):
                self.hud.show_toast(f"Guardrail: Revoked unstable rule '{rule_id}'", 3.0)
