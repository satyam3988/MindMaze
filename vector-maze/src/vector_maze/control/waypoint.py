"""Turn in place, then drive toward successive world-space waypoints."""

from math import atan2, hypot, isfinite, pi
from typing import Sequence

from vector_maze.models import Point, Pose2D, VelocityCommand


class WaypointController:
    """Bounded proportional controller; no simulator or robot dependencies."""

    def __init__(
        self,
        speed: float = 0.12,
        turn_speed: float = 2.5,
        tolerance: float = 0.002,
        heading_tolerance: float = 0.02,
    ) -> None:
        if any(
            not isfinite(v) or v <= 0 for v in (speed, turn_speed, tolerance, heading_tolerance)
        ):
            raise ValueError("Controller parameters must be finite and positive")
        self.speed = speed
        self.turn_speed = turn_speed
        self.tolerance = tolerance
        self.heading_tolerance = heading_tolerance
        self._path: tuple[Point, ...] = ()
        self._index = 0

    def set_path(self, path: Sequence[Point]) -> None:
        if any(not all(isfinite(v) for v in p) for p in path):
            raise ValueError("Waypoints must be finite")
        self._path = tuple(path)
        self._index = 0

    @property
    def finished(self) -> bool:
        return self._index >= len(self._path)

    @property
    def waypoint_index(self) -> int:
        """Current zero-based waypoint index for runtime diagnostics."""
        return self._index

    @property
    def current_waypoint(self) -> Point | None:
        """Current target, or None after completion; does not alter control."""
        return None if self.finished else self._path[self._index]

    def update(self, pose: Pose2D, dt: float) -> VelocityCommand:
        """Calculate the next command, limiting travel to the waypoint distance."""
        if not isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        while not self.finished:
            target = self._path[self._index]
            dx, dy = target[0] - pose.x, target[1] - pose.y
            distance = hypot(dx, dy)
            if distance <= self.tolerance:
                self._index += 1
                continue
            error = (atan2(dy, dx) - pose.heading + pi) % (2 * pi) - pi
            if abs(error) > self.heading_tolerance:
                angular = max(-self.turn_speed, min(self.turn_speed, error / dt))
                return VelocityCommand(angular=angular)
            return VelocityCommand(linear=min(self.speed, distance / dt))
        return VelocityCommand()
