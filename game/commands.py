"""Thread-safe command inbox for the game.

Anything (keyboard, gesture pipeline, tests) can push commands from any thread;
the game drains the queue once per frame on the Ursina main thread.

    push_lane("LEFT")      # absolute lane: LEFT / CENTER / RIGHT  (Teammate 2 format)
    push_action("JUMP")    # JUMP / CROUCH                         (Teammate 3 format)
"""

from __future__ import annotations

import queue

LANE = "lane"
ACTION = "action"

_inbox: "queue.Queue[tuple[str, str]]" = queue.Queue()


def push_lane(lane: str) -> None:
    _inbox.put((LANE, lane.upper()))


def push_action(action: str) -> None:
    _inbox.put((ACTION, action.upper()))


def drain() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    while True:
        try:
            items.append(_inbox.get_nowait())
        except queue.Empty:
            return items
