import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import Field, TypeAdapter, ValidationError

from robotic_mind.config import Settings
from robotic_mind.domain.models import AgentManifest, Model, RobotMessage, now
from robotic_mind.minds.graph import MindGraph, build_graph
from robotic_mind.platform import Platform
from robotic_mind.world import regions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


class CreateSpace(Model):
    name: str = Field(min_length=1, max_length=80)
    display_name: str = Field(default="Satyam", min_length=1, max_length=80)


class Join(Model):
    invite_code: str = Field(pattern=r"^RM-[A-Z2-9]{6}$")
    display_name: str = Field(min_length=1, max_length=80)


class Command(Model):
    text: str = Field(min_length=3, max_length=2000)


class Handshake(Model):
    type: str = Field(pattern="^join$")
    invite_code: str = Field(pattern=r"^RM-[A-Z2-9]{6}$")
    manifest: AgentManifest


def create_app(settings=None, provider=None):
    platform = Platform(settings or Settings(), provider)

    async def monitor():
        while True:
            await asyncio.sleep(2)
            await platform.monitor()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(monitor())
        yield
        task.cancel()
        for pending in tuple(platform.missions.tasks):
            pending.cancel()
        await asyncio.gather(task, *platform.missions.tasks, return_exceptions=True)
        platform.db.engine.dispose()

    app = FastAPI(title="Robotic Mind", version="0.1.0", lifespan=lifespan)
    app.state.platform = platform
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.middleware("http")
    async def limit(request: Request, call_next):
        try:
            if int(request.headers.get("content-length", 0)) > 1_000_000:
                return JSONResponse(status_code=413, content={"detail": "Payload too large"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid content length"})
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "llm_mode": platform.settings.llm_mode}

    @app.get("/api/world")
    def world():
        return {"regions": [r.model_dump() for r in regions()]}

    @app.get("/api/spaces")
    def spaces():
        return platform.db.list("space")

    @app.post("/api/spaces", status_code=201)
    async def create(body: CreateSpace):
        return await platform.create_space(body.name, body.display_name)

    @app.post("/api/spaces/join")
    async def join(body: Join):
        member = await platform.join_human(body.invite_code, body.display_name)
        return {"member": member, "space": platform.db.get(member["space_id"], "space")}

    @app.get("/api/spaces/{sid}")
    def space(sid: str):
        return platform.snapshot(sid)

    @app.get("/api/spaces/{sid}/members")
    def members(sid: str):
        return platform.members(sid)

    @app.post("/api/spaces/{sid}/commands", status_code=202)
    async def command(sid: str, body: Command):
        return await platform.missions.create(sid, body.text)

    @app.get("/api/spaces/{sid}/missions")
    def missions(sid: str):
        platform.db.get(sid, "space")
        return platform.db.list("mission", sid)

    @app.get("/api/missions/{mid}")
    def mission(mid: str):
        data = platform.db.get(mid, "mission")
        return {
            **data,
            "assignments": [
                a
                for a in platform.db.list("assignment", data["space_id"])
                if a["mission_id"] == mid
            ],
        }

    @app.get("/api/agents/{aid}")
    def agent(aid: str):
        item = platform.db.get(aid, "member")
        return next(a for a in platform.members(item["space_id"]) if a["id"] == aid)

    @app.get("/api/agents/{aid}/mind")
    def mind(aid: str):
        platform.db.get(aid, "member")
        return platform.active.get(aid)

    @app.get("/api/agents/{aid}/memories")
    def memories(aid: str):
        item = platform.db.get(aid, "member")
        return platform.db.list("memory", item["space_id"], aid)

    @app.get("/api/spaces/{sid}/mind")
    def group(sid: str):
        platform.db.get(sid, "space")
        return platform.minds.group(sid)

    @app.get("/api/spaces/{sid}/mind/graph", response_model=MindGraph)
    def neural_graph(sid: str):
        return build_graph(platform, sid)

    @app.get("/api/spaces/{sid}/events")
    def events(sid: str, after: int = 0):
        platform.db.get(sid, "space")
        return platform.db.events(sid, after)

    @app.get("/api/agents/{aid}/camera/latest")
    def camera(aid: str):
        if aid not in platform.frames:
            raise HTTPException(404, "No camera frame received")
        return Response(
            platform.frames[aid], media_type="image/jpeg", headers={"Cache-Control": "no-store"}
        )

    @app.websocket("/ws/spaces/{sid}")
    async def space_socket(ws: WebSocket, sid: str):
        await ws.accept()
        try:
            platform.db.get(sid, "space")
        except KeyError:
            await ws.close(code=1008, reason="Unknown space")
            return
        queue = platform.bus.subscribe(sid)
        try:
            await ws.send_json({"type": "snapshot", "data": platform.snapshot(sid)})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5)
                    await ws.send_json(event)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "ping", "timestamp": now()})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            platform.bus.unsubscribe(sid, queue)

    @app.websocket("/ws/robots/{aid}")
    async def robot_socket(ws: WebSocket, aid: str):
        await ws.accept()
        member, queue, sender = None, None, None
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
            if len(raw) > 65536:
                raise ValueError("Handshake too large")
            hello = Handshake.model_validate_json(raw)
            if hello.manifest.agent_id != aid:
                raise ValueError("Path identity must match manifest")
            member = await platform.register(hello.invite_code, hello.manifest)
            sid = member["space_id"]
            platform.robot_sessions[aid] = ws
            queue = platform.bus.subscribe(sid)
            assignments = [
                a
                for a in platform.db.list("assignment", sid, aid)
                if a["status"] in ("pending", "started")
                and platform.db.get(a["mission_id"], "mission")["state"] == "executing"
            ]
            await ws.send_json(
                {
                    "type": "joined",
                    "agent_id": aid,
                    "space_id": sid,
                    "assignments": assignments,
                    "group_mind": platform.minds.group(sid),
                }
            )

            async def forward():
                while True:
                    event = await queue.get()
                    if event["type"] == "assignment.created" and event["data"]["agent_id"] == aid:
                        await ws.send_json({"type": "assignment", "data": event["data"]})
                    elif event["type"] in (
                        "object.discovered",
                        "object.merged",
                        "region.cleared",
                        "mission.failed",
                        "mission.complete",
                    ):
                        await ws.send_json(event)

            sender = asyncio.create_task(forward())
            adapter = TypeAdapter(RobotMessage)
            while True:
                packet = await ws.receive()
                if packet["type"] == "websocket.disconnect":
                    break
                if packet.get("bytes") is not None:
                    frame = packet["bytes"]
                    if len(frame) > 512_000 or not frame.startswith(b"\xff\xd8"):
                        raise ValueError("Camera must be a JPEG under 512 KB")
                    decoded = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR)
                    if decoded is None or max(decoded.shape[:2]) > 1024:
                        raise ValueError("Invalid camera dimensions")
                    platform.frames[aid] = frame
                    await platform.bus.emit(sid, "camera.updated", {"agent_id": aid}, persist=False)
                    continue
                raw = packet.get("text", "")
                if len(raw) > 65536:
                    raise ValueError("Robot JSON limit is 64 KB")
                try:
                    message = adapter.validate_json(raw)
                    await platform.message(member, message)
                    await ws.send_json({"type": "ack", "message_type": message.type})
                except (ValidationError, ValueError, KeyError) as exc:
                    await ws.send_json({"type": "error", "detail": str(exc)[:500]})
        except (ValueError, ValidationError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await ws.send_json({"type": "error", "detail": str(exc)[:500]})
                await ws.close(code=1008)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            if member:
                platform.bus.unsubscribe(member["space_id"], queue)
                platform.robot_sessions.pop(aid, None)
                platform.last_seen.pop(aid, None)
                await platform.bus.emit(member["space_id"], "robot.disconnected", {"agent_id": aid})

    return app
