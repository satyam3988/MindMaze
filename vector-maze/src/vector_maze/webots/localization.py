"""Privileged pose measurement isolated behind the existing localization API."""

from typing import Protocol, Sequence

from vector_maze.interfaces import LocalizationProvider
from vector_maze.models import Pose2D
from vector_maze.webots.coordinates import webots_pose


class PoseNode(Protocol):
    def getPosition(self) -> Sequence[float]: ...
    def getOrientation(self) -> Sequence[float]: ...


class WebotsGroundTruthLocalization(LocalizationProvider):
    def __init__(self, node: PoseNode) -> None:
        self.node = node

    def get_pose(self) -> Pose2D:
        return webots_pose(self.node.getPosition(), self.node.getOrientation())
