"""No Webots GUI: exercise the actual RobotClient over a local TCP WebSocket."""

import os
import socket
import subprocess
import sys
import time

import httpx

from robotic_mind_sdk import AgentManifest, RobotClient
from robotic_mind_sdk.models import MemoryEntry, Telemetry


def test_sdk_live_transport(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'live.db'}",
        "LLM_MODE": "mock",
        "STRICT_HACKATHON_MODE": "false",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "robotic_mind.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    robot = None
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}") as http:
            for _ in range(100):
                try:
                    if http.get("/api/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.05)
            created = http.post("/api/spaces", json={"name": "SDK test"}).json()["space"]
            robot = RobotClient(
                "Rover",
                created["invite_code"],
                AgentManifest(
                    agent_id="rover",
                    display_name="Rover",
                    agent_type="rover",
                    capabilities=["camera", "navigate", "detect_color"],
                ),
                f"http://127.0.0.1:{port}",
            ).connect()
            assert robot.connected.wait(5)
            robot.publish_telemetry(Telemetry(position={"x": 4, "y": 2, "z": 0}))
            robot.remember(MemoryEntry(title="SDK memory"))
            for _ in range(100):
                saved = http.get("/api/agents/rover/memories").json()
                if saved:
                    break
                time.sleep(0.03)
            assert saved[0]["title"] == "SDK memory"
            http.post(f"/api/spaces/{created['id']}/commands", json={"text": "Find red objects"})
            assignment = None
            for _ in range(100):
                assignment = robot.next_assignment()
                if assignment:
                    break
                time.sleep(0.03)
            assert assignment.agent_id == "rover"
            assert assignment.waypoints
            assert not robot.errors
    finally:
        if robot:
            robot.close()
        process.terminate()
        process.wait(timeout=10)
