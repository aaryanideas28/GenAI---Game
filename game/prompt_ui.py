"""Simple and intuitive Claude-styled UI for entering prompt modifications at game start."""

from __future__ import annotations

from typing import Callable, Optional
from ursina import Button, Entity, InputField, Text, camera, color, destroy


PRESETS = [
    ("Shockwave Roll", "shockwave on roll"),
    ("Reverse Trains", "trains reverse on jump"),
    ("Floor is Lava", "floor is lava"),
    ("Survival Mode", "survival mode"),
    ("Jetpack Flying", "flying jetpack"),
    ("play vanilla (default)", ""),
]


class PromptUI:
    """Claude-styled Prompt dialog displayed at launch to configure game mechanics via GenAI."""

    def __init__(self, game_ref: any, on_start: Callable[[str], None]) -> None:
        self.game = game_ref
        self.on_start = on_start
        self.container: Optional[Entity] = None
        self.input_field: Optional[InputField] = None
        self.status_text: Optional[Text] = None
        self.preset_buttons: list[Button] = []
        self.is_active = False

    def show(self, default_prompt: Optional[str] = None) -> None:
        """Create and display the Claude-styled start prompt UI."""
        self.is_active = True

        # Root container on camera.ui
        self.container = Entity(parent=camera.ui, z=-1)

        # Pure black backdrop over the 3D scene (#000000)
        self.backdrop = Entity(
            parent=self.container,
            model="quad",
            color=color.black,
            scale=(2.0, 2.0),
            z=0.2,
        )

        # ---------------------------------------------------------------------
        # TOP LOGO: Official "RAIL RUSH" Running Logo
        # Big, bright, separated with comfortable spacing above the box
        # ---------------------------------------------------------------------
        import os
        logo_path = "assets/rail_rush_logo.png"
        if os.path.exists(logo_path):
            self.logo = Entity(
                parent=self.container,
                model="quad",
                texture=logo_path,
                scale=(0.52, 0.166),  # Bigger, impactful logo keeping natural aspect ratio
                position=(0, 0.380),  # Positioned high up
                z=0.05,
            )
        else:
            self.logo = Text(
                "RAIL RUSH",
                parent=self.container,
                origin=(0, 0),
                position=(0, 0.380),
                scale=2.6,
                color=color.hex("#38bdf8"),
            )

        # ---------------------------------------------------------------------
        # ROUNDED OUTLINE BOX (like Claude card container)
        # Separated from logo (top starts at y ~ 0.255, height 0.60, width 0.64)
        # White prominent outline
        # ---------------------------------------------------------------------
        self.card_outline = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#f4f4f5"),  # Prominent clean white outline
            scale=(0.648, 0.608),
            position=(0, -0.050),
            z=0.15,
        )

        # Inner dark card panel
        self.card_inner = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#19191d"),  # Sleek charcoal inner
            scale=(0.640, 0.600),
            position=(0, -0.050),
            z=0.10,
        )

        # ---------------------------------------------------------------------
        # PROMPT HEADING: In the center, in purple, robotic/monospace font
        # ---------------------------------------------------------------------
        self.lbl_prompt = Text(
            "PROMPT",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.200),
            scale=1.18,
            color=color.hex("#a855f7"),  # Vibrant Purple
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
        )

        # ---------------------------------------------------------------------
        # EXPANDING INPUT BOX:
        # - Light blue text, bold/monospace
        # - Proportional size with limit so text never spills out of bounds
        # - Auto-expanding lines like typing in Antigravity
        # ---------------------------------------------------------------------
        self.input_field = InputField(
            default_value=default_prompt or "",
            parent=self.container,
            scale=(0.56, 0.046),
            position=(0, 0.150),
            character_limit=110,
            active=True,
        )
        self.input_field.color = color.hex("#121215")

        # Style inner text field for light blue, bold, monospace
        try:
            if hasattr(self.input_field, "text_field"):
                tf = self.input_field.text_field
                tf.font = "VeraMono.ttf"
                if hasattr(tf, "text_entity") and tf.text_entity:
                    tf.text_entity.color = color.hex("#7dd3fc")  # Light Blue
                    tf.text_entity.scale = 0.95  # Clean proportional size
                    tf.text_entity.font = "VeraMono.ttf"
        except Exception:
            pass

        self.input_field.on_submit = self.submit

        # ---------------------------------------------------------------------
        # SUGGESTED PROMPTS HEADING: In the center with generous top breathing room
        # ---------------------------------------------------------------------
        self.lbl_presets = Text(
            "SUGGESTED PROMPTS",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.076),
            scale=1.05,
            color=color.hex("#e2e8f0"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
        )

        # ---------------------------------------------------------------------
        # CAPSULE BUTTONS GRID (comfortably sized & spacious)
        # Column 1: Box 1 (Purple), Box 2 (Blue), Box 3 (Purple)
        # Column 2: Box 1 (Blue), Box 2 (Purple), Box 3 (Blue)
        # Generous button dimensions (width: 0.284, height: 0.052)
        # Highly visible white crisp labels cleanly centered with zero overflow
        # ---------------------------------------------------------------------
        btn_w = 0.284
        btn_h = 0.052
        x_left = -0.150
        x_right = 0.150

        button_specs = [
            # (label, value, pos_x, pos_y, bg_color, hl_color)
            ("Shockwave Roll", "shockwave on roll", x_left, 0.020, color.hex("#7c3aed"), color.hex("#9333ea")),
            ("Reverse Trains", "trains reverse on jump", x_right, 0.020, color.hex("#2563eb"), color.hex("#3b82f6")),
            ("Floor is Lava", "floor is lava", x_left, -0.044, color.hex("#2563eb"), color.hex("#3b82f6")),
            ("Survival Mode", "survival mode", x_right, -0.044, color.hex("#7c3aed"), color.hex("#9333ea")),
            ("Jetpack Flying", "flying jetpack", x_left, -0.108, color.hex("#7c3aed"), color.hex("#9333ea")),
            ("play vanilla (default)", "", x_right, -0.108, color.hex("#2563eb"), color.hex("#3b82f6")),
        ]

        self.preset_buttons = []
        for label, val, px, py, bg_col, hl_col in button_specs:
            btn = Button(
                text="",  # Use dedicated foreground Text entity for 100% visible crisp font
                parent=self.container,
                scale=(btn_w, btn_h),
                position=(px, py),
                color=bg_col,
                highlight_color=hl_col,
                radius=0.5,
            )
            # Dedicated high-visibility label on top of button capsule
            # Perfectly proportioned scale (0.76 for longer text, 0.84 for shorter)
            font_scale = 0.74 if len(label) > 18 else 0.84
            lbl = Text(
                label,
                parent=self.container,
                origin=(0, 0),
                position=(px, py),
                scale=font_scale,
                color=color.white,
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )
            btn.label_ref = lbl
            btn.on_click = lambda v=val: self._select_preset(v)
            self.preset_buttons.append(btn)

        # ---------------------------------------------------------------------
        # SELECTED MODE DISPLAY IN ROBOTIC TEXT (Centered directly above submit button)
        # ---------------------------------------------------------------------
        self.status_text = Text(
            "[MODE: VANILLA / DEFAULT RULES]",
            parent=self.container,
            origin=(0, 0),
            position=(0, -0.170),
            scale=0.90,
            color=color.hex("#38bdf8"),  # Robotic Cyan / Light Blue
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
        )

        # ---------------------------------------------------------------------
        # START GAME BUTTON:
        # - Light blue background (#0284c7 / #38bdf8)
        # - White bold robotic text clearly legible
        # - 3D clickable bevel / shadow with rounded edges
        # ---------------------------------------------------------------------
        # 3D shadow layer underneath
        self.btn_start_shadow = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#0369a1"),
            scale=(0.502, 0.056),
            position=(0, -0.234),
            z=0.08,
        )
        self.btn_start = Button(
            text="",  # Clean dedicated overlay text
            parent=self.container,
            scale=(0.50, 0.054),
            position=(0, -0.228),
            color=color.hex("#0284c7"),  # Light Blue
            highlight_color=color.hex("#38bdf8"),
            radius=0.35,
        )
        # Highly visible bold white text over start button
        self.btn_start_label = Text(
            "START GAME (ENTER)",
            parent=self.container,
            origin=(0, 0),
            position=(0, -0.228),
            scale=1.12,
            color=color.white,
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.btn_start.on_click = self.submit

        # Initial height adjustment
        self._update_input_expansion()

    def _update_input_expansion(self) -> None:
        """Expands input box height dynamically like Antigravity without exceeding bounds."""
        if not self.input_field:
            return
        t = self.input_field.text or ""
        # 110 max chars: lines range from 1 to 3
        chars_per_line = 36
        lines = max(1, min(3, len(t) // chars_per_line + 1))
        base_h = 0.046
        new_h = base_h + (lines - 1) * 0.020
        self.input_field.scale_y = new_h

    def _select_preset(self, val: str) -> None:
        """Sets the input field text to the selected preset."""
        if self.input_field:
            self.input_field.text = val
            # Enforce light blue text color in input field
            try:
                if hasattr(self.input_field, "text_field") and hasattr(self.input_field.text_field, "text_entity"):
                    self.input_field.text_field.text_entity.color = color.hex("#7dd3fc")
            except Exception:
                pass

            self._update_input_expansion()
            if self.status_text:
                if val:
                    clean_name = val.upper()
                    self.status_text.text = f"[MODE: {clean_name}]"
                    self.status_text.color = color.hex("#c084fc")  # Purple hint for active genai prompt
                else:
                    self.status_text.text = "[MODE: VANILLA / DEFAULT RULES]"
                    self.status_text.color = color.hex("#38bdf8")  # Light blue for vanilla

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
        # Keep input text color light blue and maintain bounds expansion
        try:
            if hasattr(self.input_field, "text_field") and hasattr(self.input_field.text_field, "text_entity"):
                self.input_field.text_field.text_entity.color = color.hex("#7dd3fc")
        except Exception:
            pass
        self._update_input_expansion()
        # Update robotic mode status live if custom text is typed
        if self.input_field and self.status_text:
            typed = self.input_field.text.strip()
            if typed:
                self.status_text.text = f"[MODE: {typed[:28].upper()}]"
                self.status_text.color = color.hex("#c084fc")
            else:
                self.status_text.text = "[MODE: VANILLA / DEFAULT RULES]"
                self.status_text.color = color.hex("#38bdf8")
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
