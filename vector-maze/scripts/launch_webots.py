"""Generate the maze and open Webots GUI paused, using this Python environment."""

import argparse
import json
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path

from vector_maze.webots.config import find_webots
from vector_maze.webots.world_generator import write_world

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--webots-home", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/webots.json")
    parser.add_argument("--run", action="store_true", help="Start running rather than paused")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--vision-map", action="store_true", help="Plan ONLY from overhead RGB")
    modes.add_argument("--ground-truth-map", action="store_true", help="Privileged JSON debug mode")
    parser.add_argument(
        "--save-debug", action="store_true", help="Save initial perception snapshot"
    )
    parser.add_argument(
        "--perception-debug", action="store_true", help="Open six-panel debug window"
    )
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/perception")
    parser.add_argument("--batch", action="store_true", help="Run fast and exit with a result")
    parser.add_argument(
        "--collision-check", action="store_true", help="Batch-only physics test: drive into a wall"
    )
    parser.add_argument("--timeout", type=float, default=180, help="Batch wall-clock timeout")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.collision_check and not args.batch:
        parser.error("--collision-check requires --batch")
    if args.collision_check and args.vision_map:
        parser.error("--collision-check is a ground-truth physics debug test")
    if (args.save_debug or args.perception_debug) and not args.vision_map:
        parser.error("Perception debug flags require --vision-map")
    try:
        executable = find_webots(args.webots_home)
        required = [
            "protos/VectorRobot.proto",
            "protos/MazeWall.proto",
            "controllers/vector_maze_controller/vector_maze_controller.py",
            "controllers/overhead_camera_controller/overhead_camera_controller.py",
        ]
        for relative in required:
            if not (ROOT / "webots" / relative).is_file():
                raise FileNotFoundError(f"Missing Webots project file: {relative}")
        # Ignore generated runtime files: interpreter paths are specific to this machine.
        for controller in ("vector_maze_controller", "overhead_camera_controller"):
            runtime = ROOT / "webots/controllers" / controller / "runtime.ini"
            runtime.write_text(
                f'[python]\nCOMMAND = "{Path(sys.executable).as_posix()}"\n', encoding="utf-8"
            )
        world = write_world(
            args.config.resolve(),
            ROOT / "webots/worlds/vector_maze.wbt",
            vision_map=args.vision_map,
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = (
            str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
        )
        environment["VECTOR_MAZE_BATCH"] = "1" if args.batch else "0"
        environment["VECTOR_MAZE_COLLISION_CHECK"] = "1" if args.collision_check else "0"
        run_id = uuid.uuid4().hex
        environment["VECTOR_MAZE_RUN_ID"] = run_id
        environment["VECTOR_MAZE_VISION_MAP"] = "1" if args.vision_map else "0"
        environment["VECTOR_MAZE_SAVE_DEBUG"] = (
            "1" if (args.save_debug or args.perception_debug) else "0"
        )
        environment["VECTOR_MAZE_PERCEPTION_DIR"] = str(args.artifact_dir.resolve())
        command = [
            str(executable),
            "--stdout",
            "--stderr",
            "--mode=fast" if args.batch else ("--mode=realtime" if args.run else "--mode=pause"),
        ]
        if args.batch:
            command.extend(["--batch", "--minimize"])
        command.append(str(world))
        logging.info("Webots: %s", executable)
        logging.info("World: %s", world)
        logging.info("Python controller: %s", sys.executable)
        logging.info(
            "Navigation map source: %s",
            "CAMERA PERCEPTION" if args.vision_map else "GROUND TRUTH JSON (debug)",
        )
        if args.perception_debug:
            subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "scripts/view_perception.py"),
                    "--directory",
                    str(args.artifact_dir.resolve()),
                    "--run-id",
                    run_id,
                ],
                cwd=ROOT,
            )
        if not args.batch:
            subprocess.Popen(command, cwd=ROOT, env=environment)
            logging.info(
                "GUI launched. %s",
                "Navigation starts automatically."
                if args.run
                else "Press Play to start navigation.",
            )
            return 0
        artifacts = ROOT / "artifacts/webots"
        artifacts.mkdir(parents=True, exist_ok=True)
        log_path = artifacts / ("collision-check.log" if args.collision_check else "batch.log")
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT
            )
            try:
                code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    process.terminate()
                logging.error("Webots batch timed out; see %s", log_path)
                return 1
        logging.info("Batch exit code=%d; log=%s", code, log_path)
        report_path = artifacts / (
            "vision-navigation.json"
            if args.vision_map
            else "collision-check.json"
            if args.collision_check
            else "navigation.json"
        )
        if not report_path.is_file():
            logging.error("Webots exited without a controller report")
            return 1
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected = "COLLISION_CHECK_PASSED" if args.collision_check else "GOAL_REACHED"
        if report.get("run_id") != run_id or report.get("status") != expected:
            logging.error("No successful result from this run: %s", report)
            return 1
        if args.vision_map and report.get("map_source") != "CAMERA PERCEPTION":
            logging.error("Expected a camera-derived map report")
            return 1
        logging.info("Verified result: %s", report)
        return code
    except (FileNotFoundError, ValueError) as error:
        logging.error("%s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
