"""TEAMMATE 4: replace this stub with the key controller / game integration.

Contract:
  * EVENT_LANE_CHANGED -> {"lane": "LEFT"|"CENTER"|"RIGHT", "timestamp": float}
  * EVENT_ACTION       -> {"action": "JUMP"|"CROUCH", "timestamp": float}
Map these to game key presses / game calls.
"""

from __future__ import annotations

from event_bus import EVENT_ACTION, EVENT_LANE_CHANGED, EventBus


def _on_lane(payload: dict) -> None:
    print(f"[controller STUB] LANE: {payload['lane']}")


def _on_action(payload: dict) -> None:
    print(f"[controller STUB] ACTION: {payload['action']}")


def register(bus: EventBus) -> None:
    """Entry point called by main.py. TEAMMATE 4: replace this."""
    bus.subscribe(EVENT_LANE_CHANGED, _on_lane)
    bus.subscribe(EVENT_ACTION, _on_action)