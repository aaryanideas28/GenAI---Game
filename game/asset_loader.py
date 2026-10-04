"""Custom Asset Loader for Subway Surfers assets.

Loads user-provided textures from `game/assets/custom/` with automatic
extraction from texture atlases (e.g. Jake, train atlas, skybox, guard).
Falls back cleanly to procedural textures if custom assets are not found.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger("game.asset_loader")

ASSETS_DIR = Path(__file__).parent / "assets" / "custom"


class CustomAssetManager:
    """Manages custom texture atlases and extracted sprites."""

    def __init__(self, asset_dir: Path = ASSETS_DIR) -> None:
        self.asset_dir = asset_dir
        self._cache: dict[str, Image.Image] = {}

    def has_asset(self, filename: str) -> bool:
        return (self.asset_dir / filename).is_file()

    def load_image(self, filename: str) -> Optional[Image.Image]:
        if filename in self._cache:
            return self._cache[filename]
        path = self.asset_dir / filename
        if not path.is_file():
            return None
        try:
            im = Image.open(path).convert("RGBA")
            self._cache[filename] = im
            return im
        except Exception as exc:
            logger.warning("Failed to load custom asset %s: %s", filename, exc)
            return None

    # --- Barrier -------------------------------------------------------------
    def get_barrier_stripes(self) -> Optional[Image.Image]:
        """Extracts the iconic red/white warning stripes from train_atlas.png."""
        atlas = self.load_image("train_atlas.png")
        if atlas:
            # Region containing red/white barrier stripes in Subway Surfers atlas
            stripes = atlas.crop((315, 440, 410, 490))
            return stripes
        return None

    # --- Train ---------------------------------------------------------------
    def get_train_side(self) -> Optional[Image.Image]:
        """Extracts train side panels and doors from train_atlas.png."""
        atlas = self.load_image("train_atlas.png")
        if atlas:
            return atlas.crop((256, 260, 440, 430))
        return None

    def get_train_front(self) -> Optional[Image.Image]:
        """Extracts train nose/front cabin from train_atlas.png."""
        atlas = self.load_image("train_atlas.png")
        if atlas:
            # Use front cabin section
            return atlas.crop((0, 0, 135, 215))
        return None

    # --- Jake Character ------------------------------------------------------
    def get_jake_face(self) -> Optional[Image.Image]:
        """Extracts Jake's face from jake.png."""
        jake = self.load_image("jake.png")
        if jake:
            return jake.crop((150, 60, 256, 170))
        return None

    def get_jake_tag(self) -> Optional[Image.Image]:
        """Extracts the 'SUB SURF' graffiti tag from jake.png."""
        jake = self.load_image("jake.png")
        if jake:
            return jake.crop((68, 175, 170, 256))
        return None

    def get_jake_denim(self) -> Optional[Image.Image]:
        """Extracts denim vest texture from jake.png."""
        jake = self.load_image("jake.png")
        if jake:
            return jake.crop((64, 80, 160, 175))
        return None

    # --- Sky -----------------------------------------------------------------
    def get_sky_panorama(self) -> Optional[Image.Image]:
        """Extracts sky panorama from skybox.png or sky_panorama.png."""
        if self.has_asset("sky_panorama.png"):
            return self.load_image("sky_panorama.png")
        sky = self.load_image("skybox.png")
        if sky:
            strip = sky.crop((0, 170, 512, 341))
            return strip.resize((1024, 512), Image.Resampling.LANCZOS)
        return None


# Global singleton instance
custom_assets = CustomAssetManager()
