from ..knowledge import rag


def knowledge_retrieval(query: str, destination: str, types=("activity", "food"), k: int = 5) -> list[dict]:
    """Semantic search. Every result carries a source and an 'approximate' flag."""
    out = []
    for t in types:
        for meta, score in rag.search(query, destination, t, k):
            out.append({"id": meta["iid"], "type": t, "name": meta["name"], "cost": meta.get("cost", 0),
                        "desc": meta.get("desc", ""), "tags": meta.get("tags", ""), "area": meta.get("area", ""),
                        "hours": meta.get("hours", 0), "cap": meta.get("cap", 1), "score": round(score, 3),
                        "source": f"travelmate_kb/{destination.lower()}#{meta['iid']}", "approximate": True})
    return out
