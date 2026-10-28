import asyncio

import pytest
from fastapi.testclient import TestClient

from robotic_mind.api.app import create_app
from robotic_mind.config import Settings
from robotic_mind.domain.models import AgentManifest, MemoryEntry
from robotic_mind.minds.graph import build_graph
from robotic_mind.platform import Platform


@pytest.fixture
def platform(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'graph.db'}",
        llm_mode="mock",
        strict_hackathon_mode=False,
        _env_file=None,
    )
    p = Platform(settings)
    yield p
    p.db.engine.dispose()


def test_graph_preserves_provenance_and_private_memory(platform):
    async def seed():
        created = await platform.create_space("Neural space", "Alex")
        space = created["space"]
        await platform.register(
            space["invite_code"],
            AgentManifest(
                agent_id="rover-1",
                display_name="Rover",
                capabilities=["camera"],
            ),
        )
        await platform.minds.remember(
            space["id"],
            "rover-1",
            MemoryEntry(
                title="Private observation",
                summary="Camera evidence",
            ),
        )
        await platform.minds.remember(
            space["id"],
            "rover-1",
            MemoryEntry(
                title="Shared fact",
                summary="Verified location",
            ),
            shared=True,
        )
        return space

    space = asyncio.run(seed())
    graph = build_graph(platform, space["id"])
    by_id = {n.id: n for n in graph.nodes}
    assert all(e.source in by_id and e.target in by_id for e in graph.edges)
    private = next(n for n in graph.nodes if n.label == "Private observation")
    shared = next(n for n in graph.nodes if n.label == "Shared fact")
    assert not private.shared and shared.shared
    assert any(
        e.source == "member:rover-1" and e.target == private.id and e.relation == "remembers"
        for e in graph.edges
    )
    assert not any(e.source.startswith("group:") and e.target == private.id for e in graph.edges)
    assert any(
        e.source.startswith("group:") and e.target == shared.id and e.relation == "shares"
        for e in graph.edges
    )
    assert graph.counts["memory"] == 2


def test_graph_does_not_cross_spaces(platform):
    first = asyncio.run(platform.create_space("First", "Alex"))["space"]
    second = asyncio.run(platform.create_space("Second", "Sam"))["space"]
    asyncio.run(
        platform.minds.remember(
            second["id"],
            "coordinator",
            MemoryEntry(
                title="Other workspace knowledge",
            ),
            shared=True,
        )
    )
    graph = build_graph(platform, first["id"])
    assert not any(n.label == "Other workspace knowledge" for n in graph.nodes)
    assert all(n.source_id != second["id"] for n in graph.nodes)


def test_graph_cap_is_explicit_and_edges_remain_valid(platform):
    space = asyncio.run(platform.create_space("Capped", "Alex"))["space"]
    for i in range(15):
        asyncio.run(
            platform.minds.remember(
                space["id"],
                "coordinator",
                MemoryEntry(
                    title=f"Memory {i}",
                ),
                shared=True,
            )
        )
    graph = build_graph(platform, space["id"], limit=10)
    assert graph.truncated and len(graph.nodes) == 10 and graph.total_nodes == 21
    ids = {n.id for n in graph.nodes}
    assert all(e.source in ids and e.target in ids for e in graph.edges)


def test_graph_http_contract(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        llm_mode="mock",
        strict_hackathon_mode=False,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        sid = client.post("/api/spaces", json={"name": "Graph API"}).json()["space"]["id"]
        response = client.get(f"/api/spaces/{sid}/mind/graph")
        assert response.status_code == 200
        data = response.json()
        assert data["nodes"][0]["kind"] == "group"
        assert data["counts"]["region"] == 4
        assert client.get("/api/spaces/unknown/mind/graph").status_code == 404
