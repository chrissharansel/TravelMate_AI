from ..knowledge.destinations import KB, DISCLAIMER
from ..models import ParsedRequest, Research, Item, Strategy
from ..runtime import RunContext
from ..tools.destination_search import search_destinations, list_places
from ..tools.knowledge import knowledge_retrieval


def _item(d: dict, approx=True) -> Item:
    return Item(id=d["id"], type=d["type"], name=d["name"], cost=int(d["cost"]), desc=d.get("desc", ""), area=d.get("area", ""),
                hours=float(d.get("hours", 0) or 0), tags=d.get("tags", ""), cap=int(d.get("cap", 1) or 1),
                source=d.get("source", ""), estimate=approx)


class ResearchAgent:
    name = "Research"

    def __init__(self, ctx: RunContext):
        self.ctx = ctx

    async def research(self, parsed: ParsedRequest, strategy: Strategy) -> Research:
        ctx, dest = self.ctx, parsed.destination
        async with ctx.step(self.name, f"Research {dest}", input={"destination": dest, "interests": parsed.interests}) as st:
            await ctx.tool(self.name, "search_destinations", search_destinations, query=dest)
            cands: dict[str, Item] = {}
            sources: list[dict] = []
            for t in ("hotel", "transport"):
                for p in await ctx.tool(self.name, "list_places", list_places, destination=dest, type_=t):
                    cands[p["id"]] = _item(p)
            n_act, n_food = max(8, parsed.days * 3 + 2), max(5, parsed.days * 2 + 2)
            queries = [f"{i} {dest}" for i in parsed.interests[:3]] or [f"things to do in {dest}"]
            for q in queries + [f"popular local food {dest}"]:
                hits = await ctx.tool(self.name, "knowledge_retrieval", knowledge_retrieval, query=q, destination=dest,
                                      types=("activity", "food"), k=6)
                for h in hits:
                    prev = cands.get(h["id"])
                    cands.setdefault(h["id"], _item(h))
                    sources.append({"id": h["id"], "name": h["name"], "source": h["source"], "score": h["score"], "query": q})
            # RAG is an enhancement, not a hard dependency. Complete the local
            # catalog so activities and meals remain available if embeddings fail.
            for t in ("activity", "food"):
                for p in await ctx.tool(self.name, "list_places", list_places, destination=dest, type_=t):
                    cands.setdefault(p["id"], _item(p))

            acts = [c for c in cands.values() if c.type == "activity"]
            foods = [c for c in cands.values() if c.type == "food"]
            if len(acts) < min(n_act, 6) or len(foods) < 3:       # decision: widen the search
                await ctx.emit("decision", self.name, "info", "Too few options retrieved; widening the search")
                for h in await ctx.tool(self.name, "knowledge_retrieval", knowledge_retrieval, query=f"popular {dest}",
                                        destination=dest, types=("activity", "food"), k=10):
                    cands.setdefault(h["id"], _item(h))
                    sources.append({"id": h["id"], "name": h["name"], "source": h["source"], "score": h["score"], "query": "widen"})
            kb = KB[dest]
            res = Research(destination=dest, overview=kb["overview"], best_season=kb["best_season"],
                           transport_info=kb["transport_info"], tips=kb["tips"], candidates=list(cands.values()),
                           sources=sources, disclaimer=DISCLAIMER)
            await ctx.emit("log", self.name, "ok",
                           f"Retrieved {len(res.candidates)} options. All prices are approximate knowledge-base estimates, not live prices.",
                           data={"counts": {t: sum(c.type == t for c in res.candidates) for t in ("hotel", "transport", "activity", "food")}})
            st.output = {"candidates": len(res.candidates), "sources": len(sources)}
            return res
