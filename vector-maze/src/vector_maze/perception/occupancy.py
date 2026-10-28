"""Deterministic RGB-to-grid extraction without camera/simulator dependencies."""

import logging
from dataclasses import dataclass
from math import isfinite

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame
from vector_maze.vision.coordinates import PixelGridTransform

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionConfig:
    """Thresholds for a rectified image: dark pixels vote for occupied cells."""

    grayscale_threshold: float = 90.0
    minimum_occupancy_ratio: float = 0.5

    def __post_init__(self) -> None:
        if not isfinite(self.grayscale_threshold) or not 0 <= self.grayscale_threshold <= 255:
            raise ValueError("grayscale_threshold must be between 0 and 255")
        if not isfinite(self.minimum_occupancy_ratio) or not 0 < self.minimum_occupancy_ratio <= 1:
            raise ValueError("minimum_occupancy_ratio must be in (0, 1]")


class OccupancyGridExtractor:
    """Threshold luminance, aggregate each calibrated cell, return a binary map.

    Calibration describes geometry only. Grid dimensions come from frame size;
    no ground-truth map, robot pose, renderer colors, or simulator is consulted.
    Images must already be axis-aligned and cover the complete maze footprint.
    """

    def __init__(
        self, transform: PixelGridTransform, config: ExtractionConfig | None = None
    ) -> None:
        self.transform = transform
        self.config = config or ExtractionConfig()

    def extract(self, frame: CameraFrame) -> OccupancyGrid:
        """Extract 0=free/1=occupied from packed row-major RGB image bytes."""
        width, height = self.transform.grid_dimensions(frame.width, frame.height)
        if len(frame.rgb) != frame.width * frame.height * 3:
            raise ValueError("RGB buffer length must equal width * height * 3")
        logger.debug(
            "Extracting RGB frame %dx%d into grid %dx%d", frame.width, frame.height, width, height
        )
        p = self.transform.pixels_per_cell
        votes = [[0] * width for _ in range(height)]
        threshold = self.config.grayscale_threshold * 1000
        rgb = frame.rgb
        for v in range(frame.height):
            row = votes[v // p]
            offset = v * frame.width * 3
            for u in range(frame.width):
                i = offset + u * 3
                # RGB luminance, not BGR; integer weights avoid uint8 overflow.
                if 299 * rgb[i] + 587 * rgb[i + 1] + 114 * rgb[i + 2] <= threshold:
                    row[u // p] += 1
        cutoff = self.config.minimum_occupancy_ratio * p * p
        cells = [[int(vote >= cutoff) for vote in row] for row in votes]
        grid = OccupancyGrid(cells, self.transform.resolution)
        occupied = sum(sum(row) for row in cells)
        logger.debug(
            "Extraction complete: occupied=%d/%d, occupancy_ratio=%.4f",
            occupied,
            width * height,
            occupied / (width * height),
        )
        return grid
