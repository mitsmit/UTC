.PHONY: install serve ui

install:
	pip install -r requirements.txt

serve:
	uvicorn api:app --reload --host 0.0.0.0 --port 8002


ui:
	streamlit run ui.py
