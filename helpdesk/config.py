"""Central settings. Everything can be overridden with environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---- paths ------------------------------------------------------------------------------
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STRUCTURED_DIR = DATA_DIR / "structured"
MANIFEST = DATA_DIR / "manifest.csv"
CHROMA_DIR = Path(os.getenv("HELPDESK_CHROMA_DIR", str(ROOT / "vector_store")))
LOG_DIR = Path(os.getenv("HELPDESK_LOG_DIR", str(ROOT / "logs")))
UNANSWERED_LOG = LOG_DIR / "unanswered_questions.jsonl"
EMAIL_DRAFT_DIR = LOG_DIR / "email_drafts"
COLLECTION = "iitj_academic_docs"

# ---- models (served by Ollama) ----------------------------------------------------------
OLLAMA_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
# Chat model tag as known to Ollama. scripts/setup_ollama.sh creates the "helpdesk-*"
# variants (same weights, num_ctx raised to 8192, temperature 0.2).
CHAT_MODEL = os.getenv("HELPDESK_MODEL", "helpdesk-qwen3:8b")
EMBED_MODEL = os.getenv("HELPDESK_EMBED_MODEL", "nomic-embed-text")
TEMPERATURE = float(os.getenv("HELPDESK_TEMPERATURE", "0.2"))
# Qwen3 thinks before answering by default; that doubles latency on a laptop GPU and
# the <think> text sometimes leaks into tool arguments. "/no_think" switches it off.
QWEN_NO_THINK = os.getenv("HELPDESK_QWEN_NO_THINK", "1") == "1"

# ---- retrieval --------------------------------------------------------------------------
CHUNK_CHARS = int(os.getenv("HELPDESK_CHUNK_CHARS", "1100"))
CHUNK_OVERLAP = int(os.getenv("HELPDESK_CHUNK_OVERLAP", "180"))
TOP_K = int(os.getenv("HELPDESK_TOP_K", "5"))
# cosine similarity of the best dense hit below which we tell the agent "nothing relevant"
MIN_SIMILARITY = float(os.getenv("HELPDESK_MIN_SIMILARITY", "0.50"))
USE_BM25 = os.getenv("HELPDESK_USE_BM25", "1") == "1"

REFUSAL_TEXT = ("I don't know the answer to that from the academic documents I have access to. "
                "I have logged your question so that someone from the academic office can follow up.")
