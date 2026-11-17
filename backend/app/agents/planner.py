import json, re
from .. import copilot_service as cs
from ..models import ParsedRequest, PlanRequest, Strategy, Task, Picks, DayPick, Item, Research
from ..runtime import RunContext
from ..tools.destination_search import detect_destination, normalize_destination, supported_destinations
from ..tools.budget import line_cost

VOCAB = {"beach": "beach", "beaches": "beach", "sightseeing": "sightseeing", "food": "food", "foodie": "food",
         "adventure": "adventure", "nature": "nature", "heritage": "heritage", "history": "heritage", "shopping": "shopping",
         "nightlife": "nightlife", "relax": "relax", "culture": "culture", "trek": "trek", "temples": "heritage",
         "wildlife": "wildlife", "waterfall": "waterfall", "tea": "tea", "snow": "snow", "backwaters": "backwaters"}
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "couple": 2, "solo": 1}


def _norm_interest(s: str) -> str:
    s = s.strip().lower()
    return VOCAB.get(s, s[:-1] if s.endswith("s") and len(s) > 4 else s)


def heuristic_parse(text: str) -> dict:
    t = text.lower()
    out: dict = {"destination": detect_destination(text)}
    m = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(k)?|(?:budget|within|under)\D{0,12}([\d,]+)\s*(k)?", t)
    if m:
        raw, k = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        out["budget"] = int(float(raw.replace(",", "")) * (1000 if k else 1))
    m = re.search(r"(\d+)\s*[- ]?\s*(?:days?|nights?)", t)
    if m:
        out["days"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:people|persons|travell?ers|adults|friends)", t) or re.search(r"for\s+(\w+)\s+(?:people|persons|of us)", t)
    if m:
        v = m.group(1)
        out["travelers"] = int(v) if v.isdigit() else NUM_WORDS.get(v)
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}\b", t) and w in ("couple", "solo"):
            out["travelers"] = n
    out["interests"] = sorted({VOCAB[w] for w in re.findall(r"[a-z]+", t) if w in VOCAB})
    out["food_preferences"] = [f for f in ("vegetarian", "vegan", "seafood") if f in t or (f == "vegetarian" and re.search(r"\bveg\b", t))]
    for style, words in (("budget", ("hostel", "budget stay", "budget accommodation", "cheap")), ("luxury", ("luxury", "resort", "5-star")),
                         ("midrange", ("mid-range", "midrange", "comfortable")), ("homestay", ("homestay",))):
        if any(w in t for w in words):
            out["accommodation_style"] = style
            break
    return out


class PlannerAgent:
    name = "Planner"

    def __init__(self, ctx: RunContext, settings):
        self.ctx, self.s = ctx, settings

    # ---- understand ----
    async def understand(self, req: PlanRequest, mem: dict) -> ParsedRequest:
        ctx = self.ctx
        async with ctx.step(self.name, "Understand the travel request", input=req.model_dump(mode="json")) as st:
            h = heuristic_parse(req.message) if req.message else {}
            llm: dict = {}
            if req.message.strip():
                try:
                    llm = await cs.ask_json(
                        "Extract trip details from the user's message as JSON with keys: destination (string or null), "
                        "budget_inr (integer or null), days (integer or null), travelers (integer or null), "
                        "start_date (YYYY-MM-DD or null), interests (list of short lowercase strings), "
                        "food_preferences (list e.g. vegetarian, vegan, seafood), "
                        "accommodation_style (budget|midrange|luxury|homestay|null). Use null when not stated; never guess.",
                        f"Message: {req.message}") or {}
                    await ctx.emit("log", self.name, "ok", "LLM extracted structured trip details", data={"llm": llm})
                except cs.CopilotUnavailable:
                    raise
            else:
                await ctx.emit("decision", self.name, "info", "Structured form is complete enough; skipped the LLM parse to save Copilot usage")
            def pick(*vals):
                return next((v for v in vals if v not in (None, "", [])), None)
            def to_int(v):
                try:
                    return int(float(v)) if v is not None else None
                except (TypeError, ValueError):
                    return None
            dest = normalize_destination(req.destination) or normalize_destination(llm.get("destination")) or h.get("destination")
            budget = pick(req.budget, to_int(llm.get("budget_inr")), h.get("budget"))
            days = pick(req.days, to_int(llm.get("days")), h.get("days"), 3)
            trav = pick(req.travelers, to_int(llm.get("travelers")), h.get("travelers"), 1)
            stated = [_norm_interest(i) for i in (req.interests or llm.get("interests") or h.get("interests") or []) if isinstance(i, str)]
            food = [f.lower() for f in (llm.get("food_preferences") or h.get("food_preferences") or []) if isinstance(f, str)]
            style = pick(llm.get("accommodation_style"), h.get("accommodation_style"))
            assumed: list[str] = []
            if not stated and mem["confirmed_interests"]:
                stated = list(mem["confirmed_interests"])
                await ctx.emit("log", "Memory", "ok", f"Using confirmed preferences from memory: {', '.join(stated)}", data={"source": "confirmed"})
            if not stated:
                assumed = list(mem["assumed_interests"]) or ["sightseeing", "food"]
                await ctx.emit("log", "Memory", "info", f"No interests given; ASSUMING {', '.join(assumed)} (AI assumption, not confirmed)", data={"source": "assumed"})
            if not food and mem["food_preferences"]:
                food = list(mem["food_preferences"])
                await ctx.emit("log", "Memory", "ok", f"Using confirmed food preferences: {', '.join(food)}", data={"source": "confirmed"})
            style = style or mem.get("accommodation")
            sd = req.start_date.isoformat() if req.start_date else llm.get("start_date")
            if sd and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(sd)):
                sd = None
            missing = []
            if not dest:
                missing.append("destination")
            if not budget:
                missing.append("budget")
            parsed = ParsedRequest(destination=dest, budget=budget, days=max(1, min(int(days), 14)), travelers=max(1, min(int(trav), 12)),
                                   start_date=sd, stated_interests=list(dict.fromkeys(stated)), assumed_interests=assumed,
                                   food_preferences=food, accommodation_style=style, missing=missing)
            if missing:
                await ctx.emit("decision", self.name, "warn", f"Missing information: {', '.join(missing)}. Supported destinations: {', '.join(supported_destinations())}")
            st.output = parsed
            return parsed

    # ---- strategy ----
    def make_strategy(self, parsed: ParsedRequest) -> Strategy:
        pppd = parsed.budget / (parsed.travelers * parsed.days) if parsed.budget else 99999
        budget_mode = pppd < 2500
        notes = [f"Budget per person per day is about ₹{int(pppd):,}." if parsed.budget else "No budget given."]
        if budget_mode:
            notes.append("Tight budget: prefer budget stays, cheap transport and free attractions.")
        tasks = [Task(id="research", agent="Research", description=f"Retrieve {parsed.destination} options with RAG"),
                 Task(id="allocate", agent="Budget", description="Split the budget across stay, transport, food and activities"),
                 Task(id="draft", agent="Planner", description=f"Draft a {parsed.days}-day itinerary around: {', '.join(parsed.interests)}"),
                 Task(id="price", agent="Budget", description="Price the itinerary with deterministic Python"),
                 Task(id="review", agent="Reviewer", description="Validate budget, preferences and schedule realism"),
                 Task(id="approve", agent="Human", description="Ask the traveler to approve or request changes")]
        return Strategy(tasks=tasks, budget_mode=budget_mode, notes=notes)

    # ---- draft ----
    async def draft(self, parsed: ParsedRequest, research: Research, caps: dict, strategy: Strategy,
                    feedback: str, previous: Picks | None, attempt: int) -> Picks:
        ctx = self.ctx
        catalog = {c.id: c for c in research.candidates}
        task = "Draft itinerary" if attempt == 1 else f"Revise itinerary (attempt {attempt})"
        async with ctx.step(self.name, task, input={"attempt": attempt, "feedback": feedback, "caps": caps}) as st:
            menu = "\n".join(f"{c.id} | {c.type} | {c.name} | ₹{c.cost} | area: {c.area or '-'} | {c.hours or ''}h | {c.tags}" for c in research.candidates)
            prompt_rules = (
                f"You plan a {parsed.days}-day trip to {parsed.destination} for {parsed.travelers} traveler(s). "
                "Choose ONLY ids from the MENU. Return JSON: {\"hotel_id\": id, \"transport_id\": id, \"days\": "
                f"[{{\"activities\": [ids], \"meals\": [ids]}}]}} with exactly {parsed.days} day objects, 2-3 activities and exactly 2 meals per day. "
                "Do not repeat an activity on different days. Keep each day's activities in ONE area (the area column). "
                "Prices: hotel is per room per night (1 room per 2 people), transport per vehicle per day, activity per person, meal per person. "
                "Do not do any arithmetic; the budget is checked separately.")
            payload = (f"Interests: {', '.join(parsed.interests)}\nFood preferences: {', '.join(parsed.food_preferences) or 'none'}\n"
                       f"Accommodation style: {parsed.accommodation_style or 'not specified'}\n"
                       f"Total budget ₹{parsed.budget}. Target spend: stay ≈ ₹{caps['accommodation']}, transport ≈ ₹{caps['transport']}, "
                       f"food ≈ ₹{caps['food']}, activities ≈ ₹{caps['activities']}.\n"
                       + (f"Previous plan picks: {previous.model_dump_json()}\n" if previous else "")
                       + (f"MUST FIX: {feedback}\n" if feedback else "") + f"MENU:\n{menu}")
            raw = await cs.ask_json(prompt_rules, payload)
            picks = self._sanitize(raw, catalog, parsed) if raw else None
            if picks is None:
                await ctx.emit("decision", self.name, "warn", "LLM reply was not a valid plan; using the deterministic fallback planner")
                picks = greedy_picks(catalog, parsed, caps, strategy)
            st.output = picks
            return picks

    def _sanitize(self, raw: dict, catalog: dict[str, Item], parsed: ParsedRequest) -> Picks | None:
        try:
            hotel, trans = raw.get("hotel_id"), raw.get("transport_id")
            if catalog.get(hotel, Item(id="", type="food", name="", cost=0)).type != "hotel" or \
               catalog.get(trans, Item(id="", type="food", name="", cost=0)).type != "transport":
                return None
            used, days = set(), []
            foods = sorted([c for c in catalog.values() if c.type == "food"], key=lambda c: c.cost)
            for d in (raw.get("days") or [])[:parsed.days]:
                acts = []
                for i in d.get("activities", []):
                    if i in catalog and catalog[i].type == "activity" and i not in used and len(acts) < 3:
                        acts.append(i); used.add(i)
                meals = [i for i in d.get("meals", []) if i in catalog and catalog[i].type == "food"][:2]
                for f in foods:
                    if len(meals) >= 2:
                        break
                    if f.id not in meals:
                        meals.append(f.id)
                days.append(DayPick(activities=acts, meals=meals))
            if not days:
                return None
            while len(days) < parsed.days:
                days.append(DayPick())
            return Picks(hotel_id=hotel, transport_id=trans, days=days)
        except Exception:
            return None


def greedy_picks(catalog: dict[str, Item], parsed: ParsedRequest, caps: dict, strategy: Strategy) -> Picks:
    """Deterministic planner used only when the LLM cannot produce valid JSON."""
    interests = [i.lower() for i in parsed.interests]
    score = lambda c: sum(1 for i in interests if i in c.tags.lower() or i in c.name.lower())
    by = lambda t: [c for c in catalog.values() if c.type == t]
    hotels = sorted(by("hotel"), key=lambda c: c.cost)
    style = (parsed.accommodation_style or ("budget" if strategy.budget_mode else "midrange"))
    hotel = hotels[0] if style in ("budget", "homestay") else hotels[-1] if style == "luxury" else hotels[len(hotels) // 2]
    trans = min(by("transport"), key=lambda c: line_cost(c, parsed.days, parsed.travelers))
    acts = sorted(by("activity"), key=lambda c: (-score(c), c.cost))[:max(2, parsed.days * 2)]
    acts.sort(key=lambda c: c.area)
    veg = "vegetarian" in parsed.food_preferences
    foods = [f for f in sorted(by("food"), key=lambda c: (-score(c), c.cost)) if not veg or "veg" in f.tags]
    foods = foods or sorted(by("food"), key=lambda c: c.cost)
    days = []
    per = max(1, -(-len(acts) // parsed.days))
    for d in range(parsed.days):
        days.append(DayPick(activities=[a.id for a in acts[d * per:(d + 1) * per]][:3],
                            meals=[foods[(2 * d + k) % len(foods)].id for k in range(2)]))
    return Picks(hotel_id=hotel.id, transport_id=trans.id, days=days)
