"""Synthetic overhead RGB camera for perception and visualization."""

from collections.abc import Callable
from math import cos, sin
from time import monotonic

import pygame

from vector_maze.interfaces import CameraSource
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Pose2D


class SimulatedCamera(CameraSource):
    """Render the known world independently of display or navigation overlays."""

    def __init__(
        self,
        grid: OccupancyGrid,
        pose_reader: Callable[[], Pose2D],
        radius: float,
        pixels_per_cell: int = 48,
    ) -> None:
        if pixels_per_cell <= 0:
            raise ValueError("pixels_per_cell must be positive")
        self.grid = grid
        self.pose_reader = pose_reader
        self.radius = radius
        self.pixels_per_cell = pixels_per_cell
        self.scale = pixels_per_cell / grid.resolution
        self._background = pygame.Surface(
            (grid.width * pixels_per_cell, grid.height * pixels_per_cell)
        )
        self._background.fill((242, 245, 249))
        for y, row in enumerate(grid.cells):
            for x, wall in enumerate(row):
                if wall:
                    pygame.draw.rect(
                        self._background,
                        (38, 47, 61),
                        (
                            x * pixels_per_cell,
                            y * pixels_per_cell,
                            pixels_per_cell,
                            pixels_per_cell,
                        ),
                    )

    def capture(self) -> CameraFrame:
        surface = self._background.copy()
        pose = self.pose_reader()
        center = (round(pose.x * self.scale), round(pose.y * self.scale))
        radius = max(1, round(self.radius * self.scale))
        pygame.draw.circle(surface, (238, 157, 45), center, radius)
        tip = (
            round(center[0] + cos(pose.heading) * radius),
            round(center[1] + sin(pose.heading) * radius),
        )
        pygame.draw.line(surface, (20, 20, 20), center, tip, 3)
        return CameraFrame(
            surface.get_width(),
            surface.get_height(),
            pygame.image.tobytes(surface, "RGB"),
            monotonic(),
        )
