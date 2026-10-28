from pathlib import Path

import pytest

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Pose2D
from vector_maze.perception.occupancy import ExtractionConfig, OccupancyGridExtractor
from vector_maze.simulation.camera import SimulatedCamera
from vector_maze.vision.coordinates import PixelGridTransform


def rgb_frame(rows: list[list[tuple[int, int, int]]]) -> CameraFrame:
    """Build independent RGB fixtures without simulator rendering or map access."""
    return CameraFrame(
        len(rows[0]),
        len(rows),
        bytes(channel for row in rows for pixel in row for channel in pixel),
        0,
    )


@pytest.mark.parametrize("pixels_per_cell", [8, 20, 48])
def test_perfect_camera_frame_recovers_maze_with_robot_present(pixels_per_cell):
    truth = OccupancyGrid.load(Path(__file__).resolve().parents[1] / "assets/mazes/simple.json")
    camera = SimulatedCamera(
        truth, lambda: Pose2D(*truth.cell_center((1, 1))), 0.025, pixels_per_cell
    )
    extractor = OccupancyGridExtractor(PixelGridTransform(pixels_per_cell, 0.1))
    recovered = extractor.extract(camera.capture())
    assert recovered == truth
    assert recovered is not truth


def test_empty_free_frame_and_boundary_walls():
    transform = PixelGridTransform(2, 0.1)
    extractor = OccupancyGridExtractor(transform)
    white, black = (255, 255, 255), (0, 0, 0)
    assert extractor.extract(rgb_frame([[white] * 6] * 4)).cells == ((0, 0, 0), (0, 0, 0))
    rows = [
        [black] * 6,
        [black] * 6,
        [black, black, white, white, black, black],
        [black, black, white, white, black, black],
    ]
    assert extractor.extract(rgb_frame(rows)).cells == ((1, 1, 1), (1, 0, 1))


def test_rgb_grayscale_weights_and_inclusive_threshold():
    # Red luminance=76.245, green=149.685, blue=29.07; grayscale 90 lies on threshold.
    frame = rgb_frame([[(255, 0, 0), (0, 255, 0), (0, 0, 255), (90, 90, 90), (91, 91, 91)]])
    extractor = OccupancyGridExtractor(PixelGridTransform(1, 1))
    assert extractor.extract(frame).cells == ((1, 0, 1, 1, 0),)


def test_occupancy_ratio_tolerates_sparse_dark_noise_and_light_wall_noise():
    black, white = (0, 0, 0), (255, 255, 255)
    frame = rgb_frame([[black, white, black, black], [white, white, black, white]])
    transform = PixelGridTransform(2, 0.1)
    assert OccupancyGridExtractor(transform).extract(frame).cells == ((0, 1),)
    sensitive = OccupancyGridExtractor(transform, ExtractionConfig(minimum_occupancy_ratio=0.25))
    assert sensitive.extract(frame).cells == ((1, 1),)
    strict = OccupancyGridExtractor(transform, ExtractionConfig(minimum_occupancy_ratio=1))
    assert strict.extract(frame).cells == ((0, 0),)


def test_occupancy_ratio_is_inclusive():
    frame = rgb_frame([[(0, 0, 0), (0, 0, 0)], [(255, 255, 255)] * 2])
    assert OccupancyGridExtractor(PixelGridTransform(2, 0.1)).extract(frame).cells == ((1,),)


@pytest.mark.parametrize(
    "frame",
    [
        CameraFrame(2, 2, b"", 0),
        CameraFrame(2, 2, bytes(13), 0),
        CameraFrame(3, 2, bytes(18), 0),
        CameraFrame(0, 2, b"", 0),
    ],
)
def test_rejects_malformed_or_partial_cell_frames(frame):
    with pytest.raises(ValueError):
        OccupancyGridExtractor(PixelGridTransform(2, 0.1)).extract(frame)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"grayscale_threshold": -1},
        {"grayscale_threshold": 256},
        {"grayscale_threshold": float("nan")},
        {"minimum_occupancy_ratio": 0},
        {"minimum_occupancy_ratio": 1.1},
    ],
)
def test_invalid_extraction_configuration(kwargs):
    with pytest.raises(ValueError):
        ExtractionConfig(**kwargs)
