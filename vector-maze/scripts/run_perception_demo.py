"""Recover a maze from RGB, evaluate it, and navigate only on the recovered map."""

import argparse
import json
import logging
import os
from dataclasses import asdict
from math import isfinite
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from vector_maze.control.waypoint import WaypointController
from vector_maze.localization.ground_truth import GroundTruthLocalization
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import Pose2D
from vector_maze.navigation import MazeNavigator
from vector_maze.perception.evaluation import compare_maps
from vector_maze.perception.occupancy import ExtractionConfig, OccupancyGridExtractor
from vector_maze.planning.astar import AStarPlanner
from vector_maze.simulation.camera import SimulatedCamera
from vector_maze.simulation.robot import SimulatedRobot
from vector_maze.vision.coordinates import PixelGridTransform

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/perception.json")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--exit-on-goal", action="store_true")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--report", type=Path, help="Write metrics and navigation results as JSON")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING"), default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    if args.headless and args.screenshot:
        parser.error("--screenshot requires a rendered run")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    dt = config["dt"]
    max_steps = config["max_steps"] if args.max_steps is None else args.max_steps
    if not isfinite(dt) or dt <= 0 or max_steps <= 0:
        parser.error("dt and max_steps must be positive")
    calibration = config["perception"]
    transform = PixelGridTransform(calibration["pixels_per_cell"], calibration["resolution"])
    extractor = OccupancyGridExtractor(
        transform,
        ExtractionConfig(
            calibration["grayscale_threshold"], calibration["minimum_occupancy_ratio"]
        ),
    )

    # Ground truth defines simulator geometry; it never enters the extractor or navigator.
    ground_truth = OccupancyGrid.load(args.config.parent / config["maze"])
    start, goal = tuple(config["start"]), tuple(config["goal"])
    robot = SimulatedRobot(
        ground_truth, Pose2D(*ground_truth.cell_center(start)), config["robot_radius"]
    )
    camera = SimulatedCamera(
        ground_truth, lambda: robot.pose, robot.radius, config["pixels_per_cell"]
    )
    frame = camera.capture()
    recovered = extractor.extract(frame)
    metrics = compare_maps(ground_truth, recovered)
    logger.info(
        "Perception: cells=%d correct=%d incorrect=%d accuracy=%.4f "
        "precision=%.4f recall=%.4f IoU=%.4f",
        metrics.total_cells,
        metrics.correctly_classified_cells,
        metrics.incorrect_cells,
        metrics.accuracy,
        metrics.occupied_precision,
        metrics.occupied_recall,
        metrics.occupied_iou,
    )
    navigator = MazeNavigator(
        recovered,
        GroundTruthLocalization(lambda: robot.pose),
        AStarPlanner(),
        WaypointController(speed=config["linear_speed"]),
        robot,
        robot.radius,
    )
    view = None
    if not args.headless:
        from vector_maze.simulation.perception_view import PerceptionView

        view = PerceptionView(frame, transform)
    steps = 0
    status = "running"
    announced = False
    try:
        if not navigator.plan_to(goal):
            status = "unreachable"
            logger.error("Goal is unreachable on the recovered map")
            return 1
        while True:
            if view and not view.process_events():
                status = "closed_by_user"
                return 0
            if not view or not view.paused:
                if not navigator.reached_goal:
                    if steps >= max_steps:
                        status = "step_budget_exhausted"
                        logger.error("Goal not reached within %d steps", max_steps)
                        return 1
                    navigator.tick(dt)
                    steps += 1
                    if not robot.step(dt):
                        status = "collision"
                        logger.error("Navigation halted after a collision")
                        return 1
                if navigator.reached_goal and not announced:
                    status = "goal_reached"
                    logger.info(
                        "Goal reached in %d steps; collisions=%d", steps, robot.collision_count
                    )
                    announced = True
            if view:
                view.draw_comparison(
                    camera.capture(),
                    ground_truth,
                    recovered,
                    metrics,
                    navigator.path,
                    goal,
                    robot.pose,
                    robot.radius,
                    steps,
                    robot.collision_count,
                    navigator.reached_goal,
                )
                view.clock.tick(max(1, round(1 / dt)))
            if navigator.reached_goal and (args.headless or args.exit_on_goal):
                return 0
    except ValueError as error:
        status = "invalid_navigation_map"
        logger.error("Navigation rejected recovered map: %s", error)
        return 1
    finally:
        robot.stop()
        result = {
            "perception": asdict(metrics),
            "steps": steps,
            "collisions": robot.collision_count,
            "goal_reached": navigator.reached_goal,
            "status": status,
            "path_waypoints": len(navigator.path),
        }
        logger.info("Final result: %s", json.dumps(result))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if view:
            try:
                if args.screenshot:
                    import pygame

                    # Also render failures that occurred before the first loop draw.
                    view.draw_comparison(
                        camera.capture(),
                        ground_truth,
                        recovered,
                        metrics,
                        navigator.path,
                        goal,
                        robot.pose,
                        robot.radius,
                        steps,
                        robot.collision_count,
                        navigator.reached_goal,
                    )
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    pygame.image.save(view.screen, str(args.screenshot))
            finally:
                view.close()


if __name__ == "__main__":
    raise SystemExit(main())
