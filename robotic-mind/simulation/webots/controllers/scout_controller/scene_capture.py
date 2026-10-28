"""Opt-in documentation capture. This does not supply any perception evidence."""

import json
import re

from robotic_mind.view_geometry import look_at


class SceneCapture:
    def __init__(self, robot, root):
        self.robot, self.root = robot, root
        self.request = root / "artifacts/capture-views.json"
        self.result = root / "artifacts/capture-result.json"
        self.pending = []
        self.job = None
        self.current = None
        self.next_check = 0
        self.capture_at = 0
        self.files = []

    def tick(self, time):
        if self.current and time >= self.capture_at:
            target = self.root / "docs/images" / self.current["filename"]
            target.parent.mkdir(parents=True, exist_ok=True)
            self.robot.exportImage(str(target), 100)
            self.files.append(target.name)
            self.current = None
            if not self.pending:
                self.result.write_text(
                    json.dumps({"job": self.job, "files": self.files}), encoding="utf-8"
                )
        if not self.pending and self.current is None and time >= self.next_check:
            self.next_check = time + 1
            if self.request.exists():
                request = json.loads(self.request.read_text(encoding="utf-8"))
                if request["job"] != self.job:
                    self.job, self.pending, self.files = request["job"], request["views"][:8], []
        if self.pending and self.current is None:
            item = self.pending.pop(0)
            if not re.fullmatch(r"[a-z0-9_-]+\.png", item["filename"]):
                raise ValueError("Invalid documentation image name")
            view = self.robot.getFromDef("WAREHOUSE_VIEW")
            if item.get("focus_self"):
                target = self.robot.getSelf().getField("translation").getSFVec3f()
                eye = [a + b for a, b in zip(target, item["offset"], strict=True)]
            else:
                eye, target = item["eye"], item["target"]
            view.getField("position").setSFVec3f(eye)
            view.getField("orientation").setSFRotation(look_at(eye, target))
            view.getField("fieldOfView").setSFFloat(item.get("fov", 1.0))
            self.current, self.capture_at = item, time + 1
