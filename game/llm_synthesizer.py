"""
LLM Game Logic Synthesizer & Rule Generator - Task 1
=====================================================

Teammate Role: Generative AI & Game Logic Synthesizer

Integrates directly with frontier LLMs (Gemini / OpenAI API) using specialized
system prompts, few-shot game design contexts, and structured output parsing / streaming.

Synthesizes executable behavioral rules and dynamic event hooks beyond static numbers:
  * Custom Gameplay Rules (e.g. shockwaves on roll, train reversal on jump, inverted controls, zigzag coins)
  * Custom Mechanics & Win/Loss Conditions (survival decay, floor is lava)
  * Power-Up Directives (Jetpack hover, Coin Magnet attraction, custom power triggers)

Emits a structured ``BehavioralLogicPackage`` containing executable Python condition-action
lambdas, event triggers, and semantic descriptions.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger("llm_synthesizer")

# --- System Prompts & Few-Shot Game Design Contexts ---------------------------

SYSTEM_PROMPT = """You are an expert Generative AI Game Logic Synthesizer for a 3D Subway Surfers clone.
Your task is to convert plain text user requests into structured, executable Python game logic rules.

You emit a valid JSON object with the following schema:
{
  "title": "Title of the Game Mode",
  "summary": "Short description of the gameplay modification",
  "mode_type": "custom_rules | survival | floor_is_lava | powerup | shockwave",
  "state_init": { "key": value },
  "rules": [
    {
      "rule_id": "rule_1",
      "description": "Semantic description of what this rule does",
      "event_type": "on_roll | on_jump | on_lane_change | on_tick | on_coin_collect | on_spawn",
      "condition_code": "Python boolean lambda expression string, e.g. lambda ctx: ctx['event'] == 'on_roll'",
      "action_code": "Python side-effect lambda expression string, e.g. lambda ctx: ctx['obstacles'].clear_lane(ctx['player'].lane)"
    }
  ]
}

Available context (`ctx`) variables in lambdas:
  - `ctx['game']`: The Game instance (speed, distance, coin_count, state, score, game_over(), etc.)
  - `ctx['player']`: The Player instance (x, y, z, lane, rolling, grounded, vy, etc.)
  - `ctx['obstacles']`: The ObstacleManager instance (clear_lane(lane), reverse_trains(), attract_coins(x, z, radius))
  - `ctx['hud']`: The Hud instance (show_toast(msg), score, coins)
  - `ctx['dt']`: Delta time float for frame tick
  - `ctx['event']`: The event string ("on_roll", "on_jump", "on_lane_change", "on_tick", "on_coin_collect", "on_spawn")
  - `ctx['state']`: Mutable dict storage for rule-specific state variables (timers, scores, counters)
  - `ctx['event_payload']`: Extra dict parameters for event (e.g. {'lane': 'LEFT'}, {'coin_x': 1.0})

FEW-SHOT EXAMPLES:

Example 1: "Every time Jake rolls, emit a shockwave that clears the lane"
JSON:
{
  "title": "Shockwave Roll",
  "summary": "Rolling clears all obstacles in Jake's current lane",
  "mode_type": "shockwave",
  "state_init": {},
  "rules": [
    {
      "rule_id": "shockwave_on_roll",
      "description": "Clear obstacles in player lane upon roll",
      "event_type": "on_roll",
      "condition_code": "lambda ctx: ctx['event'] == 'on_roll'",
      "action_code": "lambda ctx: (ctx['obstacles'].clear_lane(ctx['player'].lane), ctx['hud'].show_toast('BOOM! Lane Cleared!'))"
    }
  ]
}

Example 2: "Trains reverse direction when Jake jumps"
JSON:
{
  "title": "Train Reversal",
  "summary": "Jumping reverses all subway train movement direction",
  "mode_type": "custom_rules",
  "state_init": {},
  "rules": [
    {
      "rule_id": "reverse_trains_on_jump",
      "description": "Reverse train movement when player jumps",
      "event_type": "on_jump",
      "condition_code": "lambda ctx: ctx['event'] == 'on_jump'",
      "action_code": "lambda ctx: (ctx['obstacles'].reverse_trains(), ctx['hud'].show_toast('Trains Reversed!'))"
    }
  ]
}

Example 3: "Survival mode where Jake loses score every second unless collecting coins"
JSON:
{
  "title": "Survival Mode",
  "summary": "Score constantly decays over time unless coins are collected",
  "mode_type": "survival",
  "state_init": {"coin_timer": 0.0},
  "rules": [
    {
      "rule_id": "survival_tick_decay",
      "description": "Deduct score over time",
      "event_type": "on_tick",
      "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['game'].state == 'playing'",
      "action_code": "lambda ctx: ctx['game'].apply_score_penalty(int(20 * ctx['dt']))"
    },
    {
      "rule_id": "survival_coin_restore",
      "description": "Restores score on coin pickup",
      "event_type": "on_coin_collect",
      "condition_code": "lambda ctx: ctx['event'] == 'on_coin_collect'",
      "action_code": "lambda ctx: (ctx['game'].add_bonus_score(50), ctx['hud'].show_toast('+50 Survival Bonus!'))"
    }
  ]
}

Example 4: "Floor is lava mode where jumping onto train roofs is mandatory"
JSON:
{
  "title": "Floor is Lava",
  "summary": "Running on the ground for more than 1.5 seconds triggers game over",
  "mode_type": "floor_is_lava",
  "state_init": {"lava_timer": 0.0},
  "rules": [
    {
      "rule_id": "lava_ground_check",
      "description": "Triggers crash if player stays on ground too long",
      "event_type": "on_tick",
      "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['game'].state == 'playing' and ctx['player'].y < 0.2",
      "action_code": "lambda ctx: ctx['game'].game_over() if ctx['state'].update({'lava_timer': ctx['state'].get('lava_timer', 0.0) + ctx['dt']}) or ctx['state']['lava_timer'] > 1.5 else None"
    },
    {
      "rule_id": "lava_reset_on_roof",
      "description": "Resets lava timer when on train roof or airborne",
      "event_type": "on_tick",
      "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['player'].y >= 0.2",
      "action_code": "lambda ctx: ctx['state'].update({'lava_timer': 0.0})"
    }
  ]
}

Respond ONLY with valid JSON.
"""

# --- Data Deliverables --------------------------------------------------------

@dataclass
class RuleHook:
    """An individual executable dynamic rule generated by LLM."""
    rule_id: str
    description: str
    event_type: str  # "on_roll", "on_jump", "on_lane_change", "on_tick", "on_coin_collect", "on_spawn"
    condition_code: str
    action_code: str
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    action: Optional[Callable[[Dict[str, Any]], Any]] = None

    def compile(self) -> None:
        """Safely compiles string expressions into executable Python callables."""
        if self.condition is None and self.condition_code:
            self.condition = _safe_compile_lambda(self.condition_code, is_condition=True)
        if self.action is None and self.action_code:
            self.action = _safe_compile_lambda(self.action_code, is_condition=False)


@dataclass
class BehavioralLogicPackage:
    """Structured deliverable emitted by LLM Game Logic Synthesizer."""
    title: str
    summary: str
    mode_type: str
    hooks: List[RuleHook] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)
    raw_prompt: str = ""
    json_response: str = ""

    def compile_all(self) -> None:
        """Compiles all hooks inside the package."""
        for hook in self.hooks:
            hook.compile()


# --- Expression Compiler ------------------------------------------------------

def _safe_compile_lambda(expr_str: str, is_condition: bool = True) -> Callable[[Dict[str, Any]], Any]:
    """Compiles a lambda expression string safely."""
    expr_str = expr_str.strip()
    if not expr_str.startswith("lambda"):
        expr_str = f"lambda ctx: {expr_str}"

    # Build evaluation environment with safe builtins
    eval_globals = {
        "__builtins__": {
            "abs": abs, "min": min, "max": max, "int": int, "float": float,
            "str": str, "bool": bool, "len": len, "dict": dict, "list": list,
            "set": set, "getattr": getattr, "setattr": setattr, "hasattr": hasattr,
            "None": None, "True": True, "False": False,
        }
    }
    
    try:
        fn = eval(expr_str, eval_globals)  # noqa: S307
        return fn
    except Exception as e:
        logger.warning("Failed to compile lambda expression %r: %s", expr_str, e)
        if is_condition:
            return lambda ctx: False
        return lambda ctx: None


# --- LLM Synthesizer Engine --------------------------------------------------

class LLMGameLogicSynthesizer:
    """Direct LLM Integration engine to synthesize game rules from prompts."""

    def __init__(self, api_key: Optional[str] = None, provider: str = "gemini", model_name: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.provider = provider
        self.model_name = model_name or ("gemini-2.5-flash" if provider == "gemini" else "gpt-4o")

    def synthesize(self, prompt: str, streaming_callback: Optional[Callable[[str], None]] = None) -> BehavioralLogicPackage:
        """Integrates directly with frontier LLM API (Gemini / OpenAI API) or prompt templates."""
        json_str = ""

        # Direct API call if API key is provided/available in env
        if self.api_key:
            try:
                json_str = self._call_llm_api(prompt, streaming_callback=streaming_callback)
            except Exception as exc:
                logger.error("API call to LLM provider %s failed: %s. Using dynamic prompt synthesis fallback.", self.provider, exc)

        if not json_str:
            json_str = self._synthesize_fallback_json(prompt)

        package = self._parse_json_to_package(json_str, prompt)
        package.compile_all()
        return package

    def _call_llm_api(self, prompt: str, streaming_callback: Optional[Callable[[str], None]] = None) -> str:
        """Call Gemini API via `google-genai` or OpenAI API."""
        if self.provider == "gemini":
            try:
                from google import genai
                client = genai.Client(api_key=self.api_key)
                full_prompt = f"{SYSTEM_PROMPT}\n\nUSER REQUEST:\n{prompt}"
                
                if streaming_callback:
                    response_text = ""
                    response = client.models.generate_content_stream(
                        model=self.model_name,
                        contents=full_prompt,
                    )
                    for chunk in response:
                        text = getattr(chunk, "text", "")
                        response_text += text
                        streaming_callback(text)
                    return response_text
                else:
                    response = client.models.generate_content(
                        model=self.model_name,
                        contents=full_prompt,
                    )
                    return response.text
            except ImportError:
                # Try legacy google-generativeai package if new google-genai isn't available
                try:
                    import google.generativeai as ggi
                    ggi.configure(api_key=self.api_key)
                    model = ggi.GenerativeModel(self.model_name)
                    full_prompt = f"{SYSTEM_PROMPT}\n\nUSER REQUEST:\n{prompt}"
                    res = model.generate_content(full_prompt)
                    return res.text
                except Exception as ex:
                    raise RuntimeError(f"Gemini API call failed: {ex}") from ex

        elif self.provider == "openai":
            try:
                import openai
                client = openai.OpenAI(api_key=self.api_key)
                res = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"}
                )
                return res.choices[0].message.content or ""
            except Exception as ex:
                raise RuntimeError(f"OpenAI API call failed: {ex}") from ex

        return ""

    def _synthesize_fallback_json(self, prompt: str) -> str:
        """Synthesizes structured rule packages for gameplay modes based on prompt semantics."""
        prompt_lower = prompt.lower()

        if "lava" in prompt_lower or "floor" in prompt_lower:
            return json.dumps({
                "title": "Floor is Lava Mode",
                "summary": "Jumping onto train roofs is mandatory; running on ground for 1.5s causes crash",
                "mode_type": "floor_is_lava",
                "state_init": {"lava_timer": 0.0},
                "rules": [
                    {
                        "rule_id": "lava_ground_check",
                        "description": "Triggers crash if player stays on ground too long",
                        "event_type": "on_tick",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['game'].state == 'playing' and ctx['player'].y < 0.2",
                        "action_code": "lambda ctx: (ctx['state'].update({'lava_timer': ctx['state'].get('lava_timer', 0.0) + ctx['dt']}), ctx['hud'].show_toast('LAVA WARNING!', 0.2) if ctx['state']['lava_timer'] > 0.8 else None, ctx['game'].game_over() if ctx['state']['lava_timer'] > 1.5 else None)"
                    },
                    {
                        "rule_id": "lava_reset_on_roof",
                        "description": "Resets lava timer when on train roof or airborne",
                        "event_type": "on_tick",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['player'].y >= 0.2",
                        "action_code": "lambda ctx: ctx['state'].update({'lava_timer': 0.0})"
                    }
                ]
            })

        if "survival" in prompt_lower or "lose score" in prompt_lower or "decay" in prompt_lower:
            return json.dumps({
                "title": "Survival Mode",
                "summary": "Jake loses score every second unless collecting coins",
                "mode_type": "survival",
                "state_init": {"coin_timer": 0.0},
                "rules": [
                    {
                        "rule_id": "survival_tick_decay",
                        "description": "Deduct score over time",
                        "event_type": "on_tick",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['game'].state == 'playing'",
                        "action_code": "lambda ctx: ctx['game'].apply_score_penalty(int(25 * ctx['dt']))"
                    },
                    {
                        "rule_id": "survival_coin_restore",
                        "description": "Restores score on coin pickup",
                        "event_type": "on_coin_collect",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_coin_collect'",
                        "action_code": "lambda ctx: (ctx['game'].add_bonus_score(60), ctx['hud'].show_toast('+60 Survival Coin!'))"
                    }
                ]
            })

        if "shockwave" in prompt_lower or "clear" in prompt_lower:
            return json.dumps({
                "title": "Shockwave Roll Mode",
                "summary": "Every time Jake rolls, emit a shockwave that clears obstacles in his lane",
                "mode_type": "shockwave",
                "state_init": {},
                "rules": [
                    {
                        "rule_id": "shockwave_on_roll",
                        "description": "Clear obstacles in player lane upon roll",
                        "event_type": "on_roll",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_roll'",
                        "action_code": "lambda ctx: (ctx['obstacles'].clear_lane(ctx['player'].lane), ctx['hud'].show_toast('SHOCKWAVE! Lane Cleared!'))"
                    }
                ]
            })

        if "reverse" in prompt_lower:
            return json.dumps({
                "title": "Train Reversal Mode",
                "summary": "Trains reverse direction when Jake jumps",
                "mode_type": "custom_rules",
                "state_init": {},
                "rules": [
                    {
                        "rule_id": "reverse_trains_on_jump",
                        "description": "Reverse train movement when player jumps",
                        "event_type": "on_jump",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_jump'",
                        "action_code": "lambda ctx: (ctx['obstacles'].reverse_trains(), ctx['hud'].show_toast('Trains Reversed!'))"
                    }
                ]
            })

        if "invert" in prompt_lower or "outer" in prompt_lower:
            return json.dumps({
                "title": "Inverted Outer Controls",
                "summary": "Controls invert when player steps onto outer lanes",
                "mode_type": "custom_rules",
                "state_init": {"inverted": False},
                "rules": [
                    {
                        "rule_id": "invert_controls_outer",
                        "description": "Inverts left/right movement on outer lanes",
                        "event_type": "on_lane_change",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_lane_change'",
                        "action_code": "lambda ctx: (ctx['game'].set_inverted_controls(ctx['player'].lane != 0), ctx['hud'].show_toast('Controls Inverted!' if ctx['player'].lane != 0 else 'Controls Normal'))"
                    }
                ]
            })

        if "powerup" in prompt_lower or "jetpack" in prompt_lower or "magnet" in prompt_lower:
            return json.dumps({
                "title": "Power-Up Directives Mode",
                "summary": "Dynamic Jetpack and Coin Magnet triggers on specific conditions",
                "mode_type": "powerup",
                "state_init": {"magnet_timer": 0.0, "jetpack_timer": 0.0},
                "rules": [
                    {
                        "rule_id": "powerup_coin_magnet",
                        "description": "Attracts nearby coins when magnet powerup is active",
                        "event_type": "on_tick",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['game'].state == 'playing'",
                        "action_code": "lambda ctx: (ctx['obstacles'].attract_coins(ctx['player'].x, 0.0, 8.0), ctx['hud'].show_toast('MAGNET ACTIVE!', 0.3))"
                    }
                ]
            })

        if "zigzag" in prompt_lower:
            return json.dumps({
                "title": "Zigzag Coin Formation Mode",
                "summary": "Coins spawn in alternating zigzag patterns across lanes",
                "mode_type": "custom_rules",
                "state_init": {},
                "rules": [
                    {
                        "rule_id": "zigzag_coin_spawn",
                        "description": "Spawns coins in alternating lanes",
                        "event_type": "on_spawn",
                        "condition_code": "lambda ctx: ctx['event'] == 'on_spawn'",
                        "action_code": "lambda ctx: ctx['obstacles'].spawn_zigzag_coins(ctx.get('spawn_z', 100.0))"
                    }
                ]
            })


        # Generic default custom rule package
        return json.dumps({
            "title": f"Dynamic Rule Mode ({prompt})",
            "summary": f"Custom AI Synthesized Mode for: {prompt}",
            "mode_type": "custom_rules",
            "state_init": {},
            "rules": [
                {
                    "rule_id": "generic_rule_toast",
                    "description": "Announces custom prompt active",
                    "event_type": "on_tick",
                    "condition_code": "lambda ctx: ctx['event'] == 'on_tick' and ctx['state'].get('announced') is not True",
                    "action_code": f"lambda ctx: (ctx['state'].update({{'announced': True}}), ctx['hud'].show_toast('AI Mode: {prompt}', 3.0))"
                }
            ]
        })

    def _parse_json_to_package(self, json_str: str, raw_prompt: str) -> BehavioralLogicPackage:
        """Parses LLM JSON string response into BehavioralLogicPackage."""
        # Clean markdown code blocks if present
        clean_json = json_str.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(clean_json)
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode LLM JSON: %s. Using default package.", exc)
            data = {
                "title": "AI Rule Package",
                "summary": raw_prompt,
                "mode_type": "custom_rules",
                "state_init": {},
                "rules": []
            }

        hooks = []
        for r in data.get("rules", []):
            hook = RuleHook(
                rule_id=r.get("rule_id", "rule_anon"),
                description=r.get("description", ""),
                event_type=r.get("event_type", "on_tick"),
                condition_code=r.get("condition_code", "lambda ctx: True"),
                action_code=r.get("action_code", "lambda ctx: None"),
            )
            hooks.append(hook)

        return BehavioralLogicPackage(
            title=data.get("title", "AI Mode"),
            summary=data.get("summary", raw_prompt),
            mode_type=data.get("mode_type", "custom_rules"),
            hooks=hooks,
            state=data.get("state_init", {}),
            raw_prompt=raw_prompt,
            json_response=json_str,
        )


# --- Logic Rule Executor ------------------------------------------------------

class LogicRuleExecutor:
    """Executes synthesized BehavioralLogicPackages on live game instances."""

    def __init__(self, game_ref: Any, package: Optional[BehavioralLogicPackage] = None):
        self.game = game_ref
        self.package = package
        self.inverted_controls = False

    def set_package(self, package: BehavioralLogicPackage) -> None:
        self.package = package
        self.package.compile_all()
        self.inverted_controls = False

    def trigger_event(self, event_name: str, dt: float = 0.0, payload: Optional[Dict[str, Any]] = None) -> None:
        """Evaluates condition-action lambdas registered for ``event_name``."""
        if not self.package or not self.game:
            return

        ctx = {
            "game": self.game,
            "player": getattr(self.game, "player", None),
            "obstacles": getattr(self.game, "obstacles", None),
            "hud": getattr(self.game, "hud", None),
            "world": getattr(self.game, "world", None),
            "dt": dt,
            "event": event_name,
            "state": self.package.state,
            "event_payload": payload or {},
        }

        for hook in self.package.hooks:
            if hook.event_type == event_name and hook.condition and hook.action:
                try:
                    if hook.condition(ctx):
                        hook.action(ctx)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error executing rule %s on event %s: %s", hook.rule_id, event_name, exc)
