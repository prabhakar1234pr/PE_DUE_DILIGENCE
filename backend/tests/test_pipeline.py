import os

os.environ["MOCK_MODE"] = "true"

from fastapi.testclient import TestClient

from app.agent_ppt import build_presentation
from app.agent_research import run_research
from app.main import app


def test_research_agent_output_shape() -> None:
    result = run_research("Mistral AI")
    assert "company_profile" in result
    assert "product_and_technology" in result
    assert "financial_signals" in result
    assert "market_landscape" in result
    assert "risk_assessment" in result
    assert "dashboard_metrics" in result
    assert isinstance(result.get("all_sources"), list)
    assert len(result["all_sources"]) >= 3


def test_ppt_builder_output() -> None:
    research = run_research("Mistral AI")
    slide_payload, pptx_bytes = build_presentation("Mistral AI", research)
    assert len(slide_payload["slides"]) >= 12
    assert sum(1 for s in slide_payload["slides"] if s.get("dashboard_metrics")) >= 2
    assert len(pptx_bytes) > 1000


def test_api_research_endpoint() -> None:
    client = TestClient(app)
    response = client.post("/api/research", json={"company": "Mistral AI"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] == "Mistral AI"
    assert len(payload["slides"]) >= 12
    assert "pptx_url" in payload
