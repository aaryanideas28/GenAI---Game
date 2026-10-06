"""Interactive UI, In-Game AI Prompt Console, Mobile Power-Up Badges & Leaderboard Modals.

Implements Task 5:
  1. In-Game AI Prompt Console with Command Bar, Loading Spinner & Real-Time Guardrail Feedback
  2. Mobile-style Power-Up Countdown HUD Badges with Bar Progress Indicators
  3. Student Name & Roll Number Arcade Entry Dialog on Game Over
  4. Interactive Dual-Board Leaderboard Modal (Ranked vs Sandbox) with Teacher CSV Export
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from ursina import Button, Entity, InputField, Text, camera, color, destroy

logger = logging.getLogger("interactive_ui")

# In-Game Quick Prompt Presets specified in Task 5
PRESETS_INGAME: List[Tuple[str, str]] = [
    ("Floor is Lava", "floor is lava"),
    ("Jetpack Skyway", "flying jetpack"),
    ("Coin Magnet", "coin magnet"),
    ("Default Rules", ""),
]

# Power-Up visual configurations for HUD countdown badges
POWERUP_CONFIGS: Dict[str, Dict[str, Any]] = {
    "magnet": {
        "icon": "🧲",
        "name": "Magnet",
        "color": color.hex("#ef4444"),
        "max_duration": 10.0,
        "mode": "timer",
    },
    "jetpack": {
        "icon": "🚀",
        "name": "Jetpack",
        "color": color.hex("#06b6d4"),
        "max_duration": 8.0,
        "mode": "timer",
    },
    "sneakers": {
        "icon": "👟",
        "name": "Super Sneakers",
        "color": color.hex("#22c55e"),
        "max_duration": 10.0,
        "mode": "timer",
    },
    "multiplier": {
        "icon": "✖️2",
        "name": "2X Multiplier",
        "color": color.hex("#eab308"),
        "max_duration": 12.0,
        "mode": "timer",
    },
    "hoverboard": {
        "icon": "🛹",
        "name": "Hoverboard",
        "color": color.hex("#3b82f6"),
        "max_duration": 12.0,
        "mode": "active",
    },
    "shield": {
        "icon": "🛡️",
        "name": "Shield",
        "color": color.hex("#a855f7"),
        "max_duration": 8.0,
        "mode": "timer",
    },
}


# =============================================================================
# 1. In-Game AI Prompt Console
# =============================================================================
class InGamePromptConsole:
    """In-Game command bar console triggered during gameplay (/ or T or HUD button).

    - Pauses gameplay and opens command bar overlay
    - Includes animated loading spinner while LLM dynamic logic synthesizes
    - Displays real-time guardrail feedback banner
    - Quick-prompt presets: [Floor is Lava], [Jetpack Skyway], [Coin Magnet], [Default Rules]
    """

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, game_ref: Any, on_apply: Callable[[str], None], on_close: Optional[Callable[[], None]] = None) -> None:
        self.game = game_ref
        self.on_apply = on_apply
        self.on_close = on_close
        self.container: Optional[Entity] = None
        self.input_field: Optional[InputField] = None
        self.feedback_text: Optional[Text] = None
        self.spinner_text: Optional[Text] = None
        self.preset_buttons: List[Button] = []
        self.is_active = False
        self.is_loading = False
        self.spinner_frame_idx = 0
        self.spinner_timer = 0.0

    def show(self, initial_prompt: str = "") -> None:
        """Opens the in-game prompt console and pauses gameplay."""
        self.is_active = True
        self.is_loading = False
        self.spinner_frame_idx = 0

        # UI Container on camera.ui
        self.container = Entity(parent=camera.ui, z=-2)

        # ---------------------------------------------------------------------
        # THEME: Pure black backdrop (#000000) & sleek bordered card
        # Matches PromptUI, ArcadeEntryModal, and LeaderboardModal
        # ---------------------------------------------------------------------
        self.backdrop = Entity(
            parent=self.container,
            model="quad",
            color=color.black,
            scale=(2.0, 2.0),
            z=0.2,
        )

        # Fixed width outer card with sleek border (width: 0.54, height: 0.50)
        self.card_border = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#2f3136"),
            scale=(0.544, 0.504),
            position=(0, 0.14),
            z=0.12,
        )
        self.panel = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#1a1a1e"),
            scale=(0.54, 0.50),
            position=(0, 0.14),
            z=0.1,
        )

        # Centered purple title header in robotic monospaced font
        self.title = Text(
            "IN-GAME AI PROMPT CONSOLE",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.355),
            scale=1.08,
            color=color.hex("#c084fc"),  # Robotic Purple
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # Subtitle
        self.sub_label = Text(
            "Type custom rules or select a preset. Press Enter to apply:",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.318),
            scale=0.76,
            color=color.hex("#94a3b8"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # Command Bar Input Field (light blue text, dark interior)
        self.input_field = InputField(
            default_value=initial_prompt,
            parent=self.container,
            scale=(0.48, 0.050),
            position=(0, 0.260),
            character_limit=140,
            active=True,
        )
        self.input_field.color = color.hex("#1e1f23")
        try:
            if hasattr(self.input_field, "text_field"):
                tf = self.input_field.text_field
                tf.font = "VeraMono.ttf"
                if hasattr(tf, "text_entity") and tf.text_entity:
                    tf.text_entity.font = "VeraMono.ttf"
                    tf.text_entity.color = color.hex("#7dd3fc")  # Bold light blue
        except Exception:
            pass
        self.input_field.on_submit = self.submit

        # Presets Label (anchored to card left beginning)
        self.lbl_presets = Text(
            "Suggested Presets:",
            parent=self.container,
            origin=(-0.5, 0),
            position=(-0.240, 0.205),
            scale=0.78,
            color=color.hex("#cbd5e1"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # ---------------------------------------------------------------------
        # PRESET BUTTONS (Capsules in alternating Demure Purple and Demure Blue)
        # [Floor is Lava (Purple)]      [Jetpack Skyway (Blue)]
        # [Coin Magnet (Blue)]          [Default Rules (Purple)]
        # ---------------------------------------------------------------------
        preset_specs = [
            # (label, value, x, y, bg_col, hl_col)
            ("Floor is Lava", "floor is lava", -0.125, 0.160, color.hex("#7c3aed"), color.hex("#9333ea")),
            ("Jetpack Skyway", "flying jetpack", 0.125, 0.160, color.hex("#2563eb"), color.hex("#3b82f6")),
            ("Coin Magnet", "coin magnet", -0.125, 0.108, color.hex("#2563eb"), color.hex("#3b82f6")),
            ("Default Rules", "", 0.125, 0.108, color.hex("#7c3aed"), color.hex("#9333ea")),
        ]
        self.preset_buttons = []
        for label, val, px, py, bg_col, hl_col in preset_specs:
            btn = Button(
                text="",
                parent=self.container,
                scale=(0.235, 0.042),
                position=(px, py),
                color=bg_col,
                highlight_color=hl_col,
                radius=0.4,
            )
            lbl = Text(
                label,
                parent=self.container,
                origin=(0, 0),
                position=(px, py),
                scale=0.78,
                color=color.white,
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )
            btn.label_ref = lbl
            btn.on_click = lambda v=val, l=label: self._select_preset(v, l)
            self.preset_buttons.append(btn)

        # Real-time guardrail feedback banner (centered robotic mode status)
        self.feedback_text = Text(
            self._get_initial_guardrail_feedback(),
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.052),
            scale=0.82,
            color=color.hex("#38bdf8"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # Loading spinner indicator text
        self.spinner_text = Text(
            "",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.015),
            scale=0.86,
            color=color.hex("#facc15"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # ---------------------------------------------------------------------
        # ACTION BUTTONS:
        # [APPLY & RESUME (ENTER)] in Demure Purple (#7c3aed)
        # [CANCEL (ESC)] in Demure Blue (#2563eb)
        # Rounded capsules, clearly visible white monospaced labels
        # ---------------------------------------------------------------------
        btn_y = -0.045
        self.btn_apply = Button(
            text="",
            parent=self.container,
            scale=(0.31, 0.048),
            position=(-0.085, btn_y),
            color=color.hex("#7c3aed"),  # Demure Purple
            highlight_color=color.hex("#9333ea"),
            radius=0.4,
        )
        self.btn_apply_label = Text(
            "APPLY & RESUME (ENTER)",
            parent=self.container,
            origin=(0, 0),
            position=(-0.085, btn_y),
            scale=0.80,
            color=color.white,
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.btn_apply.on_click = self.submit

        self.btn_close = Button(
            text="",
            parent=self.container,
            scale=(0.17, 0.048),
            position=(0.165, btn_y),
            color=color.hex("#2563eb"),  # Demure Blue
            highlight_color=color.hex("#3b82f6"),
            radius=0.4,
        )
        self.btn_close_label = Text(
            "CANCEL (ESC)",
            parent=self.container,
            origin=(0, 0),
            position=(0.165, btn_y),
            scale=0.80,
            color=color.white,
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.btn_close.on_click = self.close

    def _get_initial_guardrail_feedback(self) -> str:
        """Returns baseline guardrail status for current game state."""
        if hasattr(self.game, "active_prompt_summary"):
            s = self.game.active_prompt_summary
            if "vanilla" in s.lower() or "default" in s.lower() or "normal" in s.lower():
                return "Fair Play: Ranked Mode active (No custom prompt)"
            return f"Active Logic: {s} — Sandbox Mode flagged"
        return "Ready. Enter prompt to modify game rules."

    def _select_preset(self, prompt_val: str, label: str) -> None:
        """Applies a preset to the input field and updates guardrail feedback immediately."""
        if self.input_field:
            self.input_field.text = prompt_val

        # Immediate real-time guardrail feedback
        if not prompt_val or label == "Default Rules":
            feedback = "Default Rules active — Fair Play (Ranked Mode)"
            color_choice = color.hex("#4ade80")
        else:
            feedback = f"Generated {label} logic active — Sandbox Mode flagged"
            color_choice = color.hex("#38bdf8")

        if self.feedback_text:
            self.feedback_text.text = feedback
            self.feedback_text.color = color_choice

    def update_feedback(self, message: str, is_warning: bool = False, is_sandbox: bool = True) -> None:
        """Updates guardrail feedback message dynamically."""
        if self.feedback_text:
            self.feedback_text.text = message
            if is_warning:
                self.feedback_text.color = color.hex("#f87171")
            elif is_sandbox:
                self.feedback_text.color = color.hex("#38bdf8")
            else:
                self.feedback_text.color = color.hex("#4ade80")

    def tick(self, dt: float) -> None:
        """Ticks loading spinner animation if active."""
        if not self.is_active or not self.is_loading:
            return
        self.spinner_timer += dt
        if self.spinner_timer >= 0.08:
            self.spinner_timer = 0.0
            self.spinner_frame_idx = (self.spinner_frame_idx + 1) % len(self.SPINNER_FRAMES)
            char = self.SPINNER_FRAMES[self.spinner_frame_idx]
            if self.spinner_text:
                self.spinner_text.text = f"{char} Generating dynamic logic with Gemini AI..."

    def submit(self) -> None:
        """Submits prompt to synthesizer and applies dynamic logic."""
        if not self.is_active or self.is_loading:
            return
        prompt_text = self.input_field.text.strip() if self.input_field else ""

        # Update feedback based on prompt
        if not prompt_text or "default" in prompt_text.lower():
            self.update_feedback("Default Rules active — Fair Play (Ranked Mode)", is_sandbox=False)
        else:
            # Predict mode name for feedback
            first_word = prompt_text.title().split()[0] if prompt_text else "Custom"
            self.update_feedback(f"Generated {first_word} logic active — Sandbox Mode flagged", is_sandbox=True)

        self.is_loading = True
        if self.spinner_text:
            self.spinner_text.text = "⠋ Generating dynamic logic..."

        try:
            self.on_apply(prompt_text)
        finally:
            self.is_loading = False
            self.close()

    def handle_input(self, key: str) -> bool:
        """Handles keyboard input while console is active."""
        if not self.is_active:
            return False
        if key in ("enter", "return"):
            self.submit()
            return True
        if key == "escape":
            self.close()
            return True
        return False

    def close(self) -> None:
        """Hides and cleans up the console UI."""
        self.is_active = False
        self.is_loading = False
        if self.container:
            try:
                destroy(self.container)
            except Exception:
                pass
            self.container = None
            self.input_field = None
            self.feedback_text = None
            self.spinner_text = None
        if self.on_close:
            self.on_close()


# =============================================================================
# 2. Power-Up Countdown HUD Badges
# =============================================================================
class PowerUpHudBadges:
    """Mobile-style power-up icon badges with bar progress indicators.

    Renders active items (e.g., 🧲 0:08, 🚀 0:11, 🛹 Active) on camera.ui.
    """

    def __init__(self, parent_ui: Optional[Entity] = None) -> None:
        self.parent = parent_ui or camera.ui
        self.container: Optional[Entity] = None
        self.badge_entities: Dict[str, Dict[str, Any]] = {}

    def ensure_container(self) -> Entity:
        if self.container is None:
            self.container = Entity(parent=self.parent, z=-0.5)
        return self.container

    def update_badges(self, powerup_timers: Dict[str, float], invincible_timer: float = 0.0) -> None:
        """Refreshes mobile-style badges on screen based on active timers."""
        root = self.ensure_container()

        # Identify all active items
        active_items: List[Tuple[str, float, Dict[str, Any]]] = []
        for kind, remaining in powerup_timers.items():
            if remaining > 0.0 and kind in POWERUP_CONFIGS:
                active_items.append((kind, remaining, POWERUP_CONFIGS[kind]))

        # Cleanup removed badges
        current_kinds = {item[0] for item in active_items}
        for existing_kind in list(self.badge_entities.keys()):
            if existing_kind not in current_kinds:
                entry = self.badge_entities.pop(existing_kind)
                if "pill" in entry and entry["pill"]:
                    try:
                        destroy(entry["pill"])
                    except Exception:
                        pass

        # Position badges stacked vertically on the left edge
        start_y = 0.355
        gap_y = 0.058
        start_x = -0.385

        for idx, (kind, remaining, cfg) in enumerate(active_items):
            y_pos = start_y - (idx * gap_y)

            # Format countdown text
            if cfg.get("mode") == "active":
                # Matches format: 🛹 Active
                label_text = f"{cfg['icon']} Active"
                progress = 1.0
            else:
                mins = int(remaining) // 60
                secs = int(remaining) % 60
                label_text = f"{cfg['icon']} {mins}:{secs:02d}"
                max_d = float(cfg.get("max_duration", 10.0))
                progress = max(0.0, min(1.0, remaining / max_d))

            if kind in self.badge_entities:
                # Update existing badge
                b = self.badge_entities[kind]
                if b["pill"]:
                    b["pill"].y = y_pos
                if b["label"]:
                    b["label"].text = label_text
                if b["fill"]:
                    # Progress bar fill: scale_x is proportional to progress
                    b["fill"].scale_x = progress
            else:
                try:
                    # Create mobile pill badge
                    pill = Entity(
                        parent=root,
                        model="quad",
                        color=color.rgba(18, 24, 38, 230),
                        scale=(0.19, 0.048),
                        position=(start_x, y_pos),
                        z=0.05,
                    )

                    # Icon and countdown text
                    label = Text(
                        label_text,
                        parent=pill,
                        origin=(-0.5, 0),
                        position=(-0.44, 0.16),
                        scale=1.1,
                        color=color.white,
                    )

                    # Progress bar track (background)
                    track = Entity(
                        parent=pill,
                        model="quad",
                        color=color.rgba(40, 48, 68, 200),
                        scale=(0.86, 0.16),
                        position=(0, -0.26),
                        z=-0.01,
                    )

                    # Progress bar fill (colored indicator)
                    fill = Entity(
                        parent=track,
                        model="quad",
                        color=cfg["color"],
                        origin=(-0.5, 0),
                        scale=(progress, 1.0),
                        position=(-0.5, 0),
                        z=-0.02,
                    )
                except Exception:
                    from types import SimpleNamespace
                    pill = SimpleNamespace(y=y_pos)
                    label = SimpleNamespace(text=label_text)
                    track = SimpleNamespace()
                    fill = SimpleNamespace(scale_x=progress)

                self.badge_entities[kind] = {
                    "pill": pill,
                    "label": label,
                    "track": track,
                    "fill": fill,
                }

    def clear(self) -> None:
        """Removes all HUD badges."""
        for entry in self.badge_entities.values():
            if "pill" in entry and entry["pill"]:
                try:
                    destroy(entry["pill"])
                except Exception:
                    pass
        self.badge_entities.clear()
        if self.container:
            try:
                destroy(self.container)
            except Exception:
                pass
            self.container = None


# =============================================================================
# 3. Student Name Submission on Game Over (Arcade Entry Dialog)
# =============================================================================
class ArcadeEntryModal:
    """Arcade entry dialog upon crashing with Claude-style dark theme, animated capsules,
    rapidly rolling score tally, fixed-width card, purple/blue bullet points, and customized submit/skip buttons.
    """

    RUNNER_FRAMES = ["🏃", "🏃‍♂️", "🏃‍♀️", "🏃"]

    def __init__(self, game_ref: Any, on_submit: Callable[[str, str], None], on_skip: Optional[Callable[[], None]] = None) -> None:
        self.game = game_ref
        self.on_submit = on_submit
        self.on_skip = on_skip
        self.container: Optional[Entity] = None
        self.input_name: Optional[InputField] = None
        self.input_roll: Optional[InputField] = None
        self.status_banner: Optional[Text] = None
        self.is_active = False

        # Animation states
        self.target_score = 0
        self.displayed_score = 0
        self.anim_timer = 0.0
        self.runner_frame_idx = 0
        self.runner_anim_timer = 0.0
        self.coin_rot_angle = 0.0

        # UI Element references for animation
        self.txt_score_num: Optional[Text] = None
        self.coin_icon: Optional[Entity] = None
        self.runner_icon: Optional[Text] = None

    def show(self, default_name: str = "Jake", default_roll: str = "SUB-001",
             score: int = 0, coins: int = 0, distance: float = 0.0,
             prompt_summary: str = "Vanilla / Default Rules") -> None:
        """Displays arcade entry dialog on screen."""
        self.is_active = True
        self.target_score = max(0, int(score))
        self.displayed_score = 0
        self.anim_timer = 0.0
        self.runner_frame_idx = 0
        self.runner_anim_timer = 0.0
        self.coin_rot_angle = 0.0

        self.container = Entity(parent=camera.ui, z=-2)

        # Pure black backdrop (#000000)
        self.backdrop = Entity(
            parent=self.container,
            model="quad",
            color=color.black,
            scale=(2.0, 2.0),
            z=0.2,
        )

        # Fixed width outer card with sleek border (width: 0.52, height: 0.74)
        self.card_border = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#2f3136"),
            scale=(0.524, 0.744),
            position=(0, 0.01),
            z=0.12,
        )
        self.panel = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#1a1a1e"),
            scale=(0.52, 0.74),
            position=(0, 0.01),
            z=0.1,
        )

        # Top Title Header: ARCADE SCORE SUBMISSION (Claude accent purple/amber)
        self.title = Text(
            "ARCADE SCORE SUBMISSION",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.325),
            scale=1.42,
            color=color.hex("#f4f4f5"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
        )

        # Subtitle
        self.sub = Text(
            "Record your run into the classroom leaderboard",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.280),
            scale=0.82,
            color=color.hex("#9ca3af"),
        )

        # ---------------------------------------------------------------------
        # METRIC CAPSULES: SCORE, COINS, DISTANCE
        # 3 individual sleek capsules side-by-side with high-visibility white/colored text
        # ---------------------------------------------------------------------
        capsule_w = 0.155
        capsule_h = 0.062
        cap_y = 0.218

        # --- Capsule 1: Score Capsule (Left) ---
        self.cap_score = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#25262c"),
            scale=(capsule_w, capsule_h),
            position=(-0.165, cap_y),
            z=0.08,
        )
        self.cap_score_lbl = Text(
            "SCORE",
            parent=self.container,
            origin=(0, 0),
            position=(-0.165, cap_y + 0.014),
            scale=0.90,
            color=color.hex("#a1a1aa"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.cap_score_val = Text(
            f"{self.target_score:,}",
            parent=self.container,
            origin=(0, 0),
            position=(-0.165, cap_y - 0.012),
            scale=1.15,
            color=color.hex("#38bdf8"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # --- Capsule 2: Coins Capsule (Center) ---
        self.cap_coins = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#25262c"),
            scale=(capsule_w, capsule_h),
            position=(0.0, cap_y),
            z=0.08,
        )
        self.cap_coins_lbl = Text(
            "COINS",
            parent=self.container,
            origin=(0, 0),
            position=(0.0, cap_y + 0.014),
            scale=0.90,
            color=color.hex("#a1a1aa"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.cap_coins_val = Text(
            f"{coins}",
            parent=self.container,
            origin=(0, 0),
            position=(0.0, cap_y - 0.012),
            scale=1.15,
            color=color.hex("#facc15"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # --- Capsule 3: Distance Capsule (Right) ---
        self.cap_dist = Entity(
            parent=self.container,
            model="quad",
            color=color.hex("#25262c"),
            scale=(capsule_w, capsule_h),
            position=(0.165, cap_y),
            z=0.08,
        )
        self.cap_dist_lbl = Text(
            "DISTANCE",
            parent=self.container,
            origin=(0, 0),
            position=(0.165, cap_y + 0.014),
            scale=0.90,
            color=color.hex("#a1a1aa"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.cap_dist_val = Text(
            f"{distance:.0f}m",
            parent=self.container,
            origin=(0, 0),
            position=(0.165, cap_y - 0.012),
            scale=1.15,
            color=color.hex("#a78bfa"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # ---------------------------------------------------------------------
        # HUGE SCORE ROLL DISPLAY BELOW CAPSULES
        # Numbers rapidly increase from 0 to target score
        # ---------------------------------------------------------------------
        self.txt_score_heading = Text(
            "FINAL RUN SCORE",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.145),
            scale=0.88,
            color=color.hex("#a1a1aa"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.txt_score_num = Text(
            "0",
            parent=self.container,
            origin=(0, 0),
            position=(0, 0.095),
            scale=2.7,
            color=color.hex("#ffffff"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # ---------------------------------------------------------------------
        # STUDENT NAME INPUT
        # ---------------------------------------------------------------------
        self.lbl_name = Text(
            "Student Name",
            parent=self.container,
            origin=(-1, 0),
            position=(-0.24, 0.025),
            scale=0.90,
            color=color.hex("#f4f4f5"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.input_name = InputField(
            default_value=default_name or "Jake",
            parent=self.container,
            scale=(0.48, 0.048),
            position=(0, -0.015),
            character_limit=24,
            active=True,
        )
        self.input_name.color = color.hex("#1e1f23")
        try:
            if hasattr(self.input_name, "text_field"):
                tf = self.input_name.text_field
                tf.font = "VeraMono.ttf"
                if hasattr(tf, "text_entity") and tf.text_entity:
                    tf.text_entity.font = "VeraMono.ttf"
                    tf.text_entity.color = color.white
                    tf.text_entity.scale = 1.05
        except Exception:
            pass

        # ---------------------------------------------------------------------
        # BULLET POINTS: STACKED DIRECTLY BELOW ONE ANOTHER IN PURPLE & BLUE
        # Monospaced font, multiline wrapped prompt that never exceeds box limits
        # ---------------------------------------------------------------------
        is_sandbox = not (
            "vanilla" in prompt_summary.lower() or
            "default" in prompt_summary.lower() or
            "normal" in prompt_summary.lower()
        )
        board_name = "Sandbox" if is_sandbox else "Ranked (Vanilla)"

        raw_summary = prompt_summary.strip() or "Vanilla / Default Rules"
        import textwrap
        wrapped_lines = textwrap.wrap(raw_summary, width=26)
        if not wrapped_lines:
            wrapped_lines = ["Vanilla / Default Rules"]
        # Limit to max 2 lines so it never overflows box vertically
        if len(wrapped_lines) > 2:
            wrapped_lines = wrapped_lines[:2]
            wrapped_lines[1] = wrapped_lines[1][:23] + "..."

        prompt_multiline = "\n  ".join(wrapped_lines)

        # Purple Bullet: Board Type (Above) - Left aligned to beginning of card
        self.bullet_board = Text(
            "• Board: Global Leaderboard",
            parent=self.container,
            origin=(-0.5, 0),
            position=(-0.245, -0.060),
            scale=0.88,
            color=color.hex("#c084fc"),  # Demure/matte Purple
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # Blue Bullet: Active Prompt (Wrapped across lines, starts at left beginning of card, safely within card limits)
        self.bullet_prompt = Text(
            f"• Prompt: {prompt_multiline}",
            parent=self.container,
            origin=(-0.5, 0.5),  # Top-left anchored
            position=(-0.245, -0.088),
            scale=0.86,
            color=color.hex("#38bdf8"),  # Demure/matte Light Blue
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

        # Calculate dynamic vertical offset if prompt took 2 lines
        extra_h = 0.026 if len(wrapped_lines) > 1 else 0.0

        # ---------------------------------------------------------------------
        # ACTION BUTTONS:
        # 1. "SUBMIT RUN TO LEADERBOARD" in PURPLE (#7c3aed)
        #    Enlarged button dimensions (scale=(0.49, 0.056)) and tuned text scale (0.84)
        #    to guarantee text fits comfortably with generous internal margins
        # 2. "SKIP RUN" in BLUE (#2563eb)
        # ---------------------------------------------------------------------
        btn_sub_y = -0.165 - extra_h
        btn_skp_y = -0.230 - extra_h

        self.btn_submit = Button(
            text="",  # Use dedicated top-level text entity for 100% visibility
            parent=self.container,
            scale=(0.49, 0.056),
            position=(0, btn_sub_y),
            color=color.hex("#7c3aed"),  # Purple
            highlight_color=color.hex("#9333ea"),
        )
        self.btn_submit.radius = 0.35
        self.btn_submit_label = Text(
            "SUBMIT RUN TO LEADERBOARD (ENTER)",
            parent=self.container,
            origin=(0, 0),
            position=(0, btn_sub_y),
            scale=0.84,  # Fits cleanly inside button with clear breathing room
            color=color.white,
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.btn_submit.on_click = self.submit

        self.btn_skip = Button(
            text="",  # Use dedicated top-level text entity for 100% visibility
            parent=self.container,
            scale=(0.49, 0.048),
            position=(0, btn_skp_y),
            color=color.hex("#2563eb"),  # Blue
            highlight_color=color.hex("#3b82f6"),
        )
        self.btn_skip.radius = 0.35
        self.btn_skip_label = Text(
            "SKIP RUN (ESC)",
            parent=self.container,
            origin=(0, 0),
            position=(0, btn_skp_y),
            scale=0.92,
            color=color.white,
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )
        self.btn_skip.on_click = self.skip

        # Status feedback banner
        self.status_banner = Text(
            "",
            parent=self.container,
            origin=(0, 0),
            position=(0, -0.285 - extra_h),
            scale=0.82,
            color=color.hex("#c084fc"),
            font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
            z=-0.05,
        )

    def tick(self, dt: float) -> None:
        """Updates frame-by-frame animations: rapidly increasing score, rotating coin, and running figure."""
        if not self.is_active:
            return

        # 1. Rapidly rolling score animation
        if self.displayed_score < self.target_score:
            self.anim_timer += dt
            # Rapid tally calculation (reaches full score within 0.8 seconds)
            diff = self.target_score - self.displayed_score
            step = max(1, int(diff * min(1.0, dt * 8.0) + (self.target_score * dt * 0.9)))
            self.displayed_score = min(self.target_score, self.displayed_score + step)
            if self.txt_score_num:
                self.txt_score_num.text = f"{self.displayed_score:,}"
        elif self.txt_score_num and self.txt_score_num.text != f"{self.target_score:,}":
            self.txt_score_num.text = f"{self.target_score:,}"

        # 2. Coin rotating along vertical (Y) axis
        if self.coin_icon:
            self.coin_rot_angle = (self.coin_rot_angle + dt * 280.0) % 360.0
            import math
            cos_scale = abs(math.cos(math.radians(self.coin_rot_angle)))
            # Scale x dynamically to simulate 3D vertical axis rotation
            self.coin_icon.scale_x = max(0.02, 0.18 * cos_scale)

        # 3. Running figure animation
        if self.runner_icon:
            self.runner_anim_timer += dt
            if self.runner_anim_timer >= 0.15:
                self.runner_anim_timer = 0.0
                self.runner_frame_idx = (self.runner_frame_idx + 1) % len(self.RUNNER_FRAMES)
                self.runner_icon.text = self.RUNNER_FRAMES[self.runner_frame_idx]

    def submit(self) -> None:
        """Validates inputs and triggers callback."""
        if not self.is_active:
            return
        name = self.input_name.text.strip() if self.input_name else "Jake"
        if not name:
            name = "Jake"

        self.hide()
        self.on_submit(name, "")

    def skip(self) -> None:
        """Skips explicit submission and continues."""
        self.hide()
        if self.on_skip:
            self.on_skip()

    def handle_input(self, key: str) -> bool:
        """Handles keyboard navigation within the dialog."""
        if not self.is_active:
            return False
        if key in ("enter", "return"):
            self.submit()
            return True
        if key == "escape":
            self.skip()
            return True
        return False

    def hide(self) -> None:
        """Destroys dialog entities."""
        self.is_active = False
        if self.container:
            try:
                destroy(self.container)
            except Exception:
                pass
            self.container = None
            self.input_name = None
            self.input_roll = None
            self.status_banner = None
            self.txt_score_num = None
            self.coin_icon = None
            self.runner_icon = None


# =============================================================================
# 4. Interactive Leaderboard Screen Modal
# =============================================================================
class _RowAnim:
    """Animation track for a single leaderboard row entity."""

    def __init__(self, entity: Any, start_y: float, target_y: float,
                 duration: float = 0.45, delay: float = 0.0, is_new: bool = False) -> None:
        self.entity = entity
        self.start_y = start_y
        self.target_y = target_y
        self.duration = duration
        self.delay = delay
        self.is_new = is_new
        self.timer = 0.0
        self.done = (duration <= 0.0 and delay <= 0.0)


class LeaderboardModal:
    """Interactive Leaderboard Screen with unified all-mode rankings and Teacher CSV export.

    - Accessible via keyboard shortcut (L) or Game Over screen
    - Combines all student runs into a single unified leaderboard
    - Each row is a separate entity that dynamically slides into its rank position
    - Animated insertion: new scores climb from the bottom while displaced ranks slide down
    - Colorful podium styling (Gold #1, Cyan #2, Bronze #3, and Indigo/Violet tiers)
    - Export button for teachers
    """

    def __init__(self, game_ref: Any, on_close: Optional[Callable[[], None]] = None) -> None:
        self.game = game_ref
        self.on_close = on_close
        self.container: Optional[Entity] = None
        self.is_active = False
        self.active_tab = "ALL"       # Default "ALL" combines all runs together
        self.latest_entry_id: Optional[str] = None
        self.row_entities: List[Entity] = []
        self.row_anim_data: List[_RowAnim] = []
        self.animating = False
        self.btn_tab_ranked: Optional[Button] = None
        self.btn_tab_sandbox: Optional[Button] = None
        self.txt_export_status: Optional[Text] = None

    def show(self, initial_tab: str = "ALL", new_entry_id: Optional[str] = None) -> None:
        """Opens interactive leaderboard modal with optional animated insertion for new_entry_id."""
        self.is_active = True
        self.active_tab = initial_tab
        if new_entry_id:
            self.latest_entry_id = new_entry_id

        try:
            self.container = Entity(parent=camera.ui, z=-2)

            # ---------------------------------------------------------------------
            # THEME: Pure black backdrop (#000000) & colorful cyber neon border
            # ---------------------------------------------------------------------
            self.backdrop = Entity(
                parent=self.container,
                model="quad",
                color=color.black,
                scale=(2.0, 2.0),
                z=0.2,
            )

            # Card dimensions: width 0.58, height 0.84 with vibrant demure violet border
            self.card_border = Entity(
                parent=self.container,
                model="quad",
                color=color.hex("#4c1d95"),  # Vibrant Demure Violet Border
                scale=(0.586, 0.846),
                position=(0, 0),
                z=0.12,
            )
            self.panel = Entity(
                parent=self.container,
                model="quad",
                color=color.hex("#131318"),  # Deep Obsidian Panel
                scale=(0.58, 0.84),
                position=(0, 0),
                z=0.10,
            )

            # Cyber top neon accent stripe
            self.top_trim = Entity(
                parent=self.container,
                model="quad",
                color=color.hex("#a855f7"),  # Electric Purple Accent Stripe
                scale=(0.58, 0.004),
                position=(0, 0.420),
                z=0.08,
            )

            # Top Title: Centered, monospaced, Cyber Violet
            self.title = Text(
                "⚡ STUDENT LEADERBOARD & RANKINGS ⚡",
                parent=self.container,
                origin=(0, 0),
                position=(0, 0.370),
                scale=1.06,
                color=color.hex("#c084fc"),  # Cyber Violet
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )

            # Unified All-Modes Global Board Capsule Badge
            self.board_badge_bg = Entity(
                parent=self.container,
                model="quad",
                color=color.hex("#1e1b4b"),  # Deep Indigo
                scale=(0.380, 0.034),
                position=(0, 0.324),
                z=0.08,
            )
            self.board_badge_txt = Text(
                "★ ALL RUNS & MODES COMBINED ★",
                parent=self.container,
                origin=(0, 0),
                position=(0, 0.324),
                scale=0.74,
                color=color.hex("#a5b4fc"),  # Bright Lavender
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )

            # Table Column Headers (Directly aligned above each column)
            col_y = 0.274
            self.lbl_col_rank = Text(
                "RANK",
                parent=self.container,
                origin=(-0.5, 0),
                position=(-0.252, col_y),
                scale=0.72,
                color=color.hex("#c084fc"),  # Electric Purple
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )
            self.lbl_col_player = Text(
                "PLAYER",
                parent=self.container,
                origin=(-0.5, 0),
                position=(-0.165, col_y),
                scale=0.72,
                color=color.hex("#38bdf8"),  # Neon Cyan
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )
            self.lbl_col_score = Text(
                "SCORE",
                parent=self.container,
                origin=(0.5, 0),
                position=(0.075, col_y),
                scale=0.72,
                color=color.hex("#facc15"),  # Radiant Gold
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )
            self.lbl_col_prompt = Text(
                "MODE & PROMPT",
                parent=self.container,
                origin=(0, 0),
                position=(0.180, col_y),
                scale=0.72,
                color=color.hex("#34d399"),  # Mint Emerald
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )

            # Divider line
            self.divider = Entity(
                parent=self.container,
                model="quad",
                color=color.hex("#2f313e"),
                scale=(0.54, 0.002),
                position=(0, 0.254),
                z=0.08,
            )

            # Export Status Text
            self.txt_export_status = Text(
                "",
                parent=self.container,
                origin=(0, 0),
                position=(0, -0.288),
                scale=0.78,
                color=color.hex("#38bdf8"),
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )

            # ---------------------------------------------------------------------
            # FOOTER ACTION BUTTONS:
            # [EXPORT CSV (E)] in Demure Purple (#7c3aed)
            # [CLOSE (ESC/L)] in Demure Blue (#2563eb)
            # ---------------------------------------------------------------------
            btn_y = -0.345
            self.btn_export = Button(
                text="",
                parent=self.container,
                scale=(0.280, 0.048),
                position=(-0.130, btn_y),
                color=color.hex("#7c3aed"),  # Demure Purple
                highlight_color=color.hex("#9333ea"),
                radius=0.4,
            )
            self.btn_export_label = Text(
                "EXPORT CSV (E)",
                parent=self.container,
                origin=(0, 0),
                position=(-0.130, btn_y),
                scale=0.82,
                color=color.white,
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )
            self.btn_export.on_click = self.export_csv

            self.btn_close = Button(
                text="",
                parent=self.container,
                scale=(0.240, 0.048),
                position=(0.140, btn_y),
                color=color.hex("#2563eb"),  # Demure Blue
                highlight_color=color.hex("#3b82f6"),
                radius=0.4,
            )
            self.btn_close_label = Text(
                "CLOSE (ESC/L)",
                parent=self.container,
                origin=(0, 0),
                position=(0.140, btn_y),
                scale=0.82,
                color=color.white,
                font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                z=-0.05,
            )
            self.btn_close.on_click = self.close
        except Exception:
            from types import SimpleNamespace
            self.container = SimpleNamespace()
            self.txt_export_status = SimpleNamespace(text="", color=None)

        self.refresh_entries()

    def switch_tab(self, tab: str) -> None:
        """Toggles active tab (supports backward compatibility for unit tests)."""
        self.active_tab = tab
        if self.btn_tab_ranked and hasattr(self, "btn_tab_ranked_label") and self.btn_tab_ranked_label:
            if tab == "RANKED":
                self.btn_tab_ranked.color = color.hex("#2563eb")
                self.btn_tab_ranked.highlight_color = color.hex("#3b82f6")
                self.btn_tab_ranked_label.color = color.white
            else:
                self.btn_tab_ranked.color = color.hex("#25262c")
                self.btn_tab_ranked.highlight_color = color.hex("#3f414a")
                self.btn_tab_ranked_label.color = color.hex("#94a3b8")

        if self.btn_tab_sandbox and hasattr(self, "btn_tab_sandbox_label") and self.btn_tab_sandbox_label:
            if tab == "SANDBOX":
                self.btn_tab_sandbox.color = color.hex("#7c3aed")
                self.btn_tab_sandbox.highlight_color = color.hex("#9333ea")
                self.btn_tab_sandbox_label.color = color.white
            else:
                self.btn_tab_sandbox.color = color.hex("#25262c")
                self.btn_tab_sandbox.highlight_color = color.hex("#3f414a")
                self.btn_tab_sandbox_label.color = color.hex("#94a3b8")

        self.refresh_entries()

    def refresh_entries(self, new_entry_id: Optional[str] = None) -> None:
        """Renders leaderboard entries with animated insertion and colorful podium styling."""
        # Clean up existing entry entities
        for ent in self.row_entities:
            try:
                destroy(ent)
            except Exception:
                pass
        self.row_entities.clear()
        self.row_anim_data.clear()
        self.animating = False

        if not hasattr(self.game, "leaderboard") or self.game.leaderboard is None:
            return

        target_id = new_entry_id or self.latest_entry_id

        # Query all combined records (or tab filtered if explicitly set by a test)
        if self.active_tab == "RANKED" and hasattr(self.game.leaderboard, "get_ranked_board"):
            all_sorted = self.game.leaderboard.get_ranked_board(limit=100)
        elif self.active_tab == "SANDBOX" and hasattr(self.game.leaderboard, "get_sandbox_board"):
            all_sorted = self.game.leaderboard.get_sandbox_board(limit=100)
        elif hasattr(self.game.leaderboard, "get_all_entries"):
            all_sorted = self.game.leaderboard.get_all_entries()
        else:
            all_sorted = []

        if not all_sorted:
            try:
                no_data = Text(
                    "No student runs recorded on the leaderboard yet.\nPlay a run to set the first high score!",
                    parent=self.container,
                    origin=(0, 0),
                    position=(0, 0.05),
                    scale=0.88,
                    color=color.hex("#64748b"),
                    font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                    z=-0.05,
                )
            except Exception:
                from types import SimpleNamespace
                no_data = SimpleNamespace()
            self.row_entities.append(no_data)
            return

        # Prepare visible rows (up to 8 slots)
        max_slots = 8
        target_idx: Optional[int] = None
        if target_id:
            for idx_check, e in enumerate(all_sorted):
                e_id = getattr(e, "entry_id", None) or (e.get("entry_id") if isinstance(e, dict) else None)
                if e_id and e_id == target_id:
                    target_idx = idx_check
                    break

        if target_idx is not None and target_idx >= max_slots:
            # Include top 7 + the new player's entry at slot 8
            entries = all_sorted[:max_slots - 1] + [all_sorted[target_idx]]
            k_index = max_slots - 1
        elif target_idx is not None:
            entries = all_sorted[:max_slots]
            k_index = target_idx
        else:
            entries = all_sorted[:max_slots]
            k_index = None

        y_start = 0.222
        step_y = 0.058

        def slot_y(i: int) -> float:
            return y_start - (i * step_y)

        # ---------------------------------------------------------------------
        # Animated Placement Calculation:
        # If new player entry (k_index):
        #   - Rows above k_index stay in place
        #   - Rows below k_index start at (i-1) and slide down to (i)
        #   - The new player row climbs up from bottom of the board (-0.310) to k_index
        # Else:
        #   - Cascade entrance from slightly below
        # ---------------------------------------------------------------------
        for idx, entry in enumerate(entries):
            target_y = slot_y(idx)
            is_new = (k_index is not None and idx == k_index)

            if k_index is not None:
                if idx < k_index:
                    start_y = target_y
                    duration = 0.0
                    delay = 0.0
                elif idx == k_index:
                    start_y = -0.310  # Climb from bottom of board
                    duration = 0.65
                    delay = 0.20
                else:
                    start_y = slot_y(idx - 1)  # Shift down by one slot
                    duration = 0.42
                    delay = 0.06
            else:
                start_y = target_y - 0.035
                duration = 0.35
                delay = idx * 0.04

            # Determine real rank across all records
            e_id = getattr(entry, "entry_id", None) or (entry.get("entry_id") if isinstance(entry, dict) else None)
            real_rank = idx + 1
            for r_idx, sorted_e in enumerate(all_sorted, 1):
                s_id = getattr(sorted_e, "entry_id", None) or (sorted_e.get("entry_id") if isinstance(sorted_e, dict) else None)
                if s_id and s_id == e_id:
                    real_rank = r_idx
                    break

            player_name = getattr(entry, "student_name", "Anonymous")
            if len(player_name) > 12:
                player_name = player_name[:10] + ".."

            prompt_disp = getattr(entry, "active_prompt_summary", "Vanilla")
            if len(prompt_disp) > 11:
                prompt_disp = prompt_disp[:9] + ".."

            score_val = getattr(entry, "score", 0)

            # -----------------------------------------------------------------
            # COLORFUL PODIUM & TIER STYLING
            # -----------------------------------------------------------------
            if real_rank == 1:
                card_bg = color.hex("#272010")       # Obsidian Gold fill
                accent_col = color.hex("#f59e0b")    # Radiant Gold accent strip
                rank_str = f"👑 #{real_rank}"
                rank_col = color.hex("#fbbf24")      # Bright Gold
                name_col = color.hex("#fef08a")      # Pale Gold
                score_col = color.hex("#facc15")     # Gold Score
                pill_bg = color.hex("#451a03")       # Deep Amber pill
                pill_txt = color.hex("#fef3c7")
            elif real_rank == 2:
                card_bg = color.hex("#11222e")       # Obsidian Cyan fill
                accent_col = color.hex("#0284c7")    # Ice Blue accent strip
                rank_str = f"🥈 #{real_rank}"
                rank_col = color.hex("#7dd3fc")      # Ice Blue
                name_col = color.hex("#e0f2fe")      # Pale Ice
                score_col = color.hex("#38bdf8")     # Cyan Score
                pill_bg = color.hex("#082f49")       # Deep Ocean pill
                pill_txt = color.hex("#bae6fd")
            elif real_rank == 3:
                card_bg = color.hex("#261710")       # Obsidian Bronze fill
                accent_col = color.hex("#ea580c")    # Bronze Orange accent strip
                rank_str = f"🥉 #{real_rank}"
                rank_col = color.hex("#fb923c")      # Bronze Orange
                name_col = color.hex("#ffedd5")      # Pale Peach
                score_col = color.hex("#f97316")     # Bronze Score
                pill_bg = color.hex("#431407")       # Deep Rust pill
                pill_txt = color.hex("#fed7aa")
            else:
                card_bg = color.hex("#181922") if idx % 2 == 0 else color.hex("#1d1e28")
                accent_col = color.hex("#6366f1") if idx % 2 == 0 else color.hex("#8b5cf6")
                rank_str = f" #{real_rank:<2}"
                rank_col = color.hex("#a5b4fc")      # Lavender
                name_col = color.hex("#f1f5f9")      # Crisp Slate White
                score_col = color.hex("#ffffff")     # Pure White Score
                pill_bg = color.hex("#2e1065") if idx % 2 == 0 else color.hex("#1e293b")
                pill_txt = color.hex("#c7d2fe")

            # -----------------------------------------------------------------
            # SINGLE ROW CONTAINER ENTITY (Moves all children together)
            # -----------------------------------------------------------------
            try:
                row_container = Entity(
                    parent=self.container,
                    position=(0, start_y),
                    z=0.08,
                )

                # Vibrant highlight glow if this is the player's new run
                if is_new:
                    Entity(
                        parent=row_container,
                        model="quad",
                        color=color.hex("#fbbf24"),  # Radiant Golden Glow Border
                        scale=(0.548, 0.054),
                        position=(0, 0),
                        z=0.03,
                    )

                # Row Card Background
                Entity(
                    parent=row_container,
                    model="quad",
                    color=card_bg,
                    scale=(0.540, 0.050),
                    position=(0, 0),
                    z=0.02,
                )

                # Left Accent Strip
                Entity(
                    parent=row_container,
                    model="quad",
                    color=accent_col,
                    scale=(0.007, 0.048),
                    position=(-0.266, 0),
                    z=-0.01,
                )

                # Rank Text
                Text(
                    rank_str,
                    parent=row_container,
                    origin=(-0.5, 0),
                    position=(-0.252, 0),
                    scale=0.74,
                    color=rank_col,
                    font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                    z=-0.02,
                )

                # Player Name (tagged with ★ NEW if newly inserted)
                name_display = f"★ {player_name}" if is_new else player_name
                Text(
                    name_display,
                    parent=row_container,
                    origin=(-0.5, 0),
                    position=(-0.165, 0),
                    scale=0.74,
                    color=name_col if not is_new else color.hex("#fbbf24"),
                    font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                    z=-0.02,
                )

                # Score Text
                Text(
                    f"{score_val:,}",
                    parent=row_container,
                    origin=(0.5, 0),
                    position=(0.075, 0),
                    scale=0.74,
                    color=score_col,
                    font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                    z=-0.02,
                )

                # Mode & Prompt Capsule Pill
                Entity(
                    parent=row_container,
                    model="quad",
                    color=pill_bg,
                    scale=(0.145, 0.036),
                    position=(0.180, 0),
                    z=0.01,
                )
                Text(
                    prompt_disp,
                    parent=row_container,
                    origin=(0, 0),
                    position=(0.180, 0),
                    scale=0.66,
                    color=pill_txt,
                    font="VeraMono.ttf" if hasattr(Text, "default_font") else None,
                    z=-0.02,
                )

                # Hardware-accelerated easing in Ursina
                if hasattr(row_container, "animate"):
                    try:
                        from ursina import curve
                        row_container.animate("y", target_y, duration=duration, delay=delay, curve=curve.out_cubic)
                    except Exception:
                        pass

            except Exception:
                from types import SimpleNamespace
                row_container = SimpleNamespace(y=start_y)

            self.row_entities.append(row_container)
            self.row_anim_data.append(_RowAnim(
                entity=row_container,
                start_y=start_y,
                target_y=target_y,
                duration=duration,
                delay=delay,
                is_new=is_new,
            ))

        self.animating = True
        self.latest_entry_id = None

    def tick(self, dt: float) -> None:
        """Frame-by-frame interpolation to update row entities to their target positions."""
        if not self.is_active or not self.animating:
            return

        all_done = True
        for anim in self.row_anim_data:
            if anim.done:
                continue

            anim.timer += dt
            if anim.timer < anim.delay:
                anim.entity.y = anim.start_y
                all_done = False
                continue

            elapsed = anim.timer - anim.delay
            progress = min(1.0, elapsed / max(0.001, anim.duration))
            # Smooth cubic ease-out curve: 1 - (1 - t)^3
            ease = 1.0 - (1.0 - progress) ** 3
            anim.entity.y = anim.start_y + (anim.target_y - anim.start_y) * ease

            if progress >= 1.0:
                anim.entity.y = anim.target_y
                anim.done = True
            else:
                all_done = False

        if all_done:
            self.animating = False

    def export_csv(self) -> None:
        """Calls backend CSV export and updates status message."""
        if not hasattr(self.game, "leaderboard") or self.game.leaderboard is None:
            return
        try:
            csv_path = self.game.leaderboard.export_to_csv()
            filename = csv_path.name if hasattr(csv_path, "name") else str(csv_path)
            if self.txt_export_status:
                self.txt_export_status.text = f"✓ Exported to {filename}!"
                self.txt_export_status.color = color.hex("#38bdf8")
            if hasattr(self.game, "hud") and hasattr(self.game.hud, "show_toast"):
                self.game.hud.show_toast(f"Exported {filename} for teacher grading!", 3.0)
        except Exception as ex:
            logger.error("Failed to export leaderboard CSV: %s", ex)
            if self.txt_export_status:
                self.txt_export_status.text = f"Export failed: {ex}"
                self.txt_export_status.color = color.hex("#f87171")

    def handle_input(self, key: str) -> bool:
        """Handles keyboard shortcuts inside the leaderboard modal."""
        if not self.is_active:
            return False
        if key in ("escape", "l"):
            self.close()
            return True
        if key == "tab":
            new_tab = "RANKED" if self.active_tab == "SANDBOX" else "SANDBOX"
            self.switch_tab(new_tab)
            return True
        if key == "e":
            self.export_csv()
            return True
        return False

    def close(self) -> None:
        """Closes modal and returns to caller."""
        self.is_active = False
        self.animating = False
        for ent in self.row_entities:
            try:
                destroy(ent)
            except Exception:
                pass
        self.row_entities.clear()
        self.row_anim_data.clear()

        if self.container:
            try:
                destroy(self.container)
            except Exception:
                pass
            self.container = None
        if self.on_close:
            self.on_close()

