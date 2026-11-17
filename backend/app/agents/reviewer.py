from ..models import Itinerary, ParsedRequest, Research, Review, Violation
from ..runtime import RunContext
from ..tools.itinerary import validate_schedule


def _covered(interest: str, it: Itinerary, catalog) -> bool:
    i = interest.lower()
    names = [d_i for d in it.days for d_i in d.items if d_i.item_id]
    for x in names:
        c = catalog.get(x.item_id)
        if c and (i in c.tags.lower() or i in c.name.lower() or i in c.desc.lower()):
            return True
    return i in "food" and any(x.kind == "meal" for d in it.days for x in d.items)


class ReviewerAgent:
    name = "Reviewer"

    def __init__(self, ctx: RunContext):
        self.ctx = ctx

    async def review(self, it: Itinerary, parsed: ParsedRequest, research: Research, attempt: int) -> Review:
        ctx = self.ctx
        async with ctx.step(self.name, f"Review itinerary (attempt {attempt})") as st:
            catalog = {c.id: c for c in research.candidates}
            v: list[Violation] = []
            if not it.cost.within_budget and it.cost.budget:
                msg = f"Total ₹{it.cost.total:,} exceeds the budget ₹{it.cost.budget:,} by ₹{-it.cost.remaining:,}. Costliest: {', '.join(it.cost.expensive)}."
                if it.cost.suggestions:
                    msg += " Try: " + "; ".join(it.cost.suggestions)
                v.append(Violation(kind="budget", message=msg))
            for p in await ctx.tool(self.name, "validate_schedule", validate_schedule, it=it):
                v.append(Violation(kind="schedule", message=p))
            known_tags = " ".join(c.tags.lower() + " " + c.name.lower() for c in research.candidates)
            for interest in parsed.stated_interests:
                if not _covered(interest, it, catalog):
                    available = interest.lower() in known_tags
                    v.append(Violation(kind="preference", blocking=available,
                                       message=f"Interest '{interest}' is not covered." if available else f"Interest '{interest}' has no matching options in the knowledge base."))
            if "vegetarian" in parsed.food_preferences:
                for d in it.days:
                    for x in d.items:
                        c = catalog.get(x.item_id or "")
                        if x.kind == "meal" and c and "veg" not in c.tags.lower():
                            v.append(Violation(kind="preference", message=f"Meal '{c.name}' may not suit a vegetarian traveler; choose a veg-friendly option."))
            blocking = [x for x in v if x.blocking]
            review = Review(approved=not blocking, violations=v, feedback=" | ".join(x.message for x in blocking))
            await ctx.emit("review", self.name, "approved" if review.approved else "rejected",
                           "Itinerary passes all checks" if review.approved else f"{len(blocking)} blocking issue(s) found",
                           data=dict(attempt=attempt, approved=review.approved, violations=[x.model_dump() for x in v]))
            st.output = review
            return review
