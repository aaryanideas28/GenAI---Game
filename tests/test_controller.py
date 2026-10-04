"""Tests for Teammate 4: OpenCV controller and game command integration."""

from __future__ import annotations

import event_bus as eb
from controller import _on_action, _on_lane, register
from game import commands


def test_on_lane_pushes_command():
    commands.drain()  # Clear queue
    _on_lane({"lane": "LEFT", "timestamp": 123.4})
    assert commands.drain() == [(commands.LANE, "LEFT")]

    _on_lane({"lane": "RIGHT", "timestamp": 123.5})
    assert commands.drain() == [(commands.LANE, "RIGHT")]

    _on_lane({"lane": "CENTER", "timestamp": 123.6})
    assert commands.drain() == [(commands.LANE, "CENTER")]


def test_on_action_pushes_command():
    commands.drain()
    _on_action({"action": "JUMP", "timestamp": 123.7})
    assert commands.drain() == [(commands.ACTION, "JUMP")]

    _on_action({"action": "CROUCH", "timestamp": 123.8})
    assert commands.drain() == [(commands.ACTION, "CROUCH")]


def test_register_subscribes_to_event_bus():
    bus = eb.EventBus()
    commands.drain()
    register(bus)

    # Publish lane changed event through EventBus
    bus.publish(eb.EVENT_LANE_CHANGED, eb.make_lane_event("LEFT", 100.0))
    assert commands.drain() == [(commands.LANE, "LEFT")]

    # Publish action event through EventBus
    bus.publish(eb.EVENT_ACTION, eb.make_action_event("JUMP", 100.1))
    assert commands.drain() == [(commands.ACTION, "JUMP")]

    bus.publish(eb.EVENT_ACTION, eb.make_action_event("CROUCH", 100.2))
    assert commands.drain() == [(commands.ACTION, "CROUCH")]


def test_full_pipeline_to_game_commands():
    """Simulate horizontal tracker and vertical detector publishing to EventBus and draining into game commands."""
    bus = eb.EventBus()
    commands.drain()
    register(bus)

    # Simulate horizontal event
    bus.publish(eb.EVENT_LANE_CHANGED, {"lane": "RIGHT", "timestamp": 200.0})
    # Simulate vertical jump event
    bus.publish(eb.EVENT_ACTION, {"action": "JUMP", "timestamp": 200.1})

    queue_items = commands.drain()
    assert (commands.LANE, "RIGHT") in queue_items
    assert (commands.ACTION, "JUMP") in queue_items
