"""
PURE GAME LOGIC (no Ursina import) - Teammate 4
===============================================

Everything here is plain Python so it can be unit-tested without opening a window:
  * lane helpers
  * obstacle dimensions + AABB collision
  * fair obstacle-row generation (there is ALWAYS an escape lane)

World axes (same as Ursina):  x = left/right,  y = up,  z = forward (away from camera).
The player stays at z = 0; the world scrolls towards -z.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# --- Lanes -------------------------------------------------------------------
LANES: tuple[int, ...] = (-1, 0, 1)
LANE_BY_NAME: dict[str, int] = {"LEFT": -1, "CENTER": 0, "RIGHT": 1}

# --- Obstacle kinds ----------------------------------------------------------
KIND_LOW = "low_barrier"     # JUMP over it
KIND_HIGH = "high_barrier"   # ROLL under it
KIND_TRAIN = "train"         # change LANE

# (y_bottom, y_top) of the solid part of every obstacle kind
OBSTACLE_Y: dict[str, tuple[float, float]] = {
    KIND_LOW: (0.0, 1.1),
    KIND_HIGH: (1.25, 3.2),
    KIND_TRAIN: (0.0, 3.4),
}
BARRIER_LENGTH = 0.6
TRAIN_MIN_LENGTH = 10.0
TRAIN_MAX_LENGTH = 22.0

# --- Player body -------------------------------------------------------------
PLAYER_HALF_WIDTH = 0.4
PLAYER_HALF_DEPTH = 0.35
PLAYER_STAND_HEIGHT = 1.9
PLAYER_ROLL_HEIGHT = 1.0
OBSTACLE_HALF_WIDTH_FACTOR = 0.42   # obstacle half width = lane_width * factor


def clamp_lane(lane: int) -> int:
    return max(-1, min(1, lane))


def lane_to_x(lane: int, lane_width: float) -> float:
    return lane * lane_width


@dataclass
class ObstacleSpec:
    """Logical obstacle. z_start = edge nearest the player, z_end = far edge."""
    kind: str
    lane: int
    z_start: float
    length: float
    moving: bool = False
    has_ramp: bool = False

    @property
    def z_end(self) -> float:
        return self.z_start + self.length

    @property
    def z_center(self) -> float:
        return self.z_start + self.length / 2


@dataclass
class CoinSpec:
    lane: int
    z: float
    y: float


@dataclass
class RowResult:
    obstacles: list[ObstacleSpec] = field(default_factory=list)
    coins: list[CoinSpec] = field(default_factory=list)


# --- Collision ---------------------------------------------------------------
def overlaps(player_x: float, player_bottom: float, player_top: float,
             obs: ObstacleSpec, lane_width: float) -> bool:
    """Axis-aligned box test between the player (at z = 0) and an obstacle."""
    obs_x = lane_to_x(obs.lane, lane_width)
    if abs(player_x - obs_x) >= PLAYER_HALF_WIDTH + lane_width * OBSTACLE_HALF_WIDTH_FACTOR:
        return False
    if obs.z_start >= PLAYER_HALF_DEPTH or obs.z_end <= -PLAYER_HALF_DEPTH:
        return False

    if obs.kind == KIND_TRAIN:
        # If player is on or landing on the train roof (bottom >= 2.4), no crash
        if player_bottom >= 2.4:
            return False
        # If train has a frontal ramp and player is at the ramp section, no crash
        if getattr(obs, "has_ramp", False):
            ramp_len = max(2.0, obs.length * 0.17)
            if obs.z_start <= PLAYER_HALF_DEPTH and obs.z_start >= -ramp_len:
                return False

    y_bottom, y_top = OBSTACLE_Y[obs.kind]
    return player_bottom < y_top and player_top > y_bottom


def get_surface_y(player_x: float, player_y: float, lane_width: float,
                  obstacles: list[ObstacleSpec]) -> float:
    """Returns the ground/roof surface Y directly beneath the player at z = 0."""
    surf_y = 0.0
    for obs in obstacles:
        if obs.kind != KIND_TRAIN:
            continue
        obs_x = lane_to_x(obs.lane, lane_width)
        if abs(player_x - obs_x) >= PLAYER_HALF_WIDTH + lane_width * OBSTACLE_HALF_WIDTH_FACTOR:
            continue
        if obs.z_start <= PLAYER_HALF_DEPTH and obs.z_end >= -PLAYER_HALF_DEPTH:
            if getattr(obs, "has_ramp", False):
                ramp_len = max(2.0, obs.length * 0.17)
                dist = 0.0 - obs.z_start
                if dist < ramp_len:
                    ramp_h = max(0.0, min(2.80, (dist / ramp_len) * 2.80))
                    surf_y = max(surf_y, ramp_h)
                else:
                    surf_y = max(surf_y, 2.80)
            elif player_y >= 2.0:
                surf_y = max(surf_y, 2.80)
    return surf_y


def is_side_hit(obs: ObstacleSpec) -> bool:
    """True when we touched an obstacle whose front has already passed us,
    i.e. we steered into its side -> stumble back instead of crashing."""
    return obs.z_start < -PLAYER_HALF_DEPTH * 0.5


# --- Fair row generation -----------------------------------------------------
def _trains_overlap(a: ObstacleSpec, b: ObstacleSpec, margin: float = 4.0) -> bool:
    return a.z_start < b.z_end + margin and b.z_start < a.z_end + margin


def busy_lanes(live: list[ObstacleSpec], spawn_z: float, margin: float = 6.0) -> set[int]:
    """Lanes where a (static) train still reaches into the new row's area."""
    return {o.lane for o in live if o.kind == KIND_TRAIN and o.z_end > spawn_z - margin}


def can_add_moving_train(lane: int, live: list[ObstacleSpec], spawn_z: float) -> bool:
    """A moving train overtakes everything in front of it, so only allow it when
    (a) its own lane is empty up to spawn_z, and
    (b) the other two lanes never contain trains overlapping each other in z
        (otherwise all 3 lanes could be blocked at the same instant)."""
    if any(o.lane == lane and o.z_start < spawn_z + TRAIN_MAX_LENGTH for o in live):
        return False
    others = [o for o in live if o.kind == KIND_TRAIN and o.lane != lane]
    for i, a in enumerate(others):
        for b in others[i + 1:]:
            if a.lane != b.lane and _trains_overlap(a, b):
                return False
    if any(o.moving for o in live):     # at most one moving train at a time
        return False
    return True


def generate_row(rng: random.Random, spawn_z: float, live: list[ObstacleSpec],
                 cfg: dict) -> RowResult:
    """Create one row of obstacles + coins at ``spawn_z``.

    Guarantee: at least one lane contains no obstacle at all at this row, and
    the row never closes the last free lane left by long trains from earlier rows.
    """
    result = RowResult()
    busy = busy_lanes(live, spawn_z)
    available = [lane for lane in LANES if lane not in busy]
    if len(available) <= 1:
        free_lanes = available            # leave the only escape lane empty
    else:
        max_block = len(available) - 1    # always keep >= 1 lane free
        n_block = rng.choice([1, 1, 2]) if max_block >= 2 else 1
        blocked = rng.sample(available, n_block)
        free_lanes = [lane for lane in available if lane not in blocked]

        for lane in blocked:
            kind = rng.choices([KIND_TRAIN, KIND_LOW, KIND_HIGH], weights=[0.45, 0.3, 0.25])[0]
            if kind == KIND_TRAIN:
                length = rng.uniform(TRAIN_MIN_LENGTH, TRAIN_MAX_LENGTH)
                moving = (rng.random() < cfg.get("moving_train_chance", 0.0)
                          and can_add_moving_train(lane, live + result.obstacles, spawn_z))
                has_ramp = False if moving else (rng.random() < 0.45)
                spec = ObstacleSpec(KIND_TRAIN, lane, spawn_z, length, moving, has_ramp)
                result.obstacles.append(spec)
                if has_ramp and rng.random() < 0.8:
                    for step in range(5):
                        cz = spawn_z + step * 2.2
                        cy = min(3.8, 1.0 + step * 0.55)
                        result.coins.append(CoinSpec(lane, cz, cy))
            else:
                result.obstacles.append(ObstacleSpec(kind, lane, spawn_z, BARRIER_LENGTH))

    # coins: a straight line in one free lane, or an arc over a low barrier
    if rng.random() < cfg.get("coin_chance", 0.6):
        lows = [o for o in result.obstacles if o.kind == KIND_LOW]
        if lows and rng.random() < 0.4:
            o = rng.choice(lows)
            for i in range(-3, 4):
                z = o.z_start + i * 1.6
                y = 1.0 + 1.7 * (1 - (i / 3.5) ** 2)
                result.coins.append(CoinSpec(o.lane, z, y))
        elif free_lanes and not any(getattr(o, "has_ramp", False) for o in result.obstacles):
            lane = rng.choice(free_lanes)
            for i in range(6):
                result.coins.append(CoinSpec(lane, spawn_z - 6 + i * 2.2, 1.0))
    return result


def next_gap(rng: random.Random, speed: float, cfg: dict) -> float:
    """Distance until the next row; grows a little with speed so reaction time stays fair."""
    base = rng.uniform(cfg.get("spawn_gap_min", 16.0), cfg.get("spawn_gap_max", 26.0))
    start = max(1.0, cfg.get("start_speed", 15.0))
    return base * max(1.0, (speed / start) ** 0.5)
