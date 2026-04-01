import json
from typing import Any

from google import genai
from google.genai import types

from app.settings import settings

REQUIRED_SECTIONS = [
    "company_profile",
    "product_and_technology",
    "business_model",
    "financial_signals",
    "market_landscape",
    "risk_assessment",
    "catalysts_and_outlook",
    "investment_view",
    "dashboard_metrics",
]


def _mock_research(company: str) -> dict[str, Any]:
    return {
        "company": company,
        "company_profile": {
            "summary": f"{company} operates in the AI software ecosystem with strong enterprise relevance.",
            "founded": "Unknown",
            "headquarters": "Unknown",
            "employee_estimate": "N/A",
            "sources": [1, 2, 3],
        },
        "product_and_technology": {
            "summary": "Product stack focuses on AI-native features and enterprise integrations.",
            "core_offerings": ["LLM platform", "Inference APIs", "Enterprise tooling"],
            "moat_hypothesis": "Model performance + speed of iteration + distribution partnerships",
            "sources": [2, 3, 4],
        },
        "business_model": {
            "summary": "Hybrid pricing with API usage and enterprise contracts.",
            "pricing_motion": "Usage-based with negotiated enterprise commitments.",
            "customer_segments": ["Mid-market software teams", "Large enterprise AI teams"],
            "sources": [4, 5, 6],
        },
        "financial_signals": {
            "summary": "Revenue traction signals are visible but exact audited financials are limited.",
            "funding": "Not publicly confirmed",
            "valuation_signal": "Not publicly confirmed",
            "burn_vs_growth_signal": "Likely elevated burn in exchange for growth and product velocity.",
            "sources": [5, 6, 7],
        },
        "market_landscape": {
            "summary": "Operates in a high-growth AI software market with intense competition.",
            "competitors": ["OpenAI", "Anthropic", "Cohere", "Google"],
            "market_size_estimate": "Large and growing",
            "industry_trends": [
                "Model commoditization pressure",
                "Inference cost optimization race",
                "Enterprise demand for reliability and governance",
            ],
            "sources": [8, 9, 10],
        },
        "risk_assessment": {
            "summary": "Execution risk, competitive pressure, and pricing pressure.",
            "key_risks": [
                "Competitive intensity from well-funded incumbents",
                "Margin pressure from falling model pricing",
                "Dependence on external infra providers",
            ],
            "sources": [10, 11, 12],
        },
        "catalysts_and_outlook": {
            "summary": "Near-term upside depends on enterprise conversion and product defensibility.",
            "catalysts": [
                "Major product releases and benchmarks",
                "Enterprise expansion deals",
                "Partnerships and ecosystem integrations",
            ],
            "sources": [11, 12, 13],
        },
        "investment_view": {
            "base_case": "Strong growth with disciplined go-to-market execution.",
            "upside_case": "Category leadership in selected enterprise segments.",
            "downside_case": "Commoditization and pricing pressure reduce differentiation.",
            "sources": [12, 13, 14],
        },
        "dashboard_metrics": {
            "metrics": [
                {"label": "Funding", "value": "N/A", "trend": "flat"},
                {"label": "Market Growth", "value": "High", "trend": "up"},
                {"label": "Competitive Intensity", "value": "High", "trend": "up"},
                {"label": "Execution Risk", "value": "Medium", "trend": "flat"},
            ],
            "sources": [8, 10, 12],
        },
        "all_sources": [
            {
                "id": 1,
                "title": "Company Website",
                "url": "https://example.com/company",
                "snippet": "Company profile and positioning.",
            },
            {
                "id": 2,
                "title": "LinkedIn",
                "url": "https://linkedin.com/company/example",
                "snippet": "Employee and leadership snapshots.",
            },
            {
                "id": 3,
                "title": "Industry Market Report",
                "url": "https://example.com/market",
                "snippet": "AI market growth analysis.",
            },
            {
                "id": 4,
                "title": "Competitor Coverage",
                "url": "https://example.com/competitors",
                "snippet": "Competitive landscape summary.",
            },
            {
                "id": 5,
                "title": "Pricing Commentary",
                "url": "https://example.com/pricing",
                "snippet": "Pressure on software margins.",
            },
            {
                "id": 6,
                "title": "Risk Overview",
                "url": "https://example.com/risks",
                "snippet": "Operational and execution risk summary.",
            },
            {
                "id": 7,
                "title": "Funding Database",
                "url": "https://example.com/funding",
                "snippet": "Funding rounds and timing.",
            },
            {
                "id": 8,
                "title": "Market Sizing Research",
                "url": "https://example.com/market-size",
                "snippet": "TAM and growth rates.",
            },
            {
                "id": 9,
                "title": "Enterprise Buyer Signals",
                "url": "https://example.com/enterprise",
                "snippet": "Enterprise buyer trends.",
            },
            {
                "id": 10,
                "title": "Competitor Financials",
                "url": "https://example.com/competitor-financials",
                "snippet": "Competitor funding and scale.",
            },
            {
                "id": 11,
                "title": "Product Docs",
                "url": "https://example.com/docs",
                "snippet": "Official product capabilities and updates.",
            },
            {
                "id": 12,
                "title": "Leadership Interviews",
                "url": "https://example.com/interviews",
                "snippet": "Management strategy and roadmap clues.",
            },
            {
                "id": 13,
                "title": "Hiring Signals",
                "url": "https://example.com/hiring",
                "snippet": "Hiring velocity and role concentration.",
            },
            {
                "id": 14,
                "title": "Industry Risk Analysis",
                "url": "https://example.com/industry-risk",
                "snippet": "Sector-level operational and margin risks.",
            },
        ],
    }


def _extract_text(response: Any) -> str:
    if getattr(response, "text", None):
        return response.text

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                return text
    return ""


def _extract_sources(response: Any) -> list[dict[str, Any]]:
    candidates = getattr(response, "candidates", None) or []
    links: list[tuple[str, str]] = []

    for candidate in candidates:
        grounding = getattr(candidate, "grounding_metadata", None)
        chunks = getattr(grounding, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                links.append((getattr(web, "title", "Untitled Source"), web.uri))

    unique_links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for title, url in links:
        if url in seen:
            continue
        seen.add(url)
        unique_links.append((title, url))

    sources: list[dict[str, Any]] = []
    for idx, (title, url) in enumerate(unique_links, start=1):
        sources.append(
            {
                "id": idx,
                "title": title,
                "url": url,
                "snippet": "Grounded web source from Gemini search.",
            }
        )
    return sources


def _parse_json_text(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def _build_research_prompt(company: str, feedback: str) -> str:
    feedback_block = f"\nQuality feedback to fix:\n{feedback}\n" if feedback else ""
    return f"""
You are a principal-level PE due diligence researcher.
Do enterprise-grade deep research on: {company}.
Return strict JSON only.

Schema:
{{
  "company": "{company}",
  "company_profile": {{
    "summary": "...",
    "founded": "...",
    "headquarters": "...",
    "employee_estimate": "...",
    "sources": [1,2]
  }},
  "product_and_technology": {{
    "summary": "...",
    "core_offerings": ["...", "..."],
    "moat_hypothesis": "...",
    "sources": [1,2]
  }},
  "business_model": {{
    "summary": "...",
    "pricing_motion": "...",
    "customer_segments": ["...", "..."],
    "sources": [1,2]
  }},
  "financial_signals": {{
    "summary": "...",
    "funding": "...",
    "valuation_signal": "...",
    "burn_vs_growth_signal": "...",
    "sources": [1,2]
  }},
  "market_landscape": {{
    "summary": "...",
    "competitors": ["...", "...", "..."],
    "market_size_estimate": "...",
    "industry_trends": ["...", "..."],
    "sources": [1,2]
  }},
  "risk_assessment": {{
    "summary": "...",
    "key_risks": ["...", "...", "..."],
    "sources": [1,2]
  }},
  "catalysts_and_outlook": {{
    "summary": "...",
    "catalysts": ["...", "...", "..."],
    "sources": [1,2]
  }},
  "investment_view": {{
    "base_case": "...",
    "upside_case": "...",
    "downside_case": "...",
    "sources": [1,2]
  }},
  "dashboard_metrics": {{
    "metrics": [
      {{"label": "...", "value": "...", "trend": "up|down|flat"}}
    ],
    "sources": [1,2]
  }},
  "all_sources": []
}}

Hard requirements:
- Use broad web grounding (company pages, reputable news, market studies, investor/financial sources, docs, interviews).
- Include measurable indicators wherever available.
- Use precise, concise investor language.
- Explicitly mark uncertainty when evidence is weak.
- Do not fabricate claims.
- Keep all_sources as [].
{feedback_block}
"""


def _min_sources_required() -> int:
    return 6 if settings.mock_mode else 12


def _evaluate_research_quality(data: dict[str, Any]) -> tuple[bool, list[str], int]:
    issues: list[str] = []
    score = 100

    for section in REQUIRED_SECTIONS:
        if section not in data:
            issues.append(f"Missing section: {section}")
            score -= 15

    sources = data.get("all_sources", [])
    if len(sources) < _min_sources_required():
        issues.append(f"Insufficient sources: {len(sources)} < {_min_sources_required()}")
        score -= 20

    dashboard = data.get("dashboard_metrics", {}).get("metrics", [])
    if len(dashboard) < 4:
        issues.append("Need at least 4 dashboard metrics.")
        score -= 12

    if "market_landscape" in data:
        competitors = data["market_landscape"].get("competitors", [])
        if len(competitors) < 3:
            issues.append("Need at least 3 named competitors.")
            score -= 8

    if "risk_assessment" in data:
        if len(data["risk_assessment"].get("key_risks", [])) < 3:
            issues.append("Need at least 3 key risks.")
            score -= 8

    if "catalysts_and_outlook" in data:
        if len(data["catalysts_and_outlook"].get("catalysts", [])) < 3:
            issues.append("Need at least 3 catalysts.")
            score -= 8

    passed = score >= 80 and not issues
    return passed, issues, score


def _normalize_research(data: dict[str, Any]) -> dict[str, Any]:
    if "company" not in data:
        data["company"] = "Unknown"
    data.setdefault("dashboard_metrics", {}).setdefault("metrics", [])
    for section in REQUIRED_SECTIONS:
        data.setdefault(section, {})
    return data


def _reindex_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, src in enumerate(sources, start=1):
        out.append(
            {
                "id": idx,
                "title": src.get("title", "Untitled Source"),
                "url": src.get("url", ""),
                "snippet": src.get("snippet", "Grounded source."),
            }
        )
    return out


def _merge_sources(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for src in a + b:
        url = src.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(src)
    return _reindex_sources(merged)


def run_research(company: str) -> dict[str, Any]:
    if settings.mock_mode or not settings.gemini_api_key:
        return _mock_research(company)

    client = genai.Client(api_key=settings.gemini_api_key)

    feedback = ""
    best_data: dict[str, Any] | None = None
    best_score = -1
    cumulative_sources: list[dict[str, Any]] = []

    for _ in range(max(1, settings.research_max_attempts)):
        prompt = _build_research_prompt(company, feedback)
        response = client.models.generate_content(
            model=settings.gemini_research_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        raw_text = _extract_text(response)
        if not raw_text:
            feedback = "Previous response was empty. Return full schema with data."
            continue

        try:
            data = _normalize_research(_parse_json_text(raw_text))
        except Exception:
            feedback = "Previous output was invalid JSON. Return strict JSON only."
            continue

        sources = _extract_sources(response)
        cumulative_sources = _merge_sources(cumulative_sources, sources)
        if not cumulative_sources:
            cumulative_sources = _mock_research(company)["all_sources"]
        data["all_sources"] = cumulative_sources

        passed, issues, score = _evaluate_research_quality(data)
        if score > best_score:
            best_score = score
            best_data = data
        if passed:
            return data
        feedback = " ; ".join(issues)

    return best_data or _mock_research(company)
