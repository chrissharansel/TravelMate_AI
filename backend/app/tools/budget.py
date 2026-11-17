"""Deterministic money maths. The LLM never does arithmetic."""
import math
from ..models import Item, Picks, BudgetBreakdown


def line_cost(item: Item, days: int, travelers: int) -> int:
    nights = max(days - 1, 1)
    if item.type == "hotel":
        return item.cost * nights * math.ceil(travelers / 2)
    if item.type == "transport":
        return item.cost * days * math.ceil(travelers / max(item.cap, 1))
    return item.cost * travelers          # activity: per person; food: per person per meal


def calculate_budget(picks: Picks, catalog: dict[str, Item], days: int, travelers: int, budget: int | None) -> BudgetBreakdown:
    acc = line_cost(catalog[picks.hotel_id], days, travelers)
    trn = line_cost(catalog[picks.transport_id], days, travelers)
    act = sum(line_cost(catalog[i], days, travelers) for d in picks.days for i in d.activities if i in catalog)
    food = sum(line_cost(catalog[i], days, travelers) for d in picks.days for i in d.meals if i in catalog)
    total = acc + trn + act + food
    lines = [(catalog[picks.hotel_id].name, acc), (catalog[picks.transport_id].name, trn)]
    lines += [(catalog[i].name, line_cost(catalog[i], days, travelers)) for d in picks.days for i in d.activities + d.meals if i in catalog]
    expensive = [f"{n} (₹{c:,})" for n, c in sorted(lines, key=lambda x: -x[1])[:3] if c > 0]
    return BudgetBreakdown(accommodation=acc, transport=trn, food=food, activities=act, total=total, budget=budget,
                           remaining=None if budget is None else budget - total,
                           within_budget=budget is None or total <= budget, expensive=expensive)


def allocate(budget: int, budget_mode: bool) -> dict[str, int]:
    shares = dict(accommodation=.30, transport=.12, food=.33, activities=.25) if budget_mode else \
             dict(accommodation=.38, transport=.14, food=.28, activities=.20)
    return {k: int(budget * v) for k, v in shares.items()}


def _swap_options(picks: Picks, catalog: dict[str, Item], days: int, travelers: int):
    """Yield (saving, description, new_picks) for every cheaper same-type replacement."""
    def cheaper(cur: Item):
        return [i for i in catalog.values() if i.type == cur.type and i.cost < cur.cost]
    cur = catalog[picks.hotel_id]
    for alt in cheaper(cur):
        yield (line_cost(cur, days, travelers) - line_cost(alt, days, travelers),
               f"Swap stay {cur.name} for {alt.name}", picks.model_copy(update={"hotel_id": alt.id}))
    cur = catalog[picks.transport_id]
    for alt in cheaper(cur):
        yield (line_cost(cur, days, travelers) - line_cost(alt, days, travelers),
               f"Swap transport {cur.name} for {alt.name}", picks.model_copy(update={"transport_id": alt.id}))
    for di, d in enumerate(picks.days):
        for field in ("activities", "meals"):
            for pos, iid in enumerate(getattr(d, field)):
                cur = catalog[iid]
                used = {x for dd in picks.days for x in dd.activities}
                for alt in cheaper(cur):
                    if field == "activities" and alt.id in used:
                        continue
                    nd = d.model_copy(deep=True); getattr(nd, field)[pos] = alt.id
                    days_l = list(picks.days); days_l[di] = nd
                    yield (line_cost(cur, days, travelers) - line_cost(alt, days, travelers),
                           f"Day {di+1}: swap {cur.name} for {alt.name}", picks.model_copy(update={"days": days_l}))


def suggest_savings(picks: Picks, catalog, days, travelers, limit: int = 3) -> list[str]:
    best = sorted(_swap_options(picks, catalog, days, travelers), key=lambda x: -x[0])[:limit]
    return [f"{d} (saves ₹{s:,})" for s, d, _ in best if s > 0]


def auto_trim(picks: Picks, catalog, days, travelers, budget: int) -> tuple[Picks, list[str]]:
    """Last resort: greedily apply the largest saving until the plan fits. Terminates (each swap lowers cost)."""
    applied = []
    while calculate_budget(picks, catalog, days, travelers, budget).total > budget:
        opts = [o for o in _swap_options(picks, catalog, days, travelers) if o[0] > 0]
        if not opts:
            break
        s, d, picks = max(opts, key=lambda x: x[0])
        applied.append(f"{d} (saves ₹{s:,})")
    return picks, applied
