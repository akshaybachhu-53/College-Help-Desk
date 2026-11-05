"""Chunk every document in data/manifest.csv and (re)build the ChromaDB index.

Run:  python scripts/ingest.py           (needs `ollama serve` running and nomic-embed-text pulled)
      python scripts/ingest.py --dry-run (only chunk and print statistics, no embeddings)
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpdesk.rag.documents import chunk_document, load_manifest  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    chunks, missing, per_doc = [], [], Counter()
    for doc in load_manifest():
        if not doc.path.exists():
            missing.append(doc)
            continue
        cs = chunk_document(doc)
        per_doc[f"{doc.doc_id} {doc.filename}"] = len(cs)
        chunks.extend(cs)
    for k, v in per_doc.items():
        print(f"  {v:4d} chunks  {k}")
    if missing:
        print("\nMissing (run scripts/fetch_public_docs.py first):")
        for d in missing:
            print(f"  {d.doc_id} {d.filename}")
    print(f"\n{len(chunks)} chunks from {len(per_doc)} documents")
    if a.dry_run:
        return
    from helpdesk.rag.store import build_index
    n = build_index(chunks)
    print(f"Indexed {n} chunks into ChromaDB.")


if __name__ == "__main__":
    main()
