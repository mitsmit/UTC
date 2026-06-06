"""Streamlit UI — TermLens. Run with: streamlit run ui.py"""

import json
import threading
import time

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# ── Backend modules (called directly — no HTTP layer needed) ──────────────────
import aggregator
import analyzer
import comparator
from comparator import ComparisonCancelled
import extractor
import history
import preprocessor
from schemas import AnalyzeResponse
from rag import graph as rag_graph
from rag import store as rag_store
from rag.ingest import REGULATIONS as RAG_REGULATIONS

# ── design tokens ─────────────────────────────────────────────────────────────
RISK = {
    "red":     {"icon": "🔴", "label": "High risk",      "border": "#e53935", "bg": "#fdecea", "tag_bg": "#fdecea", "tag_fg": "#b71c1c"},
    "yellow":  {"icon": "🟡", "label": "Moderate",       "border": "#f9a825", "bg": "#fff8e1", "tag_bg": "#fff8e1", "tag_fg": "#7b5800"},
    "green":   {"icon": "🟢", "label": "User-friendly",  "border": "#43a047", "bg": "#e8f5e9", "tag_bg": "#e8f5e9", "tag_fg": "#1b5e20"},
    "unusual": {"icon": "⚠️", "label": "Unusual",        "border": "#7b1fa2", "bg": "#f3e5f5", "tag_bg": "#f3e5f5", "tag_fg": "#4a148c"},
}
SCORE_COLOR = {
    "Aggressive":    "#e53935",
    "Mixed":         "#f9a825",
    "Fair":          "#1976d2",
    "User-friendly": "#43a047",
}
INPUT_ICON = {"url": "🔗", "pdf": "📄", "text": "📝"}

st.set_page_config(page_title="TermLens", page_icon="🔍", layout="wide")

# ── global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.4rem !important; padding-bottom: 2rem !important; }
  .clause-card { border-radius: 6px; padding: 11px 15px; margin-bottom: 8px; line-height: 1.5; }
  .clause-card .clause-text { font-size: 0.96em; font-weight: 500; }
  .unusual-tag {
      font-size: 0.73em; font-weight: 600; letter-spacing: 0.03em;
      padding: 2px 7px; border-radius: 3px; margin-left: 8px; vertical-align: middle;
  }
  .section-title {
      font-size: 1.05em; font-weight: 700;
      margin: 0 0 14px 0; padding-bottom: 8px; border-bottom: 2px solid;
  }
  .topic-row { padding: 8px 4px; border-bottom: 1px solid #f0f0f0; font-size: 0.93em; }
  .score-card { text-align: center; padding: 18px 10px; border-radius: 10px; border: 2px solid; }
  .data-tag {
      display: inline-block; font-size: 0.68em; font-weight: 700; letter-spacing: 0.04em;
      padding: 2px 7px; border-radius: 10px; margin-left: 7px;
      background: #e3f2fd; color: #0d47a1; vertical-align: middle; text-transform: uppercase;
  }
</style>
""", unsafe_allow_html=True)

# ── session state defaults ────────────────────────────────────────────────────
for _k, _v in {
    "cmp_running":        False,
    "cmp_result":         None,
    "cmp_error":          None,
    "cmp_cancelled":      False,
    "num_companies":      2,
    "analyze_running":    False,
    "analyze_result":     None,
    "analyze_error":      None,
    "analyze_cancelled":  False,
    "comply_running":     False,
    "comply_result":      None,
    "comply_error":       None,
    "comply_cancelled":   False,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── module-level cancel flags ─────────────────────────────────────────────────
_cmp_cancel     = threading.Event()
_analyze_cancel = threading.Event()
_comply_cancel  = threading.Event()

# ── auto-load last analysis on first run ──────────────────────────────────────
if "_last_analysis" not in st.session_state:
    data = history.load_last_analysis()
    if data:
        st.session_state["_last_analysis"] = data

_DATA_TOPIC_ICON = {
    "collection": "📥", "processing": "⚙️", "sharing": "🔗",
    "retention": "🗓", "transfers": "🌍", "third_party": "🤝",
    "liability": "⚖️", "arbitration": "🔨", "security": "🔒",
    "ai_training": "🤖", "monetization": "💰", "consent": "✅",
}


# ── Pipeline (replaces the FastAPI _run_pipeline) ─────────────────────────────

def _run_pipeline(text: str, source: str,
                  input_type: str = "text", input_label: str = "") -> dict:
    if _analyze_cancel.is_set():
        raise ValueError("Analysis cancelled.")
    if not preprocessor.validate(text):
        raise ValueError("This does not appear to be a Terms and Conditions document.")
    if _analyze_cancel.is_set():
        raise ValueError("Analysis cancelled.")
    chunks     = preprocessor.chunk(text)
    if _analyze_cancel.is_set():
        raise ValueError("Analysis cancelled.")
    raw        = analyzer.analyze_chunks(chunks)
    if _analyze_cancel.is_set():
        raise ValueError("Analysis cancelled.")
    result     = aggregator.aggregate(raw, source=source)
    result_d   = result.model_dump()
    history.save(input_type=input_type,
                 input_label=input_label or source,
                 result=result_d)
    response = AnalyzeResponse(result=result,
                               char_count=len(text),
                               chunk_count=len(chunks))
    history.save_last_analysis(response.model_dump())
    return response.model_dump()


def _run_analysis_thread(action_fn) -> None:
    try:
        result = action_fn()
        if not _analyze_cancel.is_set():
            st.session_state.analyze_result = result
        else:
            st.session_state.analyze_cancelled = True
    except ValueError as e:
        if _analyze_cancel.is_set() or "cancelled" in str(e).lower():
            st.session_state.analyze_cancelled = True
        else:
            st.session_state.analyze_error = str(e)
    except Exception as e:
        st.session_state.analyze_error = f"Unexpected error: {e}"
    finally:
        st.session_state.analyze_running = False


def _run_compliance_thread(tc_text: str, tc_source: str, regulations: list[str]) -> None:
    try:
        report = rag_graph.run(tc_text, tc_source, regulations)
        if not _comply_cancel.is_set():
            st.session_state.comply_result = report
        else:
            st.session_state.comply_cancelled = True
    except Exception as e:
        if _comply_cancel.is_set():
            st.session_state.comply_cancelled = True
        else:
            st.session_state.comply_error = str(e)
    finally:
        st.session_state.comply_running = False


# ═════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def risk_banner(risk: str, tldr: str) -> None:
    r = RISK[risk]
    st.markdown(f"""
    <div style="background:{r['bg']};border-left:5px solid {r['border']};
    padding:16px 20px;border-radius:8px;margin-bottom:4px;">
      <div style="font-size:0.85em;font-weight:700;color:{r['border']};
      text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">
        {r['icon']} Overall risk — {r['label']}
      </div>
      <div style="font-size:1.02em;color:#212529">{tldr}</div>
    </div>""", unsafe_allow_html=True)


def render_section(title: str, risk_key: str, clauses: list[dict]) -> None:
    r     = RISK[risk_key]
    count = len(clauses)
    count_badge = (
        f"<span style='background:{r['border']};color:#fff;font-size:0.7em;"
        f"font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;"
        f"vertical-align:middle'>{count}</span>" if count else ""
    )
    items_html = ""
    for c in clauses:
        unusual = (
            "<span style='background:#fff3cd;color:#7b5800;font-size:0.7em;"
            "font-weight:700;padding:1px 7px;border-radius:3px;margin-left:7px;"
            "vertical-align:middle'>⚠ Unusual</span>" if c.get("unusual") else ""
        )
        dt = c.get("data_topic")
        data_tag = (
            f"<span class='data-tag'>{_DATA_TOPIC_ICON.get(dt, '🔒')} {dt.replace('_', ' ')}</span>"
            if dt else ""
        )

        def _chips(items: list, color: str) -> str:
            return "".join(
                f"<span style='display:inline-block;background:{color};border-radius:10px;"
                f"padding:1px 8px;font-size:0.7em;margin:2px 3px 2px 0;"
                f"color:#333;white-space:nowrap'>{v}</span>"
                for v in items
            )

        entity_rows = []
        if c.get("data_types"):
            entity_rows.append(f"<span style='font-size:0.7em;color:#666;font-weight:600'>Data:</span> "
                               f"{_chips(c['data_types'], '#e3f2fd')}")
        if c.get("purposes"):
            entity_rows.append(f"<span style='font-size:0.7em;color:#666;font-weight:600'>Purpose:</span> "
                               f"{_chips(c['purposes'], '#e8f5e9')}")
        if c.get("actors"):
            entity_rows.append(f"<span style='font-size:0.7em;color:#666;font-weight:600'>Actors:</span> "
                               f"{_chips(c['actors'], '#f3e5f5')}")
        if c.get("legal_constructs"):
            entity_rows.append(f"<span style='font-size:0.7em;color:#666;font-weight:600'>Legal:</span> "
                               f"{_chips(c['legal_constructs'], '#fff3e0')}")
        if c.get("retention_duration"):
            entity_rows.append(
                f"<span style='font-size:0.7em;color:#666;font-weight:600'>Retention:</span> "
                f"<span style='display:inline-block;background:#fce4ec;border-radius:10px;"
                f"padding:1px 8px;font-size:0.7em;color:#333'>🗓 {c['retention_duration']}</span>"
            )
        if c.get("consent_mechanism"):
            consent_color = {"opt-in": "#e8f5e9", "opt-out": "#fdecea",
                             "implied": "#fff8e1", "none": "#f5f5f5"}.get(
                c["consent_mechanism"], "#f5f5f5")
            entity_rows.append(
                f"<span style='font-size:0.7em;color:#666;font-weight:600'>Consent:</span> "
                f"<span style='display:inline-block;background:{consent_color};border-radius:10px;"
                f"padding:1px 8px;font-size:0.7em;color:#333'>✅ {c['consent_mechanism']}</span>"
            )
        if c.get("monetization_signal"):
            entity_rows.append(
                "<span style='display:inline-block;background:#fdecea;border-radius:10px;"
                "padding:1px 8px;font-size:0.7em;color:#b71c1c;font-weight:700'>"
                "💰 Monetization signal</span>"
            )

        entities_html = (
            f"<div style='margin-top:6px;line-height:2'>" + "<br>".join(entity_rows) + "</div>"
        ) if entity_rows else ""

        citation_html = ""
        if c.get("citation"):
            escaped = (c["citation"].replace("&", "&amp;")
                       .replace("<", "&lt;").replace(">", "&gt;"))
            citation_html = (
                f"<details style='margin-top:5px'>"
                f"<summary style='font-size:0.74em;color:#888;cursor:pointer;"
                f"user-select:none;list-style:none'>📌 Original clause</summary>"
                f"<div style='margin-top:4px;padding:6px 9px;background:#f8f9fa;"
                f"border-radius:4px;font-size:0.76em;font-family:monospace;"
                f"white-space:pre-wrap;color:#444;line-height:1.45'>{escaped}</div>"
                f"</details>"
            )
        items_html += (
            f"<div style='background:{r['bg']};border-left:3px solid {r['border']};"
            f"border-radius:0 5px 5px 0;padding:9px 12px;margin-bottom:7px;'>"
            f"<div style='font-size:0.88em;font-weight:500;color:#212529;line-height:1.45'>"
            f"{c['summary']}{unusual}{data_tag}</div>"
            f"{entities_html}{citation_html}</div>"
        )

    if not items_html:
        items_html = (
            "<div style='color:#bbb;font-size:0.85em;padding:12px 0;text-align:center'>"
            "None identified</div>"
        )

    st.markdown(
        f"<div style='border:1px solid #e0e0e0;border-radius:10px;padding:16px;background:#fff;'>"
        f"<div style='font-size:0.93em;font-weight:700;color:{r['border']};"
        f"padding-bottom:10px;margin-bottom:12px;border-bottom:2px solid {r['border']}'>"
        f"{r['icon']} {title}{count_badge}</div>"
        f"<div style='max-height:580px;overflow-y:auto;padding-right:3px'>"
        f"{items_html}</div></div>",
        unsafe_allow_html=True,
    )


def meta_pills(char_count: int, chunk_count: int, source: str) -> None:
    src = source[:50] + ("…" if len(source) > 50 else "")
    st.markdown(
        f"<div style='display:flex;gap:10px;margin:10px 0 18px 0;flex-wrap:wrap'>"
        f"<span style='background:#f1f3f4;border-radius:20px;padding:4px 12px;"
        f"font-size:0.83em;color:#555'>📏 {char_count:,} characters</span>"
        f"<span style='background:#f1f3f4;border-radius:20px;padding:4px 12px;"
        f"font-size:0.83em;color:#555'>🧩 {chunk_count} sections</span>"
        f"<span style='background:#f1f3f4;border-radius:20px;padding:4px 12px;"
        f"font-size:0.83em;color:#555'>📂 {src}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# HEADER
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style="margin-bottom:1.2rem">
  <span style="font-size:2em;font-weight:800;letter-spacing:-0.02em">🔍 TermLens</span>
  <span style="font-size:0.97em;color:#666;margin-left:14px">
    Paste, upload, or link any Terms &amp; Conditions — get a plain-English breakdown.
  </span>
</div>
""", unsafe_allow_html=True)

main_tab, compare_tab, comply_tab, history_tab = st.tabs(
    ["🔍 Analyze", "📊 Compare", "🛡 Compliance", "📜 History"]
)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — ANALYZE
# ═════════════════════════════════════════════════════════════════════════════
with main_tab:

    with st.container(border=True):
        input_url, input_text, input_pdf = st.tabs(
            ["🔗 Enter URL", "📝 Paste Text", "📄 Upload PDF"]
        )
        submitted = False
        _action   = None   # callable set per input type

        with input_text:
            pasted = st.text_area("", height=220,
                                  placeholder="Paste the full Terms and Conditions text here…",
                                  label_visibility="collapsed")
            if st.button("Analyze Text", type="primary", use_container_width=True, key="btn_text"):
                if not pasted.strip():
                    st.warning("Please paste some text first.")
                else:
                    submitted = True
                    _text_val = pasted

                    def _action():
                        txt   = extractor.extract_from_text(_text_val)
                        if len(txt) < 100:
                            raise ValueError("Text is too short to analyze.")
                        label = txt[:80].replace("\n", " ") + "…"
                        return _run_pipeline(txt, source="Pasted text",
                                             input_type="text", input_label=label)

        with input_pdf:
            uploaded = st.file_uploader("", type=["pdf"], key="single_pdf",
                                        label_visibility="collapsed")
            if st.button("Analyze PDF", type="primary", use_container_width=True, key="btn_pdf"):
                if not uploaded:
                    st.warning("Please upload a PDF file first.")
                else:
                    submitted    = True
                    _pdf_bytes   = uploaded.read()
                    _pdf_name    = uploaded.name

                    def _action():
                        txt = extractor.extract_from_pdf(_pdf_bytes)
                        return _run_pipeline(txt, source=_pdf_name,
                                             input_type="pdf", input_label=_pdf_name)

        with input_url:
            url_input = st.text_input("", placeholder="https://example.com/terms",
                                      label_visibility="collapsed")
            if st.button("Analyze URL", type="primary", use_container_width=True, key="btn_url"):
                if not url_input.strip():
                    st.warning("Please enter a URL first.")
                else:
                    submitted = True
                    _url_val  = url_input.strip()

                    def _action():
                        txt = extractor.extract_from_url(_url_val)
                        return _run_pipeline(txt, source=_url_val,
                                             input_type="url", input_label=_url_val)

    if submitted and _action and not st.session_state.analyze_running:
        _analyze_cancel.clear()
        st.session_state.analyze_running   = True
        st.session_state.analyze_result    = None
        st.session_state.analyze_error     = None
        st.session_state.analyze_cancelled = False
        _analyze_thread = threading.Thread(
            target=_run_analysis_thread,
            args=(_action,), daemon=True,
        )
        add_script_run_ctx(_analyze_thread)
        _analyze_thread.start()
        st.rerun()

    if st.session_state.analyze_running:
        info_col, stop_col = st.columns([6, 1])
        with info_col:
            st.info("⏳ Analyzing… this may take 20–40 seconds for long documents.")
        with stop_col:
            if st.button("⏹ Stop", key="btn_stop_analyze", type="secondary",
                         use_container_width=True):
                _analyze_cancel.set()
                st.session_state.analyze_running   = False
                st.session_state.analyze_cancelled = True
                st.rerun()
        time.sleep(2)
        st.rerun()

    if st.session_state.analyze_cancelled:
        st.warning("⏹ Analysis stopped.")
        st.session_state.analyze_cancelled = False

    if st.session_state.analyze_error:
        st.error(st.session_state.analyze_error)
        st.session_state.analyze_error = None

    if st.session_state.analyze_result:
        st.session_state["_last_analysis"] = st.session_state.analyze_result
        st.session_state.analyze_result = None
        st.rerun()

    if "_last_analysis" in st.session_state:
        data   = st.session_state["_last_analysis"]
        result = data["result"]
        risk   = result["overall_risk"]

        st.markdown("---")
        risk_banner(risk, result["tldr"])
        meta_pills(data["char_count"], data["chunk_count"], result["source"])

        c1, c2, c3, c4 = st.columns(4, gap="medium")
        with c1:
            render_section("Rights You Give Up", "red",     result["rights_given_up"])
        with c2:
            render_section("Your Obligations",   "yellow",  result["obligations"])
        with c3:
            render_section("Your Benefits",      "green",   result["benefits"])
        with c4:
            render_section("Unusual Clauses",    "unusual", result["unusual_clauses"])

        st.markdown("")
        st.download_button(
            "⬇  Download analysis (JSON)",
            json.dumps(result, indent=2),
            "tc_analysis.json", "application/json",
        )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMPARE
# ═════════════════════════════════════════════════════════════════════════════
with compare_tab:
    st.markdown(
        "<div style='font-size:1.05em;font-weight:600;margin-bottom:6px'>"
        "Compare up to 3 companies side by side</div>",
        unsafe_allow_html=True,
    )
    st.caption("For each company enter a name, then paste text, upload a PDF, or provide a URL.")

    add_col, rem_col, _ = st.columns([1, 1, 5])
    with add_col:
        if st.session_state.num_companies < 3:
            if st.button("＋ Add company", use_container_width=True):
                st.session_state.num_companies += 1
                st.rerun()
    with rem_col:
        if st.session_state.num_companies > 2:
            if st.button("－ Remove", use_container_width=True):
                st.session_state.num_companies -= 1
                st.rerun()

    st.markdown("")
    company_inputs = []
    slot_cols = st.columns(st.session_state.num_companies, gap="medium")
    labels    = ["🅐 Company 1", "🅑 Company 2", "🅒 Company 3"]

    for idx, col in enumerate(slot_cols):
        with col:
            with st.container(border=True):
                st.markdown(
                    f"<div style='font-weight:700;font-size:1em;margin-bottom:8px'>"
                    f"{labels[idx]}</div>", unsafe_allow_html=True,
                )
                name = st.text_input("Company name", key=f"cmp_name_{idx}",
                                     placeholder="e.g. Spotify",
                                     label_visibility="collapsed")
                st.caption("Company name")
                mode = st.radio("Input via", ["Paste text", "Upload PDF", "URL"],
                                key=f"cmp_mode_{idx}", horizontal=True,
                                label_visibility="collapsed")
                cmp_text = cmp_url = None

                if mode == "Paste text":
                    cmp_text = st.text_area("Paste T&C", height=180,
                                            key=f"cmp_text_{idx}",
                                            placeholder="Paste full T&C text…",
                                            label_visibility="collapsed")
                elif mode == "Upload PDF":
                    pdf_file = st.file_uploader("Upload PDF", type=["pdf"],
                                                key=f"cmp_pdf_{idx}",
                                                label_visibility="collapsed")
                    if pdf_file:
                        with st.spinner("Extracting…"):
                            try:
                                cmp_text = extractor.extract_from_pdf(pdf_file.read())
                                st.success(f"✓ {len(cmp_text):,} characters extracted")
                            except Exception as e:
                                st.error(str(e))
                elif mode == "URL":
                    cmp_url = st.text_input("T&C URL", key=f"cmp_url_{idx}",
                                            placeholder="https://…/terms",
                                            label_visibility="collapsed")

                company_inputs.append({"name": name, "text": cmp_text, "url": cmp_url})

    st.markdown("")

    def _run_comparison_thread(companies: list[dict]) -> None:
        try:
            results = {}
            for entry in companies:
                if _cmp_cancel.is_set():
                    st.session_state.cmp_cancelled = True
                    return

                name = entry["name"].strip() or f"Company {len(results) + 1}"
                if entry.get("url"):
                    text = extractor.extract_from_url(entry["url"])
                else:
                    text = entry["text"].strip()

                if not preprocessor.validate(text):
                    st.session_state.cmp_error = f"{name}: does not appear to be a T&C document."
                    return

                results[name] = comparator.analyze_company(name, text)

            if _cmp_cancel.is_set():
                st.session_state.cmp_cancelled = True
                return

            st.session_state.cmp_result = comparator.compare(
                results, is_cancelled=_cmp_cancel.is_set
            ).model_dump()

        except ComparisonCancelled:
            st.session_state.cmp_cancelled = True
        except Exception as e:
            st.session_state.cmp_error = str(e)
        finally:
            st.session_state.cmp_running = False

    btn_col, stop_col = st.columns([5, 1])
    with btn_col:
        run_compare = st.button("🔍 Run Comparison", type="primary",
                                use_container_width=True,
                                disabled=st.session_state.cmp_running)
    with stop_col:
        stop_pressed = st.button("⏹ Stop", use_container_width=True,
                                 disabled=not st.session_state.cmp_running,
                                 type="secondary")

    if stop_pressed and st.session_state.cmp_running:
        _cmp_cancel.set()
        st.session_state.cmp_cancelled = True
        st.session_state.cmp_running   = False

    if run_compare and not st.session_state.cmp_running:
        errors = []
        for i, c in enumerate(company_inputs):
            if not c["name"].strip():
                errors.append(f"Company {i+1}: enter a name.")
            if not c["text"] and not c["url"]:
                errors.append(f"Company {i+1}: provide text, PDF, or URL.")
        if errors:
            for e in errors:
                st.warning(e)
        else:
            _cmp_cancel.clear()
            st.session_state.cmp_running   = True
            st.session_state.cmp_result    = None
            st.session_state.cmp_error     = None
            st.session_state.cmp_cancelled = False
            _cmp_thread = threading.Thread(
                target=_run_comparison_thread,
                args=(company_inputs,), daemon=True,
            )
            add_script_run_ctx(_cmp_thread)
            _cmp_thread.start()
            st.rerun()

    if st.session_state.cmp_running:
        st.info("⏳ Comparing companies… this may take 30–90 seconds. Hit Stop to cancel.")
        time.sleep(2)
        st.rerun()

    if st.session_state.cmp_cancelled:
        st.warning("⏹ Comparison stopped.")
        st.session_state.cmp_cancelled = False

    if st.session_state.cmp_error:
        st.error(f"Comparison failed: {st.session_state.cmp_error}")
        st.session_state.cmp_error = None

    cr = st.session_state.cmp_result
    if cr:
        companies = cr["companies"]
        scores    = {s["company"]: s for s in cr["scores"]}
        winner    = cr["overall_winner"]

        st.markdown("---")
        st.markdown(
            f"<div style='background:#e8f5e9;border-left:5px solid #43a047;"
            f"padding:16px 20px;border-radius:8px;margin-bottom:20px'>"
            f"<div style='font-size:0.82em;font-weight:700;color:#2e7d32;"
            f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px'>"
            f"✅ Best choice</div>"
            f"<div style='font-size:1.1em;font-weight:700;color:#1b5e20'>{winner}</div>"
            f"<div style='font-size:0.95em;color:#2e7d32;margin-top:4px'>{cr['summary']}</div>"
            f"</div>", unsafe_allow_html=True,
        )

        st.markdown(
            "<div style='font-weight:700;font-size:1.05em;margin-bottom:12px'>"
            "User-friendliness scores</div>", unsafe_allow_html=True,
        )
        score_cols = st.columns(len(companies), gap="medium")
        for col, company in zip(score_cols, companies):
            s         = scores.get(company, {})
            score_val = s.get("score", 0)
            label     = s.get("label", "")
            color     = SCORE_COLOR.get(label, "#888")
            crown     = " 👑" if company == winner else ""
            with col:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='text-align:center;padding:8px 0'>"
                        f"<div style='font-size:1em;font-weight:700'>{company}{crown}</div>"
                        f"<div style='font-size:2.4em;font-weight:800;color:{color};line-height:1.2'>{score_val}</div>"
                        f"<div style='font-size:0.82em;color:{color};font-weight:600'>{label}</div>"
                        f"<div style='background:#eee;border-radius:4px;margin-top:8px;height:8px'>"
                        f"<div style='width:{score_val}%;background:{color};height:8px;border-radius:4px'></div>"
                        f"</div></div>", unsafe_allow_html=True,
                    )

        st.markdown("")
        with st.container(border=True):
            st.markdown(
                "<div style='font-weight:700;font-size:1.05em;margin-bottom:14px'>"
                "Topic-by-topic breakdown</div>", unsafe_allow_html=True,
            )
            hcols = st.columns([2] + [2] * len(companies))
            hcols[0].markdown("**Topic**")
            for i, company in enumerate(companies):
                hcols[i + 1].markdown(f"**{company}**")
            st.divider()

            for row_idx, topic in enumerate(cr["topics"]):
                row_bg = "#f8f9fa" if row_idx % 2 == 0 else "#ffffff"
                tcols  = st.columns([2] + [2] * len(companies))
                tcols[0].markdown(
                    f"<div style='background:{row_bg};padding:6px 4px;border-radius:4px;"
                    f"font-weight:600;font-size:0.93em'>{topic['topic']}</div>",
                    unsafe_allow_html=True,
                )
                for i, company in enumerate(companies):
                    stance  = topic["stances"].get(company, {})
                    risk    = stance.get("risk", "yellow")
                    summary = stance.get("summary", "No information")
                    present = stance.get("present", True)
                    crown   = " 👑" if stance.get("winner") else ""
                    icon    = RISK.get(risk, RISK["yellow"])["icon"]
                    text    = "🟢 Not present" if not present else f"{icon} {summary}"
                    tcols[i + 1].markdown(
                        f"<div style='background:{row_bg};padding:6px 4px;border-radius:4px;"
                        f"font-size:0.88em'>{text}{crown}</div>", unsafe_allow_html=True,
                    )

        st.markdown("")
        st.download_button(
            "⬇  Download comparison (JSON)",
            json.dumps(cr, indent=2),
            "tc_comparison.json", "application/json",
        )


# ═════════════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — COMPLIANCE
# ═════════════════════════════════════════════════════════════════════════════

_STATUS_STYLE = {
    "COMPLIANT": {"bg": "#e8f5e9", "border": "#43a047", "fg": "#1b5e20", "icon": "✅"},
    "GAP":       {"bg": "#fdecea", "border": "#e53935", "fg": "#b71c1c", "icon": "🔴"},
    "PARTIAL":   {"bg": "#fff8e1", "border": "#f9a825", "fg": "#7b5800", "icon": "🟡"},
    "N/A":       {"bg": "#f5f5f5", "border": "#bdbdbd", "fg": "#616161", "icon": "➖"},
}
_SEVERITY_COLOR = {"HIGH": "#e53935", "MEDIUM": "#f9a825", "LOW": "#66bb6a"}

with comply_tab:
    st.markdown(
        "<div style='font-size:1.05em;font-weight:600;margin-bottom:4px'>"
        "Check a T&amp;C for compliance with HIPAA, GDPR, and the EU AI Act</div>",
        unsafe_allow_html=True,
    )
    st.caption("Paste text, upload a PDF, or enter a URL — then select which regulations to check.")

    # ── ingestion status ───────────────────────────────────────────────────────
    with st.expander("📦 Regulation index status", expanded=False):
        try:
            stats = rag_store.collection_stats()
        except Exception:
            stats = {}
        for reg in RAG_REGULATIONS:
            slug  = reg["slug"]
            count = stats.get(slug, 0)
            if count:
                st.success(f"✅ {reg['name']} — {count:,} chunks indexed")
            else:
                st.warning(
                    f"⚠️ {reg['name']} — not yet indexed. "
                    f"Run: `python -m rag.ingest --reg {slug}`"
                )

    st.markdown("")

    # ── input ──────────────────────────────────────────────────────────────────
    with st.container(border=True):
        cy_url, cy_text, cy_pdf = st.tabs(["🔗 Enter URL", "📝 Paste Text", "📄 Upload PDF"])
        cy_submitted = False
        _cy_text_val = _cy_source = None

        with cy_url:
            cy_url_val = st.text_input("", placeholder="https://example.com/terms",
                                       key="cy_url_input", label_visibility="collapsed")
            if st.button("Check URL", type="primary", use_container_width=True, key="cy_btn_url"):
                if not cy_url_val.strip():
                    st.warning("Please enter a URL.")
                else:
                    cy_submitted  = True
                    _cy_text_val  = extractor.extract_from_url(cy_url_val.strip())
                    _cy_source    = cy_url_val.strip()

        with cy_text:
            cy_pasted = st.text_area("", height=200, key="cy_paste",
                                     placeholder="Paste full T&C text here…",
                                     label_visibility="collapsed")
            if st.button("Check Text", type="primary", use_container_width=True, key="cy_btn_text"):
                if not cy_pasted.strip():
                    st.warning("Please paste some text.")
                else:
                    cy_submitted = True
                    _cy_text_val = extractor.extract_from_text(cy_pasted)
                    _cy_source   = (_cy_text_val[:60].replace("\n", " ") + "…")

        with cy_pdf:
            cy_upload = st.file_uploader("", type=["pdf"], key="cy_pdf",
                                         label_visibility="collapsed")
            if st.button("Check PDF", type="primary", use_container_width=True, key="cy_btn_pdf"):
                if not cy_upload:
                    st.warning("Please upload a PDF.")
                else:
                    cy_submitted = True
                    _cy_text_val = extractor.extract_from_pdf(cy_upload.read())
                    _cy_source   = cy_upload.name

    # ── regulation selector ────────────────────────────────────────────────────
    st.markdown("")
    sel_cols = st.columns(3)
    sel_regs = []
    for i, reg in enumerate(RAG_REGULATIONS):
        with sel_cols[i]:
            if st.checkbox(reg["name"], value=True, key=f"cy_sel_{reg['slug']}"):
                sel_regs.append(reg["slug"])

    # ── launch / cancel ────────────────────────────────────────────────────────
    if cy_submitted and _cy_text_val and sel_regs and not st.session_state.comply_running:
        _comply_cancel.clear()
        st.session_state.comply_running   = True
        st.session_state.comply_result    = None
        st.session_state.comply_error     = None
        st.session_state.comply_cancelled = False
        _comply_thread = threading.Thread(
            target=_run_compliance_thread,
            args=(_cy_text_val, _cy_source, sel_regs),
            daemon=True,
        )
        add_script_run_ctx(_comply_thread)
        _comply_thread.start()
        st.rerun()
    elif cy_submitted and not sel_regs:
        st.warning("Select at least one regulation.")

    if st.session_state.comply_running:
        info_col, stop_col = st.columns([6, 1])
        with info_col:
            st.info("⏳ Running compliance check… this may take 30–90 seconds.")
        with stop_col:
            if st.button("⏹ Stop", key="cy_stop", type="secondary", use_container_width=True):
                _comply_cancel.set()
                st.session_state.comply_running   = False
                st.session_state.comply_cancelled = True
                st.rerun()
        time.sleep(2)
        st.rerun()

    if st.session_state.comply_cancelled:
        st.warning("⏹ Compliance check stopped.")
        st.session_state.comply_cancelled = False

    if st.session_state.comply_error:
        st.error(f"Compliance check failed: {st.session_state.comply_error}")
        st.session_state.comply_error = None

    # ── results ────────────────────────────────────────────────────────────────
    cr = st.session_state.comply_result
    if cr:
        overall = cr.get("overall", "N/A")
        os_     = _STATUS_STYLE.get(overall, _STATUS_STYLE["N/A"])

        st.markdown("---")
        st.markdown(
            f"<div style='background:{os_['bg']};border-left:5px solid {os_['border']};"
            f"padding:16px 20px;border-radius:8px;margin-bottom:20px'>"
            f"<div style='font-size:0.82em;font-weight:700;color:{os_['border']};"
            f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px'>"
            f"{os_['icon']} Overall — {overall}</div>"
            f"<div style='font-size:1em;color:#212529'>{cr.get('summary','')}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        for reg_result in cr.get("regulations", []):
            slug   = reg_result.get("regulation", "")
            status = reg_result.get("status", "N/A")
            rs     = _STATUS_STYLE.get(status, _STATUS_STYLE["N/A"])
            gaps   = reg_result.get("gaps", [])
            n_gaps = sum(1 for g in gaps if g.get("status") in ("GAP", "PARTIAL"))

            badge = (
                f"<span style='background:{rs['border']};color:#fff;font-size:0.7em;"
                f"font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px'>"
                f"{status}</span>"
            )
            gap_badge = (
                f"<span style='background:#fdecea;color:#b71c1c;font-size:0.7em;"
                f"font-weight:700;padding:2px 8px;border-radius:10px;margin-left:6px'>"
                f"{n_gaps} gap{'s' if n_gaps != 1 else ''}</span>"
            ) if n_gaps else ""

            with st.expander(
                f"{rs['icon']} {slug}{badge}{gap_badge} — {reg_result.get('summary','')[:80]}",
                expanded=(status in ("GAP", "PARTIAL")),
            ):
                if not gaps:
                    st.caption("No specific gaps identified.")
                for g in gaps:
                    gs   = _STATUS_STYLE.get(g.get("status", "N/A"), _STATUS_STYLE["N/A"])
                    sev  = g.get("severity", "")
                    sev_html = (
                        f"<span style='background:{_SEVERITY_COLOR.get(sev, '#eee')};"
                        f"color:#fff;font-size:0.68em;font-weight:700;"
                        f"padding:1px 7px;border-radius:3px;margin-left:6px'>{sev}</span>"
                    ) if sev and g.get("status") in ("GAP", "PARTIAL") else ""

                    st.markdown(
                        f"<div style='background:{gs['bg']};border-left:3px solid {gs['border']};"
                        f"border-radius:0 5px 5px 0;padding:9px 12px;margin-bottom:8px'>"
                        f"<div style='font-size:0.8em;font-weight:700;color:{gs['border']};"
                        f"margin-bottom:3px'>{gs['icon']} {g.get('article','')} {sev_html}</div>"
                        f"<div style='font-size:0.87em;font-weight:600;margin-bottom:4px'>"
                        f"{g.get('requirement','')}</div>"
                        f"<div style='font-size:0.82em;color:#555;margin-bottom:4px'>"
                        f"<strong>T&amp;C:</strong> {g.get('tc_clause','')}</div>"
                        + (
                            f"<div style='font-size:0.82em;color:#c62828'>"
                            f"<strong>Gap:</strong> {g.get('gap_description','')}</div>"
                            if g.get("gap_description") else ""
                        ) +
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        st.markdown("")
        st.download_button(
            "⬇  Download compliance report (JSON)",
            json.dumps(cr, indent=2),
            "compliance_report.json", "application/json",
        )


# TAB 3 — HISTORY
# ═════════════════════════════════════════════════════════════════════════════
with history_tab:
    entries = history.load()

    if not entries:
        with st.container(border=True):
            st.markdown(
                "<div style='text-align:center;padding:30px 0;color:#888'>"
                "📭 No analyses recorded yet.<br/>"
                "<span style='font-size:0.9em'>Run an analysis on the Analyze tab to get started.</span>"
                "</div>", unsafe_allow_html=True,
            )
    else:
        total = len(entries)
        n_red = sum(1 for e in entries if e["overall_risk"] == "red")
        n_yel = sum(1 for e in entries if e["overall_risk"] == "yellow")
        n_grn = sum(1 for e in entries if e["overall_risk"] == "green")

        with st.container(border=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total analyzed", total)
            m2.metric("🔴 High risk",      n_red)
            m3.metric("🟡 Moderate",       n_yel)
            m4.metric("🟢 User-friendly",  n_grn)

        st.markdown("")

        for entry in entries:
            risk    = entry["overall_risk"]
            r       = RISK[risk]
            counts  = entry["counts"]
            ts      = entry["timestamp"][:16].replace("T", "  ")
            in_icon = INPUT_ICON.get(entry["input_type"], "📄")

            with st.container(border=True):
                top_col, del_col = st.columns([9, 1])
                with top_col:
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:10px'>"
                        f"<span style='font-size:1.3em'>{in_icon}</span>"
                        f"<span style='font-weight:600;font-size:0.97em'>{entry['input_label']}</span>"
                        f"<span style='background:{r['tag_bg']};color:{r['tag_fg']};"
                        f"font-size:0.75em;font-weight:700;padding:2px 9px;border-radius:12px;"
                        f"text-transform:uppercase;letter-spacing:0.05em'>"
                        f"{r['icon']} {r['label']}</span>"
                        f"</div>", unsafe_allow_html=True,
                    )
                with del_col:
                    if st.button("🗑", key=f"del_{entry['id']}", help="Remove this entry"):
                        history.delete(entry["id"])
                        st.rerun()

                st.markdown(
                    f"<div style='background:{r['bg']};border-left:4px solid {r['border']};"
                    f"padding:10px 14px;border-radius:0 6px 6px 0;margin-bottom:10px;"
                    f"font-size:0.93em'>{entry['tldr']}</div>", unsafe_allow_html=True,
                )

                cnt_col, meta_col = st.columns([3, 2])
                with cnt_col:
                    st.markdown(
                        f"<div style='display:flex;gap:8px;flex-wrap:wrap'>"
                        f"<span style='background:#fdecea;color:#b71c1c;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.8em;font-weight:600'>"
                        f"🔴 Rights: {counts['rights_given_up']}</span>"
                        f"<span style='background:#fff8e1;color:#7b5800;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.8em;font-weight:600'>"
                        f"🟡 Obligations: {counts['obligations']}</span>"
                        f"<span style='background:#e8f5e9;color:#1b5e20;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.8em;font-weight:600'>"
                        f"🟢 Benefits: {counts['benefits']}</span>"
                        f"<span style='background:#fff3e0;color:#e65100;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.8em;font-weight:600'>"
                        f"⚠️ Unusual: {counts['unusual_clauses']}</span>"
                        f"</div>", unsafe_allow_html=True,
                    )
                with meta_col:
                    st.caption(f"🕐 {ts} UTC · {entry['source']}")

        st.markdown("")
        if st.button("🗑  Clear all history", type="secondary"):
            history.clear()
            st.rerun()
