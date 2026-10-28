import asyncio
import logging

from robotic_mind.domain.models import now, uid

log = logging.getLogger("robotic_mind.events")


class EventBus:
    def __init__(self, database):
        self.db = database
        self.listeners: dict[str, set[asyncio.Queue]] = {}
        self.handlers: dict[str, list] = {}

    def subscribe(self, space_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=256)
        self.listeners.setdefault(space_id, set()).add(queue)
        return queue

    def unsubscribe(self, space_id: str, queue):
        self.listeners.get(space_id, set()).discard(queue)

    def on(self, event_type: str, handler):
        self.handlers.setdefault(event_type, []).append(handler)

    async def emit(self, space_id: str, event_type: str, data: dict, persist: bool = True):
        event = {
            "id": uid(),
            "type": event_type,
            "space_id": space_id,
            "timestamp": now(),
            "data": data,
        }
        if persist:
            event = self.db.append_event(event)
            log.info("%s %s", event_type.upper(), data.get("summary", data.get("agent_id", "")))
        for queue in tuple(self.listeners.get(space_id, set())):
            if queue.full():
                queue.get_nowait()  # Slow clients receive the latest snapshot on reconnect.
            queue.put_nowait(event)
        for handler in self.handlers.get(event_type, []):
            await handler(event)
        return event
