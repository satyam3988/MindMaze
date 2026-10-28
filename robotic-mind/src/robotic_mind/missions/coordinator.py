from robotic_mind.agents.registry import capable
from robotic_mind.domain.models import AgentManifest, MissionPlan


def validate_plan(plan: MissionPlan, agents: list[dict], regions: list[dict]):
    registry = {a["agent_id"]: AgentManifest.model_validate(a) for a in agents}
    available = {r["id"] for r in regions}
    assigned = set()
    for assignment in plan.assignments:
        if assignment.agent_id not in registry or not capable(registry[assignment.agent_id]):
            raise ValueError("Plan references an unknown or incapable agent")
        if assignment.region not in available or assignment.region in assigned:
            raise ValueError("Plan contains unknown or duplicate regions")
        assigned.add(assignment.region)
    if assigned != available:
        raise ValueError("Plan must cover every search region")
