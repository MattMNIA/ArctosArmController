import cv2
from typing import List, Optional, Sequence


def _probe_camera(index: int) -> bool:
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap or not cap.isOpened():
        if cap:
            cap.release()
        return False
    cap.release()
    return True


def list_available_cameras(max_index: int = 8) -> List[int]:
    """Return a list of camera indexes that can be opened."""
    available = []
    for idx in range(max_index):
        if _probe_camera(idx):
            available.append(idx)
    return available


def _choose_from_user(options: Sequence[int], default: int) -> int:
    options_str = ", ".join(str(opt) for opt in options)
    print("Multiple cameras detected: " + options_str)
    prompt = f"Select camera index [{default}]: "
    while True:
        try:
            choice = input(prompt).strip()
        except EOFError:
            print("No selection received; using default camera index" f" {default}.")
            return default
        if not choice:
            return default
        if choice.lstrip("-+").isdigit():
            selected = int(choice)
            if selected in options:
                return selected
        print("Invalid selection. Choose one of: " + options_str)


def select_camera_index(
    preferred_index: Optional[int] = None,
    max_index: int = 8,
) -> int:
    """Detect and optionally prompt the user to choose a camera index."""
    available = list_available_cameras(max_index)
    if not available:
        raise RuntimeError("No cameras detected. Connect a camera and try again.")

    if len(available) == 1:
        index = available[0]
        print(f"Using camera index {index} (only available option).")
        return index

    default = preferred_index if preferred_index in available else available[0]
    return _choose_from_user(available, default)
