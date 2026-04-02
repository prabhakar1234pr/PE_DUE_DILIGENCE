import json
import logging
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agent_analyst import run_analyst
from app.agent_ppt import build_presentation
from app.agent_research import run_research, run_research_stream, _assemble_research
from app.schemas import HealthResponse, ResearchRequest, ResearchResponse, RunListResponse
from app.storage import save_pptx_and_get_url
from app.workspace import get_full_workspace, list_runs, new_run_id, run_exists

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


@app.get("/api/runs", response_model=RunListResponse)
def get_runs() -> RunListResponse:
    """List all past research runs."""
    return RunListResponse(runs=list_runs(limit=50))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    """Retrieve a past research run by run_id. Reassembles from workspace DB."""
    if not run_exists(run_id):
        raise HTTPException(status_code=404, detail="Run not found.")

    try:
        research = _assemble_research(
            company=run_id.rsplit("-", 2)[0].replace("-", " ").title(),
            run_id=run_id,
        )
        company = research.get("company", "Unknown")
        workspace = get_full_workspace(run_id)

        slide_payload, presentation = build_presentation(company, research, workspace)
        pptx_url = save_pptx_and_get_url(company, presentation)

        return ResearchResponse(
            company=company,
            generated_at=research.get("_created_at", datetime.now(UTC).isoformat()),
            research_summary=research,
            slides=slide_payload["slides"],
            sources=research.get("all_sources", []),
            pptx_url=pptx_url,
        )
    except Exception as exc:
        logger.exception("Failed to reload run %s", run_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/research", response_model=ResearchResponse)
def research_company(payload: ResearchRequest) -> ResearchResponse:
    company = payload.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    try:
        logger.info("Research run started for %s", company)

        # Agent 1: Research
        research = run_research(company)
        run_id = research.get("_run_id", new_run_id(company))

        # Agent 2: Analyst
        for _ in run_analyst(company, run_id):
            pass  # Consume events silently

        # Agent 3: PPT Builder (reads workspace + research dict)
        workspace = get_full_workspace(run_id)
        slide_payload, presentation = build_presentation(company, research, workspace)
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
    """SSE endpoint streaming all 3 agents: Research → Analyst → PPT."""
    company = payload.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    def event_generator():
        research = None
        run_id = None

        # ── Agent 1: Research (streaming) ──
        for event in run_research_stream(company):
            etype = event["event"]
            data = event["data"]

            if etype == "done":
                research = data
                run_id = research.get("_run_id")
                yield f"event: progress\ndata: {json.dumps('Research complete. Starting analysis...')}\n\n"
            else:
                yield f"event: {etype}\ndata: {json.dumps(data)}\n\n"

        if research is None or run_id is None:
            yield f"event: error\ndata: {json.dumps('Research failed.')}\n\n"
            return

        # ── Agent 2: Analyst (streaming) ──
        yield f"event: agent\ndata: {json.dumps('analyst')}\n\n"
        analyst_result = None
        for event in run_analyst(company, run_id):
            etype = event["event"]
            data = event["data"]
            if etype == "done":
                analyst_result = data
                yield f"event: progress\ndata: {json.dumps('Analysis complete. Building presentation...')}\n\n"
            else:
                yield f"event: {etype}\ndata: {json.dumps(data)}\n\n"

        # ── Agent 3: PPT Builder ──
        yield f"event: agent\ndata: {json.dumps('ppt')}\n\n"
        try:
            yield f"event: slides\ndata: {json.dumps('Generating presentation slides...')}\n\n"

            workspace = get_full_workspace(run_id)
            slide_payload, presentation = build_presentation(company, research, workspace)
            pptx_url = save_pptx_and_get_url(company, presentation)

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
            logger.exception("PPT build failed")
            yield f"event: error\ndata: {json.dumps(str(exc))}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
