import logging
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent_ppt import build_presentation
from app.agent_research import run_research
from app.schemas import HealthResponse, ResearchRequest, ResearchResponse
from app.storage import save_pptx_and_get_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PE Due Diligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="fastapi-backend")


@app.post("/api/research", response_model=ResearchResponse)
def research_company(payload: ResearchRequest) -> ResearchResponse:
    company = payload.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    try:
        logger.info("Research run started for %s", company)
        research = run_research(company)
        slide_payload, presentation = build_presentation(company, research)
        pptx_url = save_pptx_and_get_url(company, presentation)

        return ResearchResponse(
            company=company,
            generated_at=datetime.now(UTC).isoformat(),
            research_summary=research,
            slides=slide_payload["slides"],
            sources=research["all_sources"],
            pptx_url=pptx_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Research run failed")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build due diligence report: {exc}",
        ) from exc
