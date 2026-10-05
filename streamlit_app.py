"""
SUBWAY SURFERS GESTURE CONTROLLER – EXHIBITION UI
==================================================

Launch:
    streamlit run streamlit_app.py

Sidebar controls:
  * Natural-language prompt box → GuardrailEngine → PowerUpManager
  * Manual power-up activation buttons
  * Live HUD: active power-ups with countdown bars
  * Security / warning banner on blocked prompts

Main panel:
  * Live webcam feed with pose skeleton overlay
  * Game-state telemetry (FPS, lane, last action, active power-ups)
  * Per-power-up HUD badges with timer arcs

The app runs the VisionPipeline in a background thread and pushes
PoseFrames into Streamlit's session state for rendering.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import streamlit as st
from dotenv import load_dotenv

# Load API key from secure.env
load_dotenv("secure.env")

# Local modules
from event_bus import EventBus
from game_events import (
    EVENT_FRAME,
    EVENT_JUMP,
    EVENT_LANE_CHANGE,
    EVENT_ROLL,
    FrameEvent,
    GameEventDispatcher,
    JumpEvent,
    LaneChangeEvent,
    RollEvent,
)
from guardrail import GuardrailEngine, GuardrailResult
from main import build_bus, load_teammate_modules
from powerups import PowerUpManager, PowerUpName
from vision import (
    DEFAULT_CAMERA_INDEX,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_MODEL_COMPLEXITY,
    VisionPipeline,
    PoseFrame,
)

# ---------------------------------------------------------------------------
# Page config – must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Subway Surfers · Gesture Controller",
    page_icon="🛹",
    layout="wide",
    initial_sidebar_state="expanded",
)

logger = logging.getLogger("streamlit_app")

# ---------------------------------------------------------------------------
# Custom CSS – dark neon aesthetic
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;900&display=swap');

/* ---- Root variables ---- */
:root {
    --bg:        #0d0f1a;
    --surface:   #151829;
    --card:      #1c2040;
    --border:    #2a3060;
    --neon-blue: #00d4ff;
    --neon-pink: #ff2d78;
    --neon-gold: #ffd54f;
    --neon-grn:  #00ff99;
    --neon-pur:  #c678ff;
    --text:      #e8eaf6;
    --subtext:   #8892b0;
    --radius:    12px;
}

/* ---- Global ---- */
html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Outfit', sans-serif !important;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}

/* ---- Headings ---- */
h1 { color: var(--neon-blue) !important; letter-spacing: 1px; font-weight: 900; }
h2, h3 { color: var(--text) !important; font-weight: 700; }

/* ---- Text area & Input ---- */
textarea, input[type="text"] {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: var(--radius) !important;
    font-family: 'Outfit', sans-serif !important;
}

/* ---- Buttons ---- */
button[kind="primary"], .stButton > button {
    background: linear-gradient(135deg, #1a3aff 0%, var(--neon-blue) 100%) !important;
    border: none !important; border-radius: 8px !important;
    color: #fff !important; font-weight: 700 !important;
    transition: transform 0.15s, box-shadow 0.15s !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 0 20px rgba(0,212,255,0.5) !important;
}

/* ---- Metrics ---- */
[data-testid="stMetric"] {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 12px !important;
}
[data-testid="stMetricLabel"] { color: var(--subtext) !important; }
[data-testid="stMetricValue"] { color: var(--neon-blue) !important; font-weight: 700; }

/* ---- Progress bar ---- */
.stProgress > div > div { background: var(--neon-blue) !important; }

/* ---- Warning / success banners ---- */
.banner-warn {
    background: linear-gradient(90deg, #ff2d7833, #ff2d7811);
    border: 1px solid var(--neon-pink);
    border-radius: var(--radius);
    padding: 14px 18px;
    color: var(--neon-pink);
    font-weight: 600;
    animation: pulse 1s ease-in-out infinite alternate;
}
.banner-ok {
    background: linear-gradient(90deg, #00ff9933, #00ff9911);
    border: 1px solid var(--neon-grn);
    border-radius: var(--radius);
    padding: 14px 18px;
    color: var(--neon-grn);
    font-weight: 600;
}
@keyframes pulse {
    from { box-shadow: 0 0 8px #ff2d7880; }
    to   { box-shadow: 0 0 24px #ff2d78cc; }
}

/* ---- Power-up badges ---- */
.pu-badge {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 13px;
    margin: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.pu-active   { background: #00d4ff22; border: 1px solid var(--neon-blue); color: var(--neon-blue); }
.pu-inactive { background: #ffffff11; border: 1px solid #444;             color: #666; }

/* ---- Card container ---- */
.game-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 12px;
}

/* ---- Scrollbar ---- */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _ss_default(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def _init_session() -> None:
    _ss_default("pipeline_started", False)
    _ss_default("latest_frame", None)          # np.ndarray BGR
    _ss_default("latest_pose", None)           # PoseFrame
    _ss_default("fps", 0.0)
    _ss_default("current_lane", "CENTER")
    _ss_default("last_action", "-")
    _ss_default("last_action_time", 0.0)
    _ss_default("hud_powerups", [])
    _ss_default("guardrail_result", None)
    _ss_default("guardrail_history", [])
    _ss_default("game_params", {})
    _ss_default("pipeline_thread", None)
    _ss_default("bus", None)
    _ss_default("dispatcher", None)
    _ss_default("powerup_manager", None)
    _ss_default("guardrail_engine", None)
    _ss_default("pipeline", None)
    _ss_default("stop_event", None)


_init_session()


# ---------------------------------------------------------------------------
# Power-up metadata for the UI
# ---------------------------------------------------------------------------
POWERUP_META: Dict[str, Dict[str, str]] = {
    "CoinMagnet":      {"icon": "🧲", "color": "#ffd54f", "label": "Coin Magnet"},
    "Jetpack":         {"icon": "🚀", "color": "#00d4ff", "label": "Jetpack"},
    "SuperSneakers":   {"icon": "👟", "color": "#00ff99", "label": "Super Sneakers"},
    "ScoreMultiplier": {"icon": "×2", "color": "#ff2d78", "label": "2× Multiplier"},
    "Hoverboard":      {"icon": "🛹", "color": "#c678ff", "label": "Hoverboard"},
    "Shield":          {"icon": "🛡️", "color": "#ff9800", "label": "Shield"},
}


# ---------------------------------------------------------------------------
# Background vision thread
# ---------------------------------------------------------------------------
def _vision_thread(stop_evt: threading.Event,
                   pipeline: VisionPipeline,
                   bus: EventBus,
                   dispatcher: GameEventDispatcher) -> None:
    """Runs in a daemon thread: captures frames, publishes to bus."""
    from event_bus import EVENT_POSE_FOUND, EVENT_POSE_LOST, EVENT_POSE_FRAME
    prev_detected: Optional[bool] = None
    try:
        while not stop_evt.is_set():
            pf: Optional[PoseFrame] = pipeline.read()
            if pf is None:
                continue

            # Update Streamlit session state (best-effort, no lock needed for reads)
            st.session_state.latest_frame = pf.frame
            st.session_state.latest_pose  = pf
            st.session_state.fps          = pipeline.get_fps()

            bus.publish(EVENT_POSE_FRAME, pf)

            detected = pf.pose_detected
            if prev_detected is not None and detected != prev_detected:
                bus.publish(EVENT_POSE_FOUND if detected else EVENT_POSE_LOST, pf)
            elif prev_detected is None and detected:
                bus.publish(EVENT_POSE_FOUND, pf)
            prev_detected = detected
    except Exception:           # noqa: BLE001
        logger.exception("Vision thread crashed.")


def _start_pipeline() -> None:
    """Initialise and start the vision + event infrastructure."""
    if st.session_state.pipeline_started:
        return

    bus        = EventBus()
    dispatcher = GameEventDispatcher()
    dispatcher.connect(bus)
    manager    = PowerUpManager(dispatcher)
    engine     = GuardrailEngine()

    # Wire dispatcher callbacks into session state for the UI
    def _on_frame(ev: FrameEvent) -> None:
        st.session_state.fps = ev.fps
        hud = manager.hud_state()
        st.session_state.hud_powerups = hud

    def _on_jump(ev: JumpEvent) -> None:
        st.session_state.last_action      = "JUMP 🦘"
        st.session_state.last_action_time = time.time()

    def _on_roll(ev: RollEvent) -> None:
        st.session_state.last_action      = "ROLL 🔄"
        st.session_state.last_action_time = time.time()

    def _on_lane(ev: LaneChangeEvent) -> None:
        st.session_state.current_lane = ev.lane

    dispatcher.on(EVENT_FRAME,       _on_frame)
    dispatcher.on(EVENT_JUMP,        _on_jump)
    dispatcher.on(EVENT_ROLL,        _on_roll)
    dispatcher.on(EVENT_LANE_CHANGE, _on_lane)

    load_teammate_modules(bus)

    pipeline  = VisionPipeline(
        camera_index=DEFAULT_CAMERA_INDEX,
        width=DEFAULT_FRAME_WIDTH,
        height=DEFAULT_FRAME_HEIGHT,
        model_complexity=DEFAULT_MODEL_COMPLEXITY,
    )
    pipeline.start()

    stop_evt = threading.Event()
    t = threading.Thread(
        target=_vision_thread,
        args=(stop_evt, pipeline, bus, dispatcher),
        daemon=True,
        name="vision-streamlit",
    )
    t.start()

    st.session_state.bus              = bus
    st.session_state.dispatcher       = dispatcher
    st.session_state.powerup_manager  = manager
    st.session_state.guardrail_engine = engine
    st.session_state.pipeline         = pipeline
    st.session_state.pipeline_thread  = t
    st.session_state.stop_event       = stop_evt
    st.session_state.pipeline_started = True
    logger.info("Vision pipeline started via Streamlit.")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🎮 Gesture Controller")
        st.caption("Subway Surfers · Exhibition Build")
        st.divider()

        # ── Camera control ────────────────────────────────────────────
        st.markdown("### 📷 Camera")
        if not st.session_state.pipeline_started:
            if st.button("▶ Start Camera", use_container_width=True, type="primary"):
                try:
                    _start_pipeline()
                    st.success("Camera started!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to start camera: {exc}")
        else:
            st.success("✅ Camera running")
            if st.button("⏹ Stop Camera", use_container_width=True):
                _stop_pipeline()
                st.info("Camera stopped.")
                st.rerun()

        st.divider()

        # ── AI Prompt Guardrail ───────────────────────────────────────
        st.markdown("### 🤖 AI Game Parameter Prompt")
        st.caption("Describe game changes in plain English. The AI will validate and apply them safely.")

        prompt_input = st.text_area(
            "Your request",
            placeholder='e.g. "Set speed to 8 and activate jetpack"',
            height=100,
            key="prompt_input",
            label_visibility="collapsed",
        )

        col_send, col_clear = st.columns([3, 1])
        with col_send:
            send_clicked = st.button("🚀 Send to AI", use_container_width=True,
                                     type="primary", key="btn_send")
        with col_clear:
            if st.button("🗑", use_container_width=True, key="btn_clear"):
                st.session_state.guardrail_result = None
                st.rerun()

        if send_clicked and prompt_input.strip():
            engine: Optional[GuardrailEngine] = st.session_state.guardrail_engine
            if engine is None:
                # Engine not yet initialised (pipeline not started)
                engine = GuardrailEngine()
                st.session_state.guardrail_engine = engine

            with st.spinner("AI validating…"):
                result: GuardrailResult = engine.evaluate(prompt_input.strip())

            st.session_state.guardrail_result = result

            # Apply params if allowed
            if result.allowed:
                _apply_params(result)

            # Log to history
            st.session_state.guardrail_history.insert(0, {
                "prompt": prompt_input.strip(),
                "allowed": result.allowed,
                "reason": result.reason,
                "ts": time.strftime("%H:%M:%S"),
            })
            st.session_state.guardrail_history = st.session_state.guardrail_history[:10]
            st.rerun()

        # Guardrail result banner
        result: Optional[GuardrailResult] = st.session_state.guardrail_result
        if result is not None:
            if result.allowed:
                st.markdown(
                    f'<div class="banner-ok">✅ ALLOWED — {result.reason}</div>',
                    unsafe_allow_html=True,
                )
                if result.params.model_dump(exclude_none=True):
                    st.caption(f"Applied: `{result.params.model_dump(exclude_none=True)}`")
            else:
                st.markdown(
                    f'<div class="banner-warn">⚠ BLOCKED [{result.threat_level}]<br/>'
                    f'{result.reason}</div>',
                    unsafe_allow_html=True,
                )
            st.caption(f"⏱ Latency: {result.latency_ms:.0f} ms")

        # History
        if st.session_state.guardrail_history:
            with st.expander("📜 Prompt history", expanded=False):
                for entry in st.session_state.guardrail_history:
                    icon = "✅" if entry["allowed"] else "⛔"
                    st.markdown(
                        f"`{entry['ts']}` {icon} **{entry['prompt'][:60]}**\n\n"
                        f"&nbsp;&nbsp;&nbsp;_{entry['reason']}_",
                        unsafe_allow_html=True,
                    )

        st.divider()

        # ── Manual power-up buttons ───────────────────────────────────
        st.markdown("### ⚡ Power-Ups")
        st.caption("Manually activate power-ups for demonstration.")

        manager: Optional[PowerUpManager] = st.session_state.powerup_manager

        for pu_name, meta in POWERUP_META.items():
            is_active = manager.is_active(PowerUpName(pu_name)) if manager else False
            label = f"{meta['icon']} {meta['label']}"
            if is_active:
                rem = manager.remaining(PowerUpName(pu_name)) if manager else 0
                label += f" ({rem:.0f}s)"

            if st.button(label, use_container_width=True,
                         key=f"btn_pu_{pu_name}",
                         type="primary" if is_active else "secondary"):
                if manager:
                    if is_active:
                        manager.deactivate(PowerUpName(pu_name))
                    else:
                        manager.activate(PowerUpName(pu_name))
                    st.rerun()


# ---------------------------------------------------------------------------
# Param applicator
# ---------------------------------------------------------------------------
def _apply_params(result: GuardrailResult) -> None:
    """Apply validated params to game session state and manager."""
    p = result.params
    manager: Optional[PowerUpManager] = st.session_state.powerup_manager

    params_changed: Dict[str, Any] = {}

    if p.game_speed is not None:
        st.session_state.game_params["game_speed"] = p.game_speed
        if manager:
            manager.speed_multiplier = p.game_speed / 5.0  # normalize: 5.0 = ×1.0
        params_changed["game_speed"] = p.game_speed

    if p.score_multiplier is not None:
        st.session_state.game_params["score_multiplier"] = p.score_multiplier
        if manager:
            manager.score_multiplier = int(p.score_multiplier)
        params_changed["score_multiplier"] = p.score_multiplier

    if p.powerup is not None and manager:
        try:
            manager.activate(PowerUpName(p.powerup))
            params_changed["powerup_activated"] = p.powerup
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not activate power-up %r: %s", p.powerup, exc)

    # Store remaining params for the game engine
    for field_ in ("gravity", "jump_height", "coin_density",
                   "obstacle_density", "magnet_radius", "theme_color"):
        val = getattr(p, field_, None)
        if val is not None:
            st.session_state.game_params[field_] = val
            params_changed[field_] = val

    if params_changed:
        logger.info("[App] Applied params: %s", params_changed)


def _stop_pipeline() -> None:
    stop: Optional[threading.Event] = st.session_state.stop_event
    if stop:
        stop.set()
    pipeline: Optional[VisionPipeline] = st.session_state.pipeline
    if pipeline:
        pipeline.stop()
    st.session_state.pipeline_started = False


# ---------------------------------------------------------------------------
# Main panel helpers
# ---------------------------------------------------------------------------
def _frame_to_jpeg_bytes(frame: np.ndarray) -> bytes:
    """Encode numpy BGR frame as JPEG bytes for st.image."""
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return b""
    return buf.tobytes()


def _draw_hud_on_frame(frame: np.ndarray,
                        hud: List[Dict[str, Any]],
                        pipeline: Optional[VisionPipeline],
                        pose: Optional[PoseFrame]) -> np.ndarray:
    """Overlay skeleton + HUD badges onto the camera frame."""
    if pipeline is not None and pose is not None:
        overlay_lines = []
        for entry in hud:
            rem = entry.get("remaining_s", 0)
            rem_str = f"{rem:.0f}s" if rem < float("inf") else "∞"
            overlay_lines.append(f"{entry['name']}: {rem_str}")
        frame = pipeline.draw_debug(frame, pose, overlay_lines)
    return frame


def render_powerup_hud(hud: List[Dict[str, Any]]) -> None:
    """Render power-up badge row + progress bars."""
    active_names = {e["name"] for e in hud}

    badge_html = ""
    for pu_name, meta in POWERUP_META.items():
        cls = "pu-active" if pu_name in active_names else "pu-inactive"
        badge_html += (
            f'<span class="pu-badge {cls}" '
            f'style="border-color:{meta["color"]};color:{meta["color"] if pu_name in active_names else "#555"}">'
            f'{meta["icon"]} {meta["label"]}</span>'
        )
    st.markdown(f'<div style="margin-bottom:8px">{badge_html}</div>',
                unsafe_allow_html=True)

    # Progress bars for active power-ups
    for entry in hud:
        meta = POWERUP_META.get(entry["name"], {"icon": "⚡", "label": entry["name"], "color": "#fff"})
        rem  = entry.get("remaining_s", 0)
        frac = entry.get("fraction", 1.0)
        rem_str = f"{rem:.1f}s" if rem < float("inf") else "∞"
        st.markdown(
            f"<small style='color:{meta['color']}'>"
            f"{meta['icon']} **{meta['label']}** — {rem_str} remaining</small>",
            unsafe_allow_html=True,
        )
        if frac < float("inf"):
            st.progress(min(frac, 1.0))


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
def main() -> None:
    # ── Header ──────────────────────────────────────────────────────
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:4px'>🛹 Subway Surfers</h1>"
        "<p style='text-align:center;color:#8892b0;margin-top:0'>Gesture-Controlled · AI Guardrail · Live Power-Ups</p>",
        unsafe_allow_html=True,
    )

    render_sidebar()

    # ── Top metrics row ──────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    fps    = st.session_state.fps
    lane   = st.session_state.current_lane
    action = st.session_state.last_action
    a_time = st.session_state.last_action_time
    action_display = action if time.time() - a_time < 2.0 else "–"
    hud    = st.session_state.hud_powerups
    n_active = len(hud)
    manager: Optional[PowerUpManager] = st.session_state.powerup_manager
    score_mult = manager.score_multiplier if manager else 1
    speed_mult = f"×{manager.speed_multiplier:.1f}" if manager else "×1.0"

    c1.metric("📷 FPS",          f"{fps:.1f}")
    c2.metric("🛤 Lane",         lane)
    c3.metric("🎮 Last Action",  action_display)
    c4.metric("⚡ Active PUs",   n_active)
    c5.metric("×Score",         f"×{score_mult}")

    st.divider()

    # ── Main content: camera + HUD ───────────────────────────────────
    col_cam, col_hud = st.columns([3, 2])

    with col_cam:
        st.markdown("#### 📹 Live Camera Feed")
        camera_placeholder = st.empty()

        frame = st.session_state.latest_frame
        pose  = st.session_state.latest_pose
        pipeline: Optional[VisionPipeline] = st.session_state.pipeline

        if frame is not None:
            annotated = _draw_hud_on_frame(frame.copy(), hud, pipeline, pose)
            camera_placeholder.image(
                _frame_to_jpeg_bytes(annotated),
                channels="BGR",
                use_container_width=True,
                caption=f"FPS: {fps:.1f} | Pose: {'✅' if (pose and pose.pose_detected) else '❌'}",
            )
        else:
            camera_placeholder.markdown(
                '<div style="background:#151829;border:1px dashed #2a3060;'
                'border-radius:12px;padding:80px;text-align:center;color:#444">'
                '<div style="font-size:64px">📷</div>'
                '<div style="margin-top:12px">Camera not started<br/>'
                '<small>Click ▶ Start Camera in the sidebar</small></div>'
                '</div>',
                unsafe_allow_html=True,
            )

        # Auto-refresh while running
        if st.session_state.pipeline_started:
            time.sleep(0.033)   # ~30 FPS refresh cap
            st.rerun()

    with col_hud:
        st.markdown("#### ⚡ Power-Up HUD")
        render_powerup_hud(hud)

        st.divider()

        st.markdown("#### 🧠 AI Guardrail Status")
        result: Optional[GuardrailResult] = st.session_state.guardrail_result
        if result is None:
            st.caption("No prompt evaluated yet. Use the sidebar to send an AI prompt.")
        else:
            status_color = "#00ff99" if result.allowed else "#ff2d78"
            status_label = "ALLOWED ✅" if result.allowed else f"BLOCKED ⚠ [{result.threat_level}]"
            st.markdown(
                f"<div class='game-card'>"
                f"<div style='color:{status_color};font-weight:700;font-size:16px'>{status_label}</div>"
                f"<div style='margin-top:8px;color:#ccc'>{result.reason}</div>"
                f"<div style='margin-top:8px;color:#666;font-size:12px'>"
                f"⏱ {result.latency_ms:.0f}ms | Raw: <em>{result.raw_prompt[:60]}{'...' if len(result.raw_prompt) > 60 else ''}</em>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

        st.divider()

        st.markdown("#### 🎛 Active Game Parameters")
        params = st.session_state.game_params
        if params:
            for k, v in params.items():
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;"
                    f"padding:6px 0;border-bottom:1px solid #2a3060'>"
                    f"<span style='color:#8892b0'>{k}</span>"
                    f"<span style='color:#00d4ff;font-weight:700'>{v}</span></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No parameters applied yet.")

        st.divider()

        st.markdown("#### 📊 Vision Telemetry")
        if pose is not None and pose.pose_detected:
            ms = pose.mid_shoulder
            sw = pose.shoulder_width
            st.code(
                f"mid_shoulder: ({ms[0]:.3f}, {ms[1]:.3f})\n"
                f"shoulder_width: {sw:.3f}\n"
                f"visibility: {pose.shoulder_visibility:.2f}\n"
                f"lane: {lane}\n"
                f"speed_mult: {speed_mult}",
                language="yaml",
            )
        else:
            st.caption("No pose detected.")


if __name__ == "__main__":
    main()
