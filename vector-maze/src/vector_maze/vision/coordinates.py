"""Axis-aligned overhead calibration shared by perception and visualization."""

from dataclasses import dataclass
from math import floor, isfinite

from vector_maze.models import Cell, Point


@dataclass(frozen=True)
class PixelGridTransform:
    """Top-left origins, x/column right, y/row down; no perspective transform.

    Pixel coordinates are continuous image coordinates: pixel (u, v) occupies
    [u, u+1) x [v, v+1). Conversions do not round or clip. Cell bounds are
    half-open; negative coordinates use floor, matching OccupancyGrid.
    """

    pixels_per_cell: int
    resolution: float

    def __post_init__(self) -> None:
        if type(self.pixels_per_cell) is not int or self.pixels_per_cell <= 0:
            raise ValueError("pixels_per_cell must be a positive integer")
        if not isfinite(self.resolution) or self.resolution <= 0:
            raise ValueError("resolution must be finite and positive")

    @property
    def pixels_per_meter(self) -> float:
        return self.pixels_per_cell / self.resolution

    def grid_dimensions(self, width: int, height: int) -> Cell:
        """Infer columns/rows from a full, cell-aligned image; reject cropped cells."""
        if any(type(v) is not int or v <= 0 for v in (width, height)):
            raise ValueError("Image dimensions must be positive integers")
        if width % self.pixels_per_cell or height % self.pixels_per_cell:
            raise ValueError("Image dimensions must be divisible by pixels_per_cell")
        return width // self.pixels_per_cell, height // self.pixels_per_cell

    def world_to_pixel(self, point: Point) -> Point:
        return point[0] * self.pixels_per_meter, point[1] * self.pixels_per_meter

    def pixel_to_world(self, pixel: Point) -> Point:
        return pixel[0] / self.pixels_per_meter, pixel[1] / self.pixels_per_meter

    def pixel_to_cell(self, pixel: Point) -> Cell:
        return floor(pixel[0] / self.pixels_per_cell), floor(pixel[1] / self.pixels_per_cell)

    def world_to_cell(self, point: Point) -> Cell:
        return floor(point[0] / self.resolution), floor(point[1] / self.resolution)

    def cell_center_world(self, cell: Cell) -> Point:
        return (cell[0] + 0.5) * self.resolution, (cell[1] + 0.5) * self.resolution

    def cell_center_pixel(self, cell: Cell) -> Point:
        return (cell[0] + 0.5) * self.pixels_per_cell, (cell[1] + 0.5) * self.pixels_per_cell

    def cell_pixel_bounds(self, cell: Cell) -> tuple[int, int, int, int]:
        """Return left, top, right, bottom with exclusive right/bottom edges."""
        x, y = cell
        p = self.pixels_per_cell
        return x * p, y * p, (x + 1) * p, (y + 1) * p
