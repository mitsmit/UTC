"""Streamlit UI. Run with: streamlit run ui.py"""

import json

import httpx
import streamlit as st

API_BASE = "http://localhost:8001"

RISK_COLOR  = {"red": "🔴", "yellow": "🟡", "green": "🟢"}
RISK_LABEL  = {"red": "High risk", "yellow": "Moderate", "green": "User-friendly"}
OVERALL_BG  = {"red": "#fdecea", "yellow": "#fff8e1", "green": "#e8f5e9"}
OVERALL_BORDER = {"red": "#e53935", "yellow": "#f9a825", "green": "#43a047"}
SCORE_COLOR = {"Aggressive": "#e53935", "Mixed": "#f9a825",
               "Fair": "#1976d2", "User-friendly": "#43a047"}

st.set_page_config(page_title="T&C Analyzer", page_icon="📋", layout="wide")

st.title("📋 Terms & Conditions Analyzer")
st.caption(
    "Paste, upload, or link a T&C document — get a plain-English breakdown "
    "or compare up to 3 companies side by side."
)

main_tab, compare_tab = st.tabs(["🔍 Analyze", "📊 Compare"])


# ── shared helper ─────────────────────────────────────────────────────────────
def render_clauses(title: str, icon: str, clauses: list[dict]) -> None:
    st.markdown(f"### {icon} {title}")
    if not clauses:
        st.caption("None identified in this document.")
        return
    for c in clauses:
        badge = " ⚠️ *Unusual*" if c["unusual"] else ""
        with st.expander(f"{RISK_COLOR[c['risk']]} {c['summary']}{badge}", expanded=False):
            st.markdown(f"**Risk level:** {RISK_LABEL[c['risk']]}")
            if c["citation"]:
                st.markdown("**Original clause:**")
                st.code(c["citation"], language=None)
    st.markdown("")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ANALYZE
# ═══════════════════════════════════════════════════════════════════════════════
with main_tab:
    input_text, input_pdf, input_url = st.tabs(
        ["📝 Paste Text", "📄 Upload PDF", "🔗 Enter URL"]
    )

    submitted = False
    api_endpoint = None
    payload = None
    files = None

    with input_text:
        pasted = st.text_area("Paste the Terms and Conditions text here", height=260,
                              placeholder="Paste the full T&C text…")
        if st.button("Analyze Text", type="primary", use_container_width=True, key="btn_text"):
            if not pasted.strip():
                st.warning("Please paste some text first.")
            else:
                submitted = True
                api_endpoint = f"{API_BASE}/analyze/text"
                payload = {"text": pasted}

    with input_pdf:
        uploaded = st.file_uploader("Upload a PDF", type=["pdf"], key="single_pdf")
        if st.button("Analyze PDF", type="primary", use_container_width=True, key="btn_pdf"):
            if not uploaded:
                st.warning("Please upload a PDF file first.")
            else:
                submitted = True
                api_endpoint = f"{API_BASE}/analyze/pdf"
                files = {"file": (uploaded.name, uploaded.read(), "application/pdf")}

    with input_url:
        url_input = st.text_input("Enter the URL of the Terms and Conditions page",
                                  placeholder="https://example.com/terms")
        if st.button("Analyze URL", type="primary", use_container_width=True, key="btn_url"):
            if not url_input.strip():
                st.warning("Please enter a URL first.")
            else:
                submitted = True
                api_endpoint = f"{API_BASE}/analyze/url"
                payload = {"url": url_input.strip()}

    if submitted and api_endpoint:
        with st.spinner("Analyzing… this may take 20–40 seconds for long documents."):
            try:
                if files:
                    resp = httpx.post(api_endpoint, files=files, timeout=120)
                else:
                    resp = httpx.post(api_endpoint, data=payload, timeout=120)
                if resp.status_code != 200:
                    st.error(f"Analysis failed: {resp.json().get('detail', resp.text)}")
                    st.stop()
                data = resp.json()
            except httpx.ConnectError:
                st.error("Cannot reach the API. Run: `uvicorn api:app --reload --port 8001`")
                st.stop()
            except Exception as e:
                st.error(f"Unexpected error: {e}")
                st.stop()

        result = data["result"]
        risk = result["overall_risk"]

        st.markdown("---")
        st.markdown(
            f"""<div style="background:{OVERALL_BG[risk]};border-left:5px solid
            {OVERALL_BORDER[risk]};padding:16px 20px;border-radius:6px;margin-bottom:12px;">
            <strong>{RISK_COLOR[risk]} Overall risk: {RISK_LABEL[risk]}</strong><br/>
            <span style="font-size:1.05em">{result['tldr']}</span></div>""",
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Characters analyzed", f"{data['char_count']:,}")
        c2.metric("Sections processed", data["chunk_count"])
        c3.metric("Source", result["source"][:40] + ("…" if len(result["source"]) > 40 else ""))
        st.markdown("---")

        col_l, col_r = st.columns(2)
        with col_l:
            render_clauses("Rights You Give Up", "🔴", result["rights_given_up"])
            render_clauses("Your Obligations", "🟡", result["obligations"])
        with col_r:
            render_clauses("Your Benefits", "🟢", result["benefits"])
            render_clauses("Unusual Clauses", "⚠️", result["unusual_clauses"])

        st.markdown("---")
        st.download_button("⬇ Download analysis (JSON)", json.dumps(result, indent=2),
                           "tc_analysis.json", "application/json")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMPARE
# ═══════════════════════════════════════════════════════════════════════════════
with compare_tab:
    st.markdown("### Compare up to 3 companies side by side")
    st.caption(
        "For each company enter a name, then paste text, upload a PDF, or provide a URL. "
        "Add a second or third company with the buttons below."
    )

    if "num_companies" not in st.session_state:
        st.session_state.num_companies = 2

    col_add, col_remove, _ = st.columns([1, 1, 4])
    with col_add:
        if st.session_state.num_companies < 3:
            if st.button("＋ Add company", use_container_width=True):
                st.session_state.num_companies += 1
                st.rerun()
    with col_remove:
        if st.session_state.num_companies > 2:
            if st.button("－ Remove last", use_container_width=True):
                st.session_state.num_companies -= 1
                st.rerun()

    st.markdown("")
    company_inputs = []
    slot_cols = st.columns(st.session_state.num_companies)

    for idx, col in enumerate(slot_cols):
        with col:
            label = ["🅐 Company 1", "🅑 Company 2", "🅒 Company 3"][idx]
            st.markdown(f"**{label}**")
            name = st.text_input("Company name", key=f"cmp_name_{idx}",
                                 placeholder=f"e.g. Spotify")
            mode = st.radio("Input via", ["Paste text", "Upload PDF", "URL"],
                            key=f"cmp_mode_{idx}", horizontal=True)

            cmp_text = None
            cmp_url = None

            if mode == "Paste text":
                cmp_text = st.text_area("Paste T&C text", height=200,
                                        key=f"cmp_text_{idx}",
                                        placeholder="Paste full T&C here…")
            elif mode == "Upload PDF":
                pdf_file = st.file_uploader("Upload PDF", type=["pdf"],
                                            key=f"cmp_pdf_{idx}")
                if pdf_file:
                    with st.spinner("Extracting PDF text…"):
                        r = httpx.post(
                            f"{API_BASE}/extract/pdf",
                            files={"file": (pdf_file.name, pdf_file.read(),
                                            "application/pdf")},
                            timeout=30,
                        )
                        if r.status_code == 200:
                            cmp_text = r.json()["text"]
                            st.success(f"Extracted {len(cmp_text):,} characters")
                        else:
                            st.error(r.json().get("detail", "Extraction failed"))
            elif mode == "URL":
                cmp_url = st.text_input("T&C URL", key=f"cmp_url_{idx}",
                                        placeholder="https://…/terms")

            company_inputs.append({"name": name, "text": cmp_text, "url": cmp_url})

    st.markdown("")
    run_compare = st.button("🔍 Run Comparison", type="primary", use_container_width=True)

    if run_compare:
        errors = []
        for i, c in enumerate(company_inputs):
            if not c["name"].strip():
                errors.append(f"Company {i+1}: enter a name.")
            if not c["text"] and not c["url"]:
                errors.append(f"Company {i+1}: provide text, a PDF, or a URL.")
        if errors:
            for e in errors:
                st.warning(e)
        else:
            payload_companies = [
                {"name": c["name"].strip(),
                 **({"text": c["text"]} if c["text"] else {"url": c["url"]})}
                for c in company_inputs
            ]
            with st.spinner("Analyzing and comparing… this may take 30–90 seconds."):
                try:
                    resp = httpx.post(f"{API_BASE}/compare",
                                      json={"companies": payload_companies},
                                      timeout=300)
                    if resp.status_code != 200:
                        st.error(f"Comparison failed: {resp.json().get('detail', resp.text)}")
                        st.stop()
                    cr = resp.json()
                except httpx.ConnectError:
                    st.error("Cannot reach the API. Run: `uvicorn api:app --reload --port 8001`")
                    st.stop()
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.stop()

            companies = cr["companies"]
            scores = {s["company"]: s for s in cr["scores"]}
            winner = cr["overall_winner"]

            st.markdown("---")
            st.markdown(
                f"""<div style="background:#e8f5e9;border-left:5px solid #43a047;
                padding:16px 20px;border-radius:6px;margin-bottom:16px;">
                <strong>✅ Best choice: {winner}</strong><br/>
                <span style="font-size:1.02em">{cr['summary']}</span></div>""",
                unsafe_allow_html=True,
            )

            st.markdown("#### User-friendliness scores")
            score_cols = st.columns(len(companies))
            for col, company in zip(score_cols, companies):
                s = scores.get(company, {})
                score_val = s.get("score", 0)
                label = s.get("label", "")
                color = SCORE_COLOR.get(label, "#888")
                crown = " 👑" if company == winner else ""
                col.markdown(
                    f"""<div style="text-align:center;padding:12px;border-radius:8px;
                    border:2px solid {color};">
                    <div style="font-size:1.05em;font-weight:bold">{company}{crown}</div>
                    <div style="font-size:2em;font-weight:bold;color:{color}">{score_val}</div>
                    <div style="font-size:0.85em;color:{color}">{label}</div>
                    <div style="background:#eee;border-radius:4px;margin-top:6px;">
                    <div style="width:{score_val}%;background:{color};height:8px;
                    border-radius:4px;"></div></div></div>""",
                    unsafe_allow_html=True,
                )

            st.markdown("---")
            st.markdown("#### Topic-by-topic breakdown")
            header_cols = st.columns([2] + [2] * len(companies))
            header_cols[0].markdown("**Topic**")
            for i, company in enumerate(companies):
                header_cols[i + 1].markdown(f"**{company}**")
            st.markdown('<hr style="margin:4px 0"/>', unsafe_allow_html=True)

            for topic in cr["topics"]:
                row_cols = st.columns([2] + [2] * len(companies))
                row_cols[0].markdown(f"**{topic['topic']}**")
                for i, company in enumerate(companies):
                    stance = topic["stances"].get(company, {})
                    risk = stance.get("risk", "yellow")
                    summary = stance.get("summary", "No information")
                    present = stance.get("present", True)
                    crown = " 👑" if stance.get("winner") else ""
                    icon = RISK_COLOR.get(risk, "⚪")
                    row_cols[i + 1].markdown(
                        f"{'🟢 Not present' if not present else f'{icon} {summary}'}{crown}"
                    )
                st.markdown('<hr style="margin:2px 0;border-color:#eee"/>', unsafe_allow_html=True)

            st.markdown("")
            st.download_button("⬇ Download comparison (JSON)", json.dumps(cr, indent=2),
                               "tc_comparison.json", "application/json")
