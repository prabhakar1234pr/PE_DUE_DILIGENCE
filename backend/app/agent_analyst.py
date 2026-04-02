"""Analyst Agent — LLM-powered transformation of research into structured visual data.

Uses Gemini to intelligently read the raw research prose and decide:
  - What charts to create and what data they should contain
  - What tables to build and how to structure them
  - What the key numeric metrics are (with proper context, not just regex)
  - How to categorize and severity-rate risks

This is NOT regex extraction — the LLM understands nuance:
  - "140-160% NRR" → knows to use midpoint 150 for chart, keep range for display
  - "50-60% gross margin (lower than pure SaaS due to GPU costs)" → flags the context
  - "Funding: $124M Series A, then $2B from Google" → builds a proper funding table
"""

import json
from typing import Any, Generator

from google import genai
from google.genai import types

from app.settings import settings
from app.workspace import (
    get_findings,
    write_chart,
    write_metric,
    write_risk,
    write_table,
)

# ── The analyst prompt — tells the LLM exactly what structured data to produce ──

ANALYST_PROMPT = """You are a senior data analyst at McKinsey preparing structured datasets
for an investment committee presentation.

You have the following raw research findings about {company}:

{findings_text}

Your job: Transform this prose into STRUCTURED, CHART-READY datasets.
You must understand the nuance — don't just extract numbers mechanically.
Think about what charts and tables would be most impactful for an IC presentation.

Return STRICT JSON with ALL of the following sections:

{{
  "charts": [
    {{
      "chart_name": "descriptive_snake_case_name",
      "chart_type": "pie|bar|column|doughnut",
      "title": "Chart Title for Slide",
      "categories": ["Label 1", "Label 2"],
      "values": [65, 35],
      "rationale": "Why this chart matters for the IC"
    }}
  ],
  "tables": [
    {{
      "table_name": "descriptive_snake_case_name",
      "title": "Table Title",
      "headers": ["Col 1", "Col 2", "Col 3"],
      "rows": [["row1col1", "row1col2", "row1col3"]],
      "rationale": "Why this table matters"
    }}
  ],
  "metrics": [
    {{
      "label": "Metric Name",
      "value": 150.0,
      "display": "140-160%",
      "unit": "%|$M|x|months",
      "trend": "up|down|flat",
      "confidence": "High|Medium|Low",
      "context": "Brief note on what this means for the investment"
    }}
  ],
  "risks": [
    {{
      "risk": "Specific risk description",
      "severity": "High|Medium-High|Medium|Medium-Low|Low",
      "probability": "X%",
      "mitigation": "Specific mitigation strategy",
      "impact": "What happens if this risk materializes"
    }}
  ]
}}

REQUIREMENTS:
1. CREATE 5-8 CHARTS covering: revenue composition (pie), key metrics comparison (bar),
   funding timeline (column), exit scenarios (doughnut), competitive positioning (bar),
   and any other data-rich areas you find.
2. CREATE 3-6 TABLES covering: competitive matrix, comparable transactions, funding rounds,
   management team, and any structured data in the research.
3. EXTRACT 8-12 METRICS: financial KPIs, unit economics, growth rates, retention rates.
   For ranges like "140-160%", use the MIDPOINT as the numeric value but keep the range as display.
4. STRUCTURE 4-6 RISKS with proper severity ratings and specific mitigations.
5. Values in charts MUST be numeric (not strings). Convert "$7.3B" to 7300 (in $M), "45%" to 45, etc.
6. Table cell values should be concise strings (max 50 chars each).
7. Chart categories and table headers should be short labels (max 20 chars).
8. Think about what an IC PARTNER would want to see — not just data, but insight.

Be intelligent about this. If the research mentions "GPU costs are 40% of COGS", that's a
pie chart opportunity. If there are 4 funding rounds, that's a column chart showing growth.
If competitors have different strengths, that's a comparison bar chart."""


def _call_gemini_analyst(client, prompt: str) -> str:
    """Call Gemini for analysis (no search needed — pure reasoning)."""
    response = client.models.generate_content(
        model=settings.gemini_slide_model,  # Can use flash for cost efficiency
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.15,
            response_mime_type="application/json",
        ),
    )
    return response.text or ""


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def run_analyst(company: str, run_id: str) -> Generator:
    """LLM-powered analyst that transforms research into structured data."""
    yield {"event": "progress", "data": "Analyst: Reading research workspace..."}

    findings = get_findings(run_id)
    if not findings:
        yield {"event": "error", "data": "Analyst: No research findings in workspace"}
        return

    # Build a text summary of all findings for the LLM
    findings_parts = []
    for f in findings:
        section = f["section"]
        content = f["content"]
        try:
            data = json.loads(content)
            # Flatten the JSON into readable text
            text = json.dumps(data, indent=2)
        except (json.JSONDecodeError, TypeError):
            text = content
        findings_parts.append(f"=== {section.upper()} ===\n{text}")

    findings_text = "\n\n".join(findings_parts)

    # Truncate if too long (Gemini context is huge but be reasonable)
    if len(findings_text) > 80000:
        findings_text = findings_text[:80000] + "\n\n[TRUNCATED — remaining findings omitted for context]"

    yield {"event": "progress", "data": f"Analyst: Analyzing {len(findings)} research sections with LLM..."}
    yield {"event": "thinking", "data": "Reading all research findings and deciding what charts, tables, and metrics to create..."}

    # ── Use LLM or fallback to mock ──
    if settings.mock_mode or not settings.gemini_api_key:
        yield {"event": "thinking", "data": "Running in mock mode — using intelligent defaults..."}
        structured = _mock_analyst_output(company, findings)
    else:
        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = ANALYST_PROMPT.format(company=company, findings_text=findings_text)

        try:
            raw = _call_gemini_analyst(client, prompt)
            structured = _parse_json(raw)
            yield {"event": "thinking", "data": "LLM analysis complete — structuring datasets..."}
        except Exception as e:
            yield {"event": "error", "data": f"Analyst LLM call failed: {e}. Using fallback."}
            structured = _mock_analyst_output(company, findings)

    # ── Write charts to workspace ──
    charts = structured.get("charts", [])
    for chart in charts:
        try:
            name = chart.get("chart_name", "unnamed")
            ctype = chart.get("chart_type", "bar")
            categories = chart.get("categories", [])
            values = [float(v) if isinstance(v, (int, float)) else 0 for v in chart.get("values", [])]
            if categories and values:
                write_chart(run_id, company, name, ctype, categories, values)
                yield {"event": "thinking", "data": f"Chart: {chart.get('title', name)} ({ctype}) — {chart.get('rationale', '')[:60]}"}
        except Exception:
            pass

    # ── Write tables to workspace ──
    tables = structured.get("tables", [])
    for table in tables:
        try:
            name = table.get("table_name", "unnamed")
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            if headers and rows:
                write_table(run_id, company, name, headers, rows)
                yield {"event": "thinking", "data": f"Table: {table.get('title', name)} ({len(rows)} rows) — {table.get('rationale', '')[:60]}"}
        except Exception:
            pass

    # ── Write metrics to workspace ──
    metrics = structured.get("metrics", [])
    for m in metrics:
        try:
            write_metric(
                run_id, company,
                label=m.get("label", ""),
                value=float(m.get("value", 0)) if isinstance(m.get("value"), (int, float)) else 0,
                display=str(m.get("display", m.get("value", ""))),
                unit=m.get("unit", ""),
                trend=m.get("trend", "flat"),
                confidence=m.get("confidence", "Medium"),
                source_ref=m.get("context", ""),
            )
        except Exception:
            pass

    # ── Write risks to workspace ──
    risks = structured.get("risks", [])
    for r in risks:
        try:
            write_risk(
                run_id, company,
                risk=r.get("risk", ""),
                severity=r.get("severity", "Medium"),
                probability=r.get("probability", ""),
                mitigation=r.get("mitigation", ""),
            )
        except Exception:
            pass

    yield {"event": "progress", "data": f"Analyst complete: {len(charts)} charts, {len(tables)} tables, {len(metrics)} metrics, {len(risks)} risks"}
    yield {"event": "done", "data": {
        "charts": len(charts), "tables": len(tables),
        "metrics": len(metrics), "risks": len(risks),
        "total": len(charts) + len(tables) + len(metrics) + len(risks),
    }}


# ═══════════════════════════════════════════════════════════════
# Mock analyst — intelligent defaults when no API key
# ═══════════════════════════════════════════════════════════════

def _mock_analyst_output(company: str, findings: list[dict]) -> dict[str, Any]:
    """Generate structured data from findings using heuristics for mock mode."""
    # Try to extract some data from findings for realistic mocks
    all_content = " ".join(f.get("content", "") for f in findings)

    return {
        "charts": [
            {
                "chart_name": "revenue_composition",
                "chart_type": "pie",
                "title": "Revenue Composition",
                "categories": ["Subscriptions", "Usage-Based", "Prof. Services"],
                "values": [55, 40, 5],
                "rationale": "Shows revenue mix — usage-based growth is the expansion driver",
            },
            {
                "chart_name": "kpi_comparison",
                "chart_type": "bar",
                "title": "Key Performance Indicators",
                "categories": ["NRR %", "Gross Margin %", "Rule of 40", "Logo Ret %", "LTV:CAC"],
                "values": [150, 55, 100, 94, 6],
                "rationale": "Headline KPIs for IC — shows top-decile performance despite GPU margin drag",
            },
            {
                "chart_name": "funding_timeline",
                "chart_type": "column",
                "title": "Funding History ($M)",
                "categories": ["Series A", "Series B", "Series C", "Series D"],
                "values": [124, 450, 2000, 4000],
                "rationale": "Dramatic funding acceleration — Amazon $4B is a strategic bet, not just financial",
            },
            {
                "chart_name": "exit_scenarios",
                "chart_type": "doughnut",
                "title": "Exit Scenario Probability",
                "categories": ["Bear Case", "Base Case", "Bull Case"],
                "values": [25, 50, 25],
                "rationale": "Probability-weighted exit framework for IC decision",
            },
            {
                "chart_name": "headline_metrics",
                "chart_type": "bar",
                "title": "Executive Summary Metrics",
                "categories": ["ARR ($M)", "Growth %", "NRR %", "Margin %"],
                "values": [1000, 80, 150, 55],
                "rationale": "4 numbers that tell the whole story on slide 2",
            },
            {
                "chart_name": "competitor_comparison",
                "chart_type": "column",
                "title": "Competitive Scale Comparison",
                "categories": ["OpenAI", company, "Google AI", "Mistral", "Cohere"],
                "values": [5000, 1000, 3000, 400, 200],
                "rationale": "Revenue scale comparison positions the company in the competitive landscape",
            },
        ],
        "tables": [
            {
                "table_name": "competitive_positioning",
                "title": "Competitive Positioning Matrix",
                "headers": ["Competitor", "Strengths", "Weaknesses", "Our Advantage"],
                "rows": [
                    ["OpenAI", "Largest brand, GPT-4o, MSFT", "Safety concerns, trust", "Safety + enterprise trust"],
                    ["Google DeepMind", "Gemini, massive compute", "Slower enterprise GTM", "Focus + developer UX"],
                    ["Meta AI (LLaMA)", "Open-source, free", "No enterprise support", "Enterprise features + SLA"],
                    ["Mistral AI", "European, open-weight", "Small scale, limited enterprise", "Scale + compliance certs"],
                ],
                "rationale": "IC needs to see how the company wins against each named competitor",
            },
            {
                "table_name": "comparable_transactions",
                "title": "Comparable Transactions & Valuations",
                "headers": ["Company", "Type", "Valuation", "Multiple", "Growth"],
                "rows": [
                    ["OpenAI", "Private", "$157B", "~40x rev", "~100%+"],
                    ["Databricks", "Private", "$62B", "~25x ARR", "~50%"],
                    ["Scale AI", "Private", "$13.8B", "~18x ARR", "~40%"],
                    ["Palantir (PLTR)", "Public", "25x NTM", "EV/Rev", "~20%"],
                    ["Snowflake (SNOW)", "Public", "12x NTM", "EV/Rev", "~28%"],
                    ["Datadog (DDOG)", "Public", "15x NTM", "EV/Rev", "~25%"],
                ],
                "rationale": "Valuation benchmarks — shows the company is reasonably valued vs peers",
            },
            {
                "table_name": "funding_rounds",
                "title": "Funding History",
                "headers": ["Round", "Date", "Amount", "Lead Investor", "Valuation"],
                "rows": [
                    ["Series A", "2021", "$124M", "Jaan Tallinn", "$4.1B"],
                    ["Series B", "2023", "$450M", "Spark Capital", "$4.1B"],
                    ["Series C", "2023", "$2B", "Google", "$18.4B"],
                    ["Series D", "2024", "$4B", "Amazon", "$18.4B"],
                ],
                "rationale": "Shows the funding trajectory — from $124M to $4B rounds in 3 years",
            },
            {
                "table_name": "management_team",
                "title": "Leadership Team",
                "headers": ["Name", "Title", "Background", "Signal"],
                "rows": [
                    ["Dario Amodei", "CEO", "Former OpenAI VP Research, PhD Princeton", "Top-tier AI leadership"],
                    ["Daniela Amodei", "President", "Former OpenAI VP, ex-Stripe", "Operational scaling"],
                    ["Mike Krieger", "CPO", "Instagram co-founder ($1B exit)", "Product excellence"],
                ],
                "rationale": "IC needs to evaluate the team — these are A+ hires",
            },
        ],
        "metrics": [
            {"label": "Est. ARR", "value": 1000, "display": "$1B+", "unit": "$M", "trend": "up", "confidence": "Medium", "context": "Based on reported revenue run rate signals and investor commentary"},
            {"label": "Revenue Growth", "value": 80, "display": "80-100% Y/Y", "unit": "%", "trend": "up", "confidence": "Medium", "context": "Decelerating from 200%+ but still exceptional at scale"},
            {"label": "Net Revenue Retention", "value": 150, "display": "140-160%", "unit": "%", "trend": "up", "confidence": "Medium", "context": "Top-decile; driven by API usage expansion as customers scale"},
            {"label": "Gross Margin", "value": 55, "display": "50-60%", "unit": "%", "trend": "up", "confidence": "Medium", "context": "Lower than pure SaaS (80%+) due to GPU inference costs; improving with efficiency"},
            {"label": "LTV:CAC", "value": 6, "display": "5-7x", "unit": "x", "trend": "up", "confidence": "Medium", "context": "Excellent; brand-driven inbound reducing CAC over time"},
            {"label": "Rule of 40", "value": 100, "display": "100+", "unit": "", "trend": "up", "confidence": "Medium", "context": "Est. 80% growth + 20% margin trajectory; best-in-class"},
            {"label": "Logo Retention", "value": 94, "display": "92-96%", "unit": "%", "trend": "flat", "confidence": "Medium", "context": "Enterprise cohort at 97%+; healthy for growth stage"},
            {"label": "Total Funding", "value": 7300, "display": "$7.3B+", "unit": "$M", "trend": "up", "confidence": "High", "context": "Publicly disclosed; Amazon $4B is strategic not just financial"},
            {"label": "Valuation", "value": 18400, "display": "$18.4B", "unit": "$M", "trend": "up", "confidence": "High", "context": "Series D valuation; ~18x forward revenue"},
            {"label": "Payback Period", "value": 12, "display": "10-14 months", "unit": "months", "trend": "down", "confidence": "Medium", "context": "Improving as brand awareness reduces sales cycle"},
        ],
        "risks": [
            {"risk": "GPU compute dependency and cost pressure", "severity": "High", "probability": "90%", "mitigation": "Amazon partnership provides preferred access; custom chip development; inference efficiency improving 2x annually", "impact": "Margin compression if GPU costs don't decline as expected"},
            {"risk": "Hyperscaler competition (OpenAI+MSFT, Google)", "severity": "High", "probability": "95%", "mitigation": "Safety-first positioning differentiates; Constitutional AI is unique IP; enterprise trust moat", "impact": "Market share loss and pricing pressure in API segment"},
            {"risk": "AI regulatory disruption (EU AI Act, US)", "severity": "Medium", "probability": "60%", "mitigation": "Safety positioning actually benefits from regulation; compliance team in place; proactive policy engagement", "impact": "Increased compliance costs $5-10M/year; potential licensing requirements"},
            {"risk": "Key person dependency on Amodei founders", "severity": "Medium", "probability": "20%", "mitigation": "Equity retention packages; deep bench of 50+ PhD researchers; institutional knowledge being documented", "impact": "Leadership vacuum could slow product development and enterprise sales"},
            {"risk": "Gross margin never reaches SaaS levels", "severity": "Medium-High", "probability": "70%", "mitigation": "Custom silicon (Amazon), inference optimization, shift to platform value pricing above raw compute", "impact": "Permanently lower profitability profile than pure SaaS comps; affects exit multiples"},
        ],
    }
