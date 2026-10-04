"""The Inspector: iconic Subway Surfers pursuer chasing Jake."""

from __future__ import annotations

import math
from pathlib import Path
from ursina import Entity, lerp


class Inspector(Entity):
    def __init__(self, target: Entity) -> None:
        super().__init__(position=(-0.4, 0, -2.5))
        self.target = target
        self.target_dist = 2.5
        self.anim_t = 0.0
        self.alert_timer = 0.0

        from game import textures as tx
        assets_dir = Path(__file__).resolve().parent / "assets"
        model_path = assets_dir / "models" / "inspector.obj"
        enemies_img = tx.get_custom_texture("enemies_texture.png")
        if model_path.is_file() and enemies_img is not None:
            self.mesh = Entity(parent=self, model="inspector.obj", texture=enemies_img,
                               scale=0.88, y=0.0, rotation_y=90, unlit=True, double_sided=True)
        else:
            self.mesh = None

    def reset(self) -> None:
        self.target_dist = 2.5
        self.alert_timer = 0.0
        self.z = -2.5
        self.x = -0.4
        self.y = 0.0

    def alert(self, duration: float = 2.5) -> None:
        """Called when Jake stumbles or hits a train side - Inspector surges close."""
        self.alert_timer = duration
        self.target_dist = 2.0

    def catch(self) -> None:
        """Called on game over - Inspector runs right up to Jake."""
        self.target_dist = -0.6

    def tick(self, dt: float, speed: float, playing: bool) -> None:
        if playing:
            if self.alert_timer > 0:
                self.alert_timer -= dt
                self.target_dist = 1.3
            else:
                # Slowly fall behind Jake as Jake runs at full speed
                self.target_dist = lerp(self.target_dist, 5.2, min(1, dt * 0.4))

            # Follow Jake's X lane with slight lag
            target_x = self.target.x * 0.8 - 0.25
            self.x = lerp(self.x, target_x, min(1, dt * 5))
            self.z = lerp(self.z, self.target.z - self.target_dist, min(1, dt * 4))
        else:
            # Menu / Game over
            self.x = lerp(self.x, self.target.x - 0.35, min(1, dt * 5))
            self.z = lerp(self.z, self.target.z - self.target_dist, min(1, dt * 4))

        # Running step bobbing
        self.anim_t += dt * (7.0 + speed * 0.3)
        self.y = abs(math.sin(self.anim_t)) * 0.08
