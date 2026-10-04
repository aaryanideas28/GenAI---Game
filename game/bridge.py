"""Bridge: teammates' EventBus  ->  game command queue.

NOT wired in yet (teammates' code is untouched). When you integrate, either
add "game.bridge" to TEAMMATE_MODULES in main.py, or call ``register(bus)``
from controller.py. Events follow the contract in event_bus.py:

    EVENT_LANE_CHANGED -> {"lane": "LEFT"|"CENTER"|"RIGHT", "timestamp": float}
    EVENT_ACTION       -> {"action": "JUMP"|"CROUCH",       "timestamp": float}
"""

from __future__ import annotations

from game import commands


def _on_lane(payload: dict) -> None:
    commands.push_lane(payload["lane"])


def _on_action(payload: dict) -> None:
    commands.push_action(payload["action"])


def register(bus) -> None:
    from event_bus import EVENT_ACTION, EVENT_LANE_CHANGED  # imported lazily: game runs standalone too
    bus.subscribe(EVENT_LANE_CHANGED, _on_lane)
    bus.subscribe(EVENT_ACTION, _on_action)
