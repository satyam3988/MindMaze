import asyncio
import logging

from robotic_mind.agents.registry import capable
from robotic_mind.domain.models import (
    AgentManifest,
    Assignment,
    MemoryEntry,
    Mission,
    MissionPlan,
    MissionResult,
    MissionSpec,
    MissionState,
    now,
)
from robotic_mind.missions.coordinator import validate_plan
from robotic_mind.world import regions

log = logging.getLogger("robotic_mind.missions")


class MissionService:
    def __init__(self, platform, provider):
        self.platform, self.provider = platform, provider
        self.db, self.bus = platform.db, platform.bus
        self.tasks = set()
        self.lock = asyncio.Lock()

    def save(self, mission):
        self.db.put("mission", mission.id, mission.space_id, mission.model_dump(mode="json"))

    async def stage(self, mission, state):
        mission.state = state
        self.save(mission)
        await self.bus.emit(mission.space_id, f"mission.{state}", mission.model_dump(mode="json"))

    async def create(self, sid, command):
        self.db.get(sid, "space")
        async with self.lock:
            if any(m["state"] not in ("complete", "failed") for m in self.db.list("mission", sid)):
                raise ValueError("A mission is already active in this space")
            mission = Mission(space_id=sid, command=command)
            self.save(mission)
        await self.bus.emit(sid, "mission.created", mission.model_dump(mode="json"))
        task = asyncio.create_task(self.plan(mission))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return mission

    async def call(self, purpose, context, schema, sid):
        result = await self.provider.generate(purpose, context, schema)
        await self.bus.emit(
            sid,
            "llm.completed",
            {
                "provider": self.provider.name,
                "model": self.provider.model,
                "purpose": purpose,
                "request": getattr(self.provider, "last_request", None),
                "summary": f"{self.provider.name} completed {purpose}",
            },
        )
        return result

    async def plan(self, mission):
        try:
            mission.spec = await self.call(
                "understand", {"command": mission.command}, MissionSpec, mission.space_id
            )
            await self.stage(mission, MissionState.PLANNING)
            agents = [
                a["manifest"]
                for a in self.platform.members(mission.space_id)
                if a["member_type"] == "robot"
                and a["status"] == "online"
                and capable(AgentManifest.model_validate(a["manifest"]))
            ]
            world = [r.model_dump() for r in regions()]
            context = {
                "mission": mission.spec.model_dump(),
                "agents": agents,
                "regions": world,
                "positions": {
                    a["agent_id"]: self.platform.telemetry.get(a["agent_id"]) for a in agents
                },
                "group_knowledge": self.platform.minds.group(mission.space_id),
            }
            plan = await self.call("plan", context, MissionPlan, mission.space_id)
            validate_plan(plan, agents, world)
            await self.stage(mission, MissionState.ASSIGNING)
            for item in plan.assignments:
                region = next(r for r in regions() if r.id == item.region)
                assignment = Assignment(
                    **item.model_dump(),
                    mission_id=mission.id,
                    space_id=mission.space_id,
                    waypoints=region.waypoints,
                )
                self.db.put(
                    "assignment",
                    assignment.id,
                    mission.space_id,
                    assignment.model_dump(),
                    assignment.agent_id,
                )
                await self.bus.emit(mission.space_id, "assignment.created", assignment.model_dump())
            await self.stage(mission, MissionState.EXECUTING)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.fail(mission, str(exc))

    async def fail(self, mission, message):
        mission.error = message
        await self.stage(mission, MissionState.FAILED)
        log.error("MISSION %s failed: %s", mission.id, message)

    async def status(self, agent, update):
        async with self.lock:
            assignment = Assignment.model_validate(self.db.get(update.assignment_id, "assignment"))
            if assignment.agent_id != agent["id"] or assignment.space_id != agent["space_id"]:
                raise ValueError("Assignment does not belong to this robot")
            mission = Mission.model_validate(self.db.get(assignment.mission_id, "mission"))
            if mission.state != MissionState.EXECUTING:
                raise ValueError("Mission is not executing")
            if assignment.status in ("completed", "failed"):
                if assignment.status == update.status:
                    return
                raise ValueError("Assignment already ended")
            if assignment.status == "pending" and update.status == "completed":
                raise ValueError("Assignment must start before completion")
            assignment.status = update.status
            assignment.progress = 1 if update.status == "completed" else update.progress
            self.db.put(
                "assignment",
                assignment.id,
                assignment.space_id,
                assignment.model_dump(),
                agent["id"],
            )
            await self.bus.emit(
                assignment.space_id, f"assignment.{update.status}", assignment.model_dump()
            )
            if update.status == "failed":
                await self.fail(mission, f"{agent['id']} failed Sector {assignment.region}")
                return
            if update.status == "completed":
                cleared = {
                    "id": f"{mission.id}:{assignment.region}",
                    "region": assignment.region,
                    "mission_id": mission.id,
                    "agent_id": agent["id"],
                    "timestamp": now(),
                }
                self.db.put("cleared", cleared["id"], assignment.space_id, cleared, agent["id"])
                await self.bus.emit(assignment.space_id, "region.cleared", cleared)
                await self.platform.minds.remember(
                    assignment.space_id,
                    agent["id"],
                    MemoryEntry(
                        category="task_outcome",
                        title=f"Sector {assignment.region} cleared",
                        summary="Completed every waypoint in the assigned region",
                        mission_id=mission.id,
                        structured_data=cleared,
                    ),
                )
            assignments = [
                a
                for a in self.db.list("assignment", assignment.space_id)
                if a["mission_id"] == mission.id
            ]
            if assignments and all(a["status"] == "completed" for a in assignments):
                await self.stage(mission, MissionState.SYNTHESIZING)
                task = asyncio.create_task(self.finish(mission, assignments))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)

    async def finish(self, mission, assignments):
        try:
            group = self.platform.minds.group(mission.space_id)
            observations = [
                o
                for o in self.db.list("observation", mission.space_id)
                if o["mission_id"] == mission.id and o["confidence"] >= 0.7
            ]
            objects = [d for d in group["discoveries"] if mission.id in d["mission_ids"]]
            facts = {
                "unique_objects": len(objects),
                "regions_cleared": len(assignments),
                "participating_agents": len({a["agent_id"] for a in assignments}),
                "duplicates_merged": max(0, len(observations) - len(objects)),
                "coverage": 1.0,
            }
            result = await self.call(
                "synthesize", {"facts": facts, "group_mind": group}, MissionResult, mission.space_id
            )
            if any(getattr(result, key) != value for key, value in facts.items()):
                raise ValueError("Model synthesis disagrees with persisted mission facts")
            mission.result = result
            mission.completed_at = now()
            await self.platform.minds.remember(
                mission.space_id,
                "coordinator",
                MemoryEntry(
                    category="summary",
                    title="Mission complete",
                    summary=result.summary,
                    mission_id=mission.id,
                    structured_data=result.model_dump(),
                    importance=1,
                ),
                shared=True,
            )
            await self.stage(mission, MissionState.COMPLETE)
        except Exception as exc:
            await self.fail(mission, str(exc))
