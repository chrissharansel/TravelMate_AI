"""Persistent memory. 'confirmed' = stated or edited by the user; 'assumed' = inferred by the AI."""
from .repo import Repo
from .runtime import now


async def ensure_user(repo: Repo, user_id: str):
    await repo.upsert("users", {"user_id": user_id}, {"updated_at": now()},
                      on_insert={"user_id": user_id, "display_name": "Traveler", "created_at": now()})


async def load_context(repo: Repo, user_id: str) -> dict:
    prefs = await repo.get("user_preferences", {"user_id": user_id}) or {}
    mem = await repo.list("memory", {"user_id": user_id}, limit=300)
    trips = await repo.list("trips", {"user_id": user_id, "status": "approved"}, [("created_at", -1)], 3)
    confirmed = [m for m in mem if m["source"] == "confirmed"]
    return dict(
        preferences=prefs,
        confirmed_interests=sorted({*(prefs.get("preferred_activities") or []),
                                    *[m["value"] for m in confirmed if m["kind"] == "interest"]}),
        assumed_interests=sorted({m["value"] for m in mem if m["kind"] == "interest" and m["source"] == "assumed"}),
        food_preferences=sorted({*(prefs.get("food_preferences") or []),
                                 *[m["value"] for m in confirmed if m["kind"] == "food"]}),
        accommodation=(prefs.get("accommodation_preferences") or [None])[0],
        history=[dict(destination=t["destination"], days=t["duration"], budget=t["total_budget"]) for t in trips])


async def remember_item(repo: Repo, user_id: str, kind: str, value: str, source: str, trip_id: str | None):
    key = f"{kind}:{value.lower()}"
    existing = await repo.get("memory", {"user_id": user_id, "key": key})
    if existing and existing["source"] == "confirmed" and source == "assumed":
        return                                   # never downgrade a confirmed fact
    await repo.upsert("memory", {"user_id": user_id, "key": key},
                      {"kind": kind, "value": value.lower(), "source": source, "trip_id": trip_id, "updated_at": now()},
                      on_insert={"user_id": user_id, "key": key, "created_at": now()})


async def remember_approved_trip(repo: Repo, user_id: str, trip: dict):
    p = trip["parsed"]
    for i in p["stated_interests"]:
        await remember_item(repo, user_id, "interest", i, "confirmed", trip["trip_id"])
    for i in p["assumed_interests"]:
        await remember_item(repo, user_id, "interest", i, "assumed", trip["trip_id"])
    for f in p["food_preferences"]:
        await remember_item(repo, user_id, "food", f, "confirmed", trip["trip_id"])
    if p.get("accommodation_style"):
        await remember_item(repo, user_id, "accommodation", p["accommodation_style"], "assumed", trip["trip_id"])
    await remember_item(repo, user_id, "destination", trip["destination"], "confirmed", trip["trip_id"])
