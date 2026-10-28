"""Run an interactive or deterministic headless maze navigation demo."""

import argparse
import json
import logging
import os
from math import isfinite
from pathlib import Path

from vector_maze.control.waypoint import WaypointController
from vector_maze.localization.ground_truth import GroundTruthLocalization
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Pose2D
from vector_maze.navigation import MazeNavigator
from vector_maze.planning.astar import AStarPlanner
from vector_maze.simulation.robot import SimulatedRobot

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/demo.json")
    parser.add_argument("--headless", action="store_true", help="Run without a window")
    parser.add_argument("--max-steps", type=int, help="Override simulation step budget")
    parser.add_argument("--exit-on-goal", action="store_true")
    parser.add_argument("--screenshot", type=Path, help="Save the final displayed frame")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING"), default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    if args.headless and args.screenshot:
        parser.error("--screenshot requires a rendered run")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    grid = OccupancyGrid.load(args.config.parent / config["maze"])
    start, goal = tuple(config["start"]), tuple(config["goal"])
    dt = config["dt"]
    max_steps = config["max_steps"] if args.max_steps is None else args.max_steps
    if not isfinite(dt) or dt <= 0 or max_steps <= 0:
        parser.error("dt and max_steps must be positive")
    robot = SimulatedRobot(grid, Pose2D(*grid.cell_center(start)), config["robot_radius"])
    navigator = MazeNavigator(
        grid,
        GroundTruthLocalization(lambda: robot.pose),
        AStarPlanner(),
        WaypointController(speed=config["linear_speed"]),
        robot,
        robot.radius,
    )
    if not navigator.plan_to(goal):
        logger.error("Goal is unreachable")
        return 1
    view = camera = None
    if not args.headless:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        from vector_maze.simulation.camera import SimulatedCamera
        from vector_maze.simulation.view import SimulationView

        camera = SimulatedCamera(grid, lambda: robot.pose, robot.radius, config["pixels_per_cell"])
        view = SimulationView(
            grid.width * config["pixels_per_cell"], grid.height * config["pixels_per_cell"]
        )
    steps = 0
    announced = False
    try:
        while True:
            if view and not view.process_events():
                logger.info("Demo closed by user")
                return 0
            if not view or not view.paused:
                if not navigator.reached_goal:
                    if steps >= max_steps:
                        logger.error("Goal not reached within %d steps", max_steps)
                        return 1
                    navigator.tick(dt)
                    if not robot.step(dt):
                        logger.error("Navigation halted after a collision")
                        return 1
                    steps += 1
                if navigator.reached_goal and not announced:
                    logger.info(
                        "Goal reached in %d steps; collisions=%d", steps, robot.collision_count
                    )
                    announced = True
            if view and camera:
                view.draw(camera.capture(), grid, navigator.path, goal, navigator.reached_goal)
                view.clock.tick(round(1 / dt))
            if navigator.reached_goal and (args.headless or args.exit_on_goal):
                return 0
    finally:
        robot.stop()
        if view:
            if args.screenshot:
                import pygame

                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                pygame.image.save(view.screen, str(args.screenshot))
            view.close()


if __name__ == "__main__":
    raise SystemExit(main())
