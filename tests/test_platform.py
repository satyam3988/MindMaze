import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from robotic_mind.agents.registry import capable, heartbeat_state
from robotic_mind.api.app import create_app
from robotic_mind.config import Settings
from robotic_mind.domain.models import (
    AgentManifest,
    MissionPlan,
    MissionSpec,
    Position,
)
from robotic_mind.llm.mock import MockLLMProvider
from robotic_mind.llm.nebius import NebiusNemotronProvider
from robotic_mind.missions.coordinator import validate_plan
from robotic_mind.perception import detect_red, transform_view


def manifest(id="test-robot", capabilities=None):
    return AgentManifest(
        agent_id=id,
        display_name=id,
        agent_type="rover",
        capabilities=capabilities or ["camera", "navigate", "detect_color"],
    )


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", _env_file=None))
    with TestClient(app) as c:
        yield c


def space(client):
    return client.post("/api/spaces", json={"name": "Warehouse Test"}).json()["space"]


def hello(ws, s, id="test-robot"):
    ws.send_json(
        {"type": "join", "invite_code": s["invite_code"], "manifest": manifest(id).model_dump()}
    )
    packet = ws.receive_json()
    assert packet["type"] == "joined", packet
    return packet


def ack(ws, kind, data=None):
    ws.send_json({"type": kind, **({"data": data} if data is not None else {})})
    while True:
        packet = ws.receive_json()
        if packet["type"] in ("ack", "error"):
            assert packet["type"] == "ack", packet
            return


def wait_state(client, mid, expected):
    import time

    for _ in range(100):
        result = client.get(f"/api/missions/{mid}").json()
        if result["state"] == expected:
            return result
        time.sleep(0.02)
    pytest.fail(f"Expected {expected}: {result}")


def test_create_invite_and_join(client):
    s = space(client)
    assert s["invite_code"].startswith("RM-") and len(s["invite_code"]) == 9
    assert space(client)["invite_code"] != s["invite_code"]
    joined = client.post(
        "/api/spaces/join", json={"invite_code": s["invite_code"], "display_name": "Alex"}
    )
    assert joined.status_code == 200
    assert joined.json()["member"]["member_type"] == "human"
    assert (
        client.post(
            "/api/spaces/join", json={"invite_code": "RM-AAAAAA", "display_name": "X"}
        ).status_code
        == 400
    )


def test_manifest_and_capabilities():
    assert capable(manifest())
    assert not capable(manifest(capabilities=["camera"]))
    with pytest.raises(ValidationError):
        manifest("../../unsafe")


@pytest.mark.parametrize("age,expected", [(0, "online"), (15, "stale"), (40, "offline")])
def test_heartbeat(age, expected):
    timestamp = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
    assert heartbeat_state(timestamp) == expected
    assert heartbeat_state(None) == "offline"


def test_robot_registration_state_memory_and_camera(client):
    s = space(client)
    with client.websocket_connect("/ws/robots/test-robot") as ws:
        hello(ws, s)
        ack(ws, "heartbeat")
        assert client.get("/api/agents/test-robot").json()["status"] == "online"
        ack(ws, "telemetry", {"position": {"x": 2, "y": 3, "z": 1}})
        ack(ws, "active_mind", {"objective": "Inspect Sector A", "current_action": "Scanning"})
        assert client.get("/api/agents/test-robot/mind").json()["objective"] == "Inspect Sector A"
        ack(ws, "memory", {"title": "Learned location", "category": "location"})
        ack(ws, "shared_memory", {"title": "Shared warning", "category": "warning"})
        assert len(client.get("/api/agents/test-robot/memories").json()) == 2
        assert len(client.get(f"/api/spaces/{s['id']}/mind").json()["memories"]) == 1
        _, image = cv2.imencode(".jpg", np.zeros((120, 160, 3), np.uint8))
        ws.send_bytes(image.tobytes())
        ack(ws, "heartbeat")
        assert (
            client.get("/api/agents/test-robot/camera/latest").headers["content-type"]
            == "image/jpeg"
        )
        ws.send_json({"type": "telemetry", "data": {"position": {"x": "bad"}}})
        assert ws.receive_json()["type"] == "error"


def test_space_websocket_and_bus(client):
    s = space(client)
    with client.websocket_connect(f"/ws/spaces/{s['id']}") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        client.post(
            "/api/spaces/join", json={"invite_code": s["invite_code"], "display_name": "New member"}
        )
        event = ws.receive_json()
        assert event["type"] == "member.joined"
        assert event["sequence"] > 0


def test_persistence_and_restart(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'persist.db'}", _env_file=None)
    with TestClient(create_app(settings)) as c:
        s = space(c)
        with c.websocket_connect("/ws/robots/test-robot") as ws:
            hello(ws, s)
            ack(ws, "memory", {"title": "Persistent memory"})
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/api/spaces/{s['id']}").status_code == 200
        assert c.get("/api/agents/test-robot/memories").json()[0]["title"] == "Persistent memory"
        assert c.get("/api/agents/test-robot").json()["status"] == "offline"


def test_mission_full_flow_and_spatial_dedup(client):
    s = space(client)
    with client.websocket_connect("/ws/robots/test-robot") as ws:
        hello(ws, s)
        response = client.post(
            f"/api/spaces/{s['id']}/commands", json={"text": "Find all red objects"}
        )
        assert response.status_code == 202
        mid = response.json()["id"]
        mission = wait_state(client, mid, "executing")
        assert len(mission["assignments"]) == 4  # One capable rover can search all regions.
        for a in mission["assignments"]:
            ack(ws, "task_status", {"assignment_id": a["id"], "status": "started"})
            if a["region"] in ("A", "B"):
                ack(
                    ws,
                    "observation",
                    {
                        "mission_id": mid,
                        "confidence": 0.95,
                        "position": {"x": 0.05 if a["region"] == "A" else 0.15, "y": 2, "z": 0.4},
                        "region": a["region"],
                    },
                )
            ack(ws, "task_status", {"assignment_id": a["id"], "status": "completed", "progress": 1})
        result = wait_state(client, mid, "complete")["result"]
        assert result == {
            "summary": "Search complete. 1 unique red objects confirmed; 4 sectors cleared. "
            "Shared knowledge is saved in Group Mind.",
            "unique_objects": 1,
            "regions_cleared": 4,
            "participating_agents": 1,
            "duplicates_merged": 1,
            "coverage": 1.0,
        }
        assert len(client.get(f"/api/spaces/{s['id']}/mind").json()["discoveries"]) == 1
        events = client.get(f"/api/spaces/{s['id']}/events").json()
        assert any(e["type"] == "mission.complete" for e in events)
        assert any(e["type"] == "object.merged" for e in events)


def test_no_agents_fails_without_fake_success(client):
    s = space(client)
    response = client.post(f"/api/spaces/{s['id']}/commands", json={"text": "Find red objects"})
    result = wait_state(client, response.json()["id"], "failed")
    assert "No online robots" in result["error"]


def test_unsupported_mission(client):
    s = space(client)
    mid = client.post(f"/api/spaces/{s['id']}/commands", json={"text": "Deliver coffee"}).json()[
        "id"
    ]
    assert "supports" in wait_state(client, mid, "failed")["error"]


@pytest.mark.parametrize(
    "items",
    [
        [{"agent_id": "unknown", "region": "A"}],
        [{"agent_id": "test-robot", "region": "Z"}],
        [{"agent_id": "test-robot", "region": "A"}, {"agent_id": "test-robot", "region": "A"}],
    ],
)
def test_assignment_validation(items):
    with pytest.raises(ValueError):
        validate_plan(MissionPlan(assignments=items), [manifest().model_dump()], [{"id": "A"}])


def test_structured_output_validation():
    with pytest.raises(ValidationError):
        MissionPlan.model_validate_json('{"assignments":"not a list"}')
    with pytest.raises(ValidationError):
        MissionSpec.model_validate({"target": {"value": "blue"}})
    assert (
        asyncio.run(
            MockLLMProvider().generate("understand", {"command": "Find red objects"}, MissionSpec)
        ).target.value
        == "red"
    )


def test_nebius_configuration_and_retry():
    with pytest.raises(ValidationError):
        Settings(strict_hackathon_mode=True, llm_mode="mock", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(llm_mode="nebius", nebius_api_key="", _env_file=None)
    settings = Settings(llm_mode="nebius", nebius_api_key="test-only", _env_file=None)
    provider = NebiusNemotronProvider(settings)
    assert provider.model == "nvidia/nemotron-3-super-120b-a12b"
    assert str(provider.client.base_url) == settings.nebius_base_url + "/"
    provider.client.chat.completions.create = AsyncMock(side_effect=ValueError("malformed"))
    with pytest.raises(ValueError, match="two attempts"):
        asyncio.run(provider.generate("understand", {"command": "Find red objects"}, MissionSpec))
    assert provider.client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("color,expected", [((0, 0, 255), 1), ((255, 0, 0), 0), ((0, 255, 255), 0)])
def test_camera_color_perception(color, expected):
    image = np.zeros((240, 320, 3), np.uint8)
    cv2.rectangle(image, (145, 105), (175, 135), color, -1)
    detections = detect_red(image, Position())
    assert len(detections) == expected
    if detections:
        assert 0.7 <= detections[0]["confidence"] <= 1
        assert abs(detections[0]["position"].x) < 0.02


def test_transform_and_nonfinite():
    image = np.full((20, 20, 3), 100, np.uint8)
    assert transform_view(image, brightness=0.8, blur=1).mean() == 80
    with pytest.raises(ValidationError):
        Position(x=float("nan"))


def test_identity_mismatch_rejected(client):
    s = space(client)
    with client.websocket_connect("/ws/robots/wrong-path") as ws:
        ws.send_json(
            {"type": "join", "invite_code": s["invite_code"], "manifest": manifest().model_dump()}
        )
        assert ws.receive_json()["type"] == "error"


def test_limits_and_unknown_resources(client):
    assert client.get("/api/spaces/missing").status_code == 404
    assert client.post("/api/spaces", json={"name": "x" * 1000}).status_code == 422
    assert client.post("/api/spaces", content="x" * 1_000_001).status_code == 413
