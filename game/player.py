"""The player: an original blocky runner character + movement physics."""

from __future__ import annotations

import math

from ursina import Color, Entity, color, lerp

from game import logic


def _c(hex_str: str) -> Color:
    return color.hex(hex_str)


class Player(Entity):
    """Root entity at the player's feet. Body parts are children so they can animate."""

    def __init__(self, cfg: dict) -> None:
        super().__init__(position=(0, 0, 0))
        self.cfg = cfg
        self.lane = 0
        self.vy = 0.0
        self.grounded = True
        self.roll_timer = 0.0
        self.anim_t = 0.0
        self.alive = True

        self.model_root = Entity(parent=self)
        self._build_body()
        self.shadow = Entity(model="circle", color=Color(0, 0, 0, 0.35), rotation_x=90,
                             scale=(1.0, 0.7), y=0.02)

    # --- construction --------------------------------------------------------
    def _part(self, parent, scale, pos, col, model="cube") -> Entity:
        return Entity(parent=parent, model=model, scale=scale, position=pos, color=col)

    def _build_body(self) -> None:
        from pathlib import Path
        r = self.model_root
        self.parts = {}

        from game import textures as tx
        assets_dir = Path(__file__).resolve().parent / "assets"
        torso_obj = assets_dir / "models" / "jake_torso.obj"
        leg_l_obj = assets_dir / "models" / "jake_leg_l.obj"
        leg_r_obj = assets_dir / "models" / "jake_leg_r.obj"
        jake_tex_img = tx.get_custom_texture("jake_texture.png")

        if torso_obj.is_file() and leg_l_obj.is_file() and leg_r_obj.is_file() and jake_tex_img is not None:
            self.jake_mesh = Entity(parent=r, rotation_y=180)
            self.torso = Entity(parent=self.jake_mesh, model="jake_torso.obj", texture=jake_tex_img,
                                unlit=True, double_sided=True)
            self.leg_l = Entity(parent=self.jake_mesh, model="jake_leg_l.obj", texture=jake_tex_img,
                                position=(-0.15, 0.83, 0), unlit=True, double_sided=True)
            self.leg_r = Entity(parent=self.jake_mesh, model="jake_leg_r.obj", texture=jake_tex_img,
                                position=(0.15, 0.83, 0), unlit=True, double_sided=True)
            return

        jake_obj = assets_dir / "models" / "jake.obj"
        if jake_obj.is_file() and jake_tex_img is not None:
            self.jake_mesh = Entity(parent=r, model="jake.obj", texture=jake_tex_img,
                                    scale=1.02, y=0.0, rotation_y=180, unlit=True, double_sided=True)
            return

        self.jake_mesh = None
        p = self.cfg["player"]

        # legs pivot at the hips so they can swing
        self.leg_l = Entity(parent=r, position=(-0.17, 0.85, 0))
        self.leg_r = Entity(parent=r, position=(0.17, 0.85, 0))
        for leg in (self.leg_l, self.leg_r):
            self._part(leg, (0.26, 0.7, 0.28), (0, -0.38, 0), _c(p["pants"]))
            self._part(leg, (0.3, 0.16, 0.42), (0, -0.78, 0.06), _c(p["shoes"]))

        self.torso = self._part(r, (0.66, 0.7, 0.4), (0, 1.2, 0), _c(p["hoodie"]))
        self._part(self.torso, (1.02, 0.12, 1.02), (0, -0.45, 0), color.hex("#f4f4f4"))     # hem stripe
        self.backpack = self._part(r, (0.5, 0.55, 0.22), (0, 1.22, -0.3), _c(p["backpack"]))

        self.arm_l = Entity(parent=r, position=(-0.43, 1.5, 0))
        self.arm_r = Entity(parent=r, position=(0.43, 1.5, 0))
        for arm in (self.arm_l, self.arm_r):
            self._part(arm, (0.2, 0.62, 0.24), (0, -0.28, 0), _c(p["hoodie"]))
            self._part(arm, (0.18, 0.14, 0.2), (0, -0.64, 0), _c(p["skin"]))

        self.head = self._part(r, (0.48, 0.46, 0.44), (0, 1.8, 0), _c(p["skin"]))
        self.beanie = self._part(r, (0.52, 0.2, 0.48), (0, 2.05, 0), _c(p["cap"]))
        from game.asset_loader import custom_assets
        from game import textures as tx

        denim_img = custom_assets.get_jake_denim()
        if denim_img:
            self.torso.texture = tx.to_ursina("jake_denim", denim_img)

        tag_img = custom_assets.get_jake_tag()
        if tag_img:
            tag_tex = tx.to_ursina("jake_tag", tag_img)
            Entity(parent=self.backpack, model="quad", texture=tag_tex, scale=(0.88, 0.88), z=-0.52, rotation_y=180)

        face_img = custom_assets.get_jake_face()
        if face_img:
            face_tex = tx.to_ursina("jake_face", face_img)
            Entity(parent=self.head, model="quad", texture=face_tex, scale=(0.88, 0.88), z=0.52)
        else:
            self._part(r, (0.07, 0.07, 0.02), (-0.11, 1.84, 0.225), color.hex("#222222"))       # eyes
            self._part(r, (0.07, 0.07, 0.02), (0.11, 1.84, 0.225), color.hex("#222222"))

    def apply_colors(self, cfg: dict) -> None:
        """Rebuild body with new colours (used by config hot-reload)."""
        from ursina import destroy
        self.cfg = cfg
        destroy(self.model_root)
        self.model_root = Entity(parent=self)
        self._build_body()

    # --- state ---------------------------------------------------------------
    @property
    def rolling(self) -> bool:
        return self.roll_timer > 0

    @property
    def bottom(self) -> float:
        return self.y

    @property
    def top(self) -> float:
        return self.y + (logic.PLAYER_ROLL_HEIGHT if self.rolling else logic.PLAYER_STAND_HEIGHT)

    def reset(self) -> None:
        self.lane = 0
        self.position = (0, 0, 0)
        self.vy = 0.0
        self.grounded = True
        self.roll_timer = 0.0
        self.alive = True
        self.model_root.rotation = (0, 0, 0)
        self.model_root.scale = 1
        if getattr(self, "jake_mesh", None) is not None:
            self.jake_mesh.rotation = (0, 180, 0)
            if hasattr(self, "leg_l") and hasattr(self, "leg_r"):
                self.leg_l.rotation = (0, 0, 0)
                self.leg_r.rotation = (0, 0, 0)

    # --- commands ------------------------------------------------------------
    def move(self, direction: int) -> None:
        self.lane = logic.clamp_lane(self.lane + direction)

    def set_lane(self, lane: int) -> None:
        self.lane = logic.clamp_lane(lane)

    def jump(self) -> None:
        if self.grounded:
            self.vy = self.cfg["jump_velocity"]
            self.grounded = False
            self.roll_timer = 0.0

    def roll(self) -> None:
        self.roll_timer = self.cfg["roll_duration"]
        if not self.grounded:
            self.vy = min(self.vy, -self.cfg["jump_velocity"] * 1.2)    # slam down

    # --- per-frame -----------------------------------------------------------
    def tick(self, dt: float, speed: float, support_y: float = 0.0) -> None:
        target_x = logic.lane_to_x(self.lane, self.cfg["lane_width"])
        step = self.cfg["lane_switch_speed"] * dt
        dx = target_x - self.x
        self.x += max(-step, min(step, dx))

        target_ground = support_y
        if self.grounded:
            if target_ground > self.y:
                # Ascending ramp
                self.y = target_ground
            elif target_ground < self.y:
                # Walked/ran off train roof or ramp
                self.grounded = False
            else:
                self.y = target_ground
        else:
            self.vy -= self.cfg["gravity"] * dt
            self.y += self.vy * dt
            if self.y <= target_ground:
                self.y = target_ground
                self.vy = 0.0
                self.grounded = True

        if self.roll_timer > 0:
            self.roll_timer = max(0.0, self.roll_timer - dt)

        self._animate(dt, speed, dx)
        self.shadow.x = self.x
        self.shadow.y = target_ground + 0.02
        self.shadow.scale = (1.0 - min(self.y - target_ground, 3) * 0.15,
                             0.7 - min(self.y - target_ground, 3) * 0.1)

    def _animate(self, dt: float, speed: float, dx: float) -> None:
        self.anim_t += dt * (6 + speed * 0.35)
        s = math.sin(self.anim_t)
        root = self.model_root

        if getattr(self, "jake_mesh", None) is not None:
            root.rotation_z = lerp(root.rotation_z, -dx * 10, min(1, dt * 10))
            if self.rolling:
                root.scale_y = lerp(root.scale_y, 0.52, min(1, dt * 20))
                root.rotation_x = (root.rotation_x + dt * 720) % 360
                root.y = 0.38
                if hasattr(self, "leg_l") and hasattr(self, "leg_r"):
                    self.leg_l.rotation_x = -50.0
                    self.leg_r.rotation_x = -50.0
            else:
                root.scale_y = lerp(root.scale_y, 1.0, min(1, dt * 20))
                root.rotation_x = 0
                if self.grounded:
                    # Running step bounce
                    root.y = abs(s) * 0.10
                    # Articulated leg swing
                    if hasattr(self, "leg_l") and hasattr(self, "leg_r"):
                        swing = 38.0 * s
                        self.leg_l.rotation_x = swing
                        self.leg_r.rotation_x = -swing
                    # Athletic forward sprint lean & subtle hip sway
                    forward_lean = 10.0 + min(6.0, (speed / 34.0) * 5.0)
                    self.jake_mesh.rotation_x = forward_lean
                    self.jake_mesh.rotation_y = 180 + s * 4.0
                    self.jake_mesh.rotation_z = s * 2.0
                else:
                    # In-air parkour jump pose: tucked knees, forward leap
                    root.y = 0.0
                    self.jake_mesh.rotation_x = 18.0
                    self.jake_mesh.rotation_y = 180
                    self.jake_mesh.rotation_z = 0
                    if hasattr(self, "leg_l") and hasattr(self, "leg_r"):
                        self.leg_l.rotation_x = -32.0
                        self.leg_r.rotation_x = -16.0
            return

        if self.rolling:
            root.scale_y = lerp(root.scale_y, 0.5, min(1, dt * 20))
            root.rotation_x = (root.rotation_x + dt * 900) % 360
            root.y = 0.45
        else:
            root.scale_y = lerp(root.scale_y, 1.0, min(1, dt * 20))
            root.rotation_x = 0
            root.y = 0
        swing = 0 if not self.grounded else 45 * s
        self.leg_l.rotation_x = swing if self.grounded else -30
        self.leg_r.rotation_x = -swing if self.grounded else 20
        self.arm_l.rotation_x = -swing * 0.9 if self.grounded else -150
        self.arm_r.rotation_x = swing * 0.9 if self.grounded else -150
        root.rotation_z = lerp(root.rotation_z, -dx * 8, min(1, dt * 10))   # lean into lane change
        if self.grounded and not self.rolling:
            root.y = abs(s) * 0.08
