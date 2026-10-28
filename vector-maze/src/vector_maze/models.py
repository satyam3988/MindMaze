"""Shared data contracts; coordinates and distances are in meters."""

from dataclasses import dataclass
from math import isfinite

Cell = tuple[int, int]  # (column, row)
Point = tuple[float, float]


@dataclass(frozen=True)
class Pose2D:
    """World pose: x right, y down, heading clockwise in radians."""

    x: float
    y: float
    heading: float = 0.0

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.x, self.y, self.heading)):
            raise ValueError("Pose must contain finite values")


@dataclass(frozen=True)
class VelocityCommand:
    """Forward speed (m/s) and clockwise angular speed (rad/s)."""

    linear: float = 0.0
    angular: float = 0.0

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.linear, self.angular)):
            raise ValueError("Velocity must contain finite values")


@dataclass(frozen=True)
class CameraFrame:
    """Packed row-major RGB bytes plus capture time in seconds."""

    width: int
    height: int
    rgb: bytes
    timestamp: float
