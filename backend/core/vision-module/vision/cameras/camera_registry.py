from typing import Dict, Type

class CameraRegistry:
    """Manages the registration and retrieval of camera instances."""

    def __init__(self) -> None:
        self._cameras: Dict[str, Type] = {}

    def register_camera(self, name: str, camera_class: Type) -> None:
        """Register a camera class with a given name."""
        if name in self._cameras:
            raise ValueError(f"Camera '{name}' is already registered.")
        self._cameras[name] = camera_class

    def get_camera(self, name: str) -> Type:
        """Retrieve a registered camera class by name."""
        camera_class = self._cameras.get(name)
        if camera_class is None:
            raise ValueError(f"Camera '{name}' is not registered.")
        return camera_class

    def list_cameras(self) -> Dict[str, Type]:
        """List all registered cameras."""
        return self._cameras.copy()