"""Image-plane homography; no simulator or occupancy information is required."""

from dataclasses import dataclass
from math import floor, isfinite, tan

import cv2
import numpy as np

from vector_maze.models import Cell, Point


@dataclass(frozen=True)
class CameraCalibration:
    image_width: int
    image_height: int
    grid_width: int
    grid_height: int
    resolution: float
    image_corners: tuple[Point, Point, Point, Point]
    pixels_per_cell: int = 40

    def __post_init__(self):
        sizes = (
            self.image_width,
            self.image_height,
            self.grid_width,
            self.grid_height,
            self.pixels_per_cell,
        )
        if any(type(v) is not int or v <= 0 for v in sizes):
            raise ValueError("Calibration dimensions must be positive integers")
        if not isfinite(self.resolution) or self.resolution <= 0:
            raise ValueError("Calibration resolution must be finite and positive")
        points = np.asarray(self.image_corners, dtype=np.float32)
        if points.shape != (4, 2) or not np.isfinite(points).all():
            raise ValueError("Expected four finite image corners: TL, TR, BR, BL")
        if not cv2.isContourConvex(points) or cv2.contourArea(points, oriented=True) <= 1:
            raise ValueError("Calibration corners must form a clockwise convex image ROI")
        if (
            (points < 0).any()
            or (points[:, 0] >= self.image_width).any()
            or (points[:, 1] >= self.image_height).any()
        ):
            raise ValueError("Entire calibrated maze ROI must be visible in the camera image")

    @classmethod
    def top_down(
        cls,
        *,
        image_width,
        image_height,
        grid_width,
        grid_height,
        resolution,
        camera_center,
        camera_height,
        plane_height,
        horizontal_fov,
        pixels_per_cell=40,
    ):
        """Pinhole calibration from measured rig geometry, on the wall-top plane.

        This initializer is optional. Real cameras can provide four measured
        corner correspondences to the constructor, including tilted viewpoints.
        """
        values = (*camera_center, camera_height, plane_height, horizontal_fov)
        if not all(isfinite(v) for v in values) or not (
            camera_height > plane_height and 0 < horizontal_fov < 3.14159
        ):
            raise ValueError("Invalid pinhole camera geometry")
        scale = image_width / (2 * tan(horizontal_fov / 2) * (camera_height - plane_height))
        corners = tuple(
            (
                image_width / 2 + (x - camera_center[0]) * scale,
                image_height / 2 + (y - camera_center[1]) * scale,
            )
            for x, y in (
                (0, 0),
                (grid_width * resolution, 0),
                (grid_width * resolution, grid_height * resolution),
                (0, grid_height * resolution),
            )
        )
        return cls(
            image_width, image_height, grid_width, grid_height, resolution, corners, pixels_per_cell
        )

    @property
    def rectified_size(self):
        return self.grid_width * self.pixels_per_cell, self.grid_height * self.pixels_per_cell

    @property
    def image_to_world(self):
        w, h = self.grid_width * self.resolution, self.grid_height * self.resolution
        return cv2.getPerspectiveTransform(
            np.float32(self.image_corners), np.float32(((0, 0), (w, 0), (w, h), (0, h)))
        )

    @property
    def image_to_rectified(self):
        scale = self.pixels_per_cell / self.resolution
        return np.diag([scale, scale, 1.0]) @ self.image_to_world

    @staticmethod
    def _transform(point, matrix):
        p = matrix @ np.array([*point, 1.0])
        if not np.isfinite(p).all() or abs(p[2]) < 1e-12:
            raise ValueError("Point cannot be projected onto calibrated plane")
        return float(p[0] / p[2]), float(p[1] / p[2])

    def pixel_to_world(self, point: Point) -> Point:
        return self._transform(point, self.image_to_world)

    def world_to_pixel(self, point: Point) -> Point:
        return self._transform(point, np.linalg.inv(self.image_to_world))

    def world_to_cell(self, point: Point) -> Cell:
        return floor(point[0] / self.resolution), floor(point[1] / self.resolution)

    def rectify(self, rgb: np.ndarray) -> np.ndarray:
        if rgb.dtype != np.uint8 or rgb.shape != (self.image_height, self.image_width, 3):
            raise ValueError("Camera image must match calibration: uint8 RGB (height,width,3)")
        return cv2.warpPerspective(rgb, self.image_to_rectified, self.rectified_size)
