from unittest.mock import patch

from robotic_mind_sdk import AgentManifest, RobotClient
from robotic_mind_sdk.models import MemoryEntry, Telemetry


def test_sdk_typed_wire_messages():
    manifest = AgentManifest(
        agent_id="rover-05", display_name="Rover 05", capabilities=["navigate"]
    )
    client = RobotClient("Rover 05", "RM-ABC234", manifest)
    assert client.url == "ws://localhost:8000/ws/robots/rover-05"
    client.publish_telemetry(Telemetry(position={"x": 1, "y": 2, "z": 0}))
    assert client.outbox.get()["data"]["position"]["x"] == 1
    client.remember(MemoryEntry(title="Location"))
    assert client.outbox.get()["type"] == "memory"
    client.publish_shared_memory(MemoryEntry(title="Hazard"))
    assert client.outbox.get()["type"] == "shared_memory"
    assert client.next_assignment() is None
    client.task_status("id", "started")
    assert client.outbox.get()["data"]["assignment_id"] == "id"
    with patch.object(client, "_run") as run:
        client.connect().thread.join(timeout=1)
        run.assert_called_once()
    client.close()
