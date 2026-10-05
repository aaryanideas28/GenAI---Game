"""Authentic Subway Surfers world: 3D track sections, retaining arches, and overhead gantries."""

from __future__ import annotations

import random
from pathlib import Path
from ursina import Entity, Sky, color

from game import textures as tx

CHUNK_LEN = 38.7926
NUM_CHUNKS = 8
MIN_WRAP_Z = -77.5852


class World:
    """Seamless endless scrolling track built from authentic Subway Surfers 3D assets."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg

        # Sky
        self.sky = Sky(texture=tx.to_ursina(f"sky{cfg['sky_top_color']}{cfg['sky_bottom_color']}",
                                            tx.sky_gradient(cfg["sky_top_color"], cfg["sky_bottom_color"])))

        # Solid dark track ballast foundation underneath to prevent any horizon gaps
        self.bed = Entity(model="plane", color=color.hex("#2c2826"),
                          scale=(120, 1, 600), y=-0.08, z=120.0)

        from ursina import application
        application.asset_folder = Path(__file__).resolve().parent.parent

        # 3D Subway Surfers Track Chunks
        assets_dir = Path(__file__).resolve().parent / "assets"
        track_obj = assets_dir / "models" / "track_section.obj"
        main_tex_img = tx.get_custom_texture("main_texture.png")
        self.chunks: list[Entity] = []

        if track_obj.is_file() and main_tex_img is not None:
            for i in range(NUM_CHUNKS):
                z = -77.5852 + i * CHUNK_LEN
                c = Entity(model="track_section.obj", texture=main_tex_img,
                           unlit=True, double_sided=True, z=z)
                self.chunks.append(c)
        else:
            # Fallback procedural track if model is missing
            for lane in (-1, 0, 1):
                lx = lane * cfg["lane_width"]
                t = Entity(model="plane", color=color.hex("#555555"),
                           scale=(2.2, 1, 300), x=lx, z=120)
                self.chunks.append(t)

        # Overhead Subway Tunnel portals that appear periodically
        tunnel_obj = assets_dir / "models" / "tunnel_chunk.obj"
        self.tunnels: list[Entity] = []
        if tunnel_obj.is_file() and main_tex_img is not None:
            for z in (160.0, 360.0):
                tun = Entity(model="tunnel_chunk.obj", texture=main_tex_img,
                             unlit=True, double_sided=True, z=z)
                self._position_tunnel(tun)
                self.tunnels.append(tun)

    def _position_tunnel(self, tun: Entity, lane: int | None = None) -> None:
        """Position tunnel so its opening aligns with lane -1 (left), 0 (center), or +1 (right)."""
        if lane is None:
            lane = random.choice([-1, 0, 1])
        tun.tunnel_lane = lane
        if lane == 1:
            tun.x = 0.0
            tun.scale_x = 1.0
        elif lane == -1:
            tun.x = 0.0
            tun.scale_x = -1.0
        elif lane == 0:
            tun.x = -2.13
            tun.scale_x = 1.0

    def tick(self, dt: float, speed: float) -> None:
        step = speed * dt

        # Scroll track chunks
        for c in self.chunks:
            c.z -= step
            if c.z < MIN_WRAP_Z:
                c.z += NUM_CHUNKS * CHUNK_LEN

        # Scroll tunnels
        for t in self.tunnels:
            t.z -= step
            if t.z < -30.0:
                t.z += 400.0
                self._position_tunnel(t)

    def reset(self) -> None:
        """Reset track chunks and tunnel positions back to their starting layout."""
        if hasattr(self, "chunks"):
            if len(self.chunks) == NUM_CHUNKS:
                for i, c in enumerate(self.chunks):
                    c.z = MIN_WRAP_Z + i * CHUNK_LEN
            else:
                for c in self.chunks:
                    c.z = 120.0

        if hasattr(self, "tunnels"):
            initial_tunnel_zs = (160.0, 360.0)
            for i, t in enumerate(self.tunnels):
                z_pos = initial_tunnel_zs[i % len(initial_tunnel_zs)]
                t.z = z_pos
                self._position_tunnel(t)
