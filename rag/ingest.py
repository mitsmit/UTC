"""
Fetch, chunk, and embed HIPAA / GDPR / EU AI Act source texts.

Usage:
    python -m rag.ingest            # ingest all regulations
    python -m rag.ingest --reg gdpr # ingest one
"""

import argparse
import sys
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Each entry: slug, display name, source (URL or local PDF path under rag/data/)
REGULATIONS = [
    {
        "slug": "HIPAA",
        "name": "HIPAA",
        "source": "https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164",
        "type": "web",
    },
    {
        "slug": "GDPR",
        "name": "GDPR",
        "source": "https://gdpr-info.eu/",
        "type": "web",
    },
    {
        "slug": "EU_AI_ACT",
        "name": "EU AI Act",
        "source": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689",
        "type": "web",
    },
    {
        "slug": "CCPA",
        "name": "CCPA",
        "source": "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=20232024",
        "type": "web",
    },
]

CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150


def _load(reg: dict) -> list:
    """Load documents for one regulation; returns list of LangChain Documents."""
    data_dir = Path(__file__).parent / "data"
    local_pdf = data_dir / f"{reg['slug'].lower()}.pdf"

    if local_pdf.exists():
        print(f"  Loading from local PDF: {local_pdf}")
        loader = PyPDFLoader(str(local_pdf))
    elif reg["type"] == "pdf":
        print(f"  Downloading PDF: {reg['source']}")
        loader = PyPDFLoader(reg["source"])
    else:
        print(f"  Loading from web: {reg['source']}")
        loader = WebBaseLoader(reg["source"])

    docs = loader.load()
    # stamp every doc with regulation metadata
    for doc in docs:
        doc.metadata["regulation"] = reg["slug"]
        doc.metadata["regulation_name"] = reg["name"]
    return docs


def _chunk(docs: list) -> list:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
    )
    return splitter.split_documents(docs)


def ingest(slugs: list[str] | None = None) -> dict[str, list]:
    """
    Ingest one or more regulations. Returns {slug: [chunks]}.
    If slugs is None, ingests all.
    """
    targets = REGULATIONS
    if slugs:
        slugs_upper = [s.upper() for s in slugs]
        targets = [r for r in REGULATIONS if r["slug"] in slugs_upper]
        if not targets:
            raise ValueError(f"Unknown regulation(s): {slugs}. "
                             f"Valid: {[r['slug'] for r in REGULATIONS]}")

    result: dict[str, list] = {}
    for reg in targets:
        print(f"[ingest] {reg['name']} …")
        docs   = _load(reg)
        chunks = _chunk(docs)
        result[reg["slug"]] = chunks
        print(f"  → {len(docs)} pages, {len(chunks)} chunks")

    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reg", nargs="*", help="Regulation slugs to ingest (default: all)")
    args = ap.parse_args()

    from rag.store import upsert

    chunks_by_reg = ingest(args.reg)
    for slug, chunks in chunks_by_reg.items():
        print(f"[store] Upserting {len(chunks)} chunks for {slug} …")
        upsert(chunks)
    print("Done.")
