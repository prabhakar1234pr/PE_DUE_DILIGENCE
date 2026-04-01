import json
import logging
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agent_ppt import build_presentation
from app.agent_research import run_research, run_research_stream
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


@app.post("/api/research/stream")
def research_company_stream(payload: ResearchRequest):
    """SSE endpoint that streams research thinking, sources, and final result.

    Event format (one per line):
      event: <type>
      data: <json>

    Event types:
      thinking  - LLM chain-of-thought text
      search    - Google search query being executed
      source    - Source URL discovered {"title": "...", "url": "..."}
      progress  - Status message string
      attempt   - Quality check result {"attempt": N, "score": N, "issues": [...]}
      slides    - Slide generation started
      done      - Final complete response (same shape as /api/research)
      error     - Error message string
    """
    company = payload.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    def event_generator():
        research = None

        # Phase 1: Stream research with thinking
        for event in run_research_stream(company):
            etype = event["event"]
            data = event["data"]

            if etype == "done":
                research = data
                # Emit the research-done event
                yield f"event: progress\ndata: {json.dumps('Research complete. Building presentation...')}\n\n"
            else:
                yield f"event: {etype}\ndata: {json.dumps(data)}\n\n"

        if research is None:
            yield f"event: error\ndata: {json.dumps('Research failed to produce results.')}\n\n"
            return

        # Phase 2: Build presentation
        try:
            yield f"event: slides\ndata: {json.dumps('Generating presentation slides...')}\n\n"

            slide_payload, presentation = build_presentation(company, research)
            pptx_url = save_pptx_and_get_url(company, presentation)

            # Final result
            final = {
                "company": company,
                "generated_at": datetime.now(UTC).isoformat(),
                "research_summary": research,
                "slides": slide_payload["slides"],
                "sources": research["all_sources"],
                "pptx_url": pptx_url,
            }
            yield f"event: done\ndata: {json.dumps(final)}\n\n"

        except Exception as exc:
            logger.exception("Presentation build failed")
            yield f"event: error\ndata: {json.dumps(str(exc))}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
