# UTC — Understand Terms and Conditions

A local AI-powered tool that converts legal T&C documents into plain-English summaries and side-by-side company comparisons.

---

## What it does

**Analyze tab** — submit any Terms and Conditions document via paste, PDF upload, or URL. The system returns:

- **TL;DR** — one sentence capturing the most important things to know
- **Overall risk** — red / yellow / green rating for the whole document
- **Rights you give up** — data sharing, IP grants, arbitration waivers
- **Your obligations** — what you must do or comply with
- **Your benefits** — what you actually get from the agreement
- **Unusual clauses** — anything non-standard or worth flagging
- **Citations** — every bullet links back to the verbatim original clause

**Compare tab** — load 2 or 3 companies and run a side-by-side comparison:

- Per-company user-friendliness score (0–100) with label
- Topic-by-topic breakdown table (Data Sharing, Arbitration, Auto-Renewal, IP Rights, etc.)
- Winner highlighted per topic
- One-paragraph comparison summary with a clear recommendation
- JSON export of the full comparison

---

## Tech stack

| Layer | Technology |
|---|---|
| LLM | OpenAI GPT-4o |
| Backend | FastAPI |
| Frontend | Streamlit |
| PDF extraction | pdfplumber |
| URL extraction | requests + BeautifulSoup4 |
| Data validation | Pydantic v2 |

---

## Project structure

```
UTC/
├── config.py               # model names, ports, chunk settings
├── schemas.py              # Pydantic models: Clause, AnalysisResult, RiskLevel
├── prompts.py              # LLM prompts: validator, chunk extractor, TL;DR, risk
├── extractor.py            # text / PDF / URL → plain text
├── preprocessor.py         # validate doc type + section-aware chunking
├── analyzer.py             # concurrent GPT-4o clause extraction per chunk
├── aggregator.py           # merge, deduplicate, rank, TL;DR, overall risk
├── comparison_schemas.py   # Pydantic models for comparison output
├── comparison_prompts.py   # topic alignment, scoring, summary prompts
├── comparator.py           # multi-company analysis + comparison orchestration
├── api.py                  # FastAPI: /analyze/text|pdf|url, /compare, /extract/pdf
├── ui.py                   # Streamlit UI: Analyze tab + Compare tab
├── .env.template           # copy to .env and add your OpenAI key
├── requirements.txt
└── Makefile
```

---

## Setup

**1. Clone and install**

```bash
git clone https://github.com/mitsmit/UTC.git
cd UTC
pip install -r requirements.txt
```

**2. Set your OpenAI API key**

```bash
cp .env.template .env
# open .env and replace sk-your-key-here with your actual key
```

**3. Run**

Open two terminals:

```bash
# Terminal 1 — API (port 8002)
make serve

# Terminal 2 — UI
make ui
```

The UI opens at `http://localhost:8501`.

---

## API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze/text` | Analyze pasted T&C text |
| `POST` | `/analyze/pdf` | Analyze uploaded PDF |
| `POST` | `/analyze/url` | Analyze T&C page from URL |
| `POST` | `/extract/pdf` | Extract raw text from PDF (used by Compare tab) |
| `POST` | `/compare` | Compare 2–3 companies |
| `GET` | `/health` | Liveness check |

---

## Analysis pipeline

```
Input (text / PDF / URL)
        │
        ▼
Validator — is this a T&C document?
        │
        ▼
Chunker — split by section headings (~3000 char chunks)
        │
        ▼
Analyzer — GPT-4o extracts clauses concurrently per chunk
           each clause: category + summary + risk + citation
        │
        ▼
Aggregator — deduplicate, rank by risk, generate TL;DR
        │
        ▼
Structured JSON response → Streamlit UI
```

---

## Notes

- Scanned PDFs (image-only) are not supported — use a text-based PDF.
- JavaScript-rendered pages may not extract correctly via URL; paste the text instead.
- Analysis of a typical T&C takes 20–40 seconds. Comparison of 3 companies takes 30–90 seconds.
- The `.env` file is excluded from version control — never commit your API key.
