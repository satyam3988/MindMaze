# API, wire protocol, and persistence

All services bind locally. This is an invite-based local MVP, not production authentication. Read APIs expose local spaces; keep the backend on loopback. The robot join handshake validates the invite and identity. An identity is unique across the local database and cannot move between spaces. Names are rendered as text. Credentials remain backend-side.

## HTTP endpoints

| Method | Route | Result |
|---|---|---|
| GET | `/api/health` | Server status and explicit LLM mode |
| GET | `/api/world` | Regions/bounds/waypoints; no parcel ground truth |
| GET | `/api/spaces` | Available local spaces |
| POST | `/api/spaces` | `{name, display_name}` → space and human member |
| POST | `/api/spaces/join` | `{invite_code, display_name}` → space and human member |
| GET | `/api/spaces/{id}` | Complete recoverable browser snapshot |
| GET | `/api/spaces/{id}/members` | Humans/robots, computed liveness, manifests, stats, live telemetry |
| POST | `/api/spaces/{id}/commands` | `{text}` → accepted mission (202) |
| GET | `/api/spaces/{id}/missions` | Persisted mission list |
| GET | `/api/missions/{id}` | Mission and its assignments |
| GET | `/api/agents/{id}` | Agent details |
| GET | `/api/agents/{id}/mind` | Latest ephemeral Active Mind, or null |
| GET | `/api/agents/{id}/memories` | Durable individual + contributed shared memory |
| GET | `/api/spaces/{id}/mind` | Shared discoveries, memories, and cleared regions |
| GET | `/api/spaces/{id}/mind/graph` | Typed evidence neurons, provenance edges, counts, truncation flag, recent activations |
| GET | `/api/spaces/{id}/events?after=0` | Up to 200 recent persisted events after sequence |
| GET | `/api/agents/{id}/camera/latest` | Latest JPEG, no-store; 404 before first frame |
| GET | `/docs`, `/openapi.json` | FastAPI generated documentation |

Unknown records return 404; business validation returns 400; invalid HTTP models return 422. HTTP content lengths above 1 MB are rejected. JSON robot messages are limited to 64 KB; WebSocket frames are bounded to 1 MB at Uvicorn. JPEG uploads must be valid, at most 512 KB, and no dimension larger than 1024. This is not a hardened untrusted image ingestion service.

## Browser WebSocket

Connect to `/ws/spaces/{space_id}`. The first message is `{ "type": "snapshot", "data": ... }` with current membership, missions, assignments, Group Mind, recent events, and public provider metadata. Then:

```json
{
  "id": "event-uuid",
  "type": "object.discovered",
  "space_id": "space-uuid",
  "timestamp": "2026-10-28T21:00:00+00:00",
  "sequence": 42,
  "data": {"label": "red_object", "discovered_by": "scout-02"}
}
```

Durable events have a sequence. High-frequency telemetry, heartbeat, and camera notifications are transient and omit sequence. Quiet sockets receive a five-second `ping`. Browser reconnection gets a new full snapshot; event-triggered snapshot refresh is coalesced to 300 ms, with a five-second fallback. Per-space subscriber queues are bounded to 256 events and drop the oldest under backpressure; this is a live view, not a lossless stream. Use the persistent events endpoint for important history.

## Robot WebSocket

Connect to `/ws/robots/{agent_id}`. Within ten seconds, send:

```json
{
  "type": "join",
  "invite_code": "RM-XXXXXX",
  "manifest": {
    "agent_id": "rover-05",
    "display_name": "Rover 05",
    "agent_type": "rover",
    "capabilities": ["navigate", "camera", "detect_color"],
    "sensors": ["rgb_camera", "position"],
    "actions": ["move_to", "scan"]
  }
}
```

The invite is an example placeholder. Manifest/path identities must match `[a-zA-Z0-9_-]{1,64}`. Concurrent use of an identity is rejected; reconnecting to its original space preserves memory. The response is `joined` with `agent_id`, `space_id`, incomplete executable assignments, and Group Mind. A rejected handshake gets `error` and close code 1008.

| Direction | Type | Data |
|---|---|---|
| Robot → server | `heartbeat` | No `data`; SDK sends every two seconds |
| Robot → server | `telemetry` | Position, battery, heading |
| Robot → server | `active_mind` | `ActiveMindState` |
| Robot → server | `observation` | `Observation`; must belong to active assignment |
| Robot → server | `memory` | `MemoryEntry`; server owns identity/ownership fields |
| Robot → server | `shared_memory` | Explicit contributed Group Mind entry |
| Robot → server | `task_status` | Assignment ID, started/completed/failed, progress 0–1 |
| Robot → server | binary frame | Raw JPEG bytes, no JSON/base64 |
| Server → robot | `ack` | Validated message type |
| Server → robot | `error` | Bounded validation/error detail |
| Server → robot | `assignment` | Typed assignment including executable waypoints |
| Server → robot | `object.discovered`, `object.merged` | Current shared object and provenance |
| Server → robot | `region.cleared` | Region, contributor, mission reference |
| Server → robot | `mission.failed`, `mission.complete` | Mission status/result |

Except heartbeat, outbound JSON messages use `{ "type": "...", "data": {...} }`. Pydantic rejects unknown fields/nonfinite numeric values. Completed observation IDs are idempotent for the same robot; conflicting record identities cannot overwrite another entity or owner. The SDK uses a bounded outbox, receives shared knowledge, and reconnects with a fresh handshake. It does not provide durable exactly-once delivery or offline buffering guarantees.

Liveness uses heartbeat receipt time: online under 10 s; stale at 10 s; offline at 25 s, or immediately when disconnected. An offline robot is excluded from new planning. Its previous assignment remains incomplete; no automatic reassignment is implemented. A backend restart marks unfinished missions failed with an explicit restart explanation and keeps all evidence. Reconnecting to a continuously running backend resumes persisted incomplete executable assignments from the start of their sweep.

## Schemas

The neural graph is an on-demand projection of space records and configured world regions, rather than a second database of duplicated knowledge. `MindNode` contains a stable prefixed ID, kind, source record ID, label, summary, contributor, timestamp, confidence, sharing flag, status, and inspectable evidence. `MindEdge` contains stable ID, source, target, and an explicit provenance relation. Edges with missing/out-of-scope endpoints are excluded. Private memories are linked to their contributing robot, not directly marked as shared Group Mind knowledge. Output is capped at 450 nodes with `truncated` and `total_nodes` reported explicitly. The browser polls every two seconds and visualizes recent evidence timestamps/active assignments as signal paths; this does not expose model reasoning.

`domain/models.py` is the executable schema source. Important product state:

```text
AgentManifest: agent_id, display_name, agent_type, capabilities[], sensors[], actions[]
RobotAgent: manifest, status, position; supports(capability)
ActiveMindState: status, objective, assignment?, observation_summary,
  decision_summary, current_action, next_step, confidence[0..1], position, updated_at
MemoryEntry: id, owner_type[robot|human|group], owner_id, space_id,
  category, title, summary, tags[], structured_data, importance[0..1],
  created_at, mission_id?, shared
Observation: id, mission_id, observation_type=object_detection,
  label=red_object, summary, confidence[0..1], position, region, timestamp
MissionSpec: objective=find_objects, target={property:color,value:red},
  strategy=parallel_search, constraints[], completion_condition=all_regions_searched
MissionPlan: assignments[{agent_id, region, objective}]
Assignment: id, mission_id, space_id, agent_id, region, objective,
  status[pending|started|completed|failed], progress[0..1], waypoints[]
Mission: id, space_id, command, state, spec?, created_at, completed_at?, result?, error?
MissionResult: summary, unique_objects, regions_cleared, participating_agents,
  duplicates_merged, coverage[0..1]
```

Memory categories: observation, fact, location, mission, discovery, task_outcome, warning, relationship, summary. Assignment progress and cleared-sector fraction provide progress; the UI labels coverage by completed deterministic sweeps, not measured camera pixel coverage. Active Mind uses explicit summaries constructed by the controller; model hidden reasoning is neither returned nor persisted.

## Database schema

SQLite uses WAL and a 5 s busy timeout. SQLAlchemy owns two small indexed tables:

```sql
CREATE TABLE records (
  id VARCHAR PRIMARY KEY,
  kind VARCHAR NOT NULL,
  space_id VARCHAR NOT NULL,
  owner_id VARCHAR NOT NULL,
  data JSON NOT NULL
);
-- Separate indexes on kind, space_id, owner_id.
CREATE TABLE events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  space_id VARCHAR NOT NULL,
  data JSON NOT NULL
);
-- Index on space_id.
```

`records.kind`: space, member (manifest embedded for robots), mission (result embedded), assignment, observation, memory, discovery, cleared. This deliberate indexed document design avoids a large MVP migration surface. The domain validates payloads, and services enforce ownership and references; there are no SQL foreign keys. Group memories use `owner_type=group`, retain contributing `owner_id`, and set `shared=true`. Discoveries retain original position, first discoverer, unique observers, confidence, observation count, and mission IDs.

Each persistence operation commits independently; event publication and related aggregate writes are not a transactional outbox. A process failure between those operations can leave partial evidence. SQLite is durable across ordinary restarts, while mission interruption is explicit. Use a single backend worker: in-memory event routing, telemetry, active state, sockets, and latest cameras are process-local.
