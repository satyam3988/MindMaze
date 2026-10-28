import json
from math import cos, pi, sin
from pathlib import Path

import pytest

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Pose2D, VelocityCommand
from vector_maze.webots.camera import WebotsCameraSource
from vector_maze.webots.config import DriveConfig, find_webots
from vector_maze.webots.coordinates import (
    cell_to_webots,
    project_heading_to_yaw,
    project_to_webots,
    webots_pose,
    webots_to_project,
    webots_yaw_to_heading,
)
from vector_maze.webots.localization import WebotsGroundTruthLocalization
from vector_maze.webots.robot_adapter import WebotsRobotAdapter, wheel_speeds
from vector_maze.webots.world_generator import generate_world, write_world

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("point,height", [((0, 0), 0), ((0.15, 0.95), 0.06), ((-1, -2), 1)])
def test_coordinate_roundtrip(point, height):
    result = project_to_webots(point, height)
    assert result == (point[0], -point[1], height)
    assert webots_to_project(result) == point


@pytest.mark.parametrize("heading", [0, pi / 2, -pi / 2, 2.8])
def test_heading_and_orientation_matrix(heading):
    yaw = project_heading_to_yaw(heading)
    assert yaw == pytest.approx(-heading)
    assert webots_yaw_to_heading(yaw) == pytest.approx(heading)
    orientation = [cos(yaw), -sin(yaw), 0, sin(yaw), cos(yaw), 0, 0, 0, 1]
    pose = webots_pose([0.15, -0.95, 0.01], orientation)
    assert pose.x == 0.15 and pose.y == 0.95
    assert pose.heading == pytest.approx(heading)


def test_cell_start_goal_conversion():
    grid = OccupancyGrid([[0] * 13] * 11, 0.1)
    assert cell_to_webots(grid, (1, 1), 0.001) == pytest.approx((0.15, -0.15, 0.001))
    assert cell_to_webots(grid, (11, 9)) == pytest.approx((1.15, -0.95, 0))


@pytest.mark.parametrize(
    "v,omega,expected",
    [(0.1, 0, (5, 5)), (0, 1, (2.5, -2.5)), (0.1, 1, (7.5, 2.5)), (-0.1, 0, (-5, -5))],
)
def test_differential_drive(v, omega, expected):
    config = DriveConfig(0.02, 0.1, 20, 0.2, 3)
    assert wheel_speeds(VelocityCommand(v, omega), config) == pytest.approx(expected)


def test_saturation_preserves_wheel_ratio_and_command_limits():
    config = DriveConfig(0.02, 0.1, 5, 0.1, 1)
    left, right = wheel_speeds(VelocityCommand(100, 100), config)
    assert left == 5 and right == pytest.approx(5 / 3)
    assert max(abs(left), abs(right)) <= config.max_wheel_speed


@pytest.mark.parametrize(
    "kwargs",
    [
        {"wheel_radius": 0},
        {"wheel_separation": -1},
        {"max_wheel_speed": float("inf")},
        {"max_linear_velocity": float("nan")},
    ],
)
def test_invalid_drive_parameters(kwargs):
    with pytest.raises(ValueError):
        DriveConfig(**kwargs)


def test_adapter_motor_calls_and_stop():
    class FakeMotor:
        def setPosition(self, value):
            self.position = value

        def setVelocity(self, value):
            self.velocity = value

        def getMaxVelocity(self):
            return 10

    left, right = FakeMotor(), FakeMotor()
    adapter = WebotsRobotAdapter(left, right, DriveConfig())
    assert left.position == right.position == float("inf")
    adapter.command_velocity(VelocityCommand(0.05, 1))
    assert (left.velocity, right.velocity) == pytest.approx(
        wheel_speeds(VelocityCommand(0.05, 1), DriveConfig())
    )
    adapter.stop()
    assert left.velocity == right.velocity == 0
    with pytest.raises(ValueError):
        WebotsRobotAdapter(left, right, DriveConfig(max_wheel_speed=11))


def test_localization_injected_node():
    class Node:
        def getPosition(self):
            return [0.15, -0.95, 0.018]

        def getOrientation(self):
            return [1, 0, 0, 0, 1, 0, 0, 0, 1]

    assert WebotsGroundTruthLocalization(Node()).get_pose() == Pose2D(0.15, 0.95)


def test_world_generation_wall_count_physical_geometry_and_markers():
    settings = json.loads((ROOT / "configs/webots.json").read_text())
    grid = OccupancyGrid([[1, 0, 0], [0, 0, 0]], 0.1)
    text = generate_world(grid, (1, 0), (2, 1), settings, ROOT / "configs/webots.json")
    assert text.count(" MazeWall {") == 1
    assert "DEF WALL_0_0 MazeWall {\n  translation 0.05 -0.05 0.06" in text
    assert "size 0.1 0.1 0.12" in text
    assert "DEF START Pose {\n  translation 0.15 -0.05 0.001" in text
    assert "DEF GOAL Pose {\n  translation 0.25 -0.15 0.001" in text
    assert "DEF VECTOR_ROBOT VectorRobot {\n  translation 0.15 -0.05 0.001" in text
    assert 'coordinateSystem "ENU"' in text
    assert "width 640" in text and "height 480" in text
    assert "DEF PLANNED_PATH Shape" in text


def test_default_generated_world_has_every_occupied_cell(tmp_path):
    path = write_world(ROOT / "configs/webots.json", tmp_path / "world.wbt")
    text = path.read_text()
    grid = OccupancyGrid.load(ROOT / "assets/mazes/simple.json")
    assert text.count(" MazeWall {") == sum(sum(row) for row in grid.cells) == 82
    for y, row in enumerate(grid.cells):
        for x, occupied in enumerate(row):
            assert (f"DEF WALL_{x}_{y} MazeWall" in text) == bool(occupied)


def test_world_rejects_unreachable_route():
    settings = json.loads((ROOT / "configs/webots.json").read_text())
    with pytest.raises(ValueError):
        generate_world(OccupancyGrid([[0, 1, 0]], 0.1), (0, 0), (2, 0), settings, ROOT)


def test_webots_discovery_and_invalid_override(tmp_path, monkeypatch):
    executable = tmp_path / "msys64/mingw64/bin/webots.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")
    monkeypatch.setenv("WEBOTS_HOME", str(tmp_path))
    assert find_webots() == executable.resolve()
    with pytest.raises(FileNotFoundError):
        find_webots(tmp_path / "missing")


def test_camera_converts_bgra_to_rgb_and_waits_for_frame():
    class Camera:
        data = bytes([10, 20, 30, 255, 40, 50, 60, 255])

        def getWidth(self):
            return 2

        def getHeight(self):
            return 1

        def getImage(self):
            return self.data

    camera = Camera()
    source = WebotsCameraSource(camera, lambda: 1.5)
    frame = source.capture()
    assert frame.rgb == bytes([30, 20, 10, 60, 50, 40])
    assert frame.timestamp == 1.5
    camera.data = b""
    with pytest.raises(RuntimeError):
        source.capture()
