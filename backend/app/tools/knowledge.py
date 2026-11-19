"""Knowledge retrieval with semantic RAG and a deterministic local fallback."""

import re
from ..knowledge.destinations import KB

_STOP_WORDS = {"the", "a", "an", "in", "at", "for", "to", "and", "of", "near", "popular", "things", "do", "what", "where"}


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1 and token not in _STOP_WORDS}


def _keyword_search(query: str, destination: str, type_: str, k: int) -> list[tuple[dict, float]]:
    """Search the bundled destination knowledge base without embeddings."""
    destination_data = KB.get(destination)
    if not destination_data:
        return []
    query_tokens = _tokens(query) - _tokens(destination)
    scored = []
    for index, item in enumerate(destination_data["items"]):
        if item["type"] != type_:
            continue
        text = " ".join((item.get("name", ""), item.get("desc", ""), item.get("tags", ""), item.get("area", "")))
        overlap = query_tokens.intersection(_tokens(text))
        score = len(overlap) / max(len(query_tokens), 1)
        metadata = {
            "iid": f"{item['type'][0]}{index}", "name": item["name"], "cost": item.get("cost", 0),
            "desc": item.get("desc", ""), "tags": item.get("tags", ""), "area": item.get("area", ""),
            "hours": float(item.get("hours", 0) or 0), "cap": int(item.get("cap", 1) or 1),
        }
        scored.append((metadata, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:max(0, k)]


def knowledge_retrieval(query: str, destination: str, types=("activity", "food"), k: int = 5) -> list[dict]:
    """Try semantic retrieval, then fall back to local keyword search if it fails or is empty."""
    out = []
    for item_type in types:
        hits = []
        try:
            # Lazy import keeps optional RAG dependencies from breaking application startup.
            from ..knowledge import rag
            hits = rag.search(query, destination, item_type, k)
        except Exception as exc:
            print("[TravelMate] Semantic RAG unavailable; using local keyword search "
                  f"for {destination}/{item_type}. Reason: {type(exc).__name__}: {exc}")
            hits = _keyword_search(query, destination, item_type, k)
        if not hits:
            hits = _keyword_search(query, destination, item_type, k)
        for meta, score in hits:
            out.append({
                "id": meta["iid"], "type": item_type, "name": meta["name"], "cost": meta.get("cost", 0),
                "desc": meta.get("desc", ""), "tags": meta.get("tags", ""), "area": meta.get("area", ""),
                "hours": meta.get("hours", 0), "cap": meta.get("cap", 1), "score": round(float(score), 3),
                "source": f"travelmate_kb/{destination.lower()}#{meta['iid']}", "approximate": True,
            })
    return out
