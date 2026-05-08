"""FastAPI backend. Run with: uvicorn api:app --reload --port 8001"""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import aggregator
import analyzer
import comparator
import extractor
import history
import preprocessor
from comparison_schemas import CompareRequest, ComparisonResult
from schemas import AnalyzeResponse, HistoryEntry

app = FastAPI(title="TermLens API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_pipeline(
    text: str,
    source: str,
    input_type: str = "text",
    input_label: str = "",
) -> AnalyzeResponse:
    if not preprocessor.validate(text):
        raise HTTPException(
            status_code=422,
            detail="This does not appear to be a Terms and Conditions document.",
        )

    chunks = preprocessor.chunk(text)
    raw_clauses = analyzer.analyze_chunks(chunks)
    result = aggregator.aggregate(raw_clauses, source=source)

    history.save(
        input_type=input_type,
        input_label=input_label or source,
        result=result.model_dump(),
    )

    return AnalyzeResponse(
        result=result,
        char_count=len(text),
        chunk_count=len(chunks),
    )


@app.post("/analyze/text", response_model=AnalyzeResponse)
def analyze_text(text: str = Form(...)) -> AnalyzeResponse:
    extracted = extractor.extract_from_text(text)
    if len(extracted) < 100:
        raise HTTPException(status_code=400, detail="Text is too short to analyze.")
    label = extracted[:80].replace("\n", " ") + "…"
    return _run_pipeline(extracted, source="Pasted text", input_type="text", input_label=label)


@app.post("/analyze/pdf", response_model=AnalyzeResponse)
async def analyze_pdf(file: UploadFile = File(...)) -> AnalyzeResponse:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    file_bytes = await file.read()
    try:
        extracted = extractor.extract_from_pdf(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _run_pipeline(extracted, source=file.filename, input_type="pdf",
                         input_label=file.filename)


@app.post("/analyze/url", response_model=AnalyzeResponse)
def analyze_url(url: str = Form(...)) -> AnalyzeResponse:
    try:
        extracted = extractor.extract_from_url(url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _run_pipeline(extracted, source=url, input_type="url", input_label=url)


@app.post("/extract/pdf")
async def extract_pdf(file: UploadFile = File(...)) -> dict:
    """Return raw extracted text from a PDF — used by the Compare tab in the UI."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    file_bytes = await file.read()
    try:
        text = extractor.extract_from_pdf(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"text": text, "filename": file.filename}


@app.post("/compare", response_model=ComparisonResult)
def compare(req: CompareRequest) -> ComparisonResult:
    if not (2 <= len(req.companies) <= 3):
        raise HTTPException(status_code=400, detail="Provide 2 or 3 companies to compare.")

    results = {}
    for entry in req.companies:
        name = entry.name.strip() or f"Company {len(results) + 1}"

        if entry.url:
            try:
                text = extractor.extract_from_url(entry.url)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"{name}: {e}")
        elif entry.text:
            text = entry.text.strip()
        else:
            raise HTTPException(status_code=400, detail=f"{name}: provide text or url.")

        if len(text) < 100:
            raise HTTPException(status_code=400, detail=f"{name}: text too short.")

        if not preprocessor.validate(text):
            raise HTTPException(
                status_code=422,
                detail=f"{name}: does not appear to be a T&C document.",
            )

        results[name] = comparator.analyze_company(name, text)

    return comparator.compare(results)


@app.get("/history", response_model=list[HistoryEntry])
def get_history() -> list[HistoryEntry]:
    return history.load()


@app.delete("/history/{entry_id}")
def delete_entry(entry_id: str) -> dict:
    if not history.delete(entry_id):
        raise HTTPException(status_code=404, detail="Entry not found.")
    return {"deleted": entry_id}


@app.delete("/history")
def clear_history() -> dict:
    count = history.clear()
    return {"cleared": count}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
