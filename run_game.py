"""Launch the 3D Subway Surfers runner with integrated OpenCV gesture tracking.

    python run_game.py                 # Play with webcam motion gestures + keyboard
    python run_game.py --windowed      # 1280x720 window
    python run_game.py --cv-window     # Show OpenCV debug camera window alongside game
    python run_game.py --no-vision     # Keyboard-only mode
"""

import sys
from controller import start_vision_thread, stop_vision_thread
from game.runner import main

if __name__ == "__main__":
    if "--no-vision" not in sys.argv:
        show_feed = "--cv-window" in sys.argv
        start_vision_thread(show_feed=show_feed)

    try:
        main()
    finally:
        stop_vision_thread()
