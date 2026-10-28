import math

from robotic_mind.domain.models import MemoryEntry, Observation, now, uid


class MindService:
    def __init__(self, db, bus, radius=0.8):
        self.db, self.bus, self.radius = db, bus, radius
        bus.on("observation.created", self.on_observation)

    async def remember(self, space_id, agent_id, entry: MemoryEntry, shared=False):
        entry = entry.model_copy(
            update={
                "owner_id": agent_id,
                "space_id": space_id,
                "owner_type": "group" if shared else "robot",
                "shared": shared,
                "id": uid(),
            }
        )
        self.db.put("memory", entry.id, space_id, entry.model_dump(), agent_id)
        await self.bus.emit(
            space_id, "group_memory.created" if shared else "memory.created", entry.model_dump()
        )
        return entry

    async def on_observation(self, event):
        data, sid = event["data"], event["space_id"]
        agent_id = data["agent_id"]
        obs = Observation.model_validate(data["observation"])
        await self.remember(
            sid,
            agent_id,
            MemoryEntry(
                category="observation",
                title=obs.label,
                summary=obs.summary,
                mission_id=obs.mission_id,
                structured_data=obs.model_dump(),
                importance=obs.confidence,
            ),
        )
        if obs.confidence < 0.7:
            return
        objects = self.db.list("discovery", sid)
        duplicate = next(
            (
                o
                for o in objects
                if o["label"] == obs.label
                and math.dist(
                    [o["position"]["x"], o["position"]["y"]], [obs.position.x, obs.position.y]
                )
                <= self.radius
            ),
            None,
        )
        if duplicate:
            obj = duplicate
            obj["observed_by"] = sorted(set(obj["observed_by"] + [agent_id]))
            obj["confidence"] = max(obj["confidence"], obs.confidence)
            obj["observation_count"] += 1
        else:
            obj = {
                "id": uid(),
                "label": obs.label,
                "position": obs.position.model_dump(),
                "region": obs.region,
                "discovered_by": agent_id,
                "observed_by": [agent_id],
                "confidence": obs.confidence,
                "observation_count": 1,
                "created_at": now(),
                "mission_ids": [],
            }
        obj["mission_ids"] = sorted(set(obj["mission_ids"] + [obs.mission_id]))
        self.db.put("discovery", obj["id"], sid, obj)
        await self.remember(
            sid,
            agent_id,
            MemoryEntry(
                category="discovery",
                title="Discovery confirmed" if duplicate else "Red object found",
                summary=f"{agent_id} observed a red object in Sector {obs.region}",
                mission_id=obs.mission_id,
                structured_data={"discovery_id": obj["id"]},
                importance=0.9,
            ),
            shared=True,
        )
        await self.bus.emit(sid, "observation.shared", {"agent_id": agent_id, "discovery": obj})
        await self.bus.emit(sid, "object.merged" if duplicate else "object.discovered", obj)

    def group(self, space_id):
        return {
            "discoveries": self.db.list("discovery", space_id),
            "memories": [m for m in self.db.list("memory", space_id) if m["shared"]],
            "cleared_regions": self.db.list("cleared", space_id),
        }
