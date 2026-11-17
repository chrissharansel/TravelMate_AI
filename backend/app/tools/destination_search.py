from ..knowledge.destinations import KB, ALIASES


def supported_destinations() -> list[str]:
    return list(KB)


def normalize_destination(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip().lower()
    for name in KB:
        if name.lower() == t:
            return name
    return ALIASES.get(t)


def detect_destination(text: str) -> str | None:
    t = text.lower()
    for name in KB:
        if name.lower() in t:
            return name
    for alias, name in ALIASES.items():
        if alias in t:
            return name
    return None


def search_destinations(query: str) -> list[dict]:
    """Keyword search over destination names, overviews and item tags."""
    q = query.lower()
    out = []
    for name, d in KB.items():
        hay = (name + " " + d["overview"] + " " + " ".join(i["tags"] for i in d["items"])).lower()
        score = sum(w in hay for w in q.split())
        if score:
            out.append({"destination": name, "match_score": score, "overview": d["overview"]})
    return sorted(out, key=lambda x: -x["match_score"])


def list_places(destination: str, type_: str) -> list[dict]:
    """Return places of one type (hotel, activity, food, transport) with estimated costs."""
    return [{**i, "id": f"{i['type'][0]}{n}", "estimate": True, "source": f"travelmate_kb/{destination.lower()}#{i['type'][0]}{n}"}
            for n, i in enumerate(KB[destination]["items"]) if i["type"] == type_]
