from math import hypot
from pathlib import Path

import pytest

from vector_maze.control.waypoint import WaypointController
from vector_maze.interfaces import LocalizationProvider, RobotController
from vector_maze.localization.ground_truth import GroundTruthLocalization
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Pose2D, VelocityCommand
from vector_maze.navigation import MazeNavigator
from vector_maze.planning.astar import AStarPlanner
from vector_maze.simulation.robot import SimulatedRobot


def test_demo_maze_reaches_goal_without_collisions():
    grid = OccupancyGrid.load(Path(__file__).resolve().parents[1] / "assets/mazes/simple.json")
    robot = SimulatedRobot(grid, Pose2D(*grid.cell_center((1, 1))))
    controller = WaypointController()
    navigator = MazeNavigator(
        grid,
        GroundTruthLocalization(lambda: robot.pose),
        AStarPlanner(),
        controller,
        robot,
        robot.radius,
    )
    assert navigator.plan_to((11, 9))
    for _ in range(20000):
        navigator.tick(1 / 60)
        assert robot.step(1 / 60)
        if navigator.reached_goal:
            break
    assert navigator.reached_goal
    goal = grid.cell_center((11, 9))
    assert hypot(robot.pose.x - goal[0], robot.pose.y - goal[1]) <= controller.tolerance
    assert robot.collision_count == 0
    assert robot.command == VelocityCommand()


def test_core_accepts_independent_adapters_and_failed_replan_stops():
    class FakeRobot(RobotController):
        last = VelocityCommand(0.1)

        def command_velocity(self, command):
            self.last = command

    class FakeLocalization(LocalizationProvider):
        def get_pose(self):
            return Pose2D(0.5, 0.5)

    grid = OccupancyGrid([[0, 0, 1, 0]], 1.0)
    robot = FakeRobot()
    navigator = MazeNavigator(
        grid, FakeLocalization(), AStarPlanner(), WaypointController(), robot, 0.025
    )
    assert navigator.plan_to((1, 0))
    navigator.tick(0.1)
    assert robot.last.linear > 0
    assert navigator.plan_to((3, 0)) == []
    assert robot.last == VelocityCommand()
    assert not navigator.reached_goal
    with pytest.raises(ValueError):
        navigator.plan_to((-1, 0))
    assert robot.last == VelocityCommand()


def test_controller_does_not_overshoot_and_turns_before_driving():
    controller = WaypointController()
    controller.set_path([(1, 0)])
    assert controller.update(Pose2D(0, 0, 1.5), 0.1).linear == 0
    assert controller.update(Pose2D(0.999, 0), 1) == VelocityCommand()
    assert controller.finished
    controller.set_path([(1, 0)])
    assert controller.update(Pose2D(0.99, 0), 1).linear == pytest.approx(0.01)
