from datetime import datetime, timezone

from robotic_mind.domain.models import AgentManifest, RobotAgent


def capable(manifest: AgentManifest) -> bool:
    agent = RobotAgent(manifest=manifest)
    return all(agent.supports(c) for c in ("navigate", "camera", "detect_color"))


def heartbeat_state(timestamp: str | None, stale: float = 10, offline: float = 25) -> str:
    if not timestamp:
        return "offline"
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
    return "offline" if age > offline else "stale" if age > stale else "online"
