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


def make_horseshoe_magnet_mesh(radius: float = 0.45, inner_radius: float = 0.25, thickness: float = 0.14, segments: int = 12) -> Mesh:
    """Creates a 3D U-shaped horseshoe magnet mesh."""
    verts: list[Vec3] = []
    tris: list[tuple[int, int, int]] = []
    uvs: list[Vec2] = []

    half_th = thickness / 2.0
    # U-arch from 0 to pi (half circle open downwards) plus straight legs
    # Angles from 0 to pi
    for side, z in enumerate((half_th, -half_th)):
        base_idx = len(verts)
        # Inner and outer curve vertices
        for i in range(segments + 1):
            theta = math.pi * (i / segments)
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)

            # Outer point
            xo = cos_t * radius
            yo = sin_t * radius
            verts.append(Vec3(xo, yo, z))
            uvs.append(Vec2(0.5 + 0.5 * cos_t, 0.5 + 0.5 * sin_t))

            # Inner point
            xi = cos_t * inner_radius
            yi = sin_t * inner_radius
            verts.append(Vec3(xi, yi, z))
            uvs.append(Vec2(0.5 + 0.3 * cos_t, 0.5 + 0.3 * sin_t))

        # Triangles for the curved face
        for i in range(segments):
            o0 = base_idx + i * 2
            i0 = base_idx + i * 2 + 1
            o1 = base_idx + (i + 1) * 2
            i1 = base_idx + (i + 1) * 2 + 1
            if side == 0:
                tris.append((o0, o1, i0))
                tris.append((i0, o1, i1))
            else:
                tris.append((o0, i0, o1))
                tris.append((i0, i1, o1))

    # Connect front and back rims
    num_pts_per_side = (segments + 1) * 2
    for i in range(segments):
        # Outer rim
        f_o0 = i * 2
        f_o1 = (i + 1) * 2
        b_o0 = num_pts_per_side + i * 2
        b_o1 = num_pts_per_side + (i + 1) * 2
        tris.append((f_o0, b_o0, f_o1))
        tris.append((f_o1, b_o0, b_o1))

        # Inner rim
        f_i0 = i * 2 + 1
        f_i1 = (i + 1) * 2 + 1
        b_i0 = num_pts_per_side + i * 2 + 1
        b_i1 = num_pts_per_side + (i + 1) * 2 + 1
        tris.append((f_i0, f_i1, b_i0))
        tris.append((f_i1, b_i1, b_i0))

    return Mesh(vertices=verts, triangles=tris, uvs=uvs, mode="triangle")


def make_star_2x_mesh(radius: float = 0.48, thickness: float = 0.14) -> Mesh:
    """Creates a 3D star token with an embossed profile."""
    return make_star_coin_mesh(radius=radius, thickness=thickness, points=5)
