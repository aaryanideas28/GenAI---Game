"""Simple and intuitive UI for entering prompt modifications at game start."""

from __future__ import annotations

from typing import Callable, Optional
from ursina import Button, Entity, InputField, Text, camera, color, destroy


PRESETS = [
    ("Shockwave Roll", "shockwave on roll"),
    ("Reverse Trains", "trains reverse on jump"),
    ("Floor is Lava", "floor is lava"),
    ("Survival Mode", "survival mode"),
    ("Jetpack Flying", "flying jetpack"),
    ("Normal Mode", ""),
]


class PromptUI:
    """Prompt dialog displayed at start to configure game mechanics via GenAI."""

    def __init__(self, game_ref: any, on_start: Callable[[str], None]) -> None:
        self.game = game_ref
        self.on_start = on_start
        self.container: Optional[Entity] = None
        self.input_field: Optional[InputField] = None
        self.status_text: Optional[Text] = None
        self.preset_buttons: list[Button] = []
        self.is_active = False

    def show(self, default_prompt: Optional[str] = None) -> None:
        """Create and display the start prompt UI."""
        self.is_active = True

        # Root container on camera.ui
        self.container = Entity(parent=camera.ui, z=-1)

        # Darkened backdrop over the 3D scene
        self.backdrop = Entity(
            parent=self.container,
            model="quad",
            color=color.rgba(10, 15, 25, 230),
            scale=(2.0, 2.0),
            z=0.2,
        )

        # Card dialog panel (sized for 520x920 portrait window)
        self.panel = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#1e2238"),
            scale=(0.50, 0.77),
            position=(0, 0),
            z=0.1,
        )

        # Top banner accent line
        self.accent_bar = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#ffd21a"),
            scale=(0.50, 0.008),
            position=(0, 0.381),
            z=0.05,
        )

        # Title
        self.title = Text(
            "GENAI PROMPT MODIFIER",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.325),
            scale=1.55,
            color=color.hex("#ffd21a"),
        )

        # Subtitle instructions
        self.subtitle = Text(
            "Type a prompt to modify game rules,\nor select a preset below:",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.265),
            scale=0.88,
            color=color.hex("#94a3b8"),
        )

        # Input label
        self.lbl_prompt = Text(
            "Game Mechanic Prompt:",
            parent=self.container,
            origin=(-1, 0),
            position=(-0.225, 0.205),
            scale=0.9,
            color=color.hex("#e2e8f0"),
        )

        # Enlarged Input field with larger typography
        self.input_field = InputField(
            default_value=default_prompt or "",
            parent=self.container,
            scale=(0.46, 0.072),
            position=(0, 0.145),
            character_limit=120,
            active=True,
        )
        try:
            if hasattr(self.input_field, "text_field") and hasattr(self.input_field.text_field, "text_entity"):
                self.input_field.text_field.text_entity.scale *= 1.35
        except Exception:
            pass
        self.input_field.on_submit = self.submit

        # Presets label
        self.lbl_presets = Text(
            "Quick Presets:",
            parent=self.container,
            origin=(-1, 0),
            position=(-0.225, 0.08),
            scale=0.85,
            color=color.hex("#cbd5e1"),
        )

        # 6 preset buttons in 3 rows
        preset_coords = [
            (-0.115, 0.025), (0.115, 0.025),
            (-0.115, -0.035), (0.115, -0.035),
            (-0.115, -0.095), (0.115, -0.095),
        ]

        self.preset_buttons = []
        for (label, val), (px, py) in zip(PRESETS, preset_coords):
            btn = Button(
                text=label,
                parent=self.container,
                scale=(0.22, 0.046),
                position=(px, py),
                color=color.hex("#2c3452"),
                highlight_color=color.hex("#3e4b75"),
            )
            btn.on_click = lambda v=val: self._select_preset(v)
            self.preset_buttons.append(btn)

        # Status text (for feedback on preset selected)
        self.status_text = Text(
            "",
            parent=self.container,
            origin=(0, 0),
            position=(0, -0.15),
            scale=0.85,
            color=color.hex("#4ade80"),
        )

        # Start button
        self.btn_start = Button(
            text="START GAME (ENTER)",
            parent=self.container,
            scale=(0.46, 0.062),
            position=(0, -0.215),
            color=color.hex("#16a34a"),
            highlight_color=color.hex("#22c55e"),
        )
        self.btn_start.on_click = self.submit

        # Skip / Default rules button
        self.btn_skip = Button(
            text="Play Vanilla (Default Rules)",
            parent=self.container,
            scale=(0.46, 0.046),
            position=(0, -0.285),
            color=color.hex("#475569"),
            highlight_color=color.hex("#64748b"),
        )
        self.btn_skip.on_click = self._skip


    def _select_preset(self, val: str) -> None:
        """Sets the input field text to the selected preset."""
        if self.input_field:
            self.input_field.text = val
            if self.status_text:
                self.status_text.text = f"Selected: {val}" if val else "Vanilla / Default selected"

    def submit(self) -> None:
        """Submits the current prompt and starts the game."""
        text = self.input_field.text.strip() if self.input_field else ""
        self.hide()
        self.on_start(text)

    def _skip(self) -> None:
        """Starts game without any prompt modification."""
        self.hide()
        self.on_start("")

    def handle_input(self, key: str) -> bool:
        """Handle key events while prompt UI is visible."""
        if not self.is_active:
            return False
        if key in ("enter", "return"):
            self.submit()
            return True
        if key == "escape":
            self._skip()
            return True
        return False

    def hide(self) -> None:
        """Closes and removes the prompt UI."""
        self.is_active = False
        if self.container:
            try:
                destroy(self.container)
            except Exception:
                pass
            self.container = None
            self.input_field = None
