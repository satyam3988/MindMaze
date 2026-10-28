"""Hardware-independent extension points for simulation and physical adapters."""

from abc import ABC, abstractmethod

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Cell, Pose2D, VelocityCommand


class CameraSource(ABC):
    @abstractmethod
    def capture(self) -> CameraFrame:
        """Capture a calibrated-source RGB frame."""


class RobotController(ABC):
    @abstractmethod
    def command_velocity(self, command: VelocityCommand) -> None:
        """Set desired velocity until the next command; adapters enforce limits."""

    def stop(self) -> None:
        """Request zero velocity."""
        self.command_velocity(VelocityCommand())


class LocalizationProvider(ABC):
    @abstractmethod
    def get_pose(self) -> Pose2D:
        """Return the latest pose in the shared world frame."""


class PathPlanner(ABC):
    @abstractmethod
    def plan(self, grid: OccupancyGrid, start: Cell, goal: Cell) -> list[Cell]:
        """Return an endpoint-inclusive path, or [] when no path exists."""
