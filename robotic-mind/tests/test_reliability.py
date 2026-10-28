import asyncio

import pytest
from pydantic import ValidationError

from robotic_mind.config import Settings
from robotic_mind.domain.models import (
    AgentManifest,
    MissionPlan,
    MissionSpec,
    Observation,
    Position,
)
from robotic_mind.events.bus import EventBus
from robotic_mind.minds.service import MindService
from robotic_mind.missions.coordinator import validate_plan
from robotic_mind.persistence.database import Database
from robotic_mind.platform import Platform


def test_low_confidence_and_distinct_world_locations(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'confidence.db'}")
    bus = EventBus(db)
    minds = MindService(db, bus)

    async def observe(confidence, x, agent):
        obs = Observation(
            mission_id="mission", confidence=confidence, position=Position(x=x), region="A"
        )
        await bus.emit(
            "space", "observation.created", {"agent_id": agent, "observation": obs.model_dump()}
        )

    asyncio.run(observe(0.4, 0, "robot-1"))
    assert len(db.list("memory", "space")) == 1
    assert not minds.group("space")["discoveries"]
    asyncio.run(observe(0.9, 0, "robot-1"))
    asyncio.run(observe(0.95, 0.2, "robot-2"))
    asyncio.run(observe(0.96, 4, "robot-2"))
    group = minds.group("space")
    assert len(group["discoveries"]) == 2
    first = next(d for d in group["discoveries"] if d["observation_count"] == 2)
    assert first["observed_by"] == ["robot-1", "robot-2"]
    assert first["discovered_by"] == "robot-1"
    assert first["confidence"] == 0.95
    db.engine.dispose()


def test_bus_handler_delivery_and_bounded_queue(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'bus.db'}")
    bus = EventBus(db)
    seen = []

    async def handler(event):
        seen.append(event)

    bus.on("fact", handler)
    queue = bus.subscribe("space")
    for i in range(300):
        asyncio.run(bus.emit("space", "fact", {"number": i}, persist=False))
    assert queue.qsize() == 256
    assert seen[-1]["data"]["number"] == 299
    assert not db.events("space")
    bus.unsubscribe("space", queue)
    assert not bus.listeners["space"]
    db.engine.dispose()


def test_entity_identity_cannot_cross_owner_or_kind(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'identity.db'}")
    db.put("space", "same-id", "space", {"name": "original"})
    with pytest.raises(ValueError, match="identity conflicts"):
        db.put("observation", "same-id", "space", {}, "robot")
    assert db.get("same-id", "space")["name"] == "original"
    db.engine.dispose()


def test_missing_mission_fields_are_not_invented():
    with pytest.raises(ValidationError):
        MissionSpec.model_validate_json("{}")


def test_incomplete_plan_rejected():
    manifest = AgentManifest(
        agent_id="rover", display_name="Rover", capabilities=["camera", "navigate", "detect_color"]
    )
    with pytest.raises(ValueError, match="every search region"):
        validate_plan(
            MissionPlan(assignments=[{"agent_id": "rover", "region": "A"}]),
            [manifest.model_dump()],
            [{"id": "A"}, {"id": "B"}],
        )


def test_restart_marks_unfinished_mission_failed(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'restart.db'}", _env_file=None)
    first = Platform(settings)
    first.db.put(
        "mission",
        "unfinished",
        "space",
        {
            "id": "unfinished",
            "space_id": "space",
            "command": "Find red",
            "state": "executing",
        },
    )
    first.db.engine.dispose()
    second = Platform(settings)
    mission = second.db.get("unfinished", "mission")
    assert mission["state"] == "failed"
    assert "restarted" in mission["error"]
    second.db.engine.dispose()
