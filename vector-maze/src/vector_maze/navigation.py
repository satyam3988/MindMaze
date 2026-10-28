"""Core navigation orchestration. This module never imports simulation."""

import logging

from vector_maze.control.waypoint import WaypointController
from vector_maze.interfaces import LocalizationProvider, PathPlanner, RobotController
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Cell

logger = logging.getLogger(__name__)


class MazeNavigator:
    """Plan once against a footprint-safe map, then track the path using adapters."""

    def __init__(
        self,
        grid: OccupancyGrid,
        localization: LocalizationProvider,
        planner: PathPlanner,
        controller: WaypointController,
        robot: RobotController,
        radius: float,
    ) -> None:
        self.grid = grid
        self.localization = localization
        self.planner = planner
        self.controller = controller
        self.robot = robot
        self.radius = radius
        self.path: list[Cell] = []

    def plan_to(self, goal: Cell) -> list[Cell]:
        """Stop before replanning; an unreachable goal leaves the robot stopped."""
        self.robot.stop()
        self.path = []
        self.controller.set_path([])
        pose = self.localization.get_pose()
        if self.grid.collides((pose.x, pose.y), self.radius):
            raise ValueError("Localized robot footprint is in collision")
        start = self.grid.world_to_cell((pose.x, pose.y))
        safe_grid = self.grid.for_robot(self.radius)
        path = self.planner.plan(safe_grid, start, goal)
        points = [self.grid.cell_center(cell) for cell in path]
        if points and self.grid.sweep_collides((pose.x, pose.y), points[0], self.radius):
            raise ValueError("Cannot safely move to the start cell center")
        if any(self.grid.sweep_collides(a, b, self.radius) for a, b in zip(points, points[1:])):
            raise ValueError("Planned path lacks robot clearance")
        self.path = path
        self.controller.set_path(points)
        logger.info("Planned %d waypoints", len(path))
        return path

    @property
    def reached_goal(self) -> bool:
        return bool(self.path) and self.controller.finished

    def tick(self, dt: float) -> None:
        """Read localization and send velocity; the runtime advances simulation."""
        command = self.controller.update(self.localization.get_pose(), dt)
        self.robot.command_velocity(command)
