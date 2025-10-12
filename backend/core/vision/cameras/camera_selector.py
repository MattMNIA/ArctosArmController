import cv2
from typing import List, Optional


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
def select_camera_index(
    preferred_index: Optional[int] = None,
    max_index: int = 8,
) -> int:
    """Return the default camera index without prompting the user."""
    available = list_available_cameras(max_index)
    if not available:
        raise RuntimeError("No cameras detected. Connect a camera and try again.")

    if preferred_index is not None and preferred_index in available:
        return preferred_index

    if 0 in available:
        return 0

    return available[0]
