"""
Chroma vector store — one shared collection, filtered by regulation metadata.

Public API
----------
upsert(chunks)              — embed and store a list of LangChain Documents
retriever(slug, k=6)        — return a LangChain retriever filtered to one regulation
collection_stats()          — {slug: count} for each ingested regulation
is_ingested(slug) -> bool   — True if the slug has at least one chunk stored
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

import sys
import os
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

_PERSIST_DIR  = str(Path(__file__).parent / "data" / "chroma")
_COLLECTION   = "compliance_regulations"
_EMBED_MODEL  = "text-embedding-3-small"

_embeddings = OpenAIEmbeddings(
    model=_EMBED_MODEL,
    api_key=config.OPENAI_API_KEY,
)


def _store() -> Chroma:
    return Chroma(
        collection_name=_COLLECTION,
        embedding_function=_embeddings,
        persist_directory=_PERSIST_DIR,
    )


def upsert(chunks: list) -> int:
    """Embed and upsert documents. Returns number of chunks stored."""
    store = _store()
    store.add_documents(chunks)
    return len(chunks)


def retriever(slug: str, k: int = 6):
    """Return a retriever scoped to one regulation."""
    store = _store()
    return store.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": k,
            "filter": {"regulation": slug.upper()},
        },
    )


def collection_stats() -> dict[str, int]:
    """Return {regulation_slug: chunk_count} for everything in the store."""
    store   = _store()
    raw     = store.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for meta in raw.get("metadatas", []):
        slug = meta.get("regulation", "UNKNOWN")
        counts[slug] = counts.get(slug, 0) + 1
    return counts


def is_ingested(slug: str) -> bool:
    return collection_stats().get(slug.upper(), 0) > 0
