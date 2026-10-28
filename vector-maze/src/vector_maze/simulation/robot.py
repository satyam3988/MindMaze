"""Circular robot with bounded velocity and swept collision detection."""

import logging
from math import cos, isfinite, pi, sin

from vector_maze.interfaces import RobotController
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Pose2D, VelocityCommand

logger = logging.getLogger(__name__)


class SimulatedRobot(RobotController):
    """Discrete rotate-then-translate integration with fail-stop collisions."""

    def __init__(
        self,
        grid: OccupancyGrid,
        pose: Pose2D,
        radius: float = 0.025,
        max_speed: float = 0.2,
        max_turn_speed: float = 3.0,
    ) -> None:
        if any(not isfinite(v) or v <= 0 for v in (radius, max_speed, max_turn_speed)):
            raise ValueError("Robot dimensions and limits must be finite and positive")
        if grid.collides((pose.x, pose.y), radius):
            raise ValueError("Initial robot footprint is in collision")
        self.grid = grid
        self.pose = pose
        self.radius = radius
        self.max_speed = max_speed
        self.max_turn_speed = max_turn_speed
        self.command = VelocityCommand()
        self.collision_count = 0

    def command_velocity(self, command: VelocityCommand) -> None:
        self.command = VelocityCommand(
            max(-self.max_speed, min(self.max_speed, command.linear)),
            max(-self.max_turn_speed, min(self.max_turn_speed, command.angular)),
        )

    def step(self, dt: float) -> bool:
        """Advance by dt seconds; reject entire translation on collision."""
        if not isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        heading = (self.pose.heading + self.command.angular * dt + pi) % (2 * pi) - pi
        start = (self.pose.x, self.pose.y)
        end = (
            start[0] + cos(heading) * self.command.linear * dt,
            start[1] + sin(heading) * self.command.linear * dt,
        )
        if self.grid.sweep_collides(start, end, self.radius):
            self.collision_count += 1
            self.stop()
            self.pose = Pose2D(*start, heading)
            logger.warning("Motion rejected: collision at proposed position %s", end)
            return False
        self.pose = Pose2D(*end, heading)
        return True
