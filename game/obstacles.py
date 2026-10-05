"""Obstacle + coin entities. Logical data comes from game.logic; this file only draws/moves it."""

from __future__ import annotations

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
POWERUPS = (POWERUP_JETPACK, POWERUP_MAGNET, POWERUP_SNEAKERS, POWERUP_MULTIPLIER, POWERUP_HOVERBOARD)


class PowerUpToken(Entity):
    """3D Subway Surfers Power-Up Item with authentic logo textures (Jetpack, Magnet, Super Sneakers, 2X Multiplier, Hoverboard)."""
    def __init__(self, kind: str, lane: int, cfg: dict, z: float, y: float = 1.2) -> None:
        x = logic.lane_to_x(lane, cfg["lane_width"])
        super().__init__(position=(x, y, z))
        self.kind = kind
        self.lane = lane

        tex_filename = f"powerup_{kind}.png"
        tex = tx.get_custom_texture(tex_filename)
        if tex:
            self.model_part = Entity(parent=self, model="quad", texture=tex, scale=(1.35, 1.35),
                                     double_sided=True, unlit=True)
            # Glowing backing disc for 3D depth
            Entity(parent=self.model_part, model="circle", color=color.hex("#ffe855aa"), scale=(1.2, 1.2), z=0.01)
        else:
            self.model_part = Entity(parent=self, model="cube", color=color.hex("#ffea00"), scale=(0.6, 0.6, 0.2))

        # Pulsing glowing ring around item
        self.ring = Entity(parent=self, model="circle", color=color.hex("#ffffffaa"), scale=(1.1, 1.1), rotation_x=90, y=-0.5)



class ObstacleManager:
    def __init__(self, cfg: dict, seed: int | None = None) -> None:
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.obstacles: list[ObstacleEntity] = []
        self.coins: list[Coin] = []
        self.powerups: list[PowerUpToken] = []
        self.until_next = 40.0           # first row comes after a short warm-up

    def clear(self) -> None:
        for e in self.obstacles + self.coins + self.powerups:
            destroy(e)
        self.obstacles.clear()
        self.coins.clear()
        self.powerups.clear()
        self.until_next = 40.0


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
            p.z -= speed * dt
            p.rotation_y += 180 * dt

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


