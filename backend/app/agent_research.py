"""Research Agent — Dynamic, LLM-orchestrated multi-pass deep search.

The LLM decides:
  - What to research next (based on what it already knows)
  - How deep to go on each topic
  - When to follow up on interesting discoveries
  - When it has enough data to stop

Architecture:
  1. PLAN: LLM analyzes the company and creates a research plan
  2. EXECUTE: For each planned topic, run a focused Gemini + Google Search call
  3. REFLECT: After each pass, LLM reviews findings and decides:
     - Follow up on something interesting? → add new research tasks
     - Enough depth? → move to next topic
     - All done? → assemble final research
  4. ASSEMBLE: Combine all findings into structured research dict
"""

import json
import re
import time
from typing import Any, Generator

from google import genai
from google.genai import types

from app.settings import settings
from app.workspace import (
    get_findings,
    get_sources_reindexed,
    new_run_id,
    write_finding,
    write_source,
)

# ── Maximum limits to prevent runaway loops ──────────────────
MAX_RESEARCH_PASSES = 20
MIN_RESEARCH_PASSES = 6
MAX_FOLLOW_UPS = 5


# ── Gemini helpers ───────────────────────────────────────────

def _extract_text(response: Any) -> str:
    if getattr(response, "text", None):
        return response.text
    for c in getattr(response, "candidates", None) or []:
        content = getattr(c, "content", None)
        if content:
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "text", None):
                    return part.text
    return ""


def _extract_sources(response: Any) -> list[dict[str, str]]:
    seen: set[str] = set()
    sources = []
    for c in getattr(response, "candidates", None) or []:
        grounding = getattr(c, "grounding_metadata", None)
        for chunk in getattr(grounding, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None) and web.uri not in seen:
                seen.add(web.uri)
                sources.append({"title": getattr(web, "title", "Source"), "url": web.uri})
    return sources


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def _call_gemini(client, prompt: str, use_search: bool = True) -> tuple[str, list[dict]]:
    """Make a Gemini call, return (text, sources)."""
    config_kwargs: dict[str, Any] = {"temperature": 0.1}
    if use_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    response = client.models.generate_content(
        model=settings.gemini_research_model,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return _extract_text(response), _extract_sources(response)


# ═══════════════════════════════════════════════════════════════
# Phase 1: PLAN — LLM creates a research plan
# ═══════════════════════════════════════════════════════════════

PLAN_PROMPT = """You are a senior PE due diligence researcher at McKinsey.
You need to create a RESEARCH PLAN for: {company}

Based on what you know about this company, decide:
1. What specific topics need to be researched?
2. In what order? (most important first)
3. How deep should each topic go?

Consider the company type:
- Public company → needs SEC filings, earnings, analyst coverage
- Late-stage private → needs funding history, valuation signals, exit analysis
- Early-stage startup → needs product/market fit signals, founding team, seed metrics
- AI/tech company → needs technical moat analysis, model benchmarks, GPU strategy
- Regulated industry → needs compliance deep-dive, regulatory risk

CRITICAL: Each topic MUST include a "section_key" from this EXACT list:
  company_profile, management_team, product_and_technology, business_model,
  unit_economics, financial_signals, customer_evidence, market_and_competition,
  comparable_transactions, risk_and_regulatory, exit_and_investment

You MUST cover ALL 11 section_keys at least once. You can have multiple topics
for the same section_key (e.g., two topics for financial_signals: one for funding
rounds, one for revenue metrics). But every section_key must appear.

Return STRICT JSON:
{{
  "company_type": "public|late_private|early_private|other",
  "research_plan": [
    {{
      "section_key": "one of the 11 keys above",
      "topic": "descriptive topic name for this search",
      "search_query": "what to search for on Google",
      "data_to_extract": "specific data points to find",
      "priority": "critical|high|medium",
      "depth": "deep|standard|light"
    }}
  ],
  "rationale": "1-2 sentences on why this plan fits this company"
}}

Generate 10-15 research topics. Put the most important ones first.
Tailor the plan specifically to {company} — do NOT use a generic template."""


def _create_research_plan(client, company: str) -> list[dict[str, Any]]:
    """Ask the LLM to create a tailored research plan."""
    prompt = PLAN_PROMPT.format(company=company)
    text, _ = _call_gemini(client, prompt, use_search=True)

    try:
        plan = _parse_json(text)
        topics = plan.get("research_plan", [])
        if topics and len(topics) >= 3:
            return topics
    except Exception:
        pass

    # Fallback: minimal default plan
    return _default_plan(company)


def _default_plan(company: str) -> list[dict[str, Any]]:
    """Fallback plan if LLM planning fails."""
    return [
        {"section_key": "company_profile", "topic": "Company Overview", "search_query": f"{company} company overview founding headquarters employees", "data_to_extract": "founding year, HQ, employee count, key facts", "priority": "critical", "depth": "deep"},
        {"section_key": "management_team", "topic": "Leadership Team", "search_query": f"{company} CEO CTO CFO leadership team background", "data_to_extract": "named executives, titles, prior companies, achievements", "priority": "critical", "depth": "deep"},
        {"section_key": "product_and_technology", "topic": "Products & Technology", "search_query": f"{company} products technology platform features", "data_to_extract": "core products, technical moat, patents, differentiation", "priority": "critical", "depth": "deep"},
        {"section_key": "financial_signals", "topic": "Funding & Financials", "search_query": f"{company} funding rounds valuation revenue ARR investors", "data_to_extract": "funding rounds, investors, valuation, ARR, burn rate", "priority": "critical", "depth": "deep"},
        {"section_key": "business_model", "topic": "Business Model & Unit Economics", "search_query": f"{company} pricing business model revenue unit economics NRR margins", "data_to_extract": "pricing, ACV, revenue composition, CAC, LTV, NRR, margins", "priority": "critical", "depth": "deep"},
        {"section_key": "market_and_competition", "topic": "Market & Competition", "search_query": f"{company} competitors market size industry landscape TAM", "data_to_extract": "TAM/SAM/SOM, named competitors, market trends, positioning", "priority": "high", "depth": "deep"},
        {"section_key": "customer_evidence", "topic": "Customers & Traction", "search_query": f"{company} customers case studies reviews NPS retention churn", "data_to_extract": "customer logos, churn, NPS, case studies with ROI", "priority": "high", "depth": "standard"},
        {"section_key": "comparable_transactions", "topic": "Comparable Transactions", "search_query": f"{company} sector M&A acquisitions comparable valuations multiples", "data_to_extract": "M&A comps, public comps with multiples", "priority": "high", "depth": "standard"},
        {"section_key": "risk_and_regulatory", "topic": "Risks & Regulatory", "search_query": f"{company} risks regulatory compliance IP patents lawsuits", "data_to_extract": "key risks, regulatory status, IP exposure, compliance", "priority": "high", "depth": "standard"},
        {"section_key": "exit_and_investment", "topic": "Exit & Investment Thesis", "search_query": f"{company} IPO acquisition exit investment outlook valuation", "data_to_extract": "exit paths, strategic acquirers, IPO readiness, IRR", "priority": "high", "depth": "standard"},
        {"section_key": "unit_economics", "topic": "Unit Economics Deep Dive", "search_query": f"{company} CAC LTV gross margin retention payback period SaaS metrics", "data_to_extract": "CAC, LTV, LTV:CAC, NRR, gross margin, Rule of 40", "priority": "high", "depth": "standard"},
    ]


# ═══════════════════════════════════════════════════════════════
# Phase 2: EXECUTE — Run focused searches
# ═══════════════════════════════════════════════════════════════

SEARCH_PROMPT = """You are a senior PE due diligence researcher.
Research target: {company}
Topic: {topic}

SEARCH FOCUS: {search_query}
DATA TO EXTRACT: {data_to_extract}

Return STRICT JSON with your findings. Include:
- "summary": Detailed analysis (300+ chars minimum) with specific numbers
- Any structured data fields relevant to this topic
- Be quantitative: include $, %, multiples, dates, named entities

If data is unavailable, provide reasoned estimates with confidence levels.
Return JSON only. No markdown. No commentary."""


def _execute_search(client, company: str, topic: dict, run_id: str) -> Generator:
    """Execute one focused search pass."""
    topic_name = topic.get("topic", "Research")
    search_query = topic.get("search_query", f"{company} {topic_name}")
    data_to_extract = topic.get("data_to_extract", "key findings")

    yield {"event": "search", "data": search_query}

    prompt = SEARCH_PROMPT.format(
        company=company,
        topic=topic_name,
        search_query=search_query,
        data_to_extract=data_to_extract,
    )

    try:
        text, sources = _call_gemini(client, prompt, use_search=True)
    except Exception as e:
        yield {"event": "error", "data": f"{topic_name}: API error — {e}"}
        return

    if not text:
        yield {"event": "error", "data": f"{topic_name}: empty response"}
        return

    # Store sources
    for src in sources:
        write_source(run_id, company, src["title"], src["url"], "Grounded web source")
        yield {"event": "source", "data": {"title": src["title"], "url": src["url"]}}

    # Store finding — use section_key from plan, fallback to topic name mapping
    section_key = topic.get("section_key") or _topic_to_section_key(topic_name)
    try:
        data = _parse_json(text)
        write_finding(run_id, company, section_key, json.dumps(data), sources)
        summary = data.get("summary", "")[:120]
        yield {"event": "thinking", "data": f"{topic_name}: {summary}..."}
    except Exception:
        write_finding(run_id, company, section_key, text, sources)
        yield {"event": "thinking", "data": f"{topic_name}: stored raw text ({len(text)} chars)"}


def _topic_to_section_key(topic_name: str) -> str:
    """Convert a free-form topic name to a canonical section key using keyword matching."""
    lower = topic_name.lower()

    # Keyword-based matching — ORDER MATTERS (most specific first, then broader)
    keyword_map = [
        # Very specific multi-word phrases first
        (["unit economics", "cac", "ltv", "payback period", "rule of 40"], "unit_economics"),
        (["business model", "pricing strateg", "revenue model", "monetiz"], "business_model"),
        (["comparable", "comps", "m&a", "acquisition deal", "transaction"], "comparable_transactions"),
        (["exit", "ipo", "acquirer", "irr", "exit path", "ipo readiness"], "exit_and_investment"),
        # Financial keywords (before "company" since "financial overview" should match here)
        (["financial", "funding", "revenue", "arr ", "valuation", "burn rate", "investor", "series a", "series b", "series c", "series d"], "financial_signals"),
        # Management (ceo/cto before general "company")
        (["management", "leadership", "executive", "ceo", "cto", "cfo", "founder", "team lead", "c-suite"], "management_team"),
        # Product/tech
        (["product", "technology", "platform", "moat", "patent", "technical", "architecture", "r&d"], "product_and_technology"),
        # Market
        (["market", "competition", "competitor", "landscape", "tam", "sam", "industry", "positioning"], "market_and_competition"),
        # Customer (retention here is customer retention, not unit econ)
        (["customer", "client", "logo", "churn", "nps", "case stud", "traction"], "customer_evidence"),
        # Risk/regulatory
        (["risk", "regulatory", "compliance", "legal", "lawsuit"], "risk_and_regulatory"),
        # Company profile last (broadest match)
        (["company overview", "company profile", "headquarter", "founding history"], "company_profile"),
        # NRR and gross margin — unit economics
        (["nrr", "gross margin", "retention rate"], "unit_economics"),
    ]

    for keywords, section_key in keyword_map:
        if any(kw in lower for kw in keywords):
            return section_key

    # Fallback: snake_case the topic name
    return re.sub(r"[^a-z0-9]+", "_", lower).strip("_")


# ═══════════════════════════════════════════════════════════════
# Phase 3: REFLECT — LLM reviews findings and decides next steps
# ═══════════════════════════════════════════════════════════════

REFLECT_PROMPT = """You are reviewing research findings for a PE due diligence on {company}.

Research completed so far ({n_passes} passes):
{findings_summary}

Sources found: {n_sources}

Based on what you've found, decide:
1. Are there GAPS that need additional research?
2. Did you discover something interesting that needs a follow-up deep-dive?
3. Is the research comprehensive enough to write an IC memo?

Return STRICT JSON:
{{
  "is_complete": true/false,
  "confidence": "high|medium|low",
  "gaps": ["specific gap that needs research"],
  "follow_ups": [
    {{
      "topic": "specific follow-up topic",
      "search_query": "what to search",
      "data_to_extract": "what to find",
      "reason": "why this is needed"
    }}
  ],
  "assessment": "1-2 sentence assessment of research quality"
}}

Be honest. If key areas (financials, competition, risks) are weak, say so.
Only mark is_complete=true if you have enough depth for an IC memo."""


def _reflect_on_findings(client, company: str, run_id: str, n_passes: int) -> dict[str, Any]:
    """Ask the LLM to review what it's found and suggest follow-ups."""
    findings = get_findings(run_id)
    sources = get_sources_reindexed(run_id)

    # Build a condensed summary of findings
    summary_parts = []
    for f in findings:
        section = f["section"]
        content = f["content"]
        try:
            data = json.loads(content)
            s = data.get("summary", content[:200])
        except Exception:
            s = content[:200]
        summary_parts.append(f"- {section}: {s[:150]}")

    findings_summary = "\n".join(summary_parts[-15:])  # Last 15 to fit context

    prompt = REFLECT_PROMPT.format(
        company=company,
        n_passes=n_passes,
        findings_summary=findings_summary,
        n_sources=len(sources),
    )

    try:
        text, _ = _call_gemini(client, prompt, use_search=False)
        return _parse_json(text)
    except Exception:
        return {"is_complete": n_passes >= MIN_RESEARCH_PASSES, "confidence": "medium",
                "gaps": [], "follow_ups": [], "assessment": "Reflection failed, proceeding with current data."}


# ═══════════════════════════════════════════════════════════════
# Validation gate — does this company actually exist?
# ═══════════════════════════════════════════════════════════════

VALIDATE_PROMPT = """You just searched the web for information about "{company}".
Here is what you found in the first research passes:

{findings_summary}

QUESTION: Does "{company}" appear to be a real, identifiable company?

Return STRICT JSON:
{{
  "exists": true/false,
  "confidence": "high|medium|low",
  "reason": "1 sentence explanation",
  "suggested_name": "correct company name if the user may have misspelled it, or null"
}}

Rules:
- exists=true if the search found specific information ABOUT this company (founders, products, funding, HQ)
- exists=false if the search only found generic industry data or completely unrelated results
- If the findings are empty or only contain market reports not about this specific company, exists=false"""


def _validate_company_exists(client, company: str, run_id: str) -> dict[str, Any]:
    """After initial passes, check if the company actually exists."""
    findings = get_findings(run_id)
    parts = []
    for f in findings[:3]:
        content = f.get("content", "")
        try:
            data = json.loads(content)
            s = data.get("summary", content[:300])
        except Exception:
            s = content[:300]
        parts.append(f"- {f['section']}: {s[:200]}")

    summary = "\n".join(parts) if parts else "(No findings yet)"

    prompt = VALIDATE_PROMPT.format(company=company, findings_summary=summary)
    try:
        text, _ = _call_gemini(client, prompt, use_search=False)
        return _parse_json(text)
    except Exception:
        # If validation fails, assume it exists and continue
        return {"exists": True, "confidence": "low", "reason": "Validation failed, proceeding anyway.", "suggested_name": None}


# ═══════════════════════════════════════════════════════════════
# Main orchestration — PLAN → EXECUTE → VALIDATE → REFLECT loop
# ═══════════════════════════════════════════════════════════════

def run_research(company: str) -> dict[str, Any]:
    """Synchronous research — returns full research dict."""
    run_id = new_run_id(company)
    if settings.mock_mode or not settings.gemini_api_key:
        return _run_mock_research(company, run_id)

    client = genai.Client(api_key=settings.gemini_api_key)

    # Plan
    plan = _create_research_plan(client, company)

    # Execute first 2 passes, then validate
    n_passes = 0

    for topic in plan[:2]:
        for _ in _execute_search(client, company, topic, run_id):
            pass
        n_passes += 1

    # Validation gate — does this company actually exist?
    validation = _validate_company_exists(client, company, run_id)
    if not validation.get("exists", True):
        reason = validation.get("reason", "Company not found")
        suggested = validation.get("suggested_name")
        error_msg = f"Company not found: {reason}"
        if suggested:
            error_msg += f" Did you mean: {suggested}?"
        raise ValueError(error_msg)

    # Continue remaining passes
    for topic in plan[2:MAX_RESEARCH_PASSES]:
        for _ in _execute_search(client, company, topic, run_id):
            pass
        n_passes += 1

    # Reflect and follow up
    if n_passes >= MIN_RESEARCH_PASSES:
        reflection = _reflect_on_findings(client, company, run_id, n_passes)
        for fu in reflection.get("follow_ups", [])[:MAX_FOLLOW_UPS]:
            if n_passes >= MAX_RESEARCH_PASSES:
                break
            for _ in _execute_search(client, company, fu, run_id):
                pass
            n_passes += 1

    return _assemble_research(company, run_id)


def run_research_stream(company: str) -> Generator:
    """Streaming research — yields SSE events during dynamic search."""
    run_id = new_run_id(company)

    if settings.mock_mode or not settings.gemini_api_key:
        yield {"event": "progress", "data": "Running in mock mode..."}
        mock = _run_mock_research(company, run_id)
        for src in (mock.get("all_sources") or [])[:6]:
            yield {"event": "source", "data": {"title": src["title"], "url": src["url"]}}
            time.sleep(0.08)
        yield {"event": "progress", "data": "Mock research complete."}
        yield {"event": "done", "data": mock}
        return

    client = genai.Client(api_key=settings.gemini_api_key)

    # ── Phase 1: PLAN ──
    yield {"event": "thinking", "data": f"Analyzing {company} to create a tailored research plan..."}
    plan = _create_research_plan(client, company)
    yield {"event": "progress", "data": f"Research plan: {len(plan)} topics tailored for {company}"}

    for i, topic in enumerate(plan[:5]):
        yield {"event": "thinking", "data": f"Planned: [{topic.get('priority', '?')}] {topic.get('topic', '?')}"}

    # ── Phase 2: EXECUTE (first 2 passes) ──
    n_passes = 0
    for topic in plan[:2]:
        topic_name = topic.get("topic", "Research")
        yield {"event": "progress", "data": f"[{n_passes+1}/{len(plan)}] {topic_name}"}
        for event in _execute_search(client, company, topic, run_id):
            yield event
        n_passes += 1

    # ── Validation gate: does this company exist? ──
    yield {"event": "thinking", "data": f"Validating that {company} is a real, identifiable company..."}
    validation = _validate_company_exists(client, company, run_id)
    if not validation.get("exists", True):
        reason = validation.get("reason", "Company not found in search results")
        suggested = validation.get("suggested_name")
        msg = f"Company not found: {reason}"
        if suggested:
            msg += f" Did you mean: {suggested}?"
        yield {"event": "error", "data": msg}
        return
    yield {"event": "thinking", "data": f"Validated: {company} exists (confidence: {validation.get('confidence', '?')})"}

    # ── Continue remaining passes ──
    for i, topic in enumerate(plan[2:]):
        if n_passes >= MAX_RESEARCH_PASSES:
            break
        topic_name = topic.get("topic", "Research")
        priority = topic.get("priority", "standard")
        yield {"event": "progress", "data": f"[{n_passes+1}/{len(plan)}] {topic_name} ({priority})"}

        for event in _execute_search(client, company, topic, run_id):
            yield event
        n_passes += 1

    # ── Phase 3: REFLECT ──
    if n_passes >= MIN_RESEARCH_PASSES:
        yield {"event": "thinking", "data": "Reviewing findings for gaps and follow-up opportunities..."}
        reflection = _reflect_on_findings(client, company, run_id, n_passes)

        confidence = reflection.get("confidence", "unknown")
        assessment = reflection.get("assessment", "")
        yield {"event": "thinking", "data": f"Assessment: {assessment} (confidence: {confidence})"}

        follow_ups = reflection.get("follow_ups", [])
        if follow_ups and not reflection.get("is_complete", True):
            yield {"event": "progress", "data": f"Found {len(follow_ups)} areas needing deeper research"}

            for fu in follow_ups[:MAX_FOLLOW_UPS]:
                if n_passes >= MAX_RESEARCH_PASSES:
                    break
                reason = fu.get("reason", "")
                yield {"event": "thinking", "data": f"Follow-up: {fu.get('topic', '?')} — {reason}"}

                for event in _execute_search(client, company, fu, run_id):
                    yield event
                n_passes += 1
        else:
            yield {"event": "progress", "data": "Research is comprehensive — no follow-ups needed"}

    yield {"event": "progress", "data": f"Research complete: {n_passes} passes, assembling findings..."}

    research = _assemble_research(company, run_id)
    score = _score_research(research)
    yield {"event": "attempt", "data": {"attempt": 1, "score": score, "issues": []}}
    yield {"event": "done", "data": research}


# ═══════════════════════════════════════════════════════════════
# Assembly: workspace → research dict
# ═══════════════════════════════════════════════════════════════

def _assemble_research(company: str, run_id: str) -> dict[str, Any]:
    """Read all findings from workspace and assemble into research dict."""
    findings = get_findings(run_id)
    sources = get_sources_reindexed(run_id)

    research: dict[str, Any] = {"company": company}

    for finding in findings:
        section = finding["section"]
        try:
            data = json.loads(finding["content"])
        except (json.JSONDecodeError, TypeError):
            data = {"summary": finding["content"]}

        # Map section keys to research dict structure
        if section == "company_profile":
            research["company_profile"] = data
        elif section == "management_team":
            research["management_team"] = data
        elif section == "product_and_technology":
            research["product_and_technology"] = data
        elif section == "business_model":
            research["business_model"] = data
            if "unit_economics" in data:
                research["unit_economics"] = {
                    "summary": data.get("summary", ""),
                    "metrics": data["unit_economics"],
                    "confidence": data.get("confidence", "Medium"),
                }
        elif section == "unit_economics":
            research["unit_economics"] = data
        elif section == "financial_signals":
            research["financial_signals"] = data
        elif section == "market_and_competition":
            research["market_landscape"] = {
                "summary": data.get("market_summary", data.get("summary", "")),
                "competitors": data.get("competitors", []),
                "market_size_estimate": _format_market_size(data.get("market_size", data.get("market_size_estimate", ""))),
                "industry_trends": data.get("industry_trends", []),
            }
            research["competitive_positioning"] = {
                "summary": data.get("market_summary", data.get("summary", "")),
                "positioning_matrix": data.get("positioning_matrix", []),
                "key_differentiators": data.get("key_differentiators", []),
            }
        elif section == "customer_evidence":
            research["customer_evidence"] = data
        elif section == "comparable_transactions":
            research["comparable_transactions"] = data
        elif section == "risk_and_regulatory":
            research["risk_assessment"] = {
                "summary": data.get("risk_summary", data.get("summary", "")),
                "key_risks": data.get("key_risks", []),
                "overall_risk_rating": data.get("overall_risk_rating", ""),
            }
            research["regulatory_landscape"] = {
                "summary": data.get("risk_summary", data.get("summary", "")),
                "ip_exposure": data.get("ip_exposure", ""),
                "data_privacy": data.get("data_privacy", ""),
                "regulatory_moats": data.get("regulatory_moats", []),
                "regulatory_risks": data.get("regulatory_risks", []),
            }
        elif section == "exit_and_investment":
            research["exit_analysis"] = {
                "summary": data.get("exit_summary", data.get("summary", "")),
                "strategic_acquirers": data.get("strategic_acquirers", []),
                "ipo_readiness": data.get("ipo_readiness", {}),
                "exit_multiples": data.get("exit_multiples", {}),
                "implied_irr": data.get("implied_irr", {}),
            }
            research["investment_view"] = {
                "summary": data.get("investment_summary", data.get("summary", "")),
                "base_case": data.get("base_case", ""),
                "upside_case": data.get("upside_case", ""),
                "downside_case": data.get("downside_case", ""),
                "recommendation": data.get("recommendation", ""),
            }
            research["catalysts_and_outlook"] = {
                "summary": data.get("investment_summary", data.get("summary", "")),
                "catalysts": data.get("catalysts", []),
            }
        else:
            # Store any unknown section directly
            research[section] = data

    # Ensure unit_economics exists
    if "unit_economics" not in research:
        bm = research.get("business_model", {})
        if isinstance(bm, dict) and "unit_economics" in bm:
            research["unit_economics"] = {
                "summary": bm.get("summary", ""),
                "metrics": bm["unit_economics"],
                "confidence": bm.get("confidence", "Medium"),
            }
        else:
            research["unit_economics"] = {"summary": "", "metrics": {}, "confidence": "Low"}

    # Build dashboard metrics
    research["dashboard_metrics"] = {"metrics": _build_dashboard_metrics(research), "sources": []}
    research["all_sources"] = sources
    research["_run_id"] = run_id

    return research


def _format_market_size(ms: Any) -> str:
    if isinstance(ms, str):
        return ms
    if isinstance(ms, dict):
        parts = []
        for k in ("tam", "sam", "som"):
            if ms.get(k):
                parts.append(f"{k.upper()}: {ms[k]}")
        return ". ".join(parts) if parts else ""
    return ""


def _build_dashboard_metrics(research: dict) -> list[dict]:
    metrics = []
    fin = research.get("financial_signals", {})
    if isinstance(fin, dict):
        if fin.get("arr_trajectory"):
            metrics.append({"label": "Est. ARR", "value": _first_number_or_text(fin["arr_trajectory"]), "trend": "up"})
        if fin.get("revenue_growth_cagr"):
            metrics.append({"label": "Revenue Growth", "value": _first_number_or_text(fin["revenue_growth_cagr"]), "trend": "up"})
        if fin.get("total_funding"):
            metrics.append({"label": "Total Funding", "value": _first_number_or_text(fin["total_funding"]), "trend": "up"})

    ue = research.get("unit_economics", {})
    if isinstance(ue, dict):
        m = ue.get("metrics", {})
        if isinstance(m, dict):
            for key, label, trend in [
                ("nrr_ndr", "NRR", "up"), ("gross_margin", "Gross Margin", "up"),
                ("ltv_cac_ratio", "LTV:CAC", "up"), ("rule_of_40_score", "Rule of 40", "up"),
                ("logo_retention", "Logo Retention", "flat"),
            ]:
                if m.get(key):
                    metrics.append({"label": label, "value": _first_number_or_text(str(m[key])), "trend": trend})

    risk = research.get("risk_assessment", {})
    if isinstance(risk, dict) and risk.get("overall_risk_rating"):
        metrics.append({"label": "Risk Rating", "value": risk["overall_risk_rating"][:15], "trend": "flat"})

    return metrics[:10]


def _first_number_or_text(s: str) -> str:
    if not s:
        return "N/A"
    m = re.match(r'(\$[\d.,]+[BMK]?\+?|[\d.,]+%|[\d.,]+x)', s)
    return m.group(1) if m else s[:20].strip()


def _score_research(research: dict) -> int:
    score = 100
    for s in ["company_profile", "management_team", "product_and_technology",
              "business_model", "financial_signals", "market_landscape",
              "risk_assessment", "investment_view"]:
        if s not in research or not research[s]:
            score -= 10
    if len(research.get("all_sources", [])) < 10:
        score -= 15
    if len(research.get("dashboard_metrics", {}).get("metrics", [])) < 6:
        score -= 10
    return max(0, score)


# ═══════════════════════════════════════════════════════════════
# Mock research
# ═══════════════════════════════════════════════════════════════

def _mock_tool_result(company: str, section: str) -> dict[str, Any]:
    """Realistic mock data per section."""
    mocks = {
        "company_profile": {
            "summary": f"{company} is a leading AI company founded in 2021 in San Francisco. Raised $7.3B+, employs ~1,000-1,500 people. Develops the Claude AI model family for enterprise and API customers globally. Valued at $18.4B as of latest funding round.",
            "founded": "2021", "headquarters": "San Francisco, CA",
            "employee_estimate": "1,000-1,500 (LinkedIn analysis)",
            "key_facts": ["$7.3B+ total funding", "Claude AI model family", "200+ enterprise customers", "$1B+ ARR run rate estimated"],
        },
        "management_team": {
            "summary": "World-class team: CEO Dario Amodei (former OpenAI VP Research, PhD Princeton), President Daniela Amodei (former OpenAI VP), CPO Mike Krieger (Instagram co-founder). Deep bench of AI researchers from Google Brain, DeepMind, and top universities.",
            "executives": [
                {"name": "Dario Amodei", "title": "CEO & Co-Founder", "background": "Former VP Research at OpenAI, led GPT-2/GPT-3. PhD computational neuroscience Princeton.", "signal": "Top-tier AI research leadership"},
                {"name": "Daniela Amodei", "title": "President & Co-Founder", "background": "Former VP Safety & Policy at OpenAI. Previously Stripe. Financial services background.", "signal": "Strong operational scaling"},
                {"name": "Mike Krieger", "title": "Chief Product Officer", "background": "Co-founder & former CTO of Instagram ($1B acquisition by Meta). Stanford CS.", "signal": "Consumer-grade product expertise applied to enterprise AI"},
            ],
            "key_man_risk": "Moderate — Amodei siblings are co-founders with significant equity. Deep bench of research talent mitigates.",
        },
        "product_and_technology": {
            "summary": "Claude AI model family is core product. Claude 3.5 Sonnet achieves SOTA on major benchmarks. Constitutional AI provides unique safety framework. Products: API (pay-per-token), Claude.ai Pro ($20/mo), Claude for Enterprise (SSO, admin, data privacy). 200K context window is competitive advantage.",
            "core_offerings": ["Claude API (~60% revenue)", "Claude Enterprise (~30%)", "Claude.ai Pro (~10%)"],
            "moat_hypothesis": "Constitutional AI + frontier performance + enterprise trust + Amazon partnership distribution. Confidence: Medium-High.",
            "tech_differentiation": ["200K context window", "Constitutional AI (unique)", "97th percentile HumanEval", "SOC 2 Type II"],
        },
        "financial_signals": {
            "summary": "Explosive growth: $1B+ ARR estimated (2024), ~80-100% Y/Y. $7.3B total funding. Amazon $4B strategic investment. Last valuation $18.4B. Burn est. $50-100M/month offset by $3B+ cash.",
            "arr_trajectory": "$1B+ ARR (2024 est); $300-500M in 2023",
            "funding_rounds": [
                {"round": "Series A", "date": "2021", "amount": "$124M", "lead_investor": "Jaan Tallinn", "valuation": "$4.1B"},
                {"round": "Series B", "date": "2023", "amount": "$450M", "lead_investor": "Spark Capital", "valuation": "$4.1B"},
                {"round": "Series C", "date": "2023", "amount": "$2B", "lead_investor": "Google", "valuation": "$18.4B"},
                {"round": "Series D", "date": "2024", "amount": "$4B", "lead_investor": "Amazon", "valuation": "$18.4B"},
            ],
            "total_funding": "$7.3B+",
            "valuation_signal": "$18.4B (Series D). ~18x forward revenue.",
            "burn_vs_growth_signal": "Burn $50-100M/month. $3B+ cash. Runway 3+ years.",
            "revenue_growth_cagr": "80-100% Y/Y",
        },
        "business_model": {
            "summary": "Hybrid: API usage-based ($3-75/MTok) + enterprise platform ($100K-$1M+ ACV) + consumer Pro ($20/mo). 140-160% est. NRR from usage expansion. 50-60% gross margin (GPU-intensive).",
            "pricing_motion": "API: $3-$15/MTok input, $15-$75/MTok output. Enterprise: $100K-$1M+. Pro: $20/month.",
            "customer_segments": ["Enterprise ~45% rev", "Developer/API ~40%", "Consumer Pro ~15%"],
            "revenue_composition": {"subscriptions_pct": "55%", "usage_based_pct": "40%", "professional_services_pct": "5%"},
            "unit_economics": {
                "cac_estimate": "$30,000-$60,000", "ltv_estimate": "$200,000-$400,000",
                "ltv_cac_ratio": "5-7x", "nrr_ndr": "140-160%",
                "gross_margin": "50-60%", "payback_period_months": "10-14",
                "rule_of_40_score": "100+", "logo_retention": "92-96%",
            },
            "confidence": "Medium",
        },
        "market_and_competition": {
            "market_summary": "Enterprise AI/LLM market: $150-200B by 2028, 35-45% CAGR. Foundation model TAM ~$50B. Anthropic in top-3 position behind OpenAI.",
            "competitors": ["OpenAI", "Google DeepMind", "Meta AI", "Mistral AI", "Cohere", "Amazon Bedrock", "Microsoft Azure OpenAI"],
            "market_size": {"tam": "$150-200B by 2028", "sam": "$50-80B", "som": "$5-10B"},
            "industry_trends": ["70% Fortune 500 have production AI", "Model commoditization favors safety layer", "AI regulation creates barriers for new entrants", "GPU costs declining 30-40% annually"],
            "positioning_matrix": [
                {"competitor": "OpenAI", "strengths": "Largest brand, GPT-4o, Microsoft", "weaknesses": "Safety concerns, enterprise trust", "vs_target": "Anthropic wins on safety and trust"},
                {"competitor": "Google DeepMind", "strengths": "Gemini, massive compute, cloud", "weaknesses": "Slower enterprise GTM", "vs_target": "Anthropic wins on focus and DX"},
                {"competitor": "Meta AI (LLaMA)", "strengths": "Open-source, free", "weaknesses": "No enterprise support or SLA", "vs_target": "Anthropic wins on enterprise features"},
            ],
            "key_differentiators": ["Constitutional AI", "Enterprise trust (SOC 2, no training on data)", "200K context", "Amazon distribution"],
        },
        "customer_evidence": {
            "summary": "200+ enterprise customers. Top-5 US banks, Fortune 50 tech companies, consulting firms. G2: 4.7/5.0 (400+ reviews). Logo retention 92-96%. NRR 140-160%.",
            "logo_highlights": ["Top-5 US banks", "3+ Fortune 50 tech", "Deloitte, Accenture"],
            "concentration_risk": "Top 10 est. 20-30% of revenue. Amazon is largest relationship.",
            "churn_signals": "Logo retention 92-96%. Revenue retention 140-160%.",
            "nps_proxy": "G2: 4.7/5.0 (400+ reviews). #1 most admired AI tool (Stack Overflow).",
            "case_studies": ["Consulting firm: 40% faster reports, $10M+ savings", "Financial services: 50% reduction compliance time"],
        },
        "comparable_transactions": {
            "summary": "AI valuations elevated: 15-40x forward revenue for frontier companies. Supports $15-30B range for Anthropic.",
            "private_transactions": [
                {"target": "OpenAI", "acquirer_investor": "Microsoft, Thrive", "deal_value": "$157B (2024)", "revenue_multiple": "~40x", "date": "2024"},
                {"target": "Databricks", "acquirer_investor": "Series J", "deal_value": "$62B (2024)", "revenue_multiple": "~25x", "date": "2024"},
                {"target": "Scale AI", "acquirer_investor": "Series F", "deal_value": "$13.8B", "revenue_multiple": "~18x", "date": "2024"},
            ],
            "public_comps": [
                {"company": "Palantir (PLTR)", "ev_revenue_multiple": "25x NTM", "growth_rate": "~20%"},
                {"company": "Snowflake (SNOW)", "ev_revenue_multiple": "12x NTM", "growth_rate": "~28%"},
                {"company": "Datadog (DDOG)", "ev_revenue_multiple": "15x NTM", "growth_rate": "~25%"},
            ],
            "implied_valuation_range": "$15B-$30B at 15-30x forward revenue",
        },
        "risk_and_regulatory": {
            "risk_summary": "Primary: GPU cost dependency, hyperscaler competition, AI regulatory uncertainty. Net positive risk/reward with differentiated safety positioning.",
            "key_risks": [
                {"risk": "GPU compute dependency", "severity": "High", "probability": "90%", "mitigation": "Amazon partnership, inference efficiency gains"},
                {"risk": "OpenAI/Google competition", "severity": "High", "probability": "95%", "mitigation": "Safety-first positioning, enterprise trust moat"},
                {"risk": "AI regulatory disruption", "severity": "Medium", "probability": "60%", "mitigation": "Safety positioning benefits from regulation"},
                {"risk": "Key person risk (Amodei founders)", "severity": "Medium", "probability": "20%", "mitigation": "Equity retention, deep research bench"},
                {"risk": "Gross margin compression", "severity": "Medium-High", "probability": "70%", "mitigation": "Custom silicon, pricing power"},
            ],
            "overall_risk_rating": "Medium-High — exceptional position but existential competitive risks",
            "ip_exposure": "Constitutional AI proprietary. No IP litigation.",
            "data_privacy": "SOC 2 Type II. No training on customer data. GDPR compliant.",
            "regulatory_moats": ["Safety-first benefits from regulation", "SOC 2 + data guarantees"],
            "regulatory_risks": ["EU AI Act: $5-10M/year", "US AI licensing potential"],
        },
        "exit_and_investment": {
            "exit_summary": "IPO primary (2026-2027). Amazon strategic acquisition secondary. $30B-$80B exit range.",
            "strategic_acquirers": [
                {"acquirer": "Amazon", "rationale": "Already $4B invested. Bedrock AI. Compete with MSFT/OpenAI.", "willingness": "High"},
                {"acquirer": "Google", "rationale": "Already $2B+ invested. Hedge vs DeepMind.", "willingness": "Medium"},
                {"acquirer": "Salesforce", "rationale": "Einstein AI platform. Enterprise overlap.", "willingness": "Medium-High"},
            ],
            "ipo_readiness": {"assessment": "IPO-ready 2026-2027. $1B+ ARR, 80%+ growth.", "comparable_ipos": "15-30x NTM for 40%+ growth"},
            "exit_multiples": {"bear_case": "15x ($15-20B)", "base_case": "25x ($25-40B)", "bull_case": "40x ($40-80B)"},
            "implied_irr": {"bear_case": "5-10%", "base_case": "25-40%", "bull_case": "50-80%+"},
            "investment_summary": "Generational opportunity in frontier AI. Asymmetric risk/reward: downside protected by strategic value (Amazon/Google), upside driven by secular AI adoption.",
            "base_case": "Base ($25-40B, 25-40% IRR): 50-80% growth to $2-3B ARR. IPO at 20-25x. Prob: 50%.",
            "upside_case": "Upside ($40-80B, 50-80% IRR): Category leader, govt contracts, 30-40x exit. Prob: 25%.",
            "downside_case": "Downside ($15-20B, 5-10% IRR): Commoditization, 30% growth, 12-15x exit. Protected by preferred. Prob: 25%.",
            "recommendation": "STRONG PROCEED — Top-3 AI company with safety moat and hyperscaler backing.",
        },
    }
    return mocks.get(section, {"summary": f"Mock data for {section}"})


def _run_mock_research(company: str, run_id: str) -> dict[str, Any]:
    """Generate mock research with workspace writes."""
    sections = ["company_profile", "management_team", "product_and_technology",
                 "financial_signals", "business_model", "market_and_competition",
                 "customer_evidence", "comparable_transactions", "risk_and_regulatory",
                 "exit_and_investment"]

    for section in sections:
        data = _mock_tool_result(company, section)
        write_finding(run_id, company, section, json.dumps(data), [])

    mock_sources = [
        ("Company Website", "https://anthropic.com"), ("Crunchbase", "https://crunchbase.com/organization/anthropic"),
        ("LinkedIn", "https://linkedin.com/company/anthropic"), ("TechCrunch", "https://techcrunch.com/tag/anthropic"),
        ("Bloomberg", "https://bloomberg.com/anthropic"), ("G2 Reviews", "https://g2.com/products/claude"),
        ("Gartner", "https://gartner.com/ai-platforms"), ("PitchBook", "https://pitchbook.com/anthropic"),
        ("SEC Filings", "https://sec.gov/anthropic"), ("McKinsey AI Report", "https://mckinsey.com/ai-2024"),
        ("Amazon Partnership", "https://aboutamazon.com/anthropic"), ("Product Docs", "https://docs.anthropic.com"),
        ("Safety Research", "https://anthropic.com/research"), ("CB Insights", "https://cbinsights.com/ai-landscape"),
        ("IDC Forecast", "https://idc.com/ai-forecast"), ("EU AI Act", "https://digital-strategy.ec.europa.eu/ai-act"),
        ("Careers Page", "https://anthropic.com/careers"), ("Investor Report", "https://example.com/ai-investing"),
    ]
    for title, url in mock_sources:
        write_source(run_id, company, title, url, "Mock source")

    return _assemble_research(company, run_id)
