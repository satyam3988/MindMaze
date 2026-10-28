"""Project x-right/y-down to Webots ENU (Z up); all angles in radians."""

from math import atan2, pi
from typing import Sequence

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Cell, Point, Pose2D


def project_to_webots(point: Point, height: float = 0.0) -> tuple[float, float, float]:
    """Shared origin: (x, y) -> (X=x, Y=-y, Z=height), in meters."""
    return point[0], -point[1], height


def webots_to_project(position: Sequence[float]) -> Point:
    return position[0], -position[1]


def normalize_angle(angle: float) -> float:
    return (angle + pi) % (2 * pi) - pi


def project_heading_to_yaw(heading: float) -> float:
    """Clockwise project heading becomes counterclockwise Webots Z-axis yaw."""
    return normalize_angle(-heading)


def webots_yaw_to_heading(yaw: float) -> float:
    return normalize_angle(-yaw)


def cell_to_webots(
    grid: OccupancyGrid, cell: Cell, height: float = 0.0
) -> tuple[float, float, float]:
    return project_to_webots(grid.cell_center(cell), height)


def webots_pose(position: Sequence[float], orientation: Sequence[float]) -> Pose2D:
    """Read heading from the local +X forward vector in a row-major 3x3 matrix."""
    x, y = webots_to_project(position)
    yaw = atan2(orientation[3], orientation[0])
    return Pose2D(x, y, webots_yaw_to_heading(yaw))
