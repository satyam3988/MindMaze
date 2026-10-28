import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Pose2D
from vector_maze.simulation.camera import SimulatedCamera


def test_camera_rgb_contract_and_pose_updates():
    grid = OccupancyGrid([[1, 0, 0], [1, 0, 0]], 1.0)
    pose = Pose2D(1.5, 0.5)
    camera = SimulatedCamera(grid, lambda: pose, 0.1, pixels_per_cell=20)
    first = camera.capture()
    assert (first.width, first.height) == (60, 40)
    assert len(first.rgb) == 60 * 40 * 3
    assert first.rgb[:3] == bytes((38, 47, 61))
    pose = Pose2D(2.5, 0.5)
    second = camera.capture()
    assert second.rgb != first.rgb
    assert second.timestamp >= first.timestamp
