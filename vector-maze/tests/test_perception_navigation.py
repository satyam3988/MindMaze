import ast
import json
import subprocess
import sys
from pathlib import Path

from vector_maze.control.waypoint import WaypointController
from vector_maze.localization.ground_truth import GroundTruthLocalization
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import CameraFrame, Pose2D
from vector_maze.navigation import MazeNavigator
from vector_maze.perception.occupancy import OccupancyGridExtractor
from vector_maze.planning.astar import AStarPlanner
from vector_maze.simulation.robot import SimulatedRobot
from vector_maze.vision.coordinates import PixelGridTransform

ROOT = Path(__file__).resolve().parents[1]


def test_navigation_uses_image_obstacle_absent_from_simulator():
    truth = OccupancyGrid([[0] * 3] * 3, 1.0)
    # Independent image inserts a wall into physically free space.
    pixels = [(0, 0, 0) if i == 4 else (255, 255, 255) for i in range(9)]
    frame = CameraFrame(3, 3, bytes(v for pixel in pixels for v in pixel), 0)
    recovered = OccupancyGridExtractor(PixelGridTransform(1, 1.0)).extract(frame)
    robot = SimulatedRobot(truth, Pose2D(0.5, 0.5))

    class RecordingPlanner(AStarPlanner):
        received = None

        def plan(self, grid, start, goal):
            self.received = grid
            return super().plan(grid, start, goal)

    planner = RecordingPlanner()
    navigator = MazeNavigator(
        recovered,
        GroundTruthLocalization(lambda: robot.pose),
        planner,
        WaypointController(),
        robot,
        robot.radius,
    )
    path = navigator.plan_to((2, 2))
    assert navigator.grid is recovered
    assert planner.received == recovered.for_robot(robot.radius)
    assert planner.received != truth
    assert (1, 1) not in path
    for _ in range(5000):
        navigator.tick(1 / 60)
        assert robot.step(1 / 60)
        if navigator.reached_goal:
            break
    assert navigator.reached_goal
    assert robot.collision_count == 0


def test_headless_perception_demo_end_to_end(tmp_path):
    report = tmp_path / "result.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_perception_demo.py"),
            "--headless",
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(report.read_text())
    assert data["perception"]["accuracy"] == data["perception"]["occupied_iou"] == 1
    assert data["perception"]["incorrect_cells"] == 0
    assert data["goal_reached"] and data["status"] == "goal_reached"
    assert data["collisions"] == 0 and data["steps"] > 0


def test_headless_step_budget_failure_reports_and_exits(tmp_path):
    report = tmp_path / "result.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_perception_demo.py"),
            "--headless",
            "--max-steps",
            "1",
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    data = json.loads(report.read_text())
    assert data["status"] == "step_budget_exhausted" and not data["goal_reached"]
    assert data["steps"] == 1


def test_perception_and_transform_do_not_import_simulator_or_pygame():
    files = list((ROOT / "src/vector_maze/perception").glob("*.py"))
    files.append(ROOT / "src/vector_maze/vision/coordinates.py")
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            assert all(
                not (m.startswith("vector_maze.simulation") or m == "pygame") for m in modules
            ), file
