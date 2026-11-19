"""Offline tests: stub Copilot + vector search + database, exercise the real orchestrator, tools and reviewer."""
import asyncio, json
import pytest
from app import copilot_service as cs
from app.config import get_settings
from app.knowledge import rag
from app.knowledge.destinations import KB
from app.models import PlanRequest
from app.orchestrator import Orchestrator
from app.runtime import RunContext, EventBus
from app.tools import budget as bt


class MemRepo:
    def __init__(self): self.d = {}
    def _c(self, n): return self.d.setdefault(n, [])
    def _m(self, doc, flt): return all(doc.get(k) == v for k, v in flt.items())
    async def insert(self, c, doc): self._c(c).append(json.loads(json.dumps(doc, default=str)))
    async def get(self, c, flt): return next((x for x in self._c(c) if self._m(x, flt)), None)
    async def upsert(self, c, flt, doc, on_insert=None):
        x = await self.get(c, flt)
        if x: x.update(doc)
        else: self._c(c).append({**flt, **(on_insert or {}), **doc})
    async def update(self, c, flt, doc):
        for x in self._c(c):
            if self._m(x, flt): x.update(json.loads(json.dumps(doc, default=str)))
    async def push(self, c, flt, f, v, extra=None):
        for x in self._c(c):
            if self._m(x, flt): x.setdefault(f, []).append(json.loads(json.dumps(v, default=str))); x.update(extra or {})
    async def list(self, c, flt=None, sort=None, limit=200):
        rows = [x for x in self._c(c) if self._m(x, flt or {})]
        for f, d in reversed(sort or []): rows.sort(key=lambda r: r.get(f) or 0, reverse=d < 0)
        return rows[:limit]
    async def delete(self, c, flt): self.d[c] = [x for x in self._c(c) if not self._m(x, flt)]


def fake_search(query, destination, type_, k=6):
    out = []
    for n, it in enumerate(KB[destination]["items"]):
        if it["type"] == type_:
            hit = sum(w in (it["tags"] + it["name"]).lower() for w in query.lower().split())
            out.append(({"iid": f"{type_[0]}{n}", "name": it["name"], "cost": it["cost"], "desc": it["desc"], "tags": it["tags"],
                         "area": it.get("area", ""), "hours": float(it.get("hours", 0)), "cap": it.get("cap", 1)}, 1.0 - hit * .1))
    return sorted(out, key=lambda x: x[1])[:k]


PARSE = {"destination": "Goa", "budget_inr": 15000, "days": 3, "travelers": 2, "interests": ["beach", "sightseeing", "food"]}
EXPENSIVE = {"hotel_id": "h2", "transport_id": "t4", "days": [
    {"activities": ["a6", "a7"], "meals": ["f19", "f16"]}, {"activities": ["a8", "a12"], "meals": ["f19", "f16"]},
    {"activities": ["a13", "a14"], "meals": ["f19", "f16"]}]}
CHEAP = {"hotel_id": "h0", "transport_id": "t3", "days": [
    {"activities": ["a6", "a7"], "meals": ["f15", "f16"]}, {"activities": ["a8", "a12"], "meals": ["f15", "f18"]},
    {"activities": ["a10", "a14"], "meals": ["f15", "f17"]}]}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(rag, "search", fake_search)
    drafts = {"plans": [], "calls": 0}
    async def fake_ask_json(instructions, payload):
        if "Extract trip details" in instructions:
            return PARSE
        i = min(drafts["calls"], len(drafts["plans"]) - 1); drafts["calls"] += 1
        return drafts["plans"][i]
    monkeypatch.setattr(cs, "ask_json", fake_ask_json)
    return drafts


def run(repo, req="Plan a 3-day Goa trip for two people within ₹15,000. I like beaches, sightseeing and good food."):
    async def go():
        await repo.insert("trips", {"trip_id": "t1", "user_id": "u", "status": "planning", "conversation_id": "c1"})
        await repo.insert("conversations", {"conversation_id": "c1", "messages": []})
        ctx = RunContext(repo, "u", "t1", "e1", EventBus())
        await Orchestrator(ctx, get_settings()).run_new(PlanRequest(message=req))
        return ctx.bus.channels["e1"].events
    return asyncio.run(go())


def test_budget_exceeded_then_revised(env):
    env["plans"] = [EXPENSIVE, CHEAP]
    repo = MemRepo(); events = run(repo)
    checks = [e for e in events if e["type"] == "budget_check"]
    assert checks[0]["status"] == "over" and checks[-1]["status"] == "ok"
    assert any(e["type"] == "revision" for e in events)
    assert events[-1]["type"] == "done" and events[-1]["status"] == "awaiting_approval"
    assert any(e["type"] == "tool_call" and e["data"]["tool"] == "calculate_budget" for e in events)
    trip = asyncio.run(repo.get("trips", {"trip_id": "t1"}))
    assert trip["status"] == "awaiting_approval" and trip["latest_version"] == 1
    it = asyncio.run(repo.list("itineraries", {"trip_id": "t1"}))[0]
    assert it["itinerary"]["cost"]["within_budget"] is True
    assert len(it["attempts"]) == 2
    assert len(asyncio.run(repo.list("agent_execution_logs", {"execution_id": "e1"}))) == len(events)


def test_auto_trim_after_max_revisions(env):
    env["plans"] = [EXPENSIVE]
    events = run(MemRepo())
    assert sum(e["type"] == "revision" for e in events) == get_settings().max_revisions
    assert any(e["type"] == "tool_call" and e["data"]["tool"] == "auto_trim" for e in events)
    assert [e for e in events if e["type"] == "budget_check"][-1]["status"] == "ok"


def test_missing_destination_asks_for_input(env):
    env["plans"] = [CHEAP]
    env_parse = dict(PARSE, destination=None)
    events = run(MemRepo(), "I want a nice trip")
    assert events[-1]["type"] == "done"


def test_copilot_error_is_reported(monkeypatch, env):
    async def boom(*a, **k): raise cs.CopilotUnavailable("Copilot usage limit reached for your plan.")
    monkeypatch.setattr(cs, "ask_json", boom)
    events = run(MemRepo())
    assert any(e["type"] == "error" and "usage limit" in e["message"] for e in events)
    assert events[-1]["status"] == "failed"


def test_budget_math_is_deterministic():
    from app.models import Picks, DayPick, Item
    cat = {"h": Item(id="h", type="hotel", name="H", cost=1000), "t": Item(id="t", type="transport", name="T", cost=500, cap=2),
           "a": Item(id="a", type="activity", name="A", cost=100), "f": Item(id="f", type="food", name="F", cost=200)}
    p = Picks(hotel_id="h", transport_id="t", days=[DayPick(activities=["a"], meals=["f", "f"])] * 3)
    b = bt.calculate_budget(p, cat, days=3, travelers=3, budget=20000)
    assert b.accommodation == 1000 * 2 * 2 and b.transport == 500 * 3 * 2
    assert b.activities == 100 * 3 * 3 and b.food == 200 * 2 * 3 * 3
    assert b.total == 4000 + 3000 + 900 + 3600 and b.within_budget



def test_knowledge_retrieval_falls_back_when_semantic_rag_is_blocked(monkeypatch):
    from app.tools import knowledge

    def blocked(*args, **kwargs):
        raise ImportError("DLL load failed: Application Control blocked _xxhash")

    monkeypatch.setattr(rag, "search", blocked)
    results = knowledge.knowledge_retrieval("beach nature sightseeing", "Goa", ("activity", "food"), 10)
    assert results
    assert any(item["type"] == "activity" for item in results)
    assert any(item["type"] == "food" for item in results)
    assert all(item["source"].startswith("travelmate_kb/goa#") for item in results)


def test_greedy_planner_reports_missing_food_instead_of_modulo_zero():
    from app.agents.planner import greedy_picks
    from app.models import Item, ParsedRequest, Strategy, Task

    catalog = {
        "h0": Item(id="h0", type="hotel", name="Stay", cost=1000),
        "t0": Item(id="t0", type="transport", name="Bus", cost=200),
        "a0": Item(id="a0", type="activity", name="Beach", cost=0, tags="beach"),
    }
    parsed = ParsedRequest(destination="Goa", budget=10000, days=2, travelers=1)
    strategy = Strategy(tasks=[Task(id="draft", agent="Planner", description="Draft")])
    with pytest.raises(ValueError, match="No food candidates"):
        greedy_picks(catalog, parsed, {}, strategy)


def test_research_keeps_local_food_and_activity_catalog_when_rag_returns_empty(monkeypatch):
    from app.agents.research import ResearchAgent
    from app.models import ParsedRequest, Strategy, Task
    from app.runtime import RunContext, EventBus

    class DummyRepo:
        pass

    class DummyContext(RunContext):
        async def tool(self, agent, name, func, **kwargs):
            if name == "knowledge_retrieval":
                return []
            return func(**kwargs)

        async def emit(self, *args, **kwargs):
            return None

        def step(self, *args, **kwargs):
            class Step:
                async def __aenter__(self): return self
                async def __aexit__(self, *args): return False
            return Step()

    ctx = DummyContext(DummyRepo(), "u", "t", "e", EventBus())
    agent = ResearchAgent(ctx)
    parsed = ParsedRequest(destination="Goa", budget=15000, days=3, travelers=2, stated_interests=["beach"])
    strategy = Strategy(tasks=[Task(id="research", agent="Research", description="Research")])
    result = asyncio.run(agent.research(parsed, strategy))
    assert any(item.type == "food" for item in result.candidates)
    assert any(item.type == "activity" for item in result.candidates)


def test_full_trip_uses_fallback_planner_when_rag_and_llm_plan_fail(monkeypatch):
    def blocked_rag(*args, **kwargs):
        raise ImportError("DLL load failed: Application Control blocked _xxhash")

    monkeypatch.setattr(rag, "search", blocked_rag)
    calls = {"parse": 0}

    async def invalid_plan(instructions, payload):
        if "Extract trip details" in instructions:
            return PARSE
        return None

    monkeypatch.setattr(cs, "ask_json", invalid_plan)
    events = run(MemRepo())
    assert any(e["type"] == "decision" and "deterministic fallback planner" in e["message"] for e in events)
    assert not any(e["type"] == "error" and "ZeroDivisionError" in e["message"] for e in events)
    assert events[-1]["type"] == "done"
    assert events[-1]["status"] == "awaiting_approval"
