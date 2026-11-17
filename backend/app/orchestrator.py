"""Controlled orchestrator. It owns the flow and makes explicit next-step decisions
(clarify / revise / trim / ask for approval). The LLM only returns text; it never executes anything."""
import asyncio, uuid
from . import copilot_service as cs
from . import memory
from .agents.budget_agent import BudgetAgent
from .agents.planner import PlannerAgent
from .agents.research import ResearchAgent
from .agents.reviewer import ReviewerAgent
from .models import PlanRequest, ParsedRequest, Research, Picks, Itinerary
from .runtime import RunContext, now
from .tools.destination_search import supported_destinations
from .tools.itinerary import build_itinerary


class Orchestrator:
    def __init__(self, ctx: RunContext, settings):
        self.ctx, self.s, self.repo = ctx, settings, ctx.repo
        self.planner, self.research = PlannerAgent(ctx, settings), ResearchAgent(ctx)
        self.budget, self.reviewer = BudgetAgent(ctx), ReviewerAgent(ctx)

    async def _finish(self, status: str, message: str):
        await self.repo.update("trips", {"trip_id": self.ctx.trip_id}, {"status": status, "updated_at": now()})
        await self.ctx.emit("done", "Orchestrator", status, message)

    async def _say(self, text: str):
        trip = await self.repo.get("trips", {"trip_id": self.ctx.trip_id})
        if trip and trip.get("conversation_id"):
            await self.repo.push("conversations", {"conversation_id": trip["conversation_id"]}, "messages",
                                 {"role": "assistant", "content": text, "ts": now()}, {"updated_at": now()})

    # ------------------------------------------------------------------ new trip
    async def run_new(self, request: PlanRequest):
        ctx = self.ctx
        try:
            await ctx.emit("log", "Orchestrator", "info", "Run started")
            mem = await memory.load_context(self.repo, ctx.user_id)
            parsed = await self.planner.understand(request, mem)
            if parsed.destination and parsed.destination not in supported_destinations():
                parsed.missing.append("destination")
            if parsed.missing:
                text = (f"I need: {', '.join(parsed.missing)}. Supported destinations: {', '.join(supported_destinations())}.")
                await self.repo.update("trips", {"trip_id": ctx.trip_id}, {"parsed": parsed.model_dump(), "destination": parsed.destination or "Unknown"})
                await ctx.emit("needs_input", "Planner", "needs_input", text, data={"missing": parsed.missing})
                await self._say(text)
                return await self._finish("needs_info", text)
            await self.repo.update("trips", {"trip_id": ctx.trip_id}, dict(
                parsed=parsed.model_dump(), destination=parsed.destination, duration=parsed.days, total_budget=parsed.budget or 0,
                travelers=parsed.travelers, start_date=parsed.start_date, preferences=dict(
                    interests=parsed.interests, food=parsed.food_preferences, accommodation=parsed.accommodation_style)))
            async with ctx.step("Planner", "Create the planning strategy", input=parsed) as st:
                strategy = self.planner.make_strategy(parsed)
                for t in strategy.tasks:
                    await ctx.emit("task", t.agent, "planned", t.description, data=t.model_dump())
                st.output = strategy
            research = await self.research.research(parsed, strategy)
            await self.repo.update("trips", {"trip_id": ctx.trip_id}, {"research": research.model_dump(), "strategy": strategy.model_dump()})
            await self._plan_loop(parsed, research, strategy, feedback="", previous=None)
        except cs.CopilotUnavailable as e:
            await ctx.emit("error", "Orchestrator", "failed", str(e))
            await self._finish("failed", str(e))
        except Exception as e:
            await ctx.emit("error", "Orchestrator", "failed", f"{type(e).__name__}: {e}")
            await self._finish("failed", f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------ revision
    async def run_revision(self, trip: dict, feedback: str, regenerate: bool):
        ctx = self.ctx
        try:
            parsed, research = ParsedRequest(**trip["parsed"]), Research(**trip["research"])
            from .models import Strategy
            strategy = Strategy(**trip["strategy"])
            latest = await self.repo.list("itineraries", {"trip_id": trip["trip_id"]}, [("version", -1)], 1)
            previous = Picks(**latest[0]["itinerary"]["picks"]) if latest else None
            if regenerate and not feedback:
                feedback = "Regenerate: choose a clearly different mix of attractions and restaurants from the previous plan."
            await ctx.emit("decision", "Orchestrator", "info", f"Revision requested by the traveler: {feedback or 'none'}")
            await ctx.emit("log", "Orchestrator", "info", "Reusing stored research; skipping parse and retrieval")
            await self._plan_loop(parsed, research, strategy, feedback=feedback, previous=previous)
        except cs.CopilotUnavailable as e:
            await ctx.emit("error", "Orchestrator", "failed", str(e))
            await self._finish("awaiting_approval" if trip.get("latest_version") else "failed", str(e))
        except Exception as e:
            await ctx.emit("error", "Orchestrator", "failed", f"{type(e).__name__}: {e}")
            await self._finish("awaiting_approval" if trip.get("latest_version") else "failed", f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------ core loop
    async def _plan_loop(self, parsed: ParsedRequest, research: Research, strategy, feedback: str, previous: Picks | None):
        ctx, catalog = self.ctx, {c.id: c for c in research.candidates}
        caps = await self.budget.allocate(parsed, strategy)
        max_attempts, attempts, fb, picks = self.s.max_revisions + 1, [], feedback, previous
        itin = review = None
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                await ctx.emit("revision", "Orchestrator", "running", f"Revision {attempt - 1} of {self.s.max_revisions}",
                               data=dict(revision=attempt - 1, max=self.s.max_revisions))
            picks = await self.planner.draft(parsed, research, caps, strategy, fb, picks, attempt)
            cost = await self.budget.evaluate(picks, catalog, parsed, attempt)
            itin = await ctx.tool("Planner", "build_itinerary", build_itinerary, destination=parsed.destination, picks=picks,
                                  catalog=catalog, travelers=parsed.travelers, cost=cost, start_date=parsed.start_date)
            review = await self.reviewer.review(itin, parsed, research, attempt)
            attempts.append(dict(attempt=attempt, total=cost.total, within_budget=cost.within_budget,
                                 approved=review.approved, issues=[v.message for v in review.violations if v.blocking]))
            if review.approved:
                await ctx.emit("decision", "Orchestrator", "ok", "Reviewer approved: sending the itinerary to the traveler for approval")
                break
            if attempt == max_attempts:
                break
            kinds = sorted({v.kind for v in review.violations if v.blocking})
            await ctx.emit("decision", "Orchestrator", "warn", f"Reviewer rejected ({', '.join(kinds)}): routing back to the Planner for revision")
            fb = (feedback + " | " if feedback else "") + review.feedback
        if not review.approved and parsed.budget and not itin.cost.within_budget:
            await ctx.emit("decision", "Orchestrator", "warn", "Revision limit reached and still over budget: applying deterministic trimming")
            picks, applied = await self.budget.trim(picks, catalog, parsed)
            cost = await self.budget.evaluate(picks, catalog, parsed, max_attempts + 1)
            itin = await ctx.tool("Planner", "build_itinerary", build_itinerary, destination=parsed.destination, picks=picks,
                                  catalog=catalog, travelers=parsed.travelers, cost=cost, start_date=parsed.start_date)
            review = await self.reviewer.review(itin, parsed, research, max_attempts + 1)
            itin.notes.append("Automatic trimming applied: " + "; ".join(applied) if applied else "Automatic trimming could not reduce the cost further.")
            attempts.append(dict(attempt="trim", total=cost.total, within_budget=cost.within_budget, approved=review.approved, issues=[]))
        if not itin.cost.within_budget and parsed.budget:
            itin.notes.append(f"This plan is still ₹{-itin.cost.remaining:,} over your budget. Consider raising the budget or shortening the trip.")
        for v in review.violations:
            if not v.blocking:
                itin.notes.append(v.message)
        await self._save(parsed, itin, review, attempts, feedback)

    async def _save(self, parsed, itin: Itinerary, review, attempts, feedback):
        ctx = self.ctx
        latest = await self.repo.list("itineraries", {"trip_id": ctx.trip_id}, [("version", -1)], 1)
        version = (latest[0]["version"] + 1) if latest else 1
        if latest:
            await self.repo.update("itineraries", {"trip_id": ctx.trip_id, "version": latest[0]["version"]}, {"approval_status": "superseded"}) \
                if latest[0]["approval_status"] == "pending" else None
        await self.repo.insert("itineraries", dict(
            trip_id=ctx.trip_id, version=version, execution_id=ctx.execution_id, itinerary=itin.model_dump(),
            review=review.model_dump(), attempts=attempts, feedback=feedback, approval_status="pending", created_at=now()))
        end = None
        if parsed.start_date:
            from datetime import date, timedelta
            end = (date.fromisoformat(parsed.start_date) + timedelta(days=parsed.days - 1)).isoformat()
        await self.repo.update("trips", {"trip_id": ctx.trip_id}, {"status": "awaiting_approval", "latest_version": version, "end_date": end,
                                                                  "updated_at": now(), "latest_execution_id": ctx.execution_id})
        c = itin.cost
        summary = (f"Version {version}: {parsed.days}-day {parsed.destination} plan, estimated ₹{c.total:,}"
                   + (f" of ₹{c.budget:,} (₹{c.remaining:,} left)." if c.budget else "."))
        await self._say(summary)
        await ctx.emit("itinerary", "Orchestrator", "ready", summary, data=dict(version=version, total=c.total, within_budget=c.within_budget))
        await ctx.emit("awaiting_approval", "Human", "waiting", "Waiting for your approval. Approve, request changes, or regenerate.", data=dict(version=version))
        await ctx.emit("done", "Orchestrator", "awaiting_approval", summary)
