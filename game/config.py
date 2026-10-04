"""Loads game/config.json and hot-reloads it when the file changes.

The future "prompt" feature only has to rewrite config.json; the running game
picks the change up within ~1 second.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("game.config")

CONFIG_PATH = Path(__file__).with_name("config.json")

DEFAULTS: dict = {
    "start_speed": 15.0,
    "max_speed": 34.0,
    "speed_increase_per_second": 0.22,
    "gravity": 55.0,
    "jump_velocity": 17.0,
    "roll_duration": 0.7,
    "lane_switch_speed": 14.0,
    "lane_width": 2.13,
    "spawn_gap_min": 16.0,
    "spawn_gap_max": 26.0,
    "coin_chance": 0.65,
    "moving_train_chance": 0.25,
    "moving_train_extra_speed": 8.0,
    "score_per_meter": 1.0,
    "sky_top_color": "#4aa8ff",
    "sky_bottom_color": "#cdeeff",
    "train_colors": ["#2f6fd6", "#d64545", "#3aa356", "#e0a020"],
    "building_colors": ["#b5653a", "#d9c7a3", "#8a8f99", "#c98f5a"],
    "coin_color": "#ffcc1a",
    "player": {
        "hoodie": "#1fb5a8", "pants": "#2b3a67", "cap": "#ff7a1a",
        "skin": "#e8b48a", "shoes": "#f4f4f4", "backpack": "#e8425a",
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Defaults merged with the JSON file. A broken file falls back to defaults."""
    try:
        with open(path, encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    except FileNotFoundError:
        logger.warning("%s not found, using defaults", path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Could not read %s (%s), using defaults", path, exc)
    return copy.deepcopy(DEFAULTS)


class ConfigWatcher:
    """Call ``poll()`` periodically; returns a new dict when the file changed."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self._mtime = self._read_mtime()

    def _read_mtime(self) -> float:
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return 0.0

    def poll(self) -> dict | None:
        mtime = self._read_mtime()
        if mtime and mtime != self._mtime:
            self._mtime = mtime
            logger.info("config.json changed - reloading")
            return load_config(self.path)
        return None
