import secrets

from robotic_mind.agents.registry import heartbeat_state
from robotic_mind.domain.models import ActiveMindState, AgentManifest, Mission, now, uid
from robotic_mind.events.bus import EventBus
from robotic_mind.llm.mock import MockLLMProvider
from robotic_mind.llm.nebius import NebiusNemotronProvider
from robotic_mind.minds.service import MindService
from robotic_mind.missions.service import MissionService
from robotic_mind.persistence.database import Database


class Platform:
    def __init__(self, settings, provider=None):
        self.settings = settings
        self.db = Database(settings.database_url)
        self.bus = EventBus(self.db)
        self.telemetry = {}
        self.active = {}
        self.frames = {}
        self.robot_sessions = {}
        self.last_seen = {}
        self.status_cache = {}
        self.minds = MindService(self.db, self.bus, settings.dedup_radius)
        self.provider = provider or (
            NebiusNemotronProvider(settings) if settings.llm_mode == "nebius" else MockLLMProvider()
        )
        self.missions = MissionService(self, self.provider)
        # Interrupted work is retained but never represented as still executing after a restart.
        for data in self.db.list("mission"):
            if data["state"] not in ("complete", "failed"):
                data.update(state="failed", error="Backend restarted; submit a new mission")
                self.missions.save(Mission.model_validate(data))

    async def create_space(self, name, human):
        sid = uid()
        existing = {s["invite_code"] for s in self.db.list("space")}
        while True:
            code = "RM-" + "".join(
                secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6)
            )
            if code not in existing:
                break
        space = {"id": sid, "name": name, "invite_code": code, "created_at": now()}
        self.db.put("space", sid, sid, space)
        await self.bus.emit(sid, "space.created", {"summary": f"{name} created"})
        member = await self.join_human(code, human)
        return {"space": space, "member": member}

    def by_invite(self, invite):
        result = next(
            (s for s in self.db.list("space") if s["invite_code"] == invite.upper()), None
        )
        if result is None:
            raise ValueError("Invalid invite code")
        return result

    async def join_human(self, invite, name):
        space = self.by_invite(invite)
        member = {
            "id": uid(),
            "space_id": space["id"],
            "member_type": "human",
            "display_name": name,
            "status": "online",
            "capabilities": [],
            "joined_at": now(),
        }
        self.db.put("member", member["id"], space["id"], member)
        await self.bus.emit(space["id"], "member.joined", member)
        return member

    async def register(self, invite, manifest: AgentManifest):
        space = self.by_invite(invite)
        sid, aid = space["id"], manifest.agent_id
        if aid in self.robot_sessions:
            raise ValueError("Robot identity is already connected")
        try:
            old = self.db.get(aid, "member")
        except KeyError:
            old = None
        if old and (old["member_type"] != "robot" or old["space_id"] != sid):
            raise ValueError("Robot identity already belongs to another space")
        member = {
            "id": aid,
            "space_id": sid,
            "member_type": "robot",
            "display_name": manifest.display_name,
            "status": "online",
            "capabilities": manifest.capabilities,
            "manifest": manifest.model_dump(),
            "joined_at": old["joined_at"] if old else now(),
        }
        self.db.put("member", aid, sid, member)
        self.last_seen[aid] = now()
        self.status_cache[aid] = "online"
        self.active[aid] = ActiveMindState().model_dump()
        await self.bus.emit(sid, "robot.connected", member)
        return member

    def members(self, sid):
        self.db.get(sid, "space")
        members = self.db.list("member", sid)
        for member in members:
            aid = member["id"]
            if member["member_type"] == "robot":
                member["status"] = heartbeat_state(
                    self.last_seen.get(aid),
                    self.settings.stale_seconds,
                    self.settings.offline_seconds,
                )
                member["telemetry"] = self.telemetry.get(aid)
                member["active_mind"] = self.active.get(aid)
                memories = self.db.list("memory", sid, aid)
                member["stats"] = {
                    "memories": len(memories),
                    "discoveries": len([m for m in memories if m["category"] == "discovery"]),
                    "regions_visited": len(
                        {
                            m["structured_data"].get("region")
                            for m in memories
                            if m["category"] == "task_outcome"
                        }
                    ),
                    "completed_missions": len(
                        {m["mission_id"] for m in memories if m["category"] == "task_outcome"}
                    ),
                }
        return members

    async def monitor(self):
        for agent in self.db.list("member"):
            if agent["member_type"] != "robot":
                continue
            aid = agent["id"]
            status = heartbeat_state(
                self.last_seen.get(aid), self.settings.stale_seconds, self.settings.offline_seconds
            )
            if self.status_cache.get(aid) != status:
                self.status_cache[aid] = status
                await self.bus.emit(agent["space_id"], "robot." + status, {"agent_id": aid})

    async def message(self, agent, message):
        aid, sid, kind = agent["id"], agent["space_id"], message.type
        if kind == "heartbeat":
            self.last_seen[aid] = now()
            await self.bus.emit(sid, "robot.heartbeat", {"agent_id": aid}, persist=False)
        elif kind == "telemetry":
            self.telemetry[aid] = message.data.model_dump()
            await self.bus.emit(
                sid,
                "telemetry.updated",
                {"agent_id": aid, **message.data.model_dump()},
                persist=False,
            )
        elif kind == "active_mind":
            data = message.data.model_copy(update={"updated_at": now()}).model_dump()
            meaningful = any(
                self.active.get(aid, {}).get(key) != data[key]
                for key in ("objective", "current_action", "status")
            )
            self.active[aid] = data
            await self.bus.emit(
                sid, "active_mind.updated", {"agent_id": aid, **data}, persist=meaningful
            )
        elif kind == "observation":
            obs = message.data
            assignments = self.db.list("assignment", sid, aid)
            if not any(
                a["mission_id"] == obs.mission_id
                and a["region"] == obs.region
                and a["status"] == "started"
                for a in assignments
            ):
                raise ValueError("Observation must reference this robot's active region")
            if self.db.list("observation", sid, aid) and any(
                o["id"] == obs.id for o in self.db.list("observation", sid, aid)
            ):
                return
            self.db.put("observation", obs.id, sid, {**obs.model_dump(), "agent_id": aid}, aid)
            await self.bus.emit(
                sid, "observation.created", {"agent_id": aid, "observation": obs.model_dump()}
            )
        elif kind in ("memory", "shared_memory"):
            await self.minds.remember(sid, aid, message.data, shared=kind == "shared_memory")
        elif kind == "task_status":
            await self.missions.status(agent, message.data)

    def snapshot(self, sid):
        return {
            "space": self.db.get(sid, "space"),
            "members": self.members(sid),
            "missions": self.db.list("mission", sid),
            "assignments": self.db.list("assignment", sid),
            "group_mind": self.minds.group(sid),
            "events": self.db.events(sid),
            "ai": {
                "provider": self.provider.name,
                "model": self.provider.model,
                "mode": self.settings.llm_mode,
                "strict": self.settings.strict_hackathon_mode,
            },
        }
