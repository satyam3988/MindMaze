"""Each controller owns only its own pose and RGB camera. No object scene queries."""

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from controller import Supervisor  # noqa: E402
from scene_capture import SceneCapture  # noqa: E402

from robotic_mind.perception import detect_red, transform_view  # noqa: E402
from robotic_mind_sdk import AgentManifest, RobotAdapter, RobotClient  # noqa: E402
from robotic_mind_sdk.models import ActiveMindState, Observation, Position, Telemetry  # noqa: E402


class WebotsDroneAdapter(RobotAdapter):
    """Kinematic aerial motion; replaceable with a stabilized flight implementation."""

    def __init__(self, robot):
        self.robot = robot
        self.node = robot.getSelf()
        self.translation = self.node.getField("translation")
        self.camera = robot.getDevice("rgb_camera")
        self.camera.enable(128)
        self.speed = 2.4

    def get_pose(self):
        return Position(**dict(zip(("x", "y", "z"), self.translation.getSFVec3f())))

    def move_to(self, target, dt):
        pose = self.get_pose()
        start, end = np.array([pose.x, pose.y, pose.z]), np.array([target.x, target.y, target.z])
        delta = end - start
        distance = float(np.linalg.norm(delta))
        if distance <= self.speed * dt:
            self.translation.setSFVec3f(end.tolist())
            return True
        self.translation.setSFVec3f((start + delta / distance * self.speed * dt).tolist())
        return False

    def stop(self):
        pass  # A kinematic robot holds its current position.

    def capture_camera(self):
        raw = self.camera.getImage()
        if raw is None:
            return None
        return (
            np.frombuffer(raw, np.uint8)
            .reshape((self.camera.getHeight(), self.camera.getWidth(), 4))[:, :, :3]
            .copy()
        )

    def capabilities(self):
        return ["fly", "navigate", "camera", "inspect", "detect_color"]


def main():
    robot = Supervisor()
    scene_capture = SceneCapture(robot, ROOT) if robot.getName() == "Scout-01" else None
    adapter = WebotsDroneAdapter(robot)
    name = os.environ.get("ROBOT_NAME", robot.getName())
    sensors = json.loads((ROOT / "simulation/webots/config/sensors.json").read_text())
    sensor = sensors.get(robot.getName(), {})
    manifest = AgentManifest(
        agent_id=name.lower(),
        display_name=name,
        agent_type=os.environ.get("ROBOT_TYPE", "drone"),
        capabilities=adapter.capabilities(),
        sensors=["rgb_camera", "position", "altitude"],
        actions=["move_to", "scan", "inspect", "return_home"],
    )
    client = RobotClient(
        name,
        os.environ["INVITE_CODE"],
        manifest,
        os.environ.get("ROBOTIC_MIND_API", "http://localhost:8000"),
    ).connect()
    assignment, index, seen = None, 0, []
    last_sample, last_mind, dwell_until = -1, -1, 0
    timestep = int(robot.getBasicTimeStep())
    try:
        while robot.step(timestep) != -1:
            t = robot.getTime()
            if scene_capture:
                scene_capture.tick(t)
            if not client.connected.is_set():
                adapter.stop()
                continue
            if assignment and assignment.mission_id in client.cancelled_missions:
                assignment = None
                adapter.stop()
            if assignment is None:
                candidate = client.next_assignment()
                if candidate and candidate.mission_id not in client.cancelled_missions:
                    assignment, index, seen = candidate, 0, []
                    client.task_status(assignment.id, "started")
            if assignment and index < len(assignment.waypoints) and t >= dwell_until:
                if adapter.move_to(assignment.waypoints[index], timestep / 1000):
                    index += 1
                    dwell_until = t + 0.35
            if t - last_sample >= 0.4:
                last_sample = t
                pose = adapter.get_pose()
                client.publish_telemetry(Telemetry(position=pose))
                image = adapter.capture_camera()
                if image is not None:
                    image = transform_view(
                        image,
                        brightness=float(
                            os.environ.get("CAMERA_BRIGHTNESS", sensor.get("brightness", 1))
                        ),
                        blur=int(os.environ.get("CAMERA_BLUR", sensor.get("blur", 0))),
                        noise=float(os.environ.get("CAMERA_NOISE", sensor.get("noise", 0))),
                        color_shift=int(
                            os.environ.get("CAMERA_COLOR_SHIFT", sensor.get("color_shift", 0))
                        ),
                    )
                    if assignment:
                        camera_pose = pose.model_copy(update={"z": pose.z - 0.12})
                        for detected in detect_red(
                            image,
                            camera_pose,
                            fov=adapter.camera.getFov(),
                            yaw=float(sensor.get("yaw", 0)),
                        ):
                            pos = detected["position"]
                            if any(math.hypot(pos.x - p.x, pos.y - p.y) < 0.85 for p in seen):
                                continue
                            seen.append(pos)
                            known = next(
                                (
                                    d
                                    for d in client.group_mind["discoveries"]
                                    if math.hypot(
                                        pos.x - d["position"]["x"], pos.y - d["position"]["y"]
                                    )
                                    < 0.8
                                ),
                                None,
                            )
                            client.publish_observation(
                                Observation(
                                    mission_id=assignment.mission_id,
                                    confidence=detected["confidence"],
                                    position=pos,
                                    region=assignment.region,
                                    summary="Camera confirms a target already in Group Mind"
                                    if known
                                    else "New red candidate verified by RGB camera",
                                )
                            )
                            x, y, w, h = detected["bbox"]
                            cv2.rectangle(image, (x, y), (x + w, y + h), (60, 255, 120), 2)
                    ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if ok:
                        client.publish_camera(jpeg.tobytes())
            if t - last_mind >= 1:
                last_mind = t
                client.update_active_mind(
                    ActiveMindState(
                        status="searching" if assignment else "idle",
                        objective=assignment.objective if assignment else "Awaiting a mission",
                        assignment=assignment.region if assignment else None,
                        observation_summary=f"{len(seen)} red candidates verified by RGB camera",
                        decision_summary=(
                            f"Use {len(client.group_mind['discoveries'])} shared discoveries; "
                            "continue the assigned sweep without repeating local inspections"
                        ),
                        current_action=f"Waypoint {index}/{len(assignment.waypoints)}"
                        if assignment
                        else "Holding position",
                        next_step="Capture camera and continue sweep"
                        if assignment
                        else "Receive assignment",
                        position=adapter.get_pose(),
                        confidence=0.95,
                    )
                )
            if assignment and index == len(assignment.waypoints) and t >= dwell_until:
                client.task_status(assignment.id, "completed", 1)
                assignment = None
    finally:
        client.close()


if __name__ == "__main__":
    main()
