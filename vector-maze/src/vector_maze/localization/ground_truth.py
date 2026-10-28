"""Simulator-only localization injection without exposing simulation to the core."""

from collections.abc import Callable

from vector_maze.interfaces import LocalizationProvider
from vector_maze.models import Pose2D


class GroundTruthLocalization(LocalizationProvider):
    def __init__(self, pose_reader: Callable[[], Pose2D]) -> None:
        self._pose_reader = pose_reader

    def get_pose(self) -> Pose2D:
        return self._pose_reader()
