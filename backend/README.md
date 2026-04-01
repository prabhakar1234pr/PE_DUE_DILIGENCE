# Backend (FastAPI)

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API health endpoint: `http://localhost:8000/api/health`
