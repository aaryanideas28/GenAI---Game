"""Obstacle + coin entities. Logical data comes from game.logic; this file only draws/moves it."""

from __future__ import annotations

import math
import random

from ursina import Entity, color, destroy

from game import logic
from game import textures as tx

DESPAWN_Z = -20.0


from game import models3d as m3d


class ObstacleEntity(Entity):
    def __init__(self, spec: logic.ObstacleSpec, cfg: dict, rng: random.Random) -> None:
        lw = cfg["lane_width"]
        super().__init__(x=logic.lane_to_x(spec.lane, lw), z=spec.z_center)
        self.spec = spec
        width = lw * logic.OBSTACLE_HALF_WIDTH_FACTOR * 2
        if spec.kind == logic.KIND_TRAIN:
            if getattr(spec, "has_ramp", False):
                self._build_ramp_train(spec, cfg, rng, width)
            elif rng.random() < 0.55:
                self._build_silver_subway_train(spec, cfg, rng, width)
            else:
                self._build_container_train(spec, cfg, rng, width)
        elif spec.kind == logic.KIND_LOW:
            if rng.random() < 0.35:
                self._build_crossbuck_barrier(width)
            else:
                self._build_low_barrier(width)
        else:
            self._build_high_barrier(width)

    def _build_ramp_train(self, spec, cfg, rng, width) -> None:
        """Authentic red ramp train with frontal sloped ramp."""
        from pathlib import Path
        assets_dir = Path(__file__).resolve().parent / "assets"
        ramp_obj = assets_dir / "models" / "train_ramp.obj"
        trains_tex = tx.get_custom_texture("trains_texture.png")
        if ramp_obj.is_file() and trains_tex is not None:
            base_len = 6.53
            scale_z = spec.length / base_len
            Entity(parent=self, model="train_ramp.obj", texture=trains_tex,
                   scale=(1.0, 1.0, scale_z), y=0.0, rotation_y=180, unlit=True, double_sided=True)
            return

        import math
        h = logic.OBSTACLE_Y[logic.KIND_TRAIN][1] * 0.94
        L = spec.length
        ramp_len = max(2.5, L * 0.2)
        body_len = L - ramp_len
        c_tex = tx.to_ursina("container_side", tx.container_side())
        Entity(parent=self, model="cube", texture=c_tex, scale=(width, h, body_len),
               y=h / 2, z=ramp_len / 2)
        Entity(parent=self, model="cube", texture=c_tex, scale=(width, 0.25, ramp_len * 1.1),
               y=h / 2, z=-body_len / 2, rotation_x=-math.degrees(math.atan2(h, ramp_len)))

    def _build_silver_subway_train(self, spec, cfg, rng, width) -> None:
        """Authentic silver Subway Surfers train with 3D model and texture."""
        from pathlib import Path
        assets_dir = Path(__file__).resolve().parent / "assets"
        train_obj = assets_dir / "models" / "train_standard.obj"
        trains_tex = tx.get_custom_texture("trains_texture.png")
        if train_obj.is_file() and trains_tex is not None:
            scale_z = spec.length / 6.09
            Entity(parent=self, model="train_standard.obj", texture=trains_tex,
                   scale=(1.0, 1.0, scale_z), y=0.0, rotation_y=180, unlit=True, double_sided=True)
            return

        h = logic.OBSTACLE_Y[logic.KIND_TRAIN][1]
        L = spec.length
        Entity(parent=self, model="cube", color=color.hex("#c4cbd4"), scale=(width, h - 0.45, L), y=(h - 0.45) / 2 + 0.2)
        roof_mesh = m3d.make_curved_roof_mesh(width=width * 0.98, height=0.45, length=L)
        roof_tex = tx.to_ursina("roof", tx.train_roof())
        Entity(parent=self, model=roof_mesh, texture=roof_tex, color=color.hex("#d6dbe2"), y=h - 0.25)

    def _build_container_train(self, spec, cfg, rng, width) -> None:
        """Deep red shipping container train with 3D model and textures."""
        from pathlib import Path
        assets_dir = Path(__file__).resolve().parent / "assets"
        cargo_obj = assets_dir / "models" / "train_cargo.obj"
        trains_tex = tx.get_custom_texture("trains_texture.png")
        if cargo_obj.is_file() and trains_tex is not None:
            base_len = 5.79
            scale_z = spec.length / base_len
            Entity(parent=self, model="train_cargo.obj", texture=trains_tex,
                   scale=(1.0, 1.0, scale_z), y=0.0, rotation_y=180, unlit=True, double_sided=True)
            return

        h = logic.OBSTACLE_Y[logic.KIND_TRAIN][1] * 0.94
        L = spec.length
        c_tex = tx.to_ursina("container_side", tx.container_side())
        Entity(parent=self, model="cube", texture=c_tex, scale=(width, h, L), y=h / 2)

    def _build_crossbuck_barrier(self, width) -> None:
        """Railroad Crossing 'X' warning sign post (right in screenshot)."""
        post = color.hex("#f4f4f4")
        p = Entity(parent=self, model="cube", color=post, scale=(0.16, 2.2, 0.16), y=1.1)
        for y_stripe in (0.4, 0.8, 1.2, 1.6):
            Entity(parent=p, model="cube", color=color.hex("#111111"), scale=(1.05, 0.12, 1.05), y=y_stripe / 2.2 - 0.5)
        cb_tex = tx.to_ursina("crossbuck_sign", tx.crossbuck_sign())
        Entity(parent=self, model="quad", texture=cb_tex, scale=(1.4, 1.4), y=1.9, z=-0.1)

    def _build_low_barrier(self, width) -> None:
        from pathlib import Path
        assets_dir = Path(__file__).resolve().parent / "assets"
        b_name = "barrier_jump.obj"
        jump_obj = assets_dir / "models" / b_name
        main_tex = tx.get_custom_texture("main_texture.png")
        if jump_obj.is_file() and main_tex is not None:
            Entity(parent=self, model="barrier_jump.obj", texture=main_tex,
                   scale=1.0, y=0.0, unlit=True, double_sided=True)
            return

        tex = tx.to_ursina("barrier", tx.barrier())
        post = color.hex("#3a3a40")
        for sx in (-1, 1):
            Entity(parent=self, model="cube", color=post, scale=(0.14, 1.1, 0.14), x=sx * width * 0.45, y=0.55)
        Entity(parent=self, model="cube", texture=tex, scale=(width, 0.55, 0.12), y=0.75)

    def _build_high_barrier(self, width) -> None:
        from pathlib import Path
        assets_dir = Path(__file__).resolve().parent / "assets"
        roll_obj = assets_dir / "models" / "barrier_roll.obj"
        main_tex = tx.get_custom_texture("main_texture.png")
        if roll_obj.is_file() and main_tex is not None:
            Entity(parent=self, model="barrier_roll.obj", texture=main_tex,
                   scale=1.0, y=0.0, unlit=True, double_sided=True)
            return

        tex = tx.to_ursina("barrier", tx.barrier())
        post = color.hex("#3a3a40")
        top = logic.OBSTACLE_Y[logic.KIND_HIGH][1]
        for sx in (-1, 1):
            Entity(parent=self, model="cube", color=post, scale=(0.16, top, 0.16), x=sx * width * 0.47, y=top / 2)
        Entity(parent=self, model="cube", texture=tex, scale=(width, 0.9, 0.12), y=1.75)
        Entity(parent=self, model="cube", texture=tex, scale=(width, 0.5, 0.12), y=2.85)
        Entity(parent=self, model="cube", color=color.hex("#ffd400"), scale=(width * 0.98, 0.06, 0.14), y=1.28)


class Coin(Entity):
    """3D Gold Coin with embossed Star profile."""
    _star_mesh = None

    def __init__(self, spec: logic.CoinSpec, cfg: dict) -> None:
        if Coin._star_mesh is None:
            Coin._star_mesh = m3d.make_star_coin_mesh(radius=0.44, thickness=0.12)
        super().__init__(model=Coin._star_mesh, color=color.hex("#ffc814"),
                         scale=1.0, x=logic.lane_to_x(spec.lane, cfg["lane_width"]),
                         y=spec.y, z=spec.z)
        # Inner embossed golden shine
        Entity(parent=self, model="sphere", color=color.hex("#ffe855"), scale=(0.42, 0.42, 0.16))
        self.lane = spec.lane


POWERUP_JETPACK = "jetpack"
POWERUP_MAGNET = "magnet"
POWERUP_SNEAKERS = "sneakers"
POWERUP_MULTIPLIER = "multiplier"
POWERUP_HOVERBOARD = "hoverboard"
POWERUP_SHIELD = "shield"   # Headstart / Shield: smashes through obstacles safely
POWERUPS = (POWERUP_JETPACK, POWERUP_MAGNET, POWERUP_SNEAKERS, POWERUP_MULTIPLIER, POWERUP_HOVERBOARD, POWERUP_SHIELD)


def play_pickup_sound(kind: str) -> None:
    """Plays an authentic audio chime / cue for power-up collection if audio device is available."""
    try:
        from ursina import Audio
        # Audio cue trigger (safe fallback if asset file absent)
        Audio("powerup", autoplay=True, loop=False)
    except Exception:
        pass


class PickupVisualCue(Entity):
    """Floating 3D expanding burst cue when a power-up or special collectible is picked up."""
    def __init__(self, position, kind: str) -> None:
        super().__init__(position=position)
        self.age = 0.0
        self.lifetime = 0.65
        col_map = {
            "magnet": "#ffaa00",
            "jetpack": "#2ecc71",
            "sneakers": "#ff4081",
            "multiplier": "#ffd700",
            "hoverboard": "#00e5ff",
            "shield": "#00e5ff",
        }
        c = col_map.get(kind, "#ffffff")
        self.burst_ring = Entity(parent=self, model="circle", color=color.hex(c),
                                 scale=(0.9, 0.9), rotation_x=90)
        self.star_glow = Entity(parent=self, model="quad", color=color.white,
                                scale=(0.7, 0.7), double_sided=True)

    def tick(self, dt: float) -> bool:
        self.age += dt
        self.y += 2.4 * dt
        progress = min(1.0, self.age / self.lifetime)
        self.burst_ring.scale = (0.9 + progress * 2.2, 0.9 + progress * 2.2)
        alpha = max(0.0, 1.0 - progress)
        self.burst_ring.alpha = alpha
        self.star_glow.alpha = alpha
        self.star_glow.rotation_z += 360 * dt
        if self.age >= self.lifetime:
            destroy(self)
            return True
        return False


class PowerUpToken(Entity):
    """3D Subway Surfers Power-Up Collectible Item.
    Features authentic 3D geometry models:
      - Magnet Horseshoe (curved U-magnet with silver pole caps)
      - Jetpack Rocket Cylinder (dual booster cylinders with thrusters)
      - Super Sneaker Shoe (3D high-top sneaker with sole and collar)
      - 2X Star (embossed star profile token with halo)
      - Hoverboard Box (floating hover deck with repulsor pads)
      - Shield (energy buckler disc with glowing crest)
    Includes floating/bobbing oscillation and pulsing aura rings.
    """
    def __init__(self, kind: str, lane: int, cfg: dict, z: float, y: float = 1.25) -> None:
        x = logic.lane_to_x(lane, cfg["lane_width"])
        super().__init__(position=(x, y, z))
        self.kind = kind
        self.lane = lane
        self.base_y = y
        self.bob_timer = random.uniform(0.0, 6.28)

        # Build dedicated 3D geometry per collectible type
        self._build_3d_geometry(kind)

        # Pulsing glowing aura ring around base
        ring_col = "#00e5ffaa" if kind in ("shield", "hoverboard") else "#ffea00aa"
        self.ring = Entity(parent=self, model="circle", color=color.hex(ring_col),
                           scale=(1.15, 1.15), rotation_x=90, y=-0.55)

    def _build_3d_geometry(self, kind: str) -> None:
        tex_filename = f"powerup_{kind}.png"
        tex = tx.get_custom_texture(tex_filename)

        if kind == POWERUP_MAGNET:
            # 1. Magnet Horseshoe: 3D U-shaped magnet with silver pole tips
            red_col = color.hex("#e61919")
            silver_col = color.hex("#e0e0e0")
            # Left & right vertical arms
            Entity(parent=self, model="cube", color=red_col, scale=(0.14, 0.65, 0.14), x=-0.28, y=0.0)
            Entity(parent=self, model="cube", color=red_col, scale=(0.14, 0.65, 0.14), x=0.28, y=0.0)
            # Top curved bridge arch
            Entity(parent=self, model="cube", color=red_col, scale=(0.70, 0.16, 0.14), y=0.32)
            # Silver pole caps (North and South poles)
            Entity(parent=self, model="cube", color=silver_col, scale=(0.16, 0.22, 0.16), x=-0.28, y=-0.36)
            Entity(parent=self, model="cube", color=silver_col, scale=(0.16, 0.22, 0.16), x=0.28, y=-0.36)

        elif kind == POWERUP_JETPACK:
            # 2. Jetpack Rocket Cylinder: twin booster cylinders with thruster nozzles
            can_col = color.hex("#2ecc71")
            metal_col = color.hex("#4a5568")
            flame_col = color.hex("#f39c12")
            # Dual cylinders
            Entity(parent=self, model="cylinder", color=can_col, scale=(0.20, 0.70, 0.20), x=-0.22)
            Entity(parent=self, model="cylinder", color=can_col, scale=(0.20, 0.70, 0.20), x=0.22)
            # Top caps / nose domes
            Entity(parent=self, model="sphere", color=metal_col, scale=(0.22, 0.25, 0.22), x=-0.22, y=0.45)
            Entity(parent=self, model="sphere", color=metal_col, scale=(0.22, 0.25, 0.22), x=0.22, y=0.45)
            # Bottom exhaust thrusters
            Entity(parent=self, model="cylinder", color=flame_col, scale=(0.18, 0.20, 0.18), x=-0.22, y=-0.44)
            Entity(parent=self, model="cylinder", color=flame_col, scale=(0.18, 0.20, 0.18), x=0.22, y=-0.44)
            # Center mounting frame
            Entity(parent=self, model="cube", color=metal_col, scale=(0.30, 0.35, 0.08), y=0.0)

        elif kind == POWERUP_SNEAKERS:
            # 3. Super Sneaker Shoe: 3D high-top sneaker with rubber sole and collar
            sole_col = color.white
            shoe_col = color.hex("#ff3388")
            collar_col = color.hex("#ff1493")
            # White rubber sole platform
            Entity(parent=self, model="cube", color=sole_col, scale=(0.36, 0.12, 0.82), y=-0.38)
            # Shoe main body
            Entity(parent=self, model="cube", color=shoe_col, scale=(0.34, 0.32, 0.76), y=-0.18, z=-0.02)
            # High-top ankle collar
            Entity(parent=self, model="cube", color=collar_col, scale=(0.34, 0.44, 0.38), y=0.16, z=-0.16)
            # Front white toe bumper
            Entity(parent=self, model="cube", color=sole_col, scale=(0.34, 0.16, 0.20), y=-0.24, z=0.30)

        elif kind == POWERUP_MULTIPLIER:
            # 4. 2X Star: 3D 5-point star token with golden halo
            star_mesh = m3d.make_star_2x_mesh(radius=0.48, thickness=0.16)
            Entity(parent=self, model=star_mesh, color=color.hex("#ffd700"), scale=1.0)
            # Central bold red accent disc
            Entity(parent=self, model="circle", color=color.hex("#ff1744"), scale=(0.42, 0.42), z=0.09)
            Entity(parent=self, model="circle", color=color.hex("#ff1744"), scale=(0.42, 0.42), z=-0.09)

        elif kind == POWERUP_HOVERBOARD:
            # 5. Hoverboard Box / Deck: futuristic tech deck with neon repulsor glow
            deck_col = color.hex("#00c3ff")
            neon_col = color.hex("#18ffff")
            # Aerodynamic hover deck
            Entity(parent=self, model="cube", color=deck_col, scale=(0.42, 0.10, 0.95), y=-0.10)
            # Top grip tape strip
            Entity(parent=self, model="cube", color=color.hex("#111827"), scale=(0.36, 0.04, 0.85), y=-0.04)
            # Neon side edge light rails
            Entity(parent=self, model="cube", color=neon_col, scale=(0.44, 0.08, 0.96), y=-0.10)
            # Under-deck repulsor discs
            Entity(parent=self, model="cylinder", color=neon_col, scale=(0.28, 0.08, 0.28), y=-0.24, z=-0.25)
            Entity(parent=self, model="cylinder", color=neon_col, scale=(0.28, 0.08, 0.28), y=-0.24, z=0.25)

        else:  # POWERUP_SHIELD
            # 6. Shield: translucent cyan buckler aegis with protective boss
            aegis_col = color.hex("#00e5ff")
            Entity(parent=self, model="circle", color=aegis_col, scale=(0.88, 0.88), double_sided=True)
            Entity(parent=self, model="sphere", color=color.hex("#ffffff"), scale=(0.38, 0.38, 0.18))
            Entity(parent=self, model="cube", color=color.hex("#ffffff"), scale=(0.58, 0.12, 0.08))
            Entity(parent=self, model="cube", color=color.hex("#ffffff"), scale=(0.12, 0.58, 0.08))

        # Overlay authentic logo texture disc if available for high-fidelity presentation
        if tex:
            badge = Entity(parent=self, model="quad", texture=tex, scale=(1.25, 1.25),
                           double_sided=True, unlit=True)
            Entity(parent=badge, model="circle", color=color.hex("#ffffff88"), scale=(1.15, 1.15), z=0.01)

    def tick(self, dt: float, speed: float) -> None:
        """Updates token position, rotating, bobbing, and pulsing."""
        self.z -= speed * dt
        self.rotation_y += 180 * dt
        self.bob_timer += dt * 3.6
        self.y = self.base_y + math.sin(self.bob_timer) * 0.15
        pulse = 1.15 + math.sin(self.bob_timer * 2.2) * 0.12
        self.ring.scale = (pulse, pulse)


class ObstacleManager:
    def __init__(self, cfg: dict, seed: int | None = None) -> None:
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.obstacles: list[ObstacleEntity] = []
        self.coins: list[Coin] = []
        self.powerups: list[PowerUpToken] = []
        self.cues: list[PickupVisualCue] = []
        self.until_next = 40.0           # first row comes after a short warm-up

    def clear(self) -> None:
        for e in self.obstacles + self.coins + self.powerups + self.cues:
            destroy(e)
        self.obstacles.clear()
        self.coins.clear()
        self.powerups.clear()
        self.cues.clear()
        self.until_next = 40.0

    def spawn_pickup_cue(self, position, kind: str) -> None:
        """Spawns an expanding 3D visual cue and audio feedback upon token pickup."""
        cue = PickupVisualCue(position=position, kind=kind)
        self.cues.append(cue)
        play_pickup_sound(kind)

    def live_specs(self) -> list[logic.ObstacleSpec]:
        return [o.spec for o in self.obstacles]

    def tick(self, dt: float, speed: float, spawn_z: float = 150.0, world: Any = None) -> None:
        extra = self.cfg["moving_train_extra_speed"]
        for o in self.obstacles:
            dz = (speed + (extra if o.spec.moving else 0.0)) * dt
            o.spec.z_start -= dz
            o.z = o.spec.z_center
        for c in self.coins:
            c.z -= speed * dt
            c.rotation_y += 220 * dt
        for p in self.powerups:
            p.tick(dt, speed)

        # Tick active visual pickup cues
        for cue in list(self.cues):
            if cue.tick(dt):
                self.cues.remove(cue)

        # Prevent any moving obstacles from intruding into the tunnel clearance zone
        if world and hasattr(world, "tunnels"):
            for tun in world.tunnels:
                for o in list(self.obstacles):
                    if abs(o.spec.z_center - tun.z) < 28.0:
                        self.obstacles.remove(o)
                        destroy(o)

        for o in [o for o in self.obstacles if o.spec.z_end < DESPAWN_Z]:
            self.obstacles.remove(o)
            destroy(o)
        for c in [c for c in self.coins if c.z < DESPAWN_Z]:
            self.coins.remove(c)
            destroy(c)
        for p in [p for p in self.powerups if p.z < DESPAWN_Z]:
            self.powerups.remove(p)
            destroy(p)

        self.until_next -= speed * dt
        if self.until_next <= 0:
            # Check if any tunnel portal is near the obstacle spawn location
            tunnel_near = False
            near_tun = None
            if world and hasattr(world, "tunnels"):
                for tun in world.tunnels:
                    if abs(spawn_z - tun.z) < 42.0:
                        tunnel_near = True
                        near_tun = tun
                        break

            if tunnel_near and near_tun is not None:
                # Do not spawn any trains or barriers near tunnel entrance!
                # Instead, spawn guidance coins directly in the open tunnel lane
                open_lane = getattr(near_tun, "tunnel_lane", 0)
                for offset in (-4.0, 0.0, 4.0):
                    cs = logic.CoinSpec(open_lane, spawn_z + offset, 0.7)
                    self.coins.append(Coin(cs, self.cfg))
                self.until_next = 12.0
            else:
                row = logic.generate_row(self.rng, spawn_z, self.live_specs(), self.cfg)
                valid_obstacles = []
                for spec in row.obstacles:
                    too_close_to_tunnel = False
                    if world and hasattr(world, "tunnels"):
                        for tun in world.tunnels:
                            if abs(spec.z_center - tun.z) < 36.0:
                                too_close_to_tunnel = True
                                break
                    if not too_close_to_tunnel:
                        valid_obstacles.append(spec)

                for spec in valid_obstacles:
                    self.obstacles.append(ObstacleEntity(spec, self.cfg, self.rng))

                occupied = self.live_specs()
                for cs in row.coins:
                    # never put a coin inside a train
                    if any(s.kind == logic.KIND_TRAIN and s.lane == cs.lane and s.z_start - 1 < cs.z < s.z_end + 1
                           for s in occupied):
                        continue
                    self.coins.append(Coin(cs, self.cfg))

                # 20% chance to spawn a power-up token on a free lane
                if self.rng.random() < 0.20:
                    occ_lanes = {o.lane for o in valid_obstacles}
                    free_lanes = [l for l in (-1, 0, 1) if l not in occ_lanes]
                    if free_lanes:
                        p_lane = self.rng.choice(free_lanes)
                        p_kind = self.rng.choice(POWERUPS)
                        self.powerups.append(PowerUpToken(p_kind, p_lane, self.cfg, z=spawn_z + 2.0))

                self.until_next = logic.next_gap(self.rng, speed, self.cfg)

    def spawn_sky_coins(self, start_z: float = 20.0, count: int = 16) -> None:
        """Spawns a streak of sky coins for Jetpack mode."""
        for i in range(count):
            lane = (-1, 0, 1)[(i // 4) % 3]
            cs = logic.CoinSpec(lane, start_z + i * 3.5, 5.8)
            self.coins.append(Coin(cs, self.cfg))


    def clear_lane(self, lane: int) -> None:
        """Removes/destroys all obstacles in a specific lane (e.g. for Shockwave Roll)."""
        to_remove = [o for o in self.obstacles if o.spec.lane == lane]
        for o in to_remove:
            self.obstacles.remove(o)
            destroy(o)

    def reverse_trains(self) -> None:
        """Reverses the motion direction or moves train positions back (e.g. for Train Reversal)."""
        for o in self.obstacles:
            if o.spec.kind == logic.KIND_TRAIN:
                o.spec.z_start += 15.0
                o.z = o.spec.z_center

    def attract_coins(self, player_x: float, player_z: float, range_dist: float = 8.0) -> None:
        """Coin Magnet powerup: pulls coins towards player."""
        lw = self.cfg["lane_width"]
        for c in self.coins:
            dx = player_x - c.x
            dz = player_z - c.z
            dist = (dx * dx + dz * dz) ** 0.5
            if dist < range_dist and dist > 0.1:
                c.x += (dx / dist) * 12.0 * 0.05
                c.z += (dz / dist) * 12.0 * 0.05

    def spawn_zigzag_coins(self, spawn_z: float) -> None:
        """Spawns coins in an alternating zigzag pattern across lanes."""
        lanes = [-1, 0, 1, 0, -1, 0, 1]
        for i, lane in enumerate(lanes):
            cs = logic.CoinSpec(lane, spawn_z + i * 3.0, 1.0)
            self.coins.append(Coin(cs, self.cfg))

    def clear_all_obstacles(self) -> None:
        """Destroys all active obstacles on screen."""
        for o in list(self.obstacles):
            self.obstacles.remove(o)
            destroy(o)

    def spawn_coins_cluster(self, lane: int = 0, count: int = 10, start_z: float = 30.0) -> None:
        """Spawns a cluster of coins in a target lane."""
        for i in range(count):
            cs = logic.CoinSpec(lane, start_z + i * 2.5, 1.0)
            self.coins.append(Coin(cs, self.cfg))


