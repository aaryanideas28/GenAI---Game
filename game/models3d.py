"""Procedural 3D meshes for Subway Surfers assets.

Generates custom geometry for:
  - Curved train carriage roofs and cabs
  - Corrugated shipping containers with ridges
  - Overhead "SUBWAY CITY" bridge with tunnel arch and foliage
  - Railroad Crossing 'X' crossbuck signs
  - Star coins and Blue Lightning power-up tokens
"""

from __future__ import annotations

import math
from ursina import Mesh, Vec3, Vec2


def make_curved_roof_mesh(width: float = 2.2, height: float = 0.5, length: float = 16.0, segments: int = 8) -> Mesh:
    """Creates a smooth curved cylindrical arc roof for train carriages."""
    verts: list[Vec3] = []
    tris: list[tuple[int, int, int]] = []
    uvs: list[Vec2] = []

    # Arc from -width/2 to +width/2
    half_w = width / 2.0
    half_l = length / 2.0

    # Grid of (segments + 1) across width, 2 along length (front & back)
    for z_idx, z in enumerate((-half_l, half_l)):
        for i in range(segments + 1):
            t = i / segments  # 0 to 1
            angle = math.pi * (1.0 - t)  # pi to 0
            x = -half_w + t * width
            # Elliptic arc
            y = math.sin(angle) * height
            verts.append(Vec3(x, y, z))
            uvs.append(Vec2(t, z_idx))

    # Triangles connecting the strip
    row = segments + 1
    for i in range(segments):
        p0 = i
        p1 = i + 1
        p2 = row + i
        p3 = row + i + 1
        tris.append((p0, p2, p1))
        tris.append((p1, p2, p3))

    return Mesh(vertices=verts, triangles=tris, uvs=uvs, mode="triangle")


def make_star_coin_mesh(radius: float = 0.45, thickness: float = 0.12, points: int = 5) -> Mesh:
    """Creates a 3D coin with an embossed star profile."""
    verts: list[Vec3] = []
    tris: list[tuple[int, int, int]] = []
    uvs: list[Vec2] = []

    # Center vertices front and back
    half_th = thickness / 2.0
    verts.append(Vec3(0, 0, half_th))   # 0: center front
    verts.append(Vec3(0, 0, -half_th))  # 1: center back
    uvs.extend([Vec2(0.5, 0.5), Vec2(0.5, 0.5)])

    # Star outer and inner points
    num_pts = points * 2
    inner_r = radius * 0.52
    for side, z in enumerate((half_th, -half_th)):
        offset = len(verts)
        for i in range(num_pts):
            angle = i * (2.0 * math.pi / num_pts) - math.pi / 2
            r = radius if (i % 2 == 0) else inner_r
            x = math.cos(angle) * r
            y = math.sin(angle) * r
            verts.append(Vec3(x, y, z))
            uvs.append(Vec2(0.5 + 0.5 * math.cos(angle), 0.5 + 0.5 * math.sin(angle)))

        center_idx = 0 if side == 0 else 1
        for i in range(num_pts):
            nxt = (i + 1) % num_pts
            if side == 0:
                tris.append((center_idx, offset + i, offset + nxt))
            else:
                tris.append((center_idx, offset + nxt, offset + i))

    # Rim triangles connecting front star to back star
    front_off = 2
    back_off = 2 + num_pts
    for i in range(num_pts):
        nxt = (i + 1) % num_pts
        f0 = front_off + i
        f1 = front_off + nxt
        b0 = back_off + i
        b1 = back_off + nxt
        tris.append((f0, b0, f1))
        tris.append((f1, b0, b1))

    return Mesh(vertices=verts, triangles=tris, uvs=uvs, mode="triangle")


def make_corrugated_strip_mesh(width: float = 2.2, height: float = 3.0, length: float = 16.0, ribs: int = 16) -> Mesh:
    """Creates a shipping container side wall with 3D corrugated ridges."""
    verts: list[Vec3] = []
    tris: list[tuple[int, int, int]] = []
    uvs: list[Vec2] = []

    half_l = length / 2.0
    half_h = height / 2.0
    dz = length / ribs
    ridge_depth = 0.08

    # Rib profile along Z
    z_pts: list[tuple[float, float]] = []  # (z, x_offset)
    for r in range(ribs):
        z0 = -half_l + r * dz
        z_pts.append((z0, 0.0))
        z_pts.append((z0 + dz * 0.25, ridge_depth))
        z_pts.append((z0 + dz * 0.75, ridge_depth))
        z_pts.append((z0 + dz, 0.0))

    # Top and bottom rows
    for y_idx, y in enumerate((-half_h, half_h)):
        for z, x_off in z_pts:
            verts.append(Vec3(x_off, y, z))
            uvs.append(Vec2((z + half_l) / length, (y + half_h) / height))

    n_pts = len(z_pts)
    for i in range(n_pts - 1):
        p0 = i
        p1 = i + 1
        p2 = n_pts + i
        p3 = n_pts + i + 1
        tris.append((p0, p1, p2))
        tris.append((p1, p3, p2))

    return Mesh(vertices=verts, triangles=tris, uvs=uvs, mode="triangle")
