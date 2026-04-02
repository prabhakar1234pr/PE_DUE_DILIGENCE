"""Research Agent — Multi-pass deep search with workspace tools.

Architecture:
  - Each "tool" is a focused Gemini + Google Search call for one section
  - Results are written to the SQLite workspace as raw findings + sources
  - The agent orchestrates 10 focused search passes sequentially
  - Each pass streams events (thinking, search queries, sources found)
  - Quality is evaluated after all passes complete
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

# ── Research sections and their focused search prompts ────────

RESEARCH_TOOLS = [
    {
        "section": "company_profile",
        "label": "Company Profile",
        "prompt_template": """Research {company}: company overview, founding year, headquarters, employee count,
key facts. Include specific numbers: founding year, HQ city, employee estimate with methodology,
total funding raised, number of customers. Return JSON:
{{"summary": "400+ chars", "founded": "year", "headquarters": "city",
"employee_estimate": "range with source", "key_facts": ["fact with number", "fact2", "fact3"]}}""",
    },
    {
        "section": "management_team",
        "label": "Management Team",
        "prompt_template": """Research {company} leadership team: CEO, CTO, CFO, and other key executives.
For EACH person provide: full name, title, previous companies, notable achievements, education.
Minimum 3 named individuals. Return JSON:
{{"summary": "400+ chars assessing leadership quality",
"executives": [{{"name": "Full Name", "title": "CEO", "background": "prior companies and achievements", "signal": "investment implication"}}],
"key_man_risk": "assessment with specific mitigants"}}""",
    },
    {
        "section": "product_and_technology",
        "label": "Product & Technology",
        "prompt_template": """Research {company} products and technology: core product offerings, technical architecture,
patents, competitive technical advantages, deployment models. Quantify where possible.
Return JSON:
{{"summary": "400+ chars", "core_offerings": ["offering with revenue contribution estimate"],
"moat_hypothesis": "specific defensibility thesis with evidence and confidence",
"tech_differentiation": ["specific advantage with quantification"]}}""",
    },
    {
        "section": "business_model",
        "label": "Business Model & Unit Economics",
        "prompt_template": """Research {company} business model AND unit economics: pricing tiers, ACV ranges,
contract structure, revenue composition (subscription vs usage vs services %),
CAC estimate, LTV estimate, LTV:CAC ratio, NRR/NDR %, gross margin %, payback period,
Rule of 40 score. Use benchmarks from SaaS peers if exact data unavailable.
Return JSON:
{{"summary": "400+ chars", "pricing_motion": "specific tiers and ACVs",
"customer_segments": ["segment with revenue share and ACV range"],
"revenue_composition": {{"subscriptions_pct": "X%", "usage_based_pct": "Y%", "professional_services_pct": "Z%"}},
"unit_economics": {{
  "cac_estimate": "$ range", "ltv_estimate": "$ range", "ltv_cac_ratio": "Xx",
  "nrr_ndr": "X%", "gross_margin": "X%", "payback_period_months": "X months",
  "rule_of_40_score": "X", "logo_retention": "X%"
}},
"confidence": "High/Medium/Low with methodology"}}""",
    },
    {
        "section": "financial_signals",
        "label": "Financial Signals",
        "prompt_template": """Research {company} financials: ARR/revenue trajectory, funding rounds (every round with
date, amount, lead investor, valuation), burn rate, runway, revenue growth CAGR.
Name specific investors and round details. Return JSON:
{{"summary": "400+ chars", "arr_trajectory": "specific ARR range with historical data points",
"funding_rounds": [{{"round": "Series X", "date": "YYYY", "amount": "$XM", "lead_investor": "Name", "valuation": "$XB"}}],
"total_funding": "$XM+", "valuation_signal": "last valuation with implied multiples",
"burn_vs_growth_signal": "monthly burn, runway, burn multiple",
"revenue_growth_cagr": "X% with historical context"}}""",
    },
    {
        "section": "market_and_competition",
        "label": "Market Landscape & Competition",
        "prompt_template": """Research {company} market and competitive landscape: TAM/SAM/SOM with sources,
named competitors (5+), competitive positioning matrix (strengths/weaknesses vs each competitor),
industry trends with quantification, market growth rate.
Return JSON:
{{"market_summary": "400+ chars with TAM/SAM/SOM",
"competitors": ["5+ named competitors"],
"market_size": {{"tam": "$XB by YYYY", "sam": "$XB", "som": "$XB"}},
"industry_trends": ["trend with number"],
"positioning_matrix": [{{"competitor": "Name", "strengths": "specific", "weaknesses": "specific", "vs_target": "how target wins/loses"}}],
"key_differentiators": ["differentiator with evidence"]}}""",
    },
    {
        "section": "customer_evidence",
        "label": "Customer Evidence",
        "prompt_template": """Research {company} customers: notable customer logos/categories, customer concentration,
churn and retention signals, NPS/review scores (G2, Gartner), published case studies with ROI metrics.
Return JSON:
{{"summary": "300+ chars", "logo_highlights": ["named categories or logos"],
"concentration_risk": "top 10 customer share", "churn_signals": "retention data",
"nps_proxy": "review scores with sources", "case_studies": ["ROI example with metrics"]}}""",
    },
    {
        "section": "comparable_transactions",
        "label": "Comparable Transactions",
        "prompt_template": """Research comparable M&A transactions and public company valuations relevant to {company}.
Find: 3+ private M&A/funding transactions with target name, acquirer/investor, deal value, revenue multiple.
Find: 3+ public company comparables with ticker, EV/Revenue multiple, growth rate.
Return JSON:
{{"summary": "300+ chars",
"private_transactions": [{{"target": "Name", "acquirer_investor": "Name", "deal_value": "$XB", "revenue_multiple": "Xx", "date": "YYYY"}}],
"public_comps": [{{"company": "Name (TICKER)", "ev_revenue_multiple": "Xx NTM", "growth_rate": "X% Y/Y"}}],
"implied_valuation_range": "$XB-$YB based on methodology"}}""",
    },
    {
        "section": "risk_and_regulatory",
        "label": "Risks & Regulatory",
        "prompt_template": """Research {company} risks and regulatory landscape:
Key risks with severity (High/Medium/Low), probability, and specific mitigations.
IP/patent status, data privacy compliance, regulatory moats and risks.
Minimum 4 risks. Return JSON:
{{"risk_summary": "400+ chars overall assessment",
"key_risks": [{{"risk": "specific risk", "severity": "High/Medium/Low", "probability": "X%", "mitigation": "specific"}}],
"overall_risk_rating": "rating with rationale",
"ip_exposure": "patent status", "data_privacy": "compliance status",
"regulatory_moats": ["moat"], "regulatory_risks": ["risk with cost impact"]}}""",
    },
    {
        "section": "exit_and_investment",
        "label": "Exit Analysis & Investment View",
        "prompt_template": """Research {company} exit potential and investment thesis:
3+ named strategic acquirers with specific rationale for each.
IPO readiness assessment. Bear/base/bull exit multiples and implied IRR.
Investment recommendation with probability-weighted scenarios.
Return JSON:
{{"exit_summary": "300+ chars",
"strategic_acquirers": [{{"acquirer": "Named Company", "rationale": "specific logic", "willingness": "High/Medium/Low"}}],
"ipo_readiness": {{"assessment": "specific signals", "comparable_ipos": "benchmark range"}},
"exit_multiples": {{"bear_case": "Xx ($XB)", "base_case": "Xx ($XB)", "bull_case": "Xx ($XB)"}},
"implied_irr": {{"bear_case": "X%", "base_case": "X%", "bull_case": "X%"}},
"investment_summary": "400+ chars",
"base_case": "detailed with probability", "upside_case": "detailed", "downside_case": "detailed",
"recommendation": "PROCEED/PASS with priorities"}}""",
    },
]


# ── Gemini helpers ───────────────────────────────────────────

def _extract_text(response: Any) -> str:
    if getattr(response, "text", None):
        return response.text
    candidates = getattr(response, "candidates", None) or []
    for c in candidates:
        content = getattr(c, "content", None)
        if content:
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "text", None):
                    return part.text
    return ""


def _extract_sources(response: Any) -> list[dict[str, str]]:
    candidates = getattr(response, "candidates", None) or []
    seen: set[str] = set()
    sources = []
    for c in candidates:
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


# ── Mock data for testing ────────────────────────────────────

def _mock_tool_result(company: str, section: str) -> dict[str, Any]:
    """Return realistic mock data for each research section."""
    mocks = {
        "company_profile": {
            "summary": f"{company} is a leading AI company founded in 2021, headquartered in San Francisco. The company has raised over $7B in funding and employs approximately 1,000-1,500 people. It develops large language models and AI safety research, serving enterprise and API customers globally.",
            "founded": "2021", "headquarters": "San Francisco, CA",
            "employee_estimate": "1,000-1,500 (LinkedIn headcount analysis)",
            "key_facts": ["$7.3B+ total funding raised", "Claude AI model family", "200+ enterprise customers"],
        },
        "management_team": {
            "summary": "World-class leadership team combining deep AI research expertise with enterprise scaling experience. CEO Dario Amodei is a former VP of Research at OpenAI with a PhD in computational neuroscience. President Daniela Amodei brings operational excellence from her prior VP role at OpenAI. CPO Mike Krieger co-founded Instagram, bringing consumer product expertise to enterprise AI.",
            "executives": [
                {"name": "Dario Amodei", "title": "CEO & Co-Founder", "background": "Former VP Research at OpenAI, PhD computational neuroscience Princeton, led GPT-2/GPT-3 development", "signal": "Deep technical credibility, AI safety thought leader"},
                {"name": "Daniela Amodei", "title": "President & Co-Founder", "background": "Former VP Safety & Policy at OpenAI, previously at Stripe and financial services", "signal": "Strong operational leader, business scaling expertise"},
                {"name": "Mike Krieger", "title": "Chief Product Officer", "background": "Co-founder and former CTO of Instagram (acquired by Meta for $1B), Stanford CS", "signal": "Consumer-grade UX + enterprise product vision"},
            ],
            "key_man_risk": "Moderate — Amodei siblings are co-founders with significant equity. CPO hire from Instagram signals product maturity investment.",
        },
        "product_and_technology": {
            "summary": "Claude AI model family represents the core product, with Claude 3.5 Sonnet achieving state-of-the-art performance on major benchmarks. The company's Constitutional AI approach provides a differentiated safety framework. Products span API access, Claude.ai consumer, and Claude for Enterprise with SSO, admin controls, and data privacy guarantees.",
            "core_offerings": ["Claude API (inference-as-a-service, ~60% of revenue)", "Claude for Enterprise (platform licenses, ~30%)", "Claude.ai Pro subscriptions (~10%)"],
            "moat_hypothesis": "Constitutional AI safety approach + frontier model performance + enterprise trust/compliance. Switching costs from API integration depth. Confidence: Medium-High.",
            "tech_differentiation": ["200K context window (largest in market)", "Constitutional AI (unique safety approach)", "97th percentile on HumanEval coding benchmark", "SOC 2 Type II certified"],
        },
        "business_model": {
            "summary": "Hybrid revenue model: API usage-based pricing (pay-per-token) for developers and platform subscriptions for enterprise. Enterprise ACV ranges $100K-$1M+. Consumer Pro plan at $20/month provides high-volume inbound. Land-and-expand motion with 150%+ estimated NRR driven by usage growth.",
            "pricing_motion": "API: $3-$15/MTok input, $15-$75/MTok output. Enterprise: $100K-$1M+ ACV. Pro: $20/month.",
            "customer_segments": ["Enterprise (>5K employees): ~45% revenue, $200K-$1M+ ACV", "Developer/API: ~40% revenue, usage-based", "Consumer Pro: ~15% revenue, $240/year"],
            "revenue_composition": {"subscriptions_pct": "55%", "usage_based_pct": "40%", "professional_services_pct": "5%"},
            "unit_economics": {
                "cac_estimate": "$30,000-$60,000 (blended; enterprise field sales ~$80K, self-serve ~$5K)",
                "ltv_estimate": "$200,000-$400,000 (est. 3-4yr lifetime, $70K avg annual)",
                "ltv_cac_ratio": "5-7x (improving with brand-driven inbound growth)",
                "nrr_ndr": "140-160% (estimated; API usage expansion is primary driver)",
                "gross_margin": "50-60% (lower than pure SaaS due to GPU inference costs; improving with efficiency)",
                "payback_period_months": "10-14 months",
                "rule_of_40_score": "100+ (est: ~80% growth + ~20% margin trajectory)",
                "logo_retention": "90-95% (enterprise cohort ~97%+)",
            },
            "confidence": "Medium — based on disclosed pricing, peer benchmarks, and investor commentary. Not audited.",
        },
        "financial_signals": {
            "summary": "Explosive financial trajectory: estimated $1B+ ARR run rate in 2024, growing ~80%+ Y/Y. Total funding exceeds $7.3B from top-tier investors including Amazon ($4B strategic investment), Google ($2B+), Spark Capital, and others. Last valuation $18.4B (Series D, 2024). Significant cash reserves provide 3+ years runway.",
            "arr_trajectory": "$850M-$1.2B ARR (2024 est); $300M-$500M in 2023. ~100% Y/Y growth.",
            "funding_rounds": [
                {"round": "Series A", "date": "2021", "amount": "$124M", "lead_investor": "Jaan Tallinn, various", "valuation": "$4.1B"},
                {"round": "Series B", "date": "2023", "amount": "$450M", "lead_investor": "Spark Capital", "valuation": "$4.1B"},
                {"round": "Series C", "date": "2023", "amount": "$2B", "lead_investor": "Google", "valuation": "$18.4B"},
                {"round": "Series D", "date": "2024", "amount": "$4B", "lead_investor": "Amazon", "valuation": "$18.4B"},
            ],
            "total_funding": "$7.3B+",
            "valuation_signal": "$18.4B (Series D). Implied ~18x forward revenue at $1B ARR.",
            "burn_vs_growth_signal": "Est. net burn $50-100M/month (heavy GPU costs). $3B+ cash reserves. Runway 3+ years. Burn multiple ~1.5-2x.",
            "revenue_growth_cagr": "80-120% Y/Y (decelerating from >200% in 2023)",
        },
        "market_and_competition": {
            "market_summary": "The enterprise AI/LLM market is projected at $150-200B by 2028, growing 35-45% CAGR. Anthropic operates in the foundation model layer (TAM ~$50B) and enterprise AI platform layer (TAM ~$80B). The addressable market is expanding as AI adoption crosses the enterprise mainstream threshold.",
            "competitors": ["OpenAI", "Google DeepMind", "Meta AI (LLaMA)", "Mistral AI", "Cohere", "Amazon Bedrock", "Microsoft/Azure OpenAI"],
            "market_size": {"tam": "$150-200B by 2028", "sam": "$50-80B (foundation models + enterprise AI)", "som": "$5-10B"},
            "industry_trends": [
                "Enterprise AI adoption: 70% of Fortune 500 now have production AI (up from 30% in 2022)",
                "Model commoditization pushing value to safety/trust layer (favorable for Anthropic)",
                "AI regulation (EU AI Act, US executive orders) creating compliance barriers favoring established vendors",
                "GPU costs declining 30-40% annually, improving unit economics for inference providers",
            ],
            "positioning_matrix": [
                {"competitor": "OpenAI", "strengths": "Largest brand, GPT-4o, ChatGPT distribution, Microsoft partnership", "weaknesses": "Safety concerns, CEO controversy, enterprise trust issues", "vs_target": "Anthropic wins on safety positioning and enterprise trust"},
                {"competitor": "Google DeepMind", "strengths": "Gemini models, cloud distribution, massive compute", "weaknesses": "Slower enterprise go-to-market, less focused", "vs_target": "Anthropic wins on product focus and developer experience"},
                {"competitor": "Meta AI (LLaMA)", "strengths": "Open-source community, free models", "weaknesses": "No enterprise support, no safety guarantees, no API SLA", "vs_target": "Anthropic wins on enterprise features and support"},
            ],
            "key_differentiators": ["Constitutional AI safety framework (unique in market)", "Enterprise trust (SOC 2, no training on customer data)", "200K context window (competitive advantage)", "Amazon partnership for distribution"],
        },
        "customer_evidence": {
            "summary": "Rapid enterprise adoption with notable logos across finance, tech, healthcare, and government. Estimated 200+ enterprise customers. G2 and user reviews consistently rate Claude highest for safety and reasoning quality. Published case studies show 30-50% productivity gains.",
            "logo_highlights": ["Top-5 US banks (API integration)", "3+ Fortune 50 tech companies", "Major consulting firms (Deloitte, Accenture)", "US government agencies"],
            "concentration_risk": "Top 10 customers estimated at 20-30% of revenue. Amazon partnership is largest single relationship. Moderate concentration.",
            "churn_signals": "Logo retention est. 92-96%. Revenue retention 140-160% driven by usage expansion.",
            "nps_proxy": "G2: 4.7/5.0 (400+ reviews, highest in category). Gartner Peer Insights: 4.5/5.0. Stack Overflow survey: #1 most admired AI tool.",
            "case_studies": ["Consulting firm: 40% faster report generation, $10M+ annual savings", "Financial services: 50% reduction in compliance review time"],
        },
        "comparable_transactions": {
            "summary": "AI sector valuations remain elevated with frontier model companies commanding 15-30x forward revenue. Recent transactions and public comps support $15-25B valuation range for Anthropic at current scale.",
            "private_transactions": [
                {"target": "OpenAI", "acquirer_investor": "Microsoft, Thrive Capital", "deal_value": "$157B valuation (2024)", "revenue_multiple": "~40x est. revenue", "date": "2024"},
                {"target": "Databricks", "acquirer_investor": "Series J", "deal_value": "$62B valuation (2024)", "revenue_multiple": "~25x ARR", "date": "2024"},
                {"target": "Scale AI", "acquirer_investor": "Series F", "deal_value": "$13.8B valuation", "revenue_multiple": "~18x est. ARR", "date": "2024"},
            ],
            "public_comps": [
                {"company": "Palantir (PLTR)", "ev_revenue_multiple": "25x NTM", "growth_rate": "~20% Y/Y"},
                {"company": "Snowflake (SNOW)", "ev_revenue_multiple": "12x NTM", "growth_rate": "~28% Y/Y"},
                {"company": "Datadog (DDOG)", "ev_revenue_multiple": "15x NTM", "growth_rate": "~25% Y/Y"},
                {"company": "CrowdStrike (CRWD)", "ev_revenue_multiple": "18x NTM", "growth_rate": "~30% Y/Y"},
            ],
            "implied_valuation_range": "$15B-$30B based on 15-30x forward revenue at $1B+ ARR",
        },
        "risk_and_regulatory": {
            "risk_summary": "Primary risks center on compute cost dependency, competitive intensity from hyperscalers, and AI regulatory uncertainty. The risk profile is consistent with a high-growth frontier AI company where execution risk is offset by massive market tailwinds and a differentiated safety positioning.",
            "key_risks": [
                {"risk": "GPU compute dependency and cost pressure", "severity": "High", "probability": "90%", "mitigation": "Amazon partnership provides preferred access; custom chip development rumored; inference efficiency improving 2x annually"},
                {"risk": "Competitive intensity from OpenAI and Google", "severity": "High", "probability": "95%", "mitigation": "Safety-first positioning differentiates; enterprise trust is a moat; Constitutional AI is unique IP"},
                {"risk": "AI regulatory disruption (EU AI Act, US regulation)", "severity": "Medium", "probability": "60%", "mitigation": "Safety positioning actually benefits from regulation; compliance team in place; proactive policy engagement"},
                {"risk": "Key person dependency on Amodei founders", "severity": "Medium", "probability": "20%", "mitigation": "Equity retention, deep bench of research talent, institutional knowledge being documented"},
                {"risk": "Gross margin compression from GPU costs", "severity": "Medium-High", "probability": "70%", "mitigation": "Inference efficiency improving; Amazon custom silicon partnership; pricing power with enterprise customers"},
            ],
            "overall_risk_rating": "Medium-High — exceptional market position but existential competitive and compute risks. Net positive risk/reward for PE entry.",
            "ip_exposure": "Constitutional AI methodology is proprietary. No known IP litigation. Trade secrets in model training techniques.",
            "data_privacy": "SOC 2 Type II. No training on customer data (key differentiator). GDPR compliant.",
            "regulatory_moats": ["Safety-first positioning benefits from AI regulation", "SOC 2 + enterprise data guarantees", "Proactive government engagement"],
            "regulatory_risks": ["EU AI Act compliance costs: $5-10M/year estimated", "US AI executive order could impose licensing requirements", "Potential compute export controls affecting GPU access"],
        },
        "exit_and_investment": {
            "exit_summary": "Multiple high-probability exit paths within 3-5 years. IPO is primary exit (2026-2027 window). Strategic acquisition by Amazon is a secondary path. Current trajectory supports $30B-$80B exit valuation.",
            "strategic_acquirers": [
                {"acquirer": "Amazon", "rationale": "Already invested $4B. Deepen Bedrock AI platform. Compete with Microsoft/OpenAI partnership.", "willingness": "High"},
                {"acquirer": "Google/Alphabet", "rationale": "Already invested $2B+. Hedge against DeepMind. Strengthen cloud AI offerings.", "willingness": "Medium"},
                {"acquirer": "Salesforce", "rationale": "AI capabilities for Einstein platform. Enterprise customer overlap. CRM + AI integration.", "willingness": "Medium-High"},
            ],
            "ipo_readiness": {"assessment": "IPO-ready by 2026-2027. $1B+ ARR, 80%+ growth, top-tier investor base. CFO and enterprise infrastructure being built.", "comparable_ipos": "AI/SaaS IPOs pricing at 15-30x NTM for 40%+ growth"},
            "exit_multiples": {"bear_case": "15x ($15B-$20B)", "base_case": "25x ($25B-$40B)", "bull_case": "40x ($40B-$80B)"},
            "implied_irr": {"bear_case": "5-10%", "base_case": "25-40%", "bull_case": "50-80%+"},
            "investment_summary": "Anthropic represents a generational investment opportunity in frontier AI. The company occupies a uniquely defensible position combining safety leadership, enterprise trust, and hyperscaler partnerships. Risk/reward is asymmetric: downside is protected by strategic value (Amazon/Google backing), while upside is driven by secular AI adoption.",
            "base_case": "Base ($25-40B, 25-40% IRR): Sustain 50-80% growth, reach $2-3B ARR by 2027. IPO at 20-25x. Probability: 50%.",
            "upside_case": "Upside ($40-80B, 50-80% IRR): Category leadership, government contracts, Claude becomes enterprise standard. 30-40x exit. Probability: 25%.",
            "downside_case": "Downside ($15-20B, 5-10% IRR): Commoditization, margin pressure, growth decelerates to 30%. 12-15x exit. Capital protected by preferred equity. Probability: 25%.",
            "recommendation": "STRONG PROCEED — Rare opportunity to invest in a top-3 AI foundation model company with differentiated safety moat and hyperscaler backing. Key diligence: (1) Unit economics deep-dive, (2) GPU supply chain assessment, (3) Enterprise customer calls, (4) Technical evaluation.",
        },
    }
    return mocks.get(section, {"summary": f"Mock data for {section}"})


# ── Core research tool runner ────────────────────────────────

def _run_research_tool(client, company: str, tool: dict, run_id: str) -> Generator:
    """Run a single focused search pass and yield stream events."""
    section = tool["section"]
    label = tool["label"]
    prompt_template = tool["prompt_template"]

    yield {"event": "progress", "data": f"Researching: {label}..."}

    prompt = f"""You are a senior PE due diligence researcher at McKinsey.
Research target: {company}

TASK: {prompt_template.format(company=company)}

REQUIREMENTS:
- Use web search to find real, current data
- Include specific numbers, names, dates — no vague language
- Return STRICT JSON only. No markdown. No commentary.
"""

    try:
        response = client.models.generate_content(
            model=settings.gemini_research_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )
    except Exception as e:
        yield {"event": "error", "data": f"{label}: API error — {e}"}
        return

    # Extract text
    raw = _extract_text(response)
    if not raw:
        yield {"event": "error", "data": f"{label}: empty response"}
        return

    # Extract and store sources
    sources = _extract_sources(response)
    for src in sources:
        write_source(run_id, company, src["title"], src["url"], "Grounded web source")
        yield {"event": "source", "data": {"title": src["title"], "url": src["url"]}}

    # Parse JSON and store finding
    try:
        data = _parse_json(raw)
        write_finding(run_id, company, section, json.dumps(data), sources)
        yield {"event": "thinking", "data": f"{label}: found {len(sources)} sources, data extracted successfully"}
    except Exception:
        # Store raw text if JSON fails
        write_finding(run_id, company, section, raw, sources)
        yield {"event": "thinking", "data": f"{label}: stored raw text ({len(raw)} chars), JSON parse failed"}


# ── Main research orchestrators ──────────────────────────────

def run_research(company: str) -> dict[str, Any]:
    """Synchronous research — returns full research dict."""
    run_id = new_run_id(company)

    if settings.mock_mode or not settings.gemini_api_key:
        return _run_mock_research(company, run_id)

    client = genai.Client(api_key=settings.gemini_api_key)

    for tool in RESEARCH_TOOLS:
        for _ in _run_research_tool(client, company, tool, run_id):
            pass  # Consume events silently in sync mode

    return _assemble_research(company, run_id)


def run_research_stream(company: str) -> Generator:
    """Streaming research — yields SSE events during multi-pass search."""
    run_id = new_run_id(company)

    if settings.mock_mode or not settings.gemini_api_key:
        yield {"event": "progress", "data": "Running in mock mode..."}
        mock = _run_mock_research(company, run_id)
        # Simulate stream events from mock
        for src in (mock.get("all_sources") or [])[:6]:
            yield {"event": "source", "data": {"title": src["title"], "url": src["url"]}}
            time.sleep(0.1)
        yield {"event": "progress", "data": "Mock research complete."}
        yield {"event": "done", "data": mock}
        return

    client = genai.Client(api_key=settings.gemini_api_key)
    total_tools = len(RESEARCH_TOOLS)

    for i, tool in enumerate(RESEARCH_TOOLS):
        yield {"event": "progress", "data": f"[{i+1}/{total_tools}] {tool['label']}..."}
        yield {"event": "search", "data": f"{company} {tool['label'].lower()}"}

        for event in _run_research_tool(client, company, tool, run_id):
            yield event

    yield {"event": "progress", "data": "All research passes complete. Assembling findings..."}

    research = _assemble_research(company, run_id)

    # Quality check
    score = _score_research(research)
    yield {"event": "attempt", "data": {"attempt": 1, "score": score, "issues": []}}

    yield {"event": "done", "data": research}


def get_run_id_for_company(company: str) -> str:
    """Create a new run ID (used by main.py to pass to analyst)."""
    return new_run_id(company)


# ── Assembly: read workspace → build research dict ───────────

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

        # Map sections to research dict keys
        if section == "company_profile":
            research["company_profile"] = data
        elif section == "management_team":
            research["management_team"] = data
        elif section == "product_and_technology":
            research["product_and_technology"] = data
        elif section == "business_model":
            research["business_model"] = data
            # Extract unit_economics if nested
            if "unit_economics" in data:
                research["unit_economics"] = {
                    "summary": data.get("summary", ""),
                    "metrics": data["unit_economics"],
                    "confidence": data.get("confidence", "Medium"),
                }
            else:
                research["unit_economics"] = {"summary": data.get("summary", ""), "metrics": {}, "confidence": "Medium"}
        elif section == "financial_signals":
            research["financial_signals"] = data
        elif section == "market_and_competition":
            research["market_landscape"] = {
                "summary": data.get("market_summary", data.get("summary", "")),
                "competitors": data.get("competitors", []),
                "market_size_estimate": _format_market_size(data.get("market_size", {})),
                "industry_trends": data.get("industry_trends", []),
            }
            research["competitive_positioning"] = {
                "summary": data.get("market_summary", ""),
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
                "summary": data.get("risk_summary", ""),
                "ip_exposure": data.get("ip_exposure", ""),
                "data_privacy": data.get("data_privacy", ""),
                "regulatory_moats": data.get("regulatory_moats", []),
                "regulatory_risks": data.get("regulatory_risks", []),
            }
        elif section == "exit_and_investment":
            research["exit_analysis"] = {
                "summary": data.get("exit_summary", ""),
                "strategic_acquirers": data.get("strategic_acquirers", []),
                "ipo_readiness": data.get("ipo_readiness", {}),
                "exit_multiples": data.get("exit_multiples", {}),
                "implied_irr": data.get("implied_irr", {}),
            }
            research["investment_view"] = {
                "summary": data.get("investment_summary", ""),
                "base_case": data.get("base_case", ""),
                "upside_case": data.get("upside_case", ""),
                "downside_case": data.get("downside_case", ""),
                "recommendation": data.get("recommendation", ""),
            }
            research["catalysts_and_outlook"] = {
                "summary": data.get("investment_summary", ""),
                "catalysts": [],  # Will be filled if available
            }

    # Build dashboard metrics from available data
    research["dashboard_metrics"] = {"metrics": _build_dashboard_metrics(research), "sources": []}

    # Attach sources
    research["all_sources"] = sources
    research["_run_id"] = run_id

    return research


def _format_market_size(ms: dict) -> str:
    if isinstance(ms, str):
        return ms
    if isinstance(ms, dict):
        parts = []
        if ms.get("tam"):
            parts.append(f"TAM: {ms['tam']}")
        if ms.get("sam"):
            parts.append(f"SAM: {ms['sam']}")
        if ms.get("som"):
            parts.append(f"SOM: {ms['som']}")
        return ". ".join(parts) if parts else ""
    return ""


def _build_dashboard_metrics(research: dict) -> list[dict]:
    """Extract numeric metrics from research for dashboard display."""
    metrics = []

    # From financial signals
    fin = research.get("financial_signals", {})
    if isinstance(fin, dict):
        if fin.get("arr_trajectory"):
            metrics.append({"label": "Est. ARR", "value": _first_number_or_text(fin["arr_trajectory"]), "trend": "up"})
        if fin.get("revenue_growth_cagr"):
            metrics.append({"label": "Revenue Growth", "value": _first_number_or_text(fin["revenue_growth_cagr"]), "trend": "up"})

    # From unit economics
    ue = research.get("unit_economics", {})
    if isinstance(ue, dict):
        m = ue.get("metrics", {})
        if isinstance(m, dict):
            for key, label, trend in [
                ("nrr_ndr", "NRR", "up"), ("gross_margin", "Gross Margin", "up"),
                ("ltv_cac_ratio", "LTV:CAC", "up"), ("rule_of_40_score", "Rule of 40", "up"),
                ("logo_retention", "Logo Retention", "flat"), ("payback_period_months", "Payback", "down"),
            ]:
                if m.get(key):
                    metrics.append({"label": label, "value": _first_number_or_text(str(m[key])), "trend": trend})

    # From risk
    risk = research.get("risk_assessment", {})
    if isinstance(risk, dict) and risk.get("overall_risk_rating"):
        metrics.append({"label": "Risk Rating", "value": risk["overall_risk_rating"][:15], "trend": "flat"})

    return metrics[:10]


def _first_number_or_text(s: str) -> str:
    """Extract a concise display value from a verbose string."""
    if not s:
        return "N/A"
    # Try to find a $ amount or percentage at the start
    m = re.match(r'(\$[\d.,]+[BMK]?\+?|[\d.,]+%|[\d.,]+x)', s)
    if m:
        return m.group(1)
    # Return first 20 chars
    return s[:20].strip()


def _score_research(research: dict) -> int:
    """Quick quality score for streaming feedback."""
    score = 100
    required = ["company_profile", "management_team", "product_and_technology",
                 "business_model", "financial_signals", "market_landscape",
                 "risk_assessment", "investment_view"]
    for s in required:
        if s not in research or not research[s]:
            score -= 10
    sources = research.get("all_sources", [])
    if len(sources) < 10:
        score -= 15
    metrics = research.get("dashboard_metrics", {}).get("metrics", [])
    if len(metrics) < 6:
        score -= 10
    return max(0, score)


# ── Mock research runner ─────────────────────────────────────

def _run_mock_research(company: str, run_id: str) -> dict[str, Any]:
    """Generate mock research and write to workspace."""
    for tool in RESEARCH_TOOLS:
        section = tool["section"]
        mock_data = _mock_tool_result(company, section)
        write_finding(run_id, company, section, json.dumps(mock_data), [])

    # Write mock sources
    mock_sources = [
        ("Company Website", "https://anthropic.com"),
        ("Crunchbase", "https://crunchbase.com/organization/anthropic"),
        ("LinkedIn", "https://linkedin.com/company/anthropic"),
        ("TechCrunch Coverage", "https://techcrunch.com/tag/anthropic"),
        ("Bloomberg", "https://bloomberg.com/anthropic"),
        ("G2 Reviews", "https://g2.com/products/claude"),
        ("Gartner Analysis", "https://gartner.com/ai-platforms"),
        ("PitchBook", "https://pitchbook.com/anthropic"),
        ("SEC Filings", "https://sec.gov/anthropic"),
        ("Industry Report", "https://mckinsey.com/ai-2024"),
        ("Amazon Partnership", "https://aboutamazon.com/anthropic"),
        ("Product Docs", "https://docs.anthropic.com"),
        ("Safety Research", "https://anthropic.com/research"),
        ("Competitor Analysis", "https://cbinsights.com/ai-landscape"),
        ("Market Sizing", "https://idc.com/ai-forecast"),
        ("EU AI Act", "https://digital-strategy.ec.europa.eu/ai-act"),
        ("Hiring Signals", "https://anthropic.com/careers"),
        ("Investor Reports", "https://example.com/ai-investing"),
    ]
    for title, url in mock_sources:
        write_source(run_id, company, title, url, "Mock source")

    return _assemble_research(company, run_id)
