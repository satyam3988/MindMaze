from math import pi

import pytest

from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Pose2D, VelocityCommand
from vector_maze.simulation.robot import SimulatedRobot


def test_valid_movement_rotation_and_stop():
    robot = SimulatedRobot(OccupancyGrid([[0] * 4] * 4, 1.0), Pose2D(1.5, 1.5))
    robot.command_velocity(VelocityCommand(0.1))
    assert robot.step(1)
    assert robot.pose.x == pytest.approx(1.6)
    robot.command_velocity(VelocityCommand(angular=pi / 2))
    assert robot.step(1)
    assert robot.pose.heading == pytest.approx(pi / 2)
    robot.command_velocity(VelocityCommand(0.1))
    assert robot.step(1)
    assert robot.pose.y == pytest.approx(1.6)
    robot.stop()
    previous = robot.pose
    assert robot.step(1)
    assert robot.pose == previous


def test_collision_rejects_translation_and_stops():
    grid = OccupancyGrid([[0, 1, 0], [0, 0, 0]], 1.0)
    robot = SimulatedRobot(grid, Pose2D(0.5, 0.5), max_speed=3)
    robot.command_velocity(VelocityCommand(2.0))
    assert not robot.step(1)
    assert robot.pose == Pose2D(0.5, 0.5)
    assert robot.command == VelocityCommand()
    assert robot.collision_count == 1


def test_invalid_spawn_and_dt():
    grid = OccupancyGrid([[0, 1]], 1.0)
    with pytest.raises(ValueError):
        SimulatedRobot(grid, Pose2D(1.5, 0.5))
    robot = SimulatedRobot(grid, Pose2D(0.5, 0.5))
    for dt in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            robot.step(dt)


def test_velocity_is_limited():
    robot = SimulatedRobot(OccupancyGrid([[0] * 3] * 3, 1), Pose2D(1.5, 1.5))
    robot.command_velocity(VelocityCommand(999, -999))
    assert robot.command == VelocityCommand(robot.max_speed, -robot.max_turn_speed)
