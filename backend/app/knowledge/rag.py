"""RAG layer: LangChain + ChromaDB + Sentence Transformers over the local knowledge base."""
from functools import lru_cache
from langchain_core.documents import Document
from ..config import get_settings
from .destinations import KB


@lru_cache
def _store():
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings
    s = get_settings()
    return Chroma(collection_name="travel_kb", persist_directory=s.chroma_dir,
                  embedding_function=HuggingFaceEmbeddings(model_name=s.embedding_model))


def _docs() -> tuple[list[Document], list[str]]:
    docs, ids = [], []
    for dest, d in KB.items():
        for kind, text in (("overview", d["overview"]), ("season", d["best_season"]),
                           ("transport_info", d["transport_info"]), ("tips", " ".join(d["tips"]))):
            docs.append(Document(page_content=f"{dest} {kind}: {text}",
                                 metadata=dict(destination=dest, type="info", kind=kind, iid=kind, name=kind)))
            ids.append(f"{dest}:{kind}")
        for n, it in enumerate(d["items"]):
            iid = f"{it['type'][0]}{n}"
            meta = dict(destination=dest, type=it["type"], kind="item", iid=iid, name=it["name"], cost=it["cost"],
                        desc=it["desc"], tags=it["tags"], area=it.get("area", ""), hours=float(it.get("hours", 0)),
                        cap=int(it.get("cap", 1)))
            docs.append(Document(page_content=f"{it['name']}. {it['desc']}. {it['tags']}. {dest}", metadata=meta))
            ids.append(f"{dest}:{iid}")
    return docs, ids


def build_index() -> int:
    """Idempotent: (re)indexes only when the stored count differs from the knowledge base."""
    docs, ids = _docs()
    store = _store()
    if store._collection.count() != len(docs):
        store._collection.delete(ids=store._collection.get()["ids"]) if store._collection.count() else None
        store.add_documents(docs, ids=ids)
    return len(docs)


def search(query: str, destination: str, type_: str, k: int = 6) -> list[tuple[dict, float]]:
    flt = {"$and": [{"destination": destination}, {"type": type_}]}
    return [(d.metadata, float(score)) for d, score in _store().similarity_search_with_score(query, k=k, filter=flt)]
