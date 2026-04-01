# Backend (FastAPI)

## Environment

Create `backend/.env` (optional for local mock mode):

```
GEMINI_API_KEY=
GEMINI_RESEARCH_MODEL=gemini-2.5-pro
GEMINI_SLIDE_MODEL=gemini-2.5-pro
GCP_PROJECT_ID=pe-dd-demo-03312257
GCP_BUCKET_NAME=
MOCK_MODE=true
```

Use `MOCK_MODE=false` once you set your Gemini API key.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## API

- `GET /api/health`
- `POST /api/research` with payload: `{ "company": "Mistral AI" }`
