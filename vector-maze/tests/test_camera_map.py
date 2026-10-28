import ast
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from vector_maze.control.waypoint import WaypointController
from vector_maze.localization.ground_truth import GroundTruthLocalization
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Pose2D
from vector_maze.navigation import MazeNavigator
from vector_maze.perception.camera_map import (
    CalibratedOccupancyGridExtractor,
    ColorExtractionConfig,
    capture_map,
    frame_to_rgb,
    validate_map,
)
from vector_maze.perception.debug import save_debug_artifacts
from vector_maze.perception.evaluation import compare_maps
from vector_maze.planning.astar import AStarPlanner
from vector_maze.simulation.robot import SimulatedRobot
from vector_maze.vision.calibration import CameraCalibration
from vector_maze.webots.camera import (
    WebotsCameraSource,
    WebotsReceivedCameraSource,
    encode_frame,
)
from vector_maze.webots.world_generator import generate_world

ROOT = Path(__file__).resolve().parents[1]
PPC = 20


def fixture_image(cells):
    colors = np.array([[245, 245, 245], [150, 105, 65]], dtype=np.uint8)
    return np.repeat(np.repeat(colors[np.asarray(cells)], PPC, axis=0), PPC, axis=1)


def fixture_calibration(width, height):
    return CameraCalibration(
        width * PPC + 1,
        height * PPC + 1,
        width,
        height,
        0.1,
        ((0, 0), (width * PPC, 0), (width * PPC, height * PPC), (0, height * PPC)),
        PPC,
    )


def padded_image(cells):
    return np.pad(fixture_image(cells), ((0, 1), (0, 1), (0, 0)), mode="edge")


def test_webots_bgra_to_rgb_array_and_transport_roundtrip():
    class Device:
        def getWidth(self):
            return 2

        def getHeight(self):
            return 1

        def getImage(self):
            return bytes([10, 20, 30, 255, 40, 50, 60, 0])

    frame = WebotsCameraSource(Device(), lambda: 0.75).capture()

    class Receiver:
        packet = encode_frame(frame)

        def getQueueLength(self):
            return int(self.packet is not None)

        def getBytes(self):
            return self.packet

        def nextPacket(self):
            self.packet = None

    receiver = Receiver()
    decoded = WebotsReceivedCameraSource(receiver).capture()
    assert decoded == frame
    array = frame_to_rgb(decoded)
    assert array.shape == (1, 2, 3) and array.dtype == np.uint8
    assert array.tolist() == [[[30, 20, 10], [60, 50, 40]]]
    with pytest.raises(RuntimeError, match="No overhead"):
        WebotsReceivedCameraSource(receiver).capture()


@pytest.mark.parametrize("packet", [b"", b"wrong header entirely", b"RGB1" + bytes(40)])
def test_bad_transport_packet_rejected(packet):
    class Receiver:
        def getQueueLength(self):
            return 1

        def getBytes(self):
            return packet

        def nextPacket(self):
            pass

    with pytest.raises(ValueError):
        WebotsReceivedCameraSource(Receiver()).capture()


@pytest.mark.parametrize(
    "frame",
    [CameraFrame(1, 1, b"", 0), CameraFrame(0, 1, b"", 0), CameraFrame(1, 1, b"abc", float("nan"))],
)
def test_bad_frame_rejected(frame):
    with pytest.raises(ValueError):
        frame_to_rgb(frame)


def test_calibration_corners_cell_centers_and_top_down_pinhole():
    calibration = CameraCalibration.top_down(
        image_width=640,
        image_height=480,
        grid_width=13,
        grid_height=11,
        resolution=0.1,
        camera_center=(0.65, 0.55),
        camera_height=1.6,
        plane_height=0.12,
        horizontal_fov=1.0,
    )
    for pixel, world in zip(calibration.image_corners, ((0, 0), (1.3, 0), (1.3, 1.1), (0, 1.1))):
        assert calibration.pixel_to_world(pixel) == pytest.approx(world, abs=1e-7)
    for row in range(11):
        for col in range(13):
            center = ((col + 0.5) * 0.1, (row + 0.5) * 0.1)
            pixel = calibration.world_to_pixel(center)
            actual = calibration.pixel_to_world(pixel)
            assert actual == pytest.approx(center)
            assert calibration.world_to_cell(actual) == (col, row)
    assert calibration.rectified_size == (520, 440)


@pytest.mark.parametrize(
    "corners",
    [
        ((0, 0),) * 4,
        ((0, 0), (80, 0), (80, 80), (0, 80)),
        ((0, 0), (0, 40), (40, 40), (40, 0)),
        ((0, 0), (40, 40), (40, 0), (0, 40)),
    ],
)
def test_invalid_calibration_rejected(corners):
    with pytest.raises(ValueError):
        CameraCalibration(61, 61, 3, 3, 0.1, corners)


def test_tilted_homography_recovers_full_grid_and_boundary_walls():
    cells = [[1, 1, 1, 1, 1], [1, 0, 0, 0, 1], [1, 0, 1, 0, 1], [1, 0, 0, 0, 1], [1, 1, 1, 1, 1]]
    canonical = fixture_image(cells)
    corners = ((35, 15), (150, 30), (175, 175), (10, 165))
    transform = cv2.getPerspectiveTransform(
        np.float32(((0, 0), (100, 0), (100, 100), (0, 100))), np.float32(corners)
    )
    raw = cv2.warpPerspective(canonical, transform, (200, 200))
    calibration = CameraCalibration(200, 200, 5, 5, 0.1, corners, PPC)
    result = CalibratedOccupancyGridExtractor(calibration).extract(raw)
    assert result.grid == OccupancyGrid(cells, 0.1)
    assert result.rectified_rgb.shape == (100, 100, 3)
    assert result.wall_mask.dtype == np.uint8


def test_robot_goal_and_blue_route_are_separate_foreground_classes():
    cells = [[1, 1, 1, 1, 1], [1, 0, 0, 0, 1], [1, 1, 1, 1, 1]]
    raw = padded_image(cells)
    # Cover almost whole free cells so one-pixel sampling/grayscale would fail.
    for col, color in ((1, (20, 24, 28)), (2, (20, 230, 40)), (3, (20, 100, 255))):
        raw[21:39, col * 20 + 1 : col * 20 + 19] = color
    result = CalibratedOccupancyGridExtractor(fixture_calibration(5, 3)).extract(raw)
    assert result.grid == OccupancyGrid(cells, 0.1)
    assert np.count_nonzero(result.foreground_mask[21:39, 21:39]) == 18 * 18
    assert np.count_nonzero(result.wall_mask[21:39, 21:79]) == 0


def test_morphology_removes_speckles_and_fills_small_wall_holes():
    raw = padded_image([[1, 0], [0, 1]])
    raw[10, 10] = (245, 245, 245)
    raw[10, 30] = (150, 105, 65)
    result = CalibratedOccupancyGridExtractor(fixture_calibration(2, 2)).extract(raw)
    assert result.wall_mask[10, 10] == 255
    assert result.wall_mask[10, 30] == 0
    assert result.grid == OccupancyGrid([[1, 0], [0, 1]], 0.1)


def test_cell_classification_uses_area_ratio_not_center_pixel():
    raw = padded_image([[0, 0]])
    raw[:20, :16] = (150, 105, 65)  # 80% wall
    raw[:20, 20:32] = (150, 105, 65)  # 60% wall
    result = CalibratedOccupancyGridExtractor(fixture_calibration(2, 1)).extract(raw)
    assert result.grid.cells == ((1, 0),)
    assert result.cell_ratios[0].tolist() == pytest.approx([0.8, 0.6])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"morphology_kernel_size": 2},
        {"occupied_pixel_ratio": 0},
        {"wall_hsv_lower": (180, 0, 0)},
        {"maximum_map_occupancy": 0.01},
        {"wall_hsv_upper": (30, 255)},
    ],
)
def test_invalid_extraction_config_rejected(kwargs):
    with pytest.raises(ValueError):
        ColorExtractionConfig(**kwargs)


@pytest.mark.parametrize(
    "cells,start,goal,message",
    [
        ([[0, 0], [0, 0]], (0, 0), (1, 1), "occupancy ratio"),
        ([[1, 0], [0, 0]], (0, 0), (1, 1), "start.*occupied"),
        ([[0, 0], [0, 1]], (0, 0), (1, 1), "goal.*occupied"),
        ([[1, 0], [0, 0]], (1, 0), (2, 1), "outside"),
    ],
)
def test_bad_maps_fail_before_planning(cells, start, goal, message):
    with pytest.raises(ValueError, match=message):
        validate_map(
            OccupancyGrid(cells, 0.1),
            fixture_calibration(2, 2),
            start,
            goal,
            ColorExtractionConfig(),
        )


def test_image_shape_and_map_dimensions_rejected():
    calibration = fixture_calibration(3, 3)
    with pytest.raises(ValueError, match="dimensions"):
        validate_map(
            OccupancyGrid([[0]], 0.1), calibration, (0, 0), (0, 0), ColorExtractionConfig()
        )
    extractor = CalibratedOccupancyGridExtractor(calibration)
    for raw in (np.zeros((61, 61, 3), np.float32), np.zeros((60, 60, 3), np.uint8)):
        with pytest.raises(ValueError, match="uint8 RGB"):
            extractor.extract(raw)


@pytest.mark.parametrize(
    "actual,predicted,f1",
    [([[0]], [[0]], 1), ([[1]], [[0]], 0), ([[0]], [[1]], 0), ([[1, 1, 0]], [[1, 0, 1]], 0.5)],
)
def test_f1_confusion_matrix_and_zero_denominators(actual, predicted, f1):
    assert compare_maps(OccupancyGrid(actual), OccupancyGrid(predicted)).occupied_f1 == f1


def test_camera_map_exclusively_controls_planning_and_navigation():
    # A visible center wall is ABSENT from physical/reference map. Planner must avoid it.
    physical = OccupancyGrid([[0] * 5] * 5, 0.1)
    cells = [[0] * 5 for _ in range(5)]
    cells[2][2] = 1
    raw = padded_image(cells)

    class Camera:
        def capture(self):
            return CameraFrame(101, 101, raw.tobytes(), 1)

    _, extracted = capture_map(
        Camera(),
        fixture_calibration(5, 5),
        ColorExtractionConfig(minimum_map_occupancy=0.01),
        (1, 2),
        (3, 2),
    )
    robot = SimulatedRobot(physical, Pose2D(0.15, 0.25), radius=0.043)

    class Recorder(AStarPlanner):
        def plan(self, grid, start, goal):
            self.received = grid
            return super().plan(grid, start, goal)

    planner = Recorder()
    navigator = MazeNavigator(
        extracted.grid,
        GroundTruthLocalization(lambda: robot.pose),
        planner,
        WaypointController(),
        robot,
        robot.radius,
    )
    assert (2, 2) not in navigator.plan_to((3, 2))
    assert planner.received == extracted.grid.for_robot(robot.radius)
    assert planner.received != physical
    for _ in range(4000):
        navigator.tick(1 / 60)
        assert robot.step(1 / 60)
        if navigator.reached_goal:
            break
    assert navigator.reached_goal and robot.collision_count == 0


def test_capture_failure_has_no_ground_truth_fallback():
    class Camera:
        def capture(self):
            raise RuntimeError("Camera failed")

    with pytest.raises(RuntimeError, match="Camera failed"):
        capture_map(Camera(), fixture_calibration(3, 3), ColorExtractionConfig(), (0, 0), (2, 2))


def test_debug_artifacts_are_evaluation_only(tmp_path):
    raw = padded_image([[1, 0], [0, 0]])
    extracted = CalibratedOccupancyGridExtractor(fixture_calibration(2, 2)).extract(raw)
    original = extracted.grid
    truth = OccupancyGrid([[0, 0], [0, 1]], 0.1)
    save_debug_artifacts(tmp_path, raw, extracted, truth, "test")
    assert extracted.grid is original
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["false_positive"] == metrics["false_negative"] == 1
    assert len(list(tmp_path.glob("*.png"))) == 7


def test_perception_has_no_concrete_simulator_dependencies():
    paths = list((ROOT / "src/vector_maze/perception").glob("*.py"))
    paths.append(ROOT / "src/vector_maze/vision/calibration.py")
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            modules = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            assert all(
                not m.startswith(("controller", "vector_maze.webots", "vector_maze.simulation"))
                for m in modules
            ), path


def test_vision_world_generation_does_not_plan_from_json(monkeypatch):
    def forbidden(*args):
        raise AssertionError("World generator invoked JSON planner in vision mode")

    monkeypatch.setattr(AStarPlanner, "plan", forbidden)
    settings = json.loads((ROOT / "configs/webots.json").read_text())
    grid = OccupancyGrid.load(ROOT / "assets/mazes/simple.json")
    world = generate_world(
        grid, (1, 1), (11, 9), settings, ROOT / "configs/webots.json", vision_map=True
    )
    assert "coord DEF PATH_COORDINATES Coordinate { point [  ] }" in world
    assert world.count(" MazeWall {") == 82
