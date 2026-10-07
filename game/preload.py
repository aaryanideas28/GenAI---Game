"""Startup asset preloading to eliminate mid-game hitches.

Ursina's ``load_model("name.obj")`` performs, on the *first* request for a model,
a recursive ``glob`` over ``application.asset_folder`` (the whole project root,
including ``.venv``), a pure-Python OBJ parse, and a ``.bam`` write to disk.
Every later request is a cheap copy from ``mesh_importer.imported_meshes``.

Calling :func:`preload_assets` once at startup pays that cost up front (with a
narrow search path so the glob is fast), so obstacles / power-ups / player
attachments that spawn lazily during a run no longer stall the frame.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger("game.preload")

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
MODELS_DIR = ASSETS_DIR / "models"

# Every OBJ model referenced by name in world.py / obstacles.py / player.py / inspector.py.
MODEL_FILES: tuple[str, ...] = (
    # world
    "track_section.obj",
    "tunnel_chunk.obj",
    # obstacles
    "train_standard.obj",
    "train_cargo.obj",
    "train_ramp.obj",
    "barrier_jump.obj",
    "barrier_roll.obj",
    # power-up tokens + player attachments
    "magnet.obj",
    "jetpack.obj",
    "sneakers.obj",
    "sneaker_l.obj",
    "sneaker_r.obj",
    "hoverboard.obj",
    # characters
    "jake.obj",
    "jake_torso.obj",
    "jake_leg_l.obj",
    "jake_leg_r.obj",
    "inspector.obj",
)

# Custom textures fetched lazily via textures.get_custom_texture().
TEXTURE_FILES: tuple[str, ...] = (
    "main_texture.png",
    "trains_texture.png",
    "jake_texture.png",
    "enemies_texture.png",
    "jetpack.png",
    "props.png",
    "sneakers.png",
    "hoverboard.png",
    "main.png",
    "powerup_jetpack.png",
    "powerup_magnet.png",
    "powerup_sneakers.png",
    "powerup_multiplier.png",
    "powerup_hoverboard.png",
    "powerup_shield.png",
)


def preload_models() -> None:
    """Parse and cache every OBJ model so later ``Entity(model="x.obj")`` calls hit the cache."""
    from ursina.mesh_importer import imported_meshes, load_model

    for filename in MODEL_FILES:
        name = filename.rsplit(".", 1)[0]
        if name in imported_meshes or not (MODELS_DIR / filename).is_file():
            continue
        try:
            # Search only the models folder instead of the entire project tree.
            load_model(filename, path=MODELS_DIR)
        except Exception as exc:  # never block startup on a bad asset
            logger.warning("Failed to preload model %s: %s", filename, exc)


def preload_textures() -> None:
    """Load custom textures into the textures module cache."""
    from game import textures as tx

    for filename in TEXTURE_FILES:
        try:
            tx.get_custom_texture(filename)
        except Exception as exc:
            logger.warning("Failed to preload texture %s: %s", filename, exc)


def preload_assets() -> None:
    """Preload all models and textures. Call once after ``Ursina()`` is created."""
    t0 = time.perf_counter()
    preload_models()
    preload_textures()
    logger.info("Preloaded assets in %.2fs", time.perf_counter() - t0)
