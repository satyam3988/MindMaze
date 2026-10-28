from abc import ABC, abstractmethod

from robotic_mind_sdk.models import Position


class RobotAdapter(ABC):
    @abstractmethod
    def get_pose(self) -> Position: ...

    @abstractmethod
    def move_to(self, target: Position, dt: float) -> bool:
        """Move continuously; return True when the target is reached."""

    @abstractmethod
    def stop(self): ...

    @abstractmethod
    def capture_camera(self):
        """Return a BGR numpy image, or None."""

    @abstractmethod
    def capabilities(self) -> list[str]: ...
