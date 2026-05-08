"""
Validate that input is a T&C document and chunk it into analysis-sized pieces.
"""

import re

from openai import OpenAI

import config
from prompts import VALIDATOR_PROMPT

_client = OpenAI(api_key=config.OPENAI_API_KEY)


def validate(text: str) -> bool:
    """Return True if the text looks like a T&C / legal agreement."""
    sample = text[:1000]
    response = _client.chat.completions.create(
        model=config.CHAT_MODEL,
        messages=[{"role": "user", "content": VALIDATOR_PROMPT.format(sample=sample)}],
        max_tokens=5,
        temperature=0.2,
    )
    answer = response.choices[0].message.content.strip().upper()
    return "YES" in answer


def _split_on_headings(text: str) -> list[str]:
    """Split on numbered sections, ALL-CAPS headings, or markdown headings."""
    pattern = re.compile(
        r"(?=(?:\n|^)"                      # start of line
        r"(?:"
        r"\d+[\.\)]\s+[A-Z]"               # 1. Heading or 1) Heading
        r"|[A-Z][A-Z\s]{4,}(?:\n|:)"       # ALL CAPS HEADING
        r"|#{1,3}\s"                        # ## Markdown heading
        r"))",
        re.MULTILINE,
    )
    parts = pattern.split(text)
    return [p.strip() for p in parts if p.strip()]


def chunk(text: str) -> list[str]:
    """
    Split T&C text into analysis-sized chunks.
    Tries section-based splitting first; falls back to character windows.
    """
    sections = _split_on_headings(text)

    # If sections are found and reasonable in size, use them
    if len(sections) > 2:
        chunks = []
        buffer = ""
        for section in sections:
            if len(buffer) + len(section) < config.CHUNK_SIZE:
                buffer += "\n\n" + section
            else:
                if buffer:
                    chunks.append(buffer.strip())
                buffer = section
        if buffer:
            chunks.append(buffer.strip())
        return chunks

    # Fallback: sliding window over characters
    chunks = []
    start = 0
    while start < len(text):
        end = start + config.CHUNK_SIZE
        # Avoid cutting mid-sentence — snap to last newline within window
        if end < len(text):
            snap = text.rfind("\n", start, end)
            if snap > start:
                end = snap
        chunks.append(text[start:end].strip())
        start = end - config.CHUNK_OVERLAP

    return [c for c in chunks if c]
