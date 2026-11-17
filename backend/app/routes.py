import asyncio, json, uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from . import copilot_service as cs, memory
from .config import get_settings
from .db import get_db, ping_db
from .models import PlanRequest, ReviseRequest, ApproveRequest
from .orchestrator import Orchestrator
from .repo import Repo
from .runtime import RunContext, bus, now

router = APIRouter(prefix="/api")
_tasks: set[asyncio.Task] = set()
RUNNING = ("planning", "revising")


def get_repo() -> Repo:
    return Repo(get_db())


def user_id(request: Request) -> str:
    uid = request.headers.get("x-user-id", get_settings().demo_user_id)
    return uid[:64] if uid.replace("-", "").replace("_", "").isalnum() else get_settings().demo_user_id


def _spawn(coro):
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _get_trip(repo: Repo, trip_id: str, uid: str) -> dict:
    trip = await repo.get("trips", {"trip_id": trip_id, "user_id": uid})
    if not trip:
        raise HTTPException(404, "Trip not found")
    return trip


# ---------------------------------------------------------------- health / copilot
@router.get("/health")
async def health():
    out = {"api": {"ok": True}}
    try:
        out["mongodb"] = await ping_db()
    except Exception as e:
        out["mongodb"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return out


@router.get("/copilot/status")
async def copilot_status():
    try:
        return {"ok": True, "auth": await cs.auth_status(), "models": await cs.models()}
    except Exception as e:
        raise HTTPException(503, cs.friendly(e))


class PingRequest(BaseModel):
    prompt: str = Field(default="Reply with exactly: TRAVELMATE_OK", max_length=500)


@router.post("/copilot/ping")
async def copilot_ping(req: PingRequest):
    try:
        return {"ok": True, "model": get_settings().copilot_model, "reply": await cs.ask(req.prompt)}
    except cs.CopilotUnavailable as e:
        raise HTTPException(503, str(e))


# ---------------------------------------------------------------- trips
@router.post("/trips/plan")
async def plan_trip(req: PlanRequest, request: Request, repo: Repo = Depends(get_repo)):
    uid, s = user_id(request), get_settings()
    await memory.ensure_user(repo, uid)
    trip_id, execution_id, conv_id = uuid.uuid4().hex[:12], uuid.uuid4().hex[:12], uuid.uuid4().hex[:12]
    text = req.message.strip() or f"Plan a trip to {req.destination}"
    await repo.insert("conversations", dict(conversation_id=conv_id, user_id=uid, trip_id=trip_id, created_at=now(), updated_at=now(),
                                            messages=[dict(role="user", content=text, ts=now())]))
    await repo.insert("trips", dict(trip_id=trip_id, user_id=uid, destination=req.destination or "Unknown", start_date=None, end_date=None,
                                    duration=req.days or 0, total_budget=req.budget or 0, travelers=req.travelers or 1, preferences={},
                                    status="planning", conversation_id=conv_id, latest_version=0, latest_execution_id=execution_id,
                                    created_at=now(), updated_at=now()))
    ctx = RunContext(repo, uid, trip_id, execution_id)
    _spawn(Orchestrator(ctx, s).run_new(req))
    return dict(trip_id=trip_id, execution_id=execution_id, conversation_id=conv_id)


@router.get("/trips")
async def list_trips(request: Request, repo: Repo = Depends(get_repo)):
    trips = await repo.list("trips", {"user_id": user_id(request)}, [("created_at", -1)], 100)
    return [{k: v for k, v in t.items() if k not in ("research", "strategy", "parsed")} for t in trips]


@router.get("/trips/{trip_id}")
async def get_trip(trip_id: str, request: Request, version: int | None = None, repo: Repo = Depends(get_repo)):
    trip = await _get_trip(repo, trip_id, user_id(request))
    versions = await repo.list("itineraries", {"trip_id": trip_id}, [("version", -1)], 50)
    chosen = next((v for v in versions if v["version"] == version), versions[0] if versions else None) if versions else None
    r = trip.pop("research", None) or {}
    overview = {k: r.get(k) for k in ("overview", "best_season", "transport_info", "tips", "disclaimer")}
    return dict(trip=trip, itinerary=chosen, overview=overview, versions=[dict(version=v["version"], created_at=v["created_at"], approval_status=v["approval_status"],
                total=v["itinerary"]["cost"]["total"]) for v in versions])


@router.post("/trips/{trip_id}/approve")
async def approve(trip_id: str, body: ApproveRequest, request: Request, repo: Repo = Depends(get_repo)):
    uid = user_id(request)
    trip = await _get_trip(repo, trip_id, uid)
    if trip["status"] in RUNNING:
        raise HTTPException(409, "The agents are still working on this trip")
    version = body.version or trip.get("latest_version")
    if not version or not await repo.get("itineraries", {"trip_id": trip_id, "version": version}):
        raise HTTPException(404, "No itinerary to approve")
    for v in await repo.list("itineraries", {"trip_id": trip_id}):
        await repo.update("itineraries", {"trip_id": trip_id, "version": v["version"]},
                          {"approval_status": "approved" if v["version"] == version else ("superseded" if v["approval_status"] == "approved" else v["approval_status"])})
    await repo.update("trips", {"trip_id": trip_id}, {"status": "approved", "approved_version": version, "updated_at": now()})
    await memory.remember_approved_trip(repo, uid, trip)
    await repo.push("conversations", {"conversation_id": trip["conversation_id"]}, "messages",
                    {"role": "user", "content": f"Approved version {version}.", "ts": now()}, {"updated_at": now()})
    return {"status": "approved", "version": version}


@router.post("/trips/{trip_id}/save")
async def save_trip(trip_id: str, request: Request, repo: Repo = Depends(get_repo)):
    trip = await _get_trip(repo, trip_id, user_id(request))
    if trip["status"] == "awaiting_approval":
        await repo.update("trips", {"trip_id": trip_id}, {"status": "saved", "updated_at": now()})
    return {"status": "saved" if trip["status"] == "awaiting_approval" else trip["status"]}


@router.post("/trips/{trip_id}/revise")
async def revise(trip_id: str, body: ReviseRequest, request: Request, repo: Repo = Depends(get_repo)):
    uid = user_id(request)
    trip = await _get_trip(repo, trip_id, uid)
    if trip["status"] in RUNNING:
        raise HTTPException(409, "The agents are already working on this trip")
    if not trip.get("research") or not trip.get("parsed"):
        raise HTTPException(400, "This trip has no completed research to revise")
    if not (body.feedback.strip() or body.regenerate):
        raise HTTPException(422, "Provide feedback or set regenerate=true")
    execution_id = uuid.uuid4().hex[:12]
    await repo.update("trips", {"trip_id": trip_id}, {"status": "revising", "latest_execution_id": execution_id, "updated_at": now()})
    await repo.push("conversations", {"conversation_id": trip["conversation_id"]}, "messages",
                    {"role": "user", "content": body.feedback or "Regenerate the itinerary", "ts": now()}, {"updated_at": now()})
    ctx = RunContext(repo, uid, trip_id, execution_id)
    _spawn(Orchestrator(ctx, get_settings()).run_revision(trip, body.feedback.strip(), body.regenerate))
    return dict(trip_id=trip_id, execution_id=execution_id)


# ---------------------------------------------------------------- agent activity
@router.get("/agents/activity/{execution_id}")
async def activity(execution_id: str, repo: Repo = Depends(get_repo)):
    async def gen():
        if execution_id in bus.channels:
            async for e in bus.stream(execution_id):
                yield ": keep-alive\n\n" if e is None else f"id: {e['seq']}\ndata: {json.dumps(e, default=str)}\n\n"
            return
        rows = await repo.list("agent_execution_logs", {"execution_id": execution_id}, [("seq", 1)], 2000)
        if not rows:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Unknown execution id'})}\n\n"
        for r in rows:
            yield f"id: {r['seq']}\ndata: {json.dumps(r['event'], default=str)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/agents/logs/{trip_id}")
async def logs(trip_id: str, request: Request, repo: Repo = Depends(get_repo)):
    await _get_trip(repo, trip_id, user_id(request))
    return await repo.list("agent_execution_logs", {"trip_id": trip_id}, [("timestamp", 1)], 2000)


# ---------------------------------------------------------------- preferences / memory / conversations
class PreferencesIn(BaseModel):
    preferred_destinations: list[str] = Field(default_factory=list, max_length=20)
    preferred_activities: list[str] = Field(default_factory=list, max_length=20)
    food_preferences: list[str] = Field(default_factory=list, max_length=20)
    accommodation_preferences: list[str] = Field(default_factory=list, max_length=10)
    travel_style: str | None = Field(default=None, max_length=60)
    budget_preference: str | None = Field(default=None, max_length=60)


def _clean(xs): return list(dict.fromkeys(x.strip().lower()[:40] for x in xs if x.strip()))


@router.get("/preferences")
async def get_preferences(request: Request, repo: Repo = Depends(get_repo)):
    uid = user_id(request)
    prefs = await repo.get("user_preferences", {"user_id": uid}) or {}
    mem = await repo.list("memory", {"user_id": uid}, [("updated_at", -1)], 300)
    return dict(preferences=prefs, memory=mem)


@router.put("/preferences")
async def put_preferences(body: PreferencesIn, request: Request, repo: Repo = Depends(get_repo)):
    uid = user_id(request)
    await memory.ensure_user(repo, uid)
    doc = dict(preferred_destinations=_clean(body.preferred_destinations), preferred_activities=_clean(body.preferred_activities),
               food_preferences=_clean(body.food_preferences), accommodation_preferences=_clean(body.accommodation_preferences),
               travel_style=body.travel_style, budget_preference=body.budget_preference, updated_at=now())
    await repo.upsert("user_preferences", {"user_id": uid}, doc, on_insert={"user_id": uid, "created_at": now()})
    return await get_preferences(request, repo)


@router.post("/memory/{key}/confirm")
async def confirm_memory(key: str, request: Request, repo: Repo = Depends(get_repo)):
    uid = user_id(request)
    if not await repo.get("memory", {"user_id": uid, "key": key}):
        raise HTTPException(404, "Memory item not found")
    await repo.update("memory", {"user_id": uid, "key": key}, {"source": "confirmed", "updated_at": now()})
    return {"ok": True}


@router.delete("/memory/{key}")
async def delete_memory(key: str, request: Request, repo: Repo = Depends(get_repo)):
    await repo.delete("memory", {"user_id": user_id(request), "key": key})
    return {"ok": True}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request, repo: Repo = Depends(get_repo)):
    c = await repo.get("conversations", {"conversation_id": conversation_id, "user_id": user_id(request)})
    if not c:
        raise HTTPException(404, "Conversation not found")
    return c
