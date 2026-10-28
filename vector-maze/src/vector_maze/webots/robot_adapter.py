"""Velocity-to-wheel adapter; Webots API objects are injected, not imported."""

from typing import Protocol

from vector_maze.interfaces import RobotController
from vector_maze.models import VelocityCommand
from vector_maze.webots.config import DriveConfig


class Motor(Protocol):
    def setPosition(self, position: float) -> None: ...
    def setVelocity(self, velocity: float) -> None: ...
    def getMaxVelocity(self) -> float: ...


def wheel_speeds(command: VelocityCommand, config: DriveConfig) -> tuple[float, float]:
    """Return left/right rad/s, preserving curvature during wheel saturation.

    Project positive omega is clockwise: left wheel runs faster than right.
    Both hinges rotate around local +Y; positive speed drives local +X.
    """
    v = max(-config.max_linear_velocity, min(config.max_linear_velocity, command.linear))
    omega = max(-config.max_angular_velocity, min(config.max_angular_velocity, command.angular))
    left = (v + omega * config.wheel_separation / 2) / config.wheel_radius
    right = (v - omega * config.wheel_separation / 2) / config.wheel_radius
    factor = max(1.0, abs(left) / config.max_wheel_speed, abs(right) / config.max_wheel_speed)
    return left / factor, right / factor


class WebotsRobotAdapter(RobotController):
    def __init__(self, left_motor: Motor, right_motor: Motor, config: DriveConfig) -> None:
        if min(left_motor.getMaxVelocity(), right_motor.getMaxVelocity()) < config.max_wheel_speed:
            raise ValueError("Configured wheel speed exceeds a Webots motor limit")
        self.left_motor = left_motor
        self.right_motor = right_motor
        self.config = config
        self.last_command = VelocityCommand()
        for motor in (left_motor, right_motor):
            motor.setPosition(float("inf"))
            motor.setVelocity(0.0)

    def command_velocity(self, command: VelocityCommand) -> None:
        self.last_command = command
        left, right = wheel_speeds(command, self.config)
        self.left_motor.setVelocity(left)
        self.right_motor.setVelocity(right)
