"""Local embeddings through Ollama's /api/embed endpoint."""
from __future__ import annotations

import requests

from helpdesk import config

# nomic-embed-text was trained with task prefixes; without them retrieval quality drops noticeably.
_PREFIX = {"nomic-embed-text": ("search_document: ", "search_query: ")}


def _prefixes() -> tuple[str, str]:
    for name, pair in _PREFIX.items():
        if config.EMBED_MODEL.startswith(name):
            return pair
    return "", ""


def _embed(texts: list[str]) -> list[list[float]]:
    resp = requests.post(f"{config.OLLAMA_BASE}/api/embed",
                         json={"model": config.EMBED_MODEL, "input": texts}, timeout=300)
    resp.raise_for_status()
    return resp.json()["embeddings"]


def embed_documents(texts: list[str], batch: int = 32) -> list[list[float]]:
    doc_prefix, _ = _prefixes()
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        out.extend(_embed([doc_prefix + t for t in texts[i:i + batch]]))
    return out


def embed_query(text: str) -> list[float]:
    _, q_prefix = _prefixes()
    return _embed([q_prefix + text])[0]
