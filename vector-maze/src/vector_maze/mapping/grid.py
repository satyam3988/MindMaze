"""Immutable binary occupancy grid with metric geometry."""

import json
from dataclasses import dataclass
from math import floor, isfinite
from pathlib import Path
from typing import Sequence

from vector_maze.models import Cell, Point
from vector_maze.utils.geometry import segment_rectangle_distance


@dataclass(frozen=True, init=False)
class OccupancyGrid:
    cells: tuple[tuple[int, ...], ...]
    resolution: float

    def __init__(self, cells: Sequence[Sequence[int]], resolution: float = 0.1) -> None:
        rows = tuple(tuple(row) for row in cells)
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError("Grid must be nonempty and rectangular")
        if any(value not in (0, 1) for row in rows for value in row):
            raise ValueError("Grid cells must be 0 or 1")
        if not isfinite(resolution) or resolution <= 0:
            raise ValueError("Resolution must be finite and positive")
        object.__setattr__(self, "cells", rows)
        object.__setattr__(self, "resolution", resolution)

    @classmethod
    def load(cls, path: str | Path) -> "OccupancyGrid":
        """Load JSON containing cells and resolution (meters per cell)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["cells"], data["resolution"])

    @property
    def width(self) -> int:
        return len(self.cells[0])

    @property
    def height(self) -> int:
        return len(self.cells)

    def in_bounds(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def is_free(self, cell: Cell) -> bool:
        """Treat out-of-bounds cells as occupied, avoiding negative indexing."""
        return self.in_bounds(cell) and self.cells[cell[1]][cell[0]] == 0

    def cell_center(self, cell: Cell) -> Point:
        if not self.in_bounds(cell):
            raise ValueError("Cell outside grid")
        return ((cell[0] + 0.5) * self.resolution, (cell[1] + 0.5) * self.resolution)

    def world_to_cell(self, point: Point) -> Cell:
        return floor(point[0] / self.resolution), floor(point[1] / self.resolution)

    def collides(self, point: Point, radius: float) -> bool:
        """Check a circular footprint, counting contact as collision."""
        return self.sweep_collides(point, point, radius)

    def sweep_collides(self, start: Point, end: Point, radius: float) -> bool:
        """Check the complete swept circle, including maze boundaries."""
        if not isfinite(radius) or radius < 0:
            raise ValueError("Radius must be finite and nonnegative")
        if not all(isfinite(v) for v in (*start, *end)):
            raise ValueError("Coordinates must be finite")
        r = self.resolution
        if any(
            x - radius <= 0
            or y - radius <= 0
            or x + radius >= self.width * r
            or y + radius >= self.height * r
            for x, y in (start, end)
        ):
            return True
        for y, row in enumerate(self.cells):
            for x, occupied in enumerate(row):
                if (
                    occupied
                    and segment_rectangle_distance(
                        start, end, x * r, y * r, (x + 1) * r, (y + 1) * r
                    )
                    <= radius + 1e-12
                ):
                    return True
        return False

    def for_robot(self, radius: float) -> "OccupancyGrid":
        """Mark cells whose centers cannot safely contain the robot footprint."""
        return OccupancyGrid(
            [
                [int(self.collides(self.cell_center((x, y)), radius)) for x in range(self.width)]
                for y in range(self.height)
            ],
            self.resolution,
        )
