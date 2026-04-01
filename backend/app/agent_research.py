import json
from typing import Any

from google import genai
from google.genai import types

from app.settings import settings


def _mock_research(company: str) -> dict[str, Any]:
    return {
        "company": company,
        "overview": {
            "summary": f"{company} is an AI-focused company with rapid growth signals.",
            "founded": "Unknown",
            "funding": "Not publicly confirmed",
            "team": "Leadership details available in sources",
            "sources": [1, 2],
        },
        "market": {
            "summary": "Operates in a high-growth AI software market.",
            "competitors": ["OpenAI", "Anthropic", "Cohere", "Google"],
            "market_size": "Large and growing",
            "sources": [3, 4],
        },
        "risks": {
            "summary": "Execution risk, competitive pressure, and pricing pressure.",
            "sources": [5, 6],
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


def run_research(company: str) -> dict[str, Any]:
    if settings.mock_mode or not settings.gemini_api_key:
        return _mock_research(company)

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""
Research company: {company}

Return strict JSON only. No markdown.
Schema:
{{
  "company": "{company}",
  "overview": {{
    "summary": "...",
    "founded": "...",
    "funding": "...",
    "team": "...",
    "sources": [1,2]
  }},
  "market": {{
    "summary": "...",
    "competitors": ["...", "..."],
    "market_size": "...",
    "sources": [1,2]
  }},
  "risks": {{
    "summary": "...",
    "sources": [1,2]
  }},
  "all_sources": []
}}

Requirements:
- Use Google Search grounding and recent credible sources.
- Be concise and factual.
- Do not invent citations.
- all_sources should be left as [] (it will be injected from grounding links).
"""

    response = client.models.generate_content(
        model=settings.gemini_research_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
        ),
    )

    raw_text = _extract_text(response)
    if not raw_text:
        return _mock_research(company)

    cleaned = raw_text.strip().strip("```json").strip("```").strip()
    data = json.loads(cleaned)

    sources = _extract_sources(response)
    if not sources:
        sources = _mock_research(company)["all_sources"]

    data["all_sources"] = sources
    return data
