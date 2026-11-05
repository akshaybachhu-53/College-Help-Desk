"""ChromaDB vector store + an in-memory BM25 index over the same chunks.

Hybrid retrieval matters for this corpus: questions often hinge on exact tokens
("RKA", "700-level", "Major", course codes) that dense 768-d embeddings blur, while
paraphrased questions ("can I skip classes") need the dense side. The two ranked lists
are merged with reciprocal-rank fusion (k = 60).
"""
from __future__ import annotations

import re
from functools import lru_cache

import chromadb

from helpdesk import config
from helpdesk.rag.documents import Chunk
from helpdesk.rag.embeddings import embed_documents, embed_query

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def build_index(chunks: list[Chunk], reset: bool = True) -> int:
    c = client()
    if reset:
        try:
            c.delete_collection(config.COLLECTION)
        except Exception:
            pass
    col = c.get_or_create_collection(config.COLLECTION, metadata={"hnsw:space": "cosine"})
    vectors = embed_documents([ch.text for ch in chunks])
    B = 200
    for i in range(0, len(chunks), B):
        part = chunks[i:i + B]
        col.add(ids=[ch.chunk_id for ch in part], documents=[ch.text for ch in part],
                metadatas=[ch.meta for ch in part], embeddings=vectors[i:i + B])
    _bm25.cache_clear()
    return col.count()


@lru_cache(maxsize=1)
def _collection():
    return client().get_collection(config.COLLECTION)


@lru_cache(maxsize=1)
def _bm25():
    from rank_bm25 import BM25Okapi
    data = _collection().get(include=["documents", "metadatas"])
    corpus = [_tokens(d) for d in data["documents"]]
    return BM25Okapi(corpus), data["ids"], data["documents"], data["metadatas"]


def search(query: str, k: int = config.TOP_K) -> tuple[list[dict], float]:
    """Return (hits, best_dense_similarity). Each hit: {id, text, meta, similarity, rank_sources}."""
    col = _collection()
    n_dense = max(k * 3, 12)
    res = col.query(query_embeddings=[embed_query(query)], n_results=n_dense,
                    include=["documents", "metadatas", "distances"])
    dense = [{"id": i, "text": d, "meta": m, "similarity": round(1 - dist, 3)}
             for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])]

    best = dense[0]["similarity"] if dense else 0.0
    if not config.USE_BM25:
        return dense[:k], best

    bm25, ids, docs, metas = _bm25()
    scores = bm25.get_scores(_tokens(query))
    top_sparse = sorted(range(len(ids)), key=lambda j: scores[j], reverse=True)[:n_dense]
    sparse = [{"id": ids[j], "text": docs[j], "meta": metas[j], "similarity": None}
              for j in top_sparse if scores[j] > 0]

    fused: dict[str, dict] = {}
    for lst, tag in ((dense, "dense"), (sparse, "bm25")):
        for rank, hit in enumerate(lst):
            entry = fused.setdefault(hit["id"], {**hit, "rrf": 0.0, "rank_sources": []})
            entry["rrf"] += 1.0 / (60 + rank + 1)
            entry["rank_sources"].append(tag)
            if hit["similarity"] is not None:
                entry["similarity"] = hit["similarity"]
    ranked = sorted(fused.values(), key=lambda h: h["rrf"], reverse=True)
    return ranked[:k], best
