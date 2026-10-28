import json
import logging
import queue
import threading
import time

from websockets.sync.client import connect

from robotic_mind_sdk.models import Assignment

log = logging.getLogger("robotic_mind_sdk")


class RobotClient:
    """Background transport keeps HTTP/model latency out of the simulator step loop."""

    def __init__(self, name, invite_code, manifest, server_url="http://localhost:8000"):
        self.name, self.invite_code, self.manifest = name, invite_code, manifest
        self.url = server_url.replace("http://", "ws://").replace("https://", "wss://")
        self.url = self.url.rstrip("/") + "/ws/robots/" + manifest.agent_id
        self.assignments = queue.Queue()
        self.outbox = queue.Queue(maxsize=128)
        self.connected = threading.Event()
        self.closed = threading.Event()
        self.group_mind = {"discoveries": [], "cleared_regions": []}
        self.errors = []
        self.cancelled_missions = set()
        self.socket = None
        self.thread = None

    def connect(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def _run(self):
        while not self.closed.is_set():
            try:
                with connect(self.url, max_size=1_000_000, open_timeout=5) as ws:
                    self.socket = ws
                    ws.send(
                        json.dumps(
                            {
                                "type": "join",
                                "invite_code": self.invite_code,
                                "manifest": self.manifest.model_dump(),
                            }
                        )
                    )
                    hello = json.loads(ws.recv(timeout=10))
                    if hello["type"] != "joined":
                        raise ValueError(hello.get("detail", "Join failed"))
                    self.group_mind = hello["group_mind"]
                    for assignment in hello["assignments"]:
                        self.assignments.put(Assignment.model_validate(assignment))
                    self.connected.set()
                    heartbeat = 0
                    while not self.closed.is_set():
                        if time.monotonic() - heartbeat > 2:
                            ws.send('{"type":"heartbeat"}')
                            heartbeat = time.monotonic()
                        for _ in range(16):
                            try:
                                packet = self.outbox.get_nowait()
                            except queue.Empty:
                                break
                            ws.send(packet if isinstance(packet, bytes) else json.dumps(packet))
                        try:
                            event = json.loads(ws.recv(timeout=0.02))
                        except TimeoutError:
                            continue
                        kind = event["type"]
                        if kind == "assignment":
                            self.assignments.put(Assignment.model_validate(event["data"]))
                        elif kind in ("object.discovered", "object.merged"):
                            items = self.group_mind["discoveries"]
                            self.group_mind["discoveries"] = [
                                d for d in items if d["id"] != event["data"]["id"]
                            ] + [event["data"]]
                        elif kind == "region.cleared":
                            self.group_mind["cleared_regions"].append(event["data"])
                        elif kind == "mission.failed":
                            self.cancelled_missions.add(event["data"]["id"])
                        elif kind == "error":
                            self.errors.append(event["detail"])
                            log.error("Robot protocol: %s", event["detail"])
            except Exception as exc:
                if not self.closed.is_set():
                    log.warning("Robot transport reconnecting: %s", exc)
            finally:
                self.connected.clear()
                self.socket = None
            self.closed.wait(1)

    def _send(self, kind, data):
        value = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
        self.outbox.put({"type": kind, "data": value}, timeout=1)

    def publish_telemetry(self, data):
        self._send("telemetry", data)

    def publish_observation(self, data):
        self._send("observation", data)

    def update_active_mind(self, data):
        self._send("active_mind", data)

    def remember(self, data):
        self._send("memory", data)

    def publish_shared_memory(self, data):
        self._send("shared_memory", data)

    def publish_camera(self, jpeg: bytes):
        if not self.outbox.full():
            self.outbox.put_nowait(jpeg)

    def task_status(self, assignment_id, status, progress=0):
        self._send(
            "task_status", {"assignment_id": assignment_id, "status": status, "progress": progress}
        )

    def next_assignment(self):
        try:
            return self.assignments.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self.closed.set()
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=3)
