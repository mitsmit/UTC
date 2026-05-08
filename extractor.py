"""
Extract plain text from three input types:
  extract_from_text(text)  → str
  extract_from_pdf(bytes)  → str
  extract_from_url(url)    → str
"""

import io
import re

import pdfplumber
import requests
from bs4 import BeautifulSoup

import config

# Tags whose content is never useful for T&C analysis
_STRIP_TAGS = [
    "script", "style", "nav", "header", "footer",
    "aside", "form", "button", "iframe", "noscript",
]


def extract_from_text(text: str) -> str:
    return text.strip()


def extract_from_pdf(file_bytes: bytes) -> str:
    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())

    if not pages:
        raise ValueError(
            "No text could be extracted from this PDF. "
            "It may be a scanned image — please use a text-based PDF."
        )

    return "\n\n".join(pages)


def extract_from_url(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=config.REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (TC-Analyzer/1.0)"},
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ValueError(f"Request timed out after {config.REQUEST_TIMEOUT}s: {url}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Could not fetch URL: {e}")

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    # Prefer main content containers if present
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"(content|terms|policy|main)", re.I))
        or soup.find(class_=re.compile(r"(content|terms|policy|main)", re.I))
        or soup.body
    )

    if not main:
        raise ValueError("Could not extract content from this URL.")

    text = main.get_text(separator="\n")
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
