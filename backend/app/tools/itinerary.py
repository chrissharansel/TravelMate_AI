"""Itinerary builder + schedule validation (deterministic)."""
from datetime import date, timedelta
from ..models import Item, Picks, DayPlan, ScheduledItem, Itinerary, BudgetBreakdown

MAX_DAY_HOURS = 10.0
TRAVEL_GAP = 0.75


def _fmt(t: float) -> str:
    return f"{int(t):02d}:{int(round((t % 1) * 60)):02d}"


def build_itinerary(destination: str, picks: Picks, catalog: dict[str, Item], travelers: int,
                    cost: BudgetBreakdown, start_date: str | None = None) -> Itinerary:
    days = []
    for n, dp in enumerate(picks.days, start=1):
        acts = [catalog[i] for i in dp.activities if i in catalog]
        acts.sort(key=lambda a: a.area)                       # group nearby attractions
        meals = [catalog[i] for i in dp.meals if i in catalog][:3]
        items, t, hours, last_area = [], 9.0, 0.0, None
        lunch_done = False
        for a in acts:
            if last_area is not None and a.area != last_area:
                t += TRAVEL_GAP; hours += TRAVEL_GAP
                items.append(ScheduledItem(time=_fmt(t - TRAVEL_GAP), kind="travel", name=f"Travel to {a.area}", duration_hours=TRAVEL_GAP, area=a.area))
            if not lunch_done and meals and t >= 12.5:
                m = meals[0]; items.append(ScheduledItem(time=_fmt(t), kind="meal", item_id=m.id, name=m.name, cost=m.cost * travelers, duration_hours=1, area=m.area))
                t += 1; hours += 1; lunch_done = True
            items.append(ScheduledItem(time=_fmt(t), kind="activity", item_id=a.id, name=a.name, cost=a.cost * travelers, duration_hours=a.hours or 1, area=a.area))
            t += a.hours or 1; hours += a.hours or 1; last_area = a.area
        remaining = meals[1:] if lunch_done else meals
        for k, m in enumerate(remaining):
            slot = 13.0 if (not lunch_done and k == 0) else 19.5
            items.append(ScheduledItem(time=_fmt(slot), kind="meal", item_id=m.id, name=m.name, cost=m.cost * travelers, duration_hours=1, area=m.area))
            hours += 1
        items.sort(key=lambda x: x.time)
        d_iso = (date.fromisoformat(start_date) + timedelta(days=n - 1)).isoformat() if start_date else None
        days.append(DayPlan(day=n, date=d_iso, items=items, total_hours=round(hours, 1),
                            areas=sorted({a.area for a in acts}), day_cost=sum(i.cost for i in items)))
    return Itinerary(destination=destination, travelers=travelers, days=days, hotel=catalog[picks.hotel_id],
                     transport=catalog[picks.transport_id], picks=picks, cost=cost,
                     notes=["Costs are approximate estimates from a static knowledge base, not live prices.",
                            "Day cost excludes accommodation and transport; see the budget breakdown. Travel to the destination is not included."])


def validate_schedule(it: Itinerary) -> list[str]:
    problems, seen = [], set()
    for d in it.days:
        acts = [i for i in d.items if i.kind == "activity"]
        meals = [i for i in d.items if i.kind == "meal"]
        if not acts:
            problems.append(f"Day {d.day} has no activities.")
        if len(meals) < 2:
            problems.append(f"Day {d.day} has fewer than 2 meals.")
        if d.total_hours > MAX_DAY_HOURS:
            problems.append(f"Day {d.day} is unrealistic ({d.total_hours} h of activities, travel and meals; max {MAX_DAY_HOURS}).")
        if len(d.areas) > 2:
            problems.append(f"Day {d.day} spreads across {len(d.areas)} areas ({', '.join(d.areas)}); group nearby places.")
        for a in acts:
            if a.item_id in seen:
                problems.append(f"{a.name} is repeated on more than one day.")
            seen.add(a.item_id)
    return problems
