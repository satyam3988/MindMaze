"""Webots controller runtimes reuse the core; only this entrypoint imports its API."""

import json
import logging
import os
import sys
from dataclasses import asdict
from math import hypot
from pathlib import Path

from vector_maze.control.waypoint import WaypointController
from vector_maze.mapping.grid import OccupancyGrid
from vector_maze.models import VelocityCommand
from vector_maze.navigation import MazeNavigator
from vector_maze.perception.camera_map import ColorExtractionConfig, capture_map
from vector_maze.perception.debug import save_debug_artifacts
from vector_maze.perception.evaluation import compare_maps
from vector_maze.planning.astar import AStarPlanner
from vector_maze.vision.calibration import CameraCalibration
from vector_maze.webots.camera import WebotsCameraSource, WebotsReceivedCameraSource, encode_frame
from vector_maze.webots.config import DriveConfig
from vector_maze.webots.localization import WebotsGroundTruthLocalization
from vector_maze.webots.robot_adapter import WebotsRobotAdapter

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts/webots"
logger = logging.getLogger(__name__)


def calibration_from_config(config):
    data = dict(config["calibration"])
    if "image_corners" in data:
        data.pop("camera_center", None)
        data.pop("plane_height", None)
        return CameraCalibration(config["camera_width"], config["camera_height_pixels"], **data)
    return CameraCalibration.top_down(
        image_width=config["camera_width"],
        image_height=config["camera_height_pixels"],
        camera_height=config["camera_height"],
        horizontal_fov=config["camera_horizontal_fov"],
        **data,
    )


def display_path(supervisor, grid, path):
    """Draw only the route actually returned by MazeNavigator (no obstacle reads)."""
    points = supervisor.getFromDef("PATH_COORDINATES").getField("point")
    indices = supervisor.getFromDef("PATH_GEOMETRY").getField("coordIndex")
    while points.getCount():
        points.removeMF(0)
    while indices.getCount():
        indices.removeMF(0)
    for i, cell in enumerate(path):
        x, y = grid.cell_center(cell)
        points.insertMFVec3f(-1, [x, -y, 0.002])
        indices.insertMFInt32(-1, i)
    indices.insertMFInt32(-1, -1)


def load_settings() -> tuple[dict, Path]:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "configs/webots.json"
    return json.loads(path.read_text(encoding="utf-8")), path


def navigation_main() -> None:
    from controller import Supervisor

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    collision_check = os.environ.get("VECTOR_MAZE_COLLISION_CHECK") == "1"
    vision_map = os.environ.get("VECTOR_MAZE_VISION_MAP") == "1"
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        force=True,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                ARTIFACTS
                / (
                    "vision-controller.log"
                    if vision_map
                    else "collision-controller.log"
                    if collision_check
                    else "controller.log"
                ),
                mode="w",
                encoding="utf-8",
            ),
        ],
    )
    config, config_path = load_settings()
    supervisor = Supervisor()
    timestep = int(supervisor.getBasicTimeStep())
    dt = timestep / 1000
    robot_node = supervisor.getSelf()
    drive = DriveConfig(**config["drive"])
    robot = WebotsRobotAdapter(
        supervisor.getDevice("left wheel motor"), supervisor.getDevice("right wheel motor"), drive
    )
    localization = WebotsGroundTruthLocalization(robot_node)
    goal = tuple(config["goal"])
    goal_point = None
    controller = WaypointController(
        speed=config["linear_speed"],
        turn_speed=config["turn_speed"],
        tolerance=config["waypoint_tolerance"],
        heading_tolerance=config["heading_tolerance"],
    )
    navigator = None
    map_report = {}
    failure = None
    robot_node.enableContactPointsTracking(timestep, True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    batch = os.environ.get("VECTOR_MAZE_BATCH") == "1"
    collision_check = os.environ.get("VECTOR_MAZE_COLLISION_CHECK") == "1"
    collisions = 0
    in_contact = False
    steps = 0
    max_displacement = 0.0
    next_log = 0.0
    status = "RUNNING"
    initial = localization.get_pose()
    report_name = (
        "vision-navigation.json"
        if vision_map
        else ("collision-check.json" if collision_check else "navigation.json")
    )
    try:
        logger.info(
            "Navigation map source: %s",
            "CAMERA PERCEPTION" if vision_map else "GROUND TRUTH JSON (debug)",
        )
        logger.info("Localization source: WEBOTS GROUND TRUTH")
        if vision_map:
            receiver = supervisor.getDevice("overhead RGB receiver")
            receiver.enable(timestep)
        # Let gravity settle the real rigid body before planning; never set its pose.
        for _ in range(round(0.5 / dt)):
            if supervisor.step(timestep) == -1:
                return
        initial = localization.get_pose()
        if vision_map:
            calibration = calibration_from_config(config)
            extraction_config = ColorExtractionConfig(**config["perception"])
            deadline = supervisor.getTime() + 5
            while receiver.getQueueLength() == 0:
                if supervisor.getTime() >= deadline:
                    raise RuntimeError("Overhead RGB camera timeout; navigation stopped")
                if supervisor.step(timestep) == -1:
                    raise RuntimeError("Simulation closed while waiting for camera")
            rgb, extracted = capture_map(
                WebotsReceivedCameraSource(receiver),
                calibration,
                extraction_config,
                tuple(config["start"]),
                goal,
            )
            grid = extracted.grid
            logger.info(
                "Camera=%dx%d ROI=%s Rectified=%s Grid=%dx%d Occupied=%d Free=%d "
                "Occupancy ratio=%.3f",
                calibration.image_width,
                calibration.image_height,
                calibration.image_corners,
                calibration.rectified_size,
                grid.width,
                grid.height,
                sum(map(sum, grid.cells)),
                grid.width * grid.height - sum(map(sum, grid.cells)),
                sum(map(sum, grid.cells)) / (grid.width * grid.height),
            )
        else:
            grid = OccupancyGrid.load(config_path.parent / config["maze"])
            # This debug check is intentionally absent from camera-map navigation.
            missing = [
                f"WALL_{x}_{y}"
                for y, row in enumerate(grid.cells)
                for x, occupied in enumerate(row)
                if occupied and supervisor.getFromDef(f"WALL_{x}_{y}") is None
            ]
            if missing:
                raise RuntimeError(f"World is missing physical walls: {missing}")
        goal_point = grid.cell_center(goal)
        navigator = MazeNavigator(
            grid, localization, AStarPlanner(), controller, robot, config["robot_radius"]
        )
        path = navigator.plan_to(goal)
        if not path:
            raise ValueError("Goal unreachable")
        display_path(supervisor, grid, path)
        if vision_map:
            # Evaluation happens AFTER planning. The reference never enters the navigator.
            truth_for_evaluation = OccupancyGrid.load(config_path.parent / config["maze"])
            metrics = asdict(compare_maps(truth_for_evaluation, grid))
            map_report = {
                "metrics": metrics,
                "recovered_cells": grid.cells,
                "camera_resolution": [rgb.shape[1], rgb.shape[0]],
                "rectified_resolution": list(calibration.rectified_size),
                "image_corners": calibration.image_corners,
                "homography_image_to_world": calibration.image_to_world.tolist(),
                "cell_resolution": grid.resolution,
                "path": path,
                "robot_radius": config["robot_radius"],
            }
            logger.info("Camera map evaluation only: %s", json.dumps(metrics))
            if os.environ.get("VECTOR_MAZE_SAVE_DEBUG") == "1":
                directory = Path(
                    os.environ.get("VECTOR_MAZE_PERCEPTION_DIR", str(ROOT / "artifacts/perception"))
                )
                save_debug_artifacts(
                    directory,
                    rgb,
                    extracted,
                    truth_for_evaluation,
                    os.environ.get("VECTOR_MAZE_RUN_ID"),
                )
        logger.info(
            "WEBOTS 3D NAVIGATION | Maze=%s | Start=%s | Goal=%s | Path length=%d",
            config["maze"],
            config["start"],
            goal,
            len(path),
        )
        supervisor.exportImage(str(ARTIFACTS / "perspective-start.png"), 95)
        while supervisor.step(timestep) != -1:
            steps += 1
            pose = localization.get_pose()
            max_displacement = max(max_displacement, hypot(pose.x - initial.x, pose.y - initial.y))
            # Ignore ground support contacts. Wall contacts are elevated and real ODE contacts.
            wall_contacts = [p for p in robot_node.getContactPoints(True) if p.point[2] > 0.005]
            contact = bool(wall_contacts)
            if contact and not in_contact:
                collisions += 1
            in_contact = contact
            if collision_check:
                robot.command_velocity(VelocityCommand(linear=0.06))
                if contact:
                    status = "COLLISION_CHECK_PASSED"
                    break
            else:
                if contact:
                    status = "COLLISION"
                    break
                navigator.tick(dt)
                if navigator.reached_goal:
                    status = "GOAL_REACHED"
                    break
            if supervisor.getTime() >= next_log:
                target = controller.current_waypoint
                waypoint_distance = hypot(target[0] - pose.x, target[1] - pose.y) if target else 0
                logger.info(
                    "state=%s t=%.2f pose=(%.3f,%.3f,%.3f) waypoint=%d/%d "
                    "waypoint_distance=%.4f v=%.3f omega=%.3f goal_distance=%.3f",
                    status,
                    supervisor.getTime(),
                    pose.x,
                    pose.y,
                    pose.heading,
                    controller.waypoint_index,
                    len(path),
                    waypoint_distance,
                    robot.last_command.linear,
                    robot.last_command.angular,
                    hypot(pose.x - goal_point[0], pose.y - goal_point[1]),
                )
                next_log = supervisor.getTime() + 1
            if supervisor.getTime() >= (
                30 if collision_check else config["max_simulation_seconds"]
            ):
                status = "TIMEOUT"
                break
        else:
            status = "SIMULATION_CLOSED"
    except Exception as error:
        status = "ERROR"
        failure = str(error)
        logger.exception("Webots navigation failed")
    finally:
        robot.stop()
        pose = localization.get_pose()
        result = {
            "run_id": os.environ.get("VECTOR_MAZE_RUN_ID"),
            "status": status,
            "map_source": "CAMERA PERCEPTION" if vision_map else "GROUND TRUTH JSON",
            "localization_source": "WEBOTS GROUND TRUTH",
            "error": failure,
            "stopped_command": asdict(robot.last_command),
            "goal_reached": bool(navigator and navigator.reached_goal),
            "simulation_time": supervisor.getTime(),
            "steps": steps,
            "collisions": collisions,
            "max_displacement": max_displacement,
            "pose": asdict(pose),
            "goal_distance": hypot(pose.x - goal_point[0], pose.y - goal_point[1])
            if goal_point
            else None,
            "path_length": len(navigator.path) if navigator else 0,
            **map_report,
        }
        (ARTIFACTS / report_name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        logger.info("FINAL WEBOTS RESULT %s", json.dumps(result))
        # Flush zero motor commands through actual physics before pausing/quitting.
        for _ in range(4):
            if supervisor.step(timestep) == -1:
                break
        supervisor.exportImage(str(ARTIFACTS / "perspective-final.png"), 95)
        if batch:
            supervisor.simulationQuit(
                0 if status in ("GOAL_REACHED", "COLLISION_CHECK_PASSED") else 1
            )
        else:
            supervisor.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
            while supervisor.step(timestep) != -1:
                pass


def camera_main() -> None:
    from controller import Robot

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=True)
    robot = Robot()
    timestep = int(robot.getBasicTimeStep())
    device = robot.getDevice("overhead camera")
    device.enable(timestep * 4)
    source = WebotsCameraSource(device, robot.getTime)
    emitter = robot.getDevice("overhead RGB emitter")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    next_capture = 0.55
    first = True
    while robot.step(timestep) != -1:
        if robot.getTime() >= next_capture:
            frame = source.capture()
            if first:
                device.saveImage(str(ARTIFACTS / "overhead-start.png"), 95)
                logger.info(
                    "Overhead RGB camera ready: %dx%d, packed RGB bytes=%d",
                    frame.width,
                    frame.height,
                    len(frame.rgb),
                )
                first = False
                emitter.send(encode_frame(frame))
            # Static map: one initial frame, no recurring image writes or extraction.
            next_capture = float("inf")
