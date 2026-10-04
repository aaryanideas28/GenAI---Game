# Motion-Controlled Endless Runner - Vision Pipeline

**Teammate 1 (Lead Integrator & Vision Pipeline)**  
Foundation module for webcam capture, MediaPipe Pose tracking, coordinate normalization, and decoupled pub-sub event distribution.

---

## 1. Quick Start & Installation

### Requirements
- Python 3.10+
- Standard USB Webcam / Integrated Laptop Camera

### Install Dependencies
```bash
# Optional: create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS / Linux

# Install pinned dependencies
pip install -r requirements.txt
```

### Run Pipeline (Live Debug GUI)
```bash
python main.py
```
*Controls*: Press **`q`** or **`ESC`** in the window to quit cleanly.

### Automated Self-Test (No GUI)
```bash
python main.py --selftest
```
Runs a 30-frame benchmark reporting average processing FPS and pose detection rate.

---

## 2. Coordinate System & Mirroring Contract

To ensure intuitive motion controls, the camera stream is **horizontally mirrored** (`cv2.flip(frame, 1)`) before MediaPipe processing.

- **Origin `(0.0, 0.0)`**: Top-Left corner of the screen.
- **X-Axis**: Increases horizontally to the **RIGHT** (`0.0` = screen left, `0.5` = center, `1.0` = screen right).
- **Y-Axis**: Increases vertically **DOWNWARD** (`0.0` = top, `1.0` = bottom).
- **Behavior**:
  - Leaning your body to **your real-life left** moves your avatar/mid-shoulder dot to **screen left** (decreasing `mid_shoulder_x`).
  - Leaning your body to **your real-life right** moves your avatar/mid-shoulder dot to **screen right** (increasing `mid_shoulder_x`).
  - Downstream modules do **NOT** need to invert horizontal coordinates!

---

## 3. PoseFrame Schema

Every frame generates a structured `@dataclass(frozen=True)` instance:

| Field | Type | Description |
|---|---|---|
| `frame_width` | `int` | Width of camera frame (pixels) |
| `frame_height` | `int` | Height of camera frame (pixels) |
| `timestamp` | `float` | Capture timestamp (`time.time()`) |
| `pose_detected` | `bool` | `True` if pose was detected, `False` if lost/searching |
| `landmarks` | `list \| None` | Raw 33 MediaPipe `NormalizedLandmark` objects (`None` if lost) |
| `nose` | `(float, float) \| None` | Normalized `(x, y)` of nose (landmark 0) |
| `left_shoulder` | `(float, float) \| None` | Normalized `(x, y)` of left shoulder (landmark 11) |
| `right_shoulder` | `(float, float) \| None` | Normalized `(x, y)` of right shoulder (landmark 12) |
| `mid_shoulder` | `(float, float) \| None` | Normalized `((l_x + r_x)/2, (l_y + r_y)/2)` anchor point |
| `mid_shoulder_px`| `(int, int) \| None` | Pixel coordinates `(x, y)` of mid_shoulder |
| `shoulder_visibility` | `float` | `min(left_vis, right_vis)` [0.0 to 1.0] |
| `frame` | `np.ndarray \| None` | Mirrored BGR image frame |

Convert to plain dictionary at any time using: `pose_frame.to_dict()`

---

## 4. How Teammates Subscribe (5-Line Example)

Other modules (horizontal lean, jump detection, game engine) subscribe to the event bus without touching camera or OpenCV code:

```python
from event_bus import EventBus, EVENT_POSE_FRAME
from vision import PoseFrame

def on_move(frame: PoseFrame):
    if frame.pose_detected and frame.mid_shoulder:
        print(f"Player X: {frame.mid_shoulder[0]:.2f}")

bus = EventBus()
bus.subscribe(EVENT_POSE_FRAME, on_move)
```

### Event Names
- `EVENT_POSE_FRAME` (`"pose_frame"`): Dispatched every frame with current `PoseFrame`.
- `EVENT_POSE_LOST` (`"pose_lost"`): Dispatched once when player exits frame / tracking is lost.
- `EVENT_POSE_FOUND` (`"pose_found"`): Dispatched once when player re-enters frame.

---

## 5. Teammate Hand-off Guides

### Teammate 2 (Horizontal Movement)
Use helper `get_horizontal_payload(pose_frame)`:
```python
from vision import get_horizontal_payload

payload = get_horizontal_payload(pose_frame)
# Returns: {"pose_detected": bool, "mid_shoulder_x": float | None, "mid_shoulder_y": float | None, ...}

if payload["pose_detected"]:
    x = payload["mid_shoulder_x"]
    if x < 0.42:
        lane = "LEFT"
    elif x > 0.58:
        lane = "RIGHT"
    else:
        lane = "CENTER"
```

### Teammate 3 (Jump Detection)
Use `pose_frame.landmarks` with constants exported in `vision.py`:
- `LEFT_HIP` (`23`), `RIGHT_HIP` (`24`)
- `LEFT_KNEE` (`25`), `RIGHT_KNEE` (`26`)
- `LEFT_ANKLE` (`27`), `RIGHT_ANKLE` (`28`)
- Compare vertical coordinates (`landmark.y`) against calibrated standing baselines.
