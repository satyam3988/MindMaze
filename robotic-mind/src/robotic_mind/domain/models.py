from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return uuid4().hex


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Position(Model):
    x: float = Field(default=0, ge=-1000, le=1000)
    y: float = Field(default=0, ge=-1000, le=1000)
    z: float = Field(default=3, ge=-10, le=1000)


class AgentManifest(Model):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    display_name: str = Field(min_length=1, max_length=80)
    agent_type: str = Field(default="robot", max_length=40)
    capabilities: list[str] = Field(max_length=32)
    sensors: list[str] = Field(default_factory=list, max_length=32)
    actions: list[str] = Field(default_factory=list, max_length=32)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


class ActiveMindState(Model):
    status: str = Field(default="idle", max_length=40)
    objective: str = Field(default="Awaiting a mission", max_length=500)
    assignment: str | None = None
    observation_summary: str = Field(default="No observation yet", max_length=500)
    decision_summary: str = Field(default="Ready for an assignment", max_length=500)
    current_action: str = Field(default="Holding position", max_length=500)
    next_step: str = Field(default="Receive an assignment", max_length=500)
    confidence: float = Field(default=1, ge=0, le=1)
    position: Position = Field(default_factory=Position)
    updated_at: str = Field(default_factory=now)


class RobotAgent(Model):
    """Robot identity and capabilities, independent of its hardware adapter."""

    manifest: AgentManifest
    status: Literal["online", "stale", "offline"] = "offline"
    position: Position = Field(default_factory=Position)

    def supports(self, capability: str) -> bool:
        return self.manifest.supports(capability)


class MemoryEntry(Model):
    id: str = Field(default_factory=uid)
    owner_type: Literal["robot", "human", "group"] = "robot"
    owner_id: str = ""
    space_id: str = ""
    category: Literal[
        "observation",
        "fact",
        "location",
        "mission",
        "discovery",
        "task_outcome",
        "warning",
        "relationship",
        "summary",
    ] = "fact"
    title: str = Field(max_length=150)
    summary: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    structured_data: dict = Field(default_factory=dict)
    importance: float = Field(default=0.5, ge=0, le=1)
    created_at: str = Field(default_factory=now)
    mission_id: str | None = None
    shared: bool = False


class Observation(Model):
    id: str = Field(default_factory=uid)
    mission_id: str
    observation_type: Literal["object_detection"] = "object_detection"
    label: Literal["red_object"] = "red_object"
    summary: str = Field(default="Red object detected in camera", max_length=500)
    confidence: float = Field(ge=0, le=1)
    position: Position
    region: str
    timestamp: str = Field(default_factory=now)


class Region(Model):
    id: str
    name: str
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    waypoints: list[Position]


class MissionState(StrEnum):
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    ASSIGNING = "assigning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    FAILED = "failed"


class Target(Model):
    property: Literal["color"] = "color"
    value: Literal["red"] = "red"


class MissionSpec(Model):
    objective: Literal["find_objects"]
    target: Target
    strategy: Literal["parallel_search"]
    constraints: list[Literal["avoid_duplicate_search"]]
    completion_condition: Literal["all_regions_searched"]


class PlannedAssignment(Model):
    agent_id: str
    region: str
    objective: str = "Search for red objects"


class MissionPlan(Model):
    assignments: list[PlannedAssignment] = Field(min_length=1, max_length=100)


class Assignment(PlannedAssignment):
    id: str = Field(default_factory=uid)
    mission_id: str
    space_id: str
    status: Literal["pending", "started", "completed", "failed"] = "pending"
    progress: float = Field(default=0, ge=0, le=1)
    waypoints: list[Position]


class MissionResult(Model):
    summary: str = Field(max_length=2000)
    unique_objects: int = Field(ge=0)
    regions_cleared: int = Field(ge=0)
    participating_agents: int = Field(ge=0)
    duplicates_merged: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)


class Mission(Model):
    id: str = Field(default_factory=uid)
    space_id: str
    command: str
    state: MissionState = MissionState.UNDERSTANDING
    spec: MissionSpec | None = None
    created_at: str = Field(default_factory=now)
    completed_at: str | None = None
    result: MissionResult | None = None
    error: str | None = None


class Telemetry(Model):
    position: Position
    battery: float = Field(default=100, ge=0, le=100)
    heading: float = 0


class TaskStatus(Model):
    assignment_id: str
    status: Literal["started", "completed", "failed"]
    progress: float = Field(default=0, ge=0, le=1)


class HeartbeatMessage(Model):
    type: Literal["heartbeat"]


class TelemetryMessage(Model):
    type: Literal["telemetry"]
    data: Telemetry


class MindMessage(Model):
    type: Literal["active_mind"]
    data: ActiveMindState


class ObservationMessage(Model):
    type: Literal["observation"]
    data: Observation


class MemoryMessage(Model):
    type: Literal["memory", "shared_memory"]
    data: MemoryEntry


class TaskMessage(Model):
    type: Literal["task_status"]
    data: TaskStatus


RobotMessage = Annotated[
    HeartbeatMessage
    | TelemetryMessage
    | MindMessage
    | ObservationMessage
    | MemoryMessage
    | TaskMessage,
    Field(discriminator="type"),
]
