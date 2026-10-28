"""Classical, source-independent RGB map extraction with explicit calibration."""

from dataclasses import dataclass
from math import isfinite

import cv2
import numpy as np

from vector_maze.interfaces import CameraSource
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Cell
from vector_maze.vision.calibration import CameraCalibration


def frame_to_rgb(frame: CameraFrame) -> np.ndarray:
    """Shared packed RGB contract to a uint8 HWC array, without color guessing."""
    if frame.width <= 0 or frame.height <= 0 or not isfinite(frame.timestamp):
        raise ValueError("Invalid camera frame dimensions or timestamp")
    if len(frame.rgb) != frame.width * frame.height * 3:
        raise ValueError("Camera frame does not contain width*height*3 packed RGB bytes")
    return np.frombuffer(frame.rgb, dtype=np.uint8).reshape(frame.height, frame.width, 3)


@dataclass(frozen=True)
class ColorExtractionConfig:
    wall_hsv_lower: tuple[int, int, int] = (8, 65, 45)
    wall_hsv_upper: tuple[int, int, int] = (32, 255, 255)
    occupied_pixel_ratio: float = 0.75
    morphology_kernel_size: int = 3
    minimum_map_occupancy: float = 0.05
    maximum_map_occupancy: float = 0.95

    def __post_init__(self):
        for lo, hi, limit in zip(self.wall_hsv_lower, self.wall_hsv_upper, (179, 255, 255)):
            if not 0 <= lo <= hi <= limit:
                raise ValueError("Invalid OpenCV HSV wall bounds")
        if len(self.wall_hsv_lower) != 3 or len(self.wall_hsv_upper) != 3:
            raise ValueError("HSV bounds must contain three channels")
        if not 0 < self.occupied_pixel_ratio <= 1:
            raise ValueError("Cell occupancy threshold must be in (0,1]")
        k = self.morphology_kernel_size
        if type(k) is not int or k < 1 or k % 2 == 0:
            raise ValueError("Morphology kernel must have positive odd size")
        if not 0 <= self.minimum_map_occupancy < self.maximum_map_occupancy <= 1:
            raise ValueError("Invalid map occupancy validation bounds")


@dataclass(frozen=True)
class ExtractionResult:
    grid: OccupancyGrid
    rectified_rgb: np.ndarray
    wall_mask: np.ndarray
    cell_ratios: np.ndarray
    foreground_mask: np.ndarray


class CalibratedOccupancyGridExtractor:
    """Robot/markers have separate color classes; never consult a reference map.

    Brown cardboard is the wall class. Achromatic robot body, cyan eyes,
    blue start/path and green goal are excluded. This is appearance-based
    segmentation (Option A), independent of robot pose or simulator internals.
    """

    def __init__(self, calibration: CameraCalibration, config=None):
        self.calibration = calibration
        self.config = config or ColorExtractionConfig()

    def extract(self, rgb: np.ndarray) -> ExtractionResult:
        rectified = self.calibration.rectify(rgb)
        hsv = cv2.cvtColor(rectified, cv2.COLOR_RGB2HSV)
        cfg = self.config
        mask = cv2.inRange(hsv, np.uint8(cfg.wall_hsv_lower), np.uint8(cfg.wall_hsv_upper))
        # Independent foreground labels: neutral body/white marker and green/cyan/blue marks.
        neutral = cv2.inRange(hsv, np.uint8((0, 0, 0)), np.uint8((179, 55, 255)))
        markers = cv2.inRange(hsv, np.uint8((35, 60, 0)), np.uint8((130, 255, 255)))
        foreground = cv2.bitwise_or(neutral, markers)
        mask[foreground != 0] = 0
        kernel = np.ones((cfg.morphology_kernel_size,) * 2, np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        c = self.calibration
        ratios = (
            mask.reshape(c.grid_height, c.pixels_per_cell, c.grid_width, c.pixels_per_cell) != 0
        ).mean(axis=(1, 3))
        grid = OccupancyGrid(
            (ratios >= cfg.occupied_pixel_ratio).astype(int).tolist(), c.resolution
        )
        return ExtractionResult(grid, rectified, mask, ratios, foreground)


def validate_map(
    grid: OccupancyGrid,
    calibration: CameraCalibration,
    start: Cell,
    goal: Cell,
    config: ColorExtractionConfig,
) -> None:
    if (grid.width, grid.height, grid.resolution) != (
        calibration.grid_width,
        calibration.grid_height,
        calibration.resolution,
    ):
        raise ValueError("Perceived map dimensions/resolution do not match calibration")
    for label, cell in (("start", start), ("goal", goal)):
        if not grid.in_bounds(cell):
            raise ValueError(f"Configured {label} cell {cell} is outside perceived map")
        if not grid.is_free(cell):
            raise ValueError(f"Perceived {label} cell {cell} is occupied; navigation stopped")
    ratio = sum(map(sum, grid.cells)) / (grid.width * grid.height)
    if not config.minimum_map_occupancy <= ratio <= config.maximum_map_occupancy:
        raise ValueError(f"Nonsensical perceived occupancy ratio {ratio:.3f}; navigation stopped")


def capture_map(
    source: CameraSource,
    calibration: CameraCalibration,
    config: ColorExtractionConfig,
    start: Cell,
    goal: Cell,
):
    """Only camera RGB plus calibration/mission configuration enter this boundary."""
    rgb = frame_to_rgb(source.capture())
    result = CalibratedOccupancyGridExtractor(calibration, config).extract(rgb)
    validate_map(result.grid, calibration, start, goal, config)
    return rgb, result
