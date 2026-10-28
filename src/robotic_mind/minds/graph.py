"""A provenance graph projected from persisted evidence, not model reasoning."""

from collections import Counter
from typing import Literal

from pydantic import Field

from robotic_mind.domain.models import Model, now
from robotic_mind.world import regions

NodeKind = Literal[
    "group",
    "human",
    "robot",
    "mission",
    "assignment",
    "region",
    "observation",
    "memory",
    "discovery",
]


class MindNode(Model):
    id: str
    kind: NodeKind
    label: str
    summary: str = ""
    source_id: str
    owner_id: str | None = None
    timestamp: str | None = None
    confidence: float | None = None
    shared: bool = False
    status: str | None = None
    evidence: dict = Field(default_factory=dict)


class MindEdge(Model):
    id: str
    source: str
    target: str
    relation: str


class MindGraph(Model):
    space_id: str
    generated_at: str = Field(default_factory=now)
    nodes: list[MindNode]
    edges: list[MindEdge]
    counts: dict[str, int]
    total_nodes: int
    truncated: bool
    recent_events: list[dict]


def build_graph(platform, space_id: str, limit: int = 450) -> MindGraph:
    db = platform.db
    space = db.get(space_id, "space")
    nodes: dict[str, MindNode] = {}
    edges: dict[str, MindEdge] = {}

    def node(prefix, source_id, kind, label, **kwargs):
        id = f"{prefix}:{source_id}"
        nodes[id] = MindNode(id=id, source_id=source_id, kind=kind, label=label, **kwargs)
        return id

    def edge(source, target, relation):
        id = f"{source}/{relation}/{target}"
        edges[id] = MindEdge(id=id, source=source, target=target, relation=relation)

    root = node(
        "group",
        space_id,
        "group",
        "Group Mind",
        summary=space["name"],
        shared=True,
        timestamp=space["created_at"],
    )
    for member in platform.members(space_id):
        id = node(
            "member",
            member["id"],
            member["member_type"],
            member["display_name"],
            summary="Space member",
            status=member["status"],
            timestamp=member["joined_at"],
            evidence={
                "capabilities": member["capabilities"],
                "active_mind": member.get("active_mind"),
                "stats": member.get("stats"),
            },
        )
        edge(root, id, "has member")
    for region in regions():
        id = node(
            "region",
            region.id,
            "region",
            region.name,
            summary=f"{len(region.waypoints)} search waypoints",
            evidence=region.model_dump(),
        )
        edge(root, id, "maps")
    for mission in db.list("mission", space_id):
        id = node(
            "mission",
            mission["id"],
            "mission",
            "Search mission",
            summary=mission["command"],
            timestamp=mission["created_at"],
            status=mission["state"],
            evidence={"result": mission["result"], "error": mission["error"]},
        )
        edge(root, id, "coordinates")
    for item in db.list("assignment", space_id):
        id = node(
            "assignment",
            item["id"],
            "assignment",
            f"Sweep {item['region']}",
            summary=item["objective"],
            owner_id=item["agent_id"],
            status=item["status"],
            evidence={
                "mission_id": item["mission_id"],
                "region": item["region"],
                "progress": item["progress"],
            },
        )
        edge(f"mission:{item['mission_id']}", id, "assigns")
        edge(f"member:{item['agent_id']}", id, "executes")
        edge(id, f"region:{item['region']}", "searches")
    for i, item in enumerate(db.list("discovery", space_id)):
        id = node(
            "discovery",
            item["id"],
            "discovery",
            f"Red object {i + 1:02d}",
            summary=f"Confirmed camera discovery in Sector {item['region']}",
            owner_id=item["discovered_by"],
            timestamp=item["created_at"],
            confidence=item["confidence"],
            shared=True,
            evidence={
                "position": item["position"],
                "observed_by": item["observed_by"],
                "observation_count": item["observation_count"],
                "region": item["region"],
            },
        )
        edge(root, id, "knows")
        edge(id, f"region:{item['region']}", "located in")
        for observer in item["observed_by"]:
            edge(
                f"member:{observer}",
                id,
                "discovered" if observer == item["discovered_by"] else "confirmed",
            )
        for mid in item["mission_ids"]:
            edge(f"mission:{mid}", id, "found")
    for item in db.list("observation", space_id):
        id = node(
            "observation",
            item["id"],
            "observation",
            "Camera observation",
            summary=item["summary"],
            owner_id=item["agent_id"],
            timestamp=item["timestamp"],
            confidence=item["confidence"],
            evidence={"position": item["position"], "region": item["region"]},
        )
        edge(f"member:{item['agent_id']}", id, "observed")
        edge(f"mission:{item['mission_id']}", id, "collected")
    for item in db.list("memory", space_id):
        id = node(
            "memory",
            item["id"],
            "memory",
            item["title"],
            summary=item["summary"],
            owner_id=item["owner_id"],
            timestamp=item["created_at"],
            shared=item["shared"],
            evidence={
                "category": item["category"],
                "importance": item["importance"],
                "tags": item["tags"],
                "structured_data": item["structured_data"],
            },
        )
        edge(f"member:{item['owner_id']}", id, "contributed" if item["shared"] else "remembers")
        if item["shared"]:
            edge(root, id, "shares")
        if item["mission_id"]:
            edge(f"mission:{item['mission_id']}", id, "produced")
        evidence = item["structured_data"]
        if evidence.get("discovery_id"):
            edge(id, f"discovery:{evidence['discovery_id']}", "supports")
        if item["category"] == "observation" and evidence.get("id"):
            edge(f"observation:{evidence['id']}", id, "stored as")
        if evidence.get("region") and item["category"] == "task_outcome":
            edge(id, f"region:{evidence['region']}", "cleared")

    total = len(nodes)
    # Preserve identities/discoveries/regions, then the newest evidence. Report the cap honestly.
    if total > limit:
        stable = [
            n
            for n in nodes.values()
            if n.kind in ("group", "robot", "human", "region", "discovery")
        ]
        evidence = sorted(
            (n for n in nodes.values() if n not in stable),
            key=lambda n: n.timestamp or "",
            reverse=True,
        )
        nodes = {n.id: n for n in (stable + evidence)[:limit]}
    valid = [e for e in edges.values() if e.source in nodes and e.target in nodes]
    meaningful = [
        e
        for e in db.events(space_id, limit=80)
        if e["type"]
        in (
            "object.discovered",
            "object.merged",
            "memory.created",
            "group_memory.created",
            "region.cleared",
            "mission.complete",
            "mission.executing",
            "robot.connected",
        )
    ]
    return MindGraph(
        space_id=space_id,
        nodes=list(nodes.values()),
        edges=valid,
        counts=dict(Counter(n.kind for n in nodes.values())),
        total_nodes=total,
        truncated=total > len(nodes),
        recent_events=meaningful[-12:],
    )
