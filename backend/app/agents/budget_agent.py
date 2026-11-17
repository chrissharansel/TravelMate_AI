from ..models import ParsedRequest, Picks, Item, BudgetBreakdown, Strategy
from ..runtime import RunContext
from ..tools import budget as bt


class BudgetAgent:
    name = "Budget"

    def __init__(self, ctx: RunContext):
        self.ctx = ctx

    async def allocate(self, parsed: ParsedRequest, strategy: Strategy) -> dict:
        async with self.ctx.step(self.name, "Allocate the budget", input={"budget": parsed.budget}) as st:
            caps = await self.ctx.tool(self.name, "allocate_budget", bt.allocate, budget=parsed.budget or 0, budget_mode=strategy.budget_mode)
            st.output = caps
            return caps

    async def evaluate(self, picks: Picks, catalog: dict[str, Item], parsed: ParsedRequest, attempt: int) -> BudgetBreakdown:
        ctx = self.ctx
        async with ctx.step(self.name, f"Calculate trip cost (attempt {attempt})") as st:
            cost = await ctx.tool(self.name, "calculate_budget", bt.calculate_budget, picks=picks, catalog=catalog,
                                  days=parsed.days, travelers=parsed.travelers, budget=parsed.budget)
            if not cost.within_budget:
                cost.suggestions = await ctx.tool(self.name, "suggest_savings", bt.suggest_savings, picks=picks, catalog=catalog,
                                                  days=parsed.days, travelers=parsed.travelers)
            await ctx.emit("budget_check", self.name, "ok" if cost.within_budget else "over",
                           (f"₹{cost.total:,} is within the ₹{cost.budget:,} budget (₹{cost.remaining:,} left)" if cost.within_budget and cost.budget
                            else f"₹{cost.total:,} exceeds the ₹{cost.budget:,} budget by ₹{-(cost.remaining or 0):,}" if cost.budget else f"Total ₹{cost.total:,}"),
                           data=dict(attempt=attempt, **cost.model_dump()))
            st.output = cost
            return cost

    async def trim(self, picks: Picks, catalog, parsed: ParsedRequest):
        ctx = self.ctx
        async with ctx.step(self.name, "Apply automatic cost trimming (revision limit reached)") as st:
            new, applied = await ctx.tool(self.name, "auto_trim", bt.auto_trim, picks=picks, catalog=catalog,
                                          days=parsed.days, travelers=parsed.travelers, budget=parsed.budget)
            st.output = applied
            return new, applied
