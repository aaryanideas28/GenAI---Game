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


class LightningToken(Entity):
    """Blue Lightning power-up token hovering above tracks."""
    def __init__(self, lane: int, x: float, y: float, z: float) -> None:
        super().__init__(model="sphere", color=color.hex("#1888ff"), scale=(0.6, 0.8, 0.2), position=(x, y, z))
        # Inner glowing bolt
        Entity(parent=self, model="quad", color=color.white, scale=(0.4, 0.6), z=-0.11)
        self.lane = lane


class ObstacleManager:
    def __init__(self, cfg: dict, seed: int | None = None) -> None:
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.obstacles: list[ObstacleEntity] = []
        self.coins: list[Coin] = []
        self.until_next = 40.0           # first row comes after a short warm-up

    def clear(self) -> None:
        for e in self.obstacles + self.coins:
            destroy(e)
        self.obstacles.clear()
        self.coins.clear()
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
                self.until_next = logic.next_gap(self.rng, speed, self.cfg)
