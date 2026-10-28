"""Opt-in real physics checks; normal tests never require an installed simulator."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.environ.get("VECTOR_MAZE_WEBOTS_TEST") != "1",
    reason="Set VECTOR_MAZE_WEBOTS_TEST=1 to run real Webots physics",
)


def test_real_webots_reaches_goal_with_wheel_motion():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/launch_webots.py"), "--batch"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=190,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((ROOT / "artifacts/webots/navigation.json").read_text())
    assert report["goal_reached"] and report["status"] == "GOAL_REACHED"
    assert report["max_displacement"] > 1
    assert report["goal_distance"] <= 0.003
    assert report["collisions"] == 0


def test_real_webots_wall_blocks_robot():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/launch_webots.py"), "--batch", "--collision-check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=190,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((ROOT / "artifacts/webots/collision-check.json").read_text())
    assert report["status"] == "COLLISION_CHECK_PASSED"
    assert report["collisions"] == 1
    # The wall starts at X=0.4; the front body must remain on this side of it.
    assert report["pose"]["x"] < 0.4


@pytest.mark.parametrize("layout", ["simple", "open", "serpentine"])
def test_real_rendered_camera_navigation_multiple_layouts(layout):
    config = ROOT / "configs" / ("webots.json" if layout == "simple" else f"webots-{layout}.json")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/launch_webots.py"),
            "--vision-map",
            "--batch",
            "--save-debug",
            "--config",
            str(config),
            "--artifact-dir",
            str(ROOT / "artifacts/perception" / layout),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=190,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((ROOT / "artifacts/webots/vision-navigation.json").read_text())
    assert report["map_source"] == "CAMERA PERCEPTION"
    assert report["localization_source"] == "WEBOTS GROUND TRUTH"
    assert report["status"] == "GOAL_REACHED" and report["goal_reached"]
    assert report["collisions"] == 0 and report["goal_distance"] <= 0.003
    assert report["metrics"]["accuracy"] == report["metrics"]["occupied_f1"] == 1
    assert report["metrics"]["false_positive"] == report["metrics"]["false_negative"] == 0
    assert report["camera_resolution"] == [640, 480]
    assert report["steps"] > 1000 and report["max_displacement"] > 1
    snapshot = ROOT / "artifacts/perception" / layout
    metadata = json.loads((snapshot / "metrics.json").read_text())
    assert metadata["run_id"] == report["run_id"]
    (snapshot / "navigation.json").write_text(json.dumps(report, indent=2) + "\n")


def test_real_bad_perception_stops_without_json_fallback(tmp_path):
    config = json.loads((ROOT / "configs/webots.json").read_text())
    config["maze"] = str(ROOT / "assets/mazes/simple.json")
    config["perception"]["wall_hsv_lower"] = [140, 65, 45]
    config["perception"]["wall_hsv_upper"] = [150, 255, 255]
    config_path = tmp_path / "invalid-wall-class.json"
    config_path.write_text(json.dumps(config))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/launch_webots.py"),
            "--vision-map",
            "--batch",
            "--config",
            str(config_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=190,
    )
    assert result.returncode != 0
    report = json.loads((ROOT / "artifacts/webots/vision-navigation.json").read_text())
    assert report["map_source"] == "CAMERA PERCEPTION" and report["status"] == "ERROR"
    assert "occupancy ratio" in report["error"]
    assert report["steps"] == report["path_length"] == 0
    assert not report["goal_reached"] and report["collisions"] == 0
    assert report["stopped_command"] == {"linear": 0.0, "angular": 0.0}
