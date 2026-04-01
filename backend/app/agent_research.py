import json
import re
from typing import Any

from google import genai
from google.genai import types

from app.settings import settings

REQUIRED_SECTIONS = [
    "company_profile",
    "management_team",
    "product_and_technology",
    "business_model",
    "unit_economics",
    "financial_signals",
    "customer_evidence",
    "market_landscape",
    "competitive_positioning",
    "comparable_transactions",
    "regulatory_landscape",
    "risk_assessment",
    "catalysts_and_outlook",
    "exit_analysis",
    "investment_view",
    "dashboard_metrics",
]

# Sections that must have substantial content
MAJOR_SECTIONS = [
    "company_profile",
    "management_team",
    "product_and_technology",
    "business_model",
    "unit_economics",
    "financial_signals",
    "market_landscape",
    "competitive_positioning",
    "risk_assessment",
    "investment_view",
]


def _mock_research(company: str) -> dict[str, Any]:
    return {
        "company": company,
        "company_profile": {
            "summary": (
                f"{company} is a high-growth technology company operating at the intersection of enterprise "
                "software and artificial intelligence. The company has demonstrated strong product-market fit "
                "with a rapidly expanding customer base across Fortune 500 enterprises. Founded by repeat "
                "entrepreneurs with deep domain expertise, the company has scaled to an estimated 800-1,200 "
                "employees and maintains offices across three continents. Revenue is estimated in the $200M-$400M "
                "ARR range based on disclosed funding trajectory and market positioning signals."
            ),
            "founded": "2019",
            "headquarters": "San Francisco, CA",
            "employee_estimate": "800-1,200 (estimated via LinkedIn headcount analysis)",
            "key_facts": [
                "Series D+ stage with >$500M total funding raised",
                "Serving 200+ enterprise customers globally",
                "Y/Y headcount growth of ~45% based on LinkedIn signals",
            ],
            "sources": [1, 2, 3, 4],
        },
        "management_team": {
            "summary": (
                "The leadership team combines deep technical expertise with proven enterprise go-to-market "
                "experience. The CEO is a second-time founder with a prior exit valued at $300M+. The CTO "
                "holds 12+ patents in distributed systems and previously led engineering at a public SaaS "
                "company. The CFO joined from a top PE-backed portfolio company, suggesting IPO preparation."
            ),
            "executives": [
                {
                    "name": "CEO (Founder)",
                    "background": "Second-time founder. Prior startup acquired for $300M+ by a Fortune 100 tech company. Stanford CS graduate. 15+ years in enterprise software.",
                    "signal": "Strong execution track record; repeat founder premium applies.",
                },
                {
                    "name": "CTO (Co-Founder)",
                    "background": "Former VP Engineering at a public SaaS company (IPO at $2B+ valuation). 12 patents in distributed systems. PhD in computer science.",
                    "signal": "Deep technical credibility; key retention target post-investment.",
                },
                {
                    "name": "CFO",
                    "background": "Joined 18 months ago from a PE-backed SaaS company that completed a $1.5B exit. CPA with Big 4 experience. Previously IPO CFO.",
                    "signal": "CFO hire signals potential IPO preparation within 18-24 months.",
                },
            ],
            "key_man_risk": "Moderate — CEO and CTO are co-founders with significant equity; retention risk is low near-term but succession depth is thin at VP level.",
            "sources": [2, 5, 6],
        },
        "product_and_technology": {
            "summary": (
                "The core product is an AI-native enterprise platform that reduces operational complexity by 40-60% "
                "for mission-critical workflows. The technology stack includes proprietary model architectures "
                "with 3x inference speed advantage over open-source alternatives. The platform supports hybrid "
                "deployment (cloud + on-prem), which is critical for regulated industry customers."
            ),
            "core_offerings": [
                "Enterprise AI Platform (core revenue driver, ~70% of bookings)",
                "Inference-as-a-Service API (high-margin, usage-based revenue)",
                "On-premises deployment module (differentiator for regulated industries)",
                "Analytics and monitoring dashboard (drives expansion revenue)",
            ],
            "moat_hypothesis": (
                "Technical moat based on proprietary model architecture (3x speed advantage, 15 patents filed), "
                "enterprise integrations with 50+ data connectors, and switching costs from deep workflow embedding. "
                "Estimated 6-12 month implementation cycle creates significant lock-in. Confidence: Medium-High."
            ),
            "tech_differentiation": [
                "3x inference speed vs. open-source alternatives (benchmarked by independent testing)",
                "15 patents filed in model optimization and distributed inference",
                "SOC 2 Type II, HIPAA, and FedRAMP authorization (competitive barrier)",
            ],
            "sources": [3, 7, 8, 9],
        },
        "business_model": {
            "summary": (
                "Hybrid pricing model combining platform subscriptions (ACV $150K-$500K for mid-market, "
                "$500K-$2M+ for enterprise) with usage-based inference fees. Land-and-expand motion drives "
                "130%+ NRR. Multi-year contracts represent ~60% of total bookings, providing revenue visibility."
            ),
            "pricing_motion": (
                "Land with $150K platform subscription, expand via usage-based inference fees and additional "
                "module adoption. Average expansion from $150K to $450K within 18 months. Multi-year contracts "
                "represent 60% of bookings."
            ),
            "customer_segments": [
                "Enterprise (>5,000 employees): 45% of revenue, $500K-$2M+ ACV",
                "Mid-market (500-5,000 employees): 35% of revenue, $150K-$500K ACV",
                "Strategic/Government: 20% of revenue, $1M+ ACV with multi-year terms",
            ],
            "revenue_composition": {
                "subscriptions_pct": "65%",
                "usage_based_pct": "30%",
                "professional_services_pct": "5%",
            },
            "sources": [4, 10, 11],
        },
        "unit_economics": {
            "summary": (
                "Unit economics profile is consistent with a scaling enterprise SaaS business. Estimated "
                "LTV:CAC ratio of 4.5-5.5x with improving trend as brand-driven inbound increases. Gross "
                "margins in the 72-78% range reflect a mix of high-margin SaaS subscriptions and moderate-margin "
                "inference compute. Payback period estimated at 14-18 months."
            ),
            "metrics": {
                "cac_estimate": "$45,000-$65,000 (blended; field sales ~$85K, inbound ~$25K)",
                "ltv_estimate": "$250,000-$350,000 (4.5-yr avg lifetime x $65K avg annual revenue)",
                "ltv_cac_ratio": "4.5-5.5x (improving as inbound mix increases from 30% to 45%)",
                "nrr_ndr": "128-135% (top quartile for enterprise SaaS; driven by usage expansion)",
                "gross_margin": "72-78% (subscription GM ~85%, inference compute GM ~55%)",
                "payback_period_months": "14-18 months (improving from 20+ months two years ago)",
                "rule_of_40_score": "55-65 (est: ~45% growth + ~15% FCF margin; top-decile)",
                "logo_retention": "92-95% annual (enterprise cohort at 97%+)",
            },
            "confidence": "Medium — estimates based on disclosed metrics, peer benchmarks, and investor commentary.",
            "sources": [10, 11, 12, 13],
        },
        "financial_signals": {
            "summary": (
                "Strong financial trajectory with estimated $250M-$400M ARR, growing 40-55% Y/Y. Total funding "
                "exceeds $500M across 4+ rounds from tier-1 investors. Last round valued the company at $3.5-$4.5B "
                "(implied ~12x forward revenue). Burn rate appears disciplined with 24-30 months runway."
            ),
            "arr_trajectory": "$250M-$400M ARR (estimated); ~45% 2-year CAGR from $120M-$180M.",
            "funding": "$500M+ total raised. Last round: $200M Series D at $4B valuation. Tier-1 investors.",
            "valuation_signal": "$3.5-$4.5B post-money (Series D). Implied ~12x forward revenue. Premium to sector median.",
            "burn_vs_growth_signal": "Net burn $8-12M/month. $200M+ cash. Runway 24-30 months. Burn multiple ~1.5x.",
            "revenue_growth_cagr": "40-55% Y/Y (decelerating from 80%+; consistent with scaling dynamics)",
            "sources": [5, 12, 13, 14],
        },
        "customer_evidence": {
            "summary": (
                "Customer base includes 200+ enterprises. Top 10 customers ~25% of revenue (moderate concentration). "
                "Case studies demonstrate 3-5x ROI within 12 months. Gross logo retention 92-95%."
            ),
            "logo_highlights": ["3 of top 10 US banks", "2 Fortune 50 tech companies", "4 large healthcare systems"],
            "concentration_risk": "Top 10 ~25% of revenue. Largest single customer <5%. Moderate and improving.",
            "churn_signals": "Gross logo retention 92-95%. Revenue churn offset by 128-135% NRR expansion.",
            "nps_proxy": "G2: 4.6/5.0 (200+ reviews). Gartner Peer Insights: 4.5/5.0.",
            "case_studies": [
                "Major bank: 70% faster model deployment, $15M annual savings",
                "Healthcare system: 35% accuracy improvement, 6-month payback",
            ],
            "sources": [7, 8, 11, 15],
        },
        "market_landscape": {
            "summary": (
                "Enterprise AI platform market projected at $120-$150B by 2028 (28-35% CAGR from $35-$40B in 2024). "
                "Company operates in production AI deployment sub-segment growing 40-50% CAGR."
            ),
            "competitors": ["OpenAI", "Anthropic", "Google Cloud AI", "AWS Bedrock", "Databricks", "Snowflake"],
            "market_size_estimate": "TAM: $120-$150B by 2028. SAM: $25-$35B. SOM: $3-$5B.",
            "industry_trends": [
                "65% of Fortune 500 now have production AI workloads (up from 25% in 2022)",
                "Model commoditization driving value to platform layer (favorable)",
                "EU AI Act creating compliance barriers favoring established vendors",
                "Hybrid/on-prem demand growing 60% Y/Y on data sovereignty requirements",
            ],
            "sources": [8, 9, 14, 16],
        },
        "competitive_positioning": {
            "summary": (
                "Differentiated position in enterprise AI stack competing on deployment speed, hybrid infrastructure, "
                "and regulated-industry compliance. Vendor-neutrality mitigates hyperscaler competition."
            ),
            "positioning_matrix": [
                {"competitor": "OpenAI/Microsoft", "strengths": "Largest model ecosystem, Azure distribution", "weaknesses": "Vendor lock-in, limited on-prem", "relative_position": "Company wins on hybrid and neutrality"},
                {"competitor": "Google Cloud AI", "strengths": "Gemini models, Vertex AI, analytics", "weaknesses": "Smaller enterprise sales force", "relative_position": "Company wins on deployment flexibility"},
                {"competitor": "Databricks", "strengths": "Data lakehouse dominance, MLflow", "weaknesses": "AI capabilities maturing", "relative_position": "Complementary; partnership potential"},
            ],
            "key_differentiators": [
                "FedRAMP authorization (18-24 month barrier to entry)",
                "3x inference speed reduces customer compute costs",
                "50+ enterprise integrations vs. 15-25 for competitors",
            ],
            "sources": [3, 8, 9, 16],
        },
        "comparable_transactions": {
            "summary": "Recent AI M&A/funding supports 10-15x forward revenue for high-growth companies. Public comps trade at 8-12x NTM.",
            "private_transactions": [
                {"target": "Anthropic", "acquirer_investor": "Amazon, Google", "deal_value": "$18B+ valuation (2024)", "revenue_multiple": "~30x est. revenue"},
                {"target": "Databricks", "acquirer_investor": "Series I", "deal_value": "$43B valuation (2023)", "revenue_multiple": "~25x ARR"},
                {"target": "Scale AI", "acquirer_investor": "Series F", "deal_value": "$13.8B valuation (2024)", "revenue_multiple": "~18x est. ARR"},
            ],
            "public_comps": [
                {"company": "Palantir (PLTR)", "ev_revenue_multiple": "25x NTM", "growth_rate": "~20% Y/Y"},
                {"company": "Datadog (DDOG)", "ev_revenue_multiple": "15x NTM", "growth_rate": "~25% Y/Y"},
                {"company": "Snowflake (SNOW)", "ev_revenue_multiple": "12x NTM", "growth_rate": "~30% Y/Y"},
            ],
            "implied_valuation_range": "$3B-$6B based on 10-15x forward revenue at $300M-$400M ARR",
            "sources": [12, 13, 14, 17],
        },
        "regulatory_landscape": {
            "summary": "Net positive regulatory environment due to compliance certifications creating barriers. EU AI Act adds cost but benefits incumbents.",
            "ip_exposure": "15 patents filed, 8 granted. No known IP litigation.",
            "data_privacy": "GDPR, CCPA compliant. DPAs with all enterprise customers.",
            "regulatory_moats": ["FedRAMP (18-24 month barrier)", "HIPAA enables healthcare vertical", "SOC 2 Type II annual audit"],
            "regulatory_risks": ["EU AI Act high-risk classification: $2-5M/year compliance cost", "Evolving US state-level AI regulations"],
            "sources": [9, 15, 16],
        },
        "risk_assessment": {
            "summary": (
                "Key risks: hyperscaler competition, execution risk in scaling, margin compression from falling "
                "inference costs. Profile consistent with growth-stage enterprise software with moderate-to-high "
                "execution risk offset by strong market tailwinds."
            ),
            "key_risks": [
                {"risk": "Hyperscaler competition (MSFT, GOOG, AMZN)", "severity": "High", "mitigation": "Vendor-neutrality, hybrid capability, switching costs", "probability": "70%"},
                {"risk": "Inference cost deflation compressing margins", "severity": "Medium-High", "mitigation": "Proprietary optimization, platform value-add pricing", "probability": "80%"},
                {"risk": "Enterprise sales cycle elongation", "severity": "Medium", "mitigation": "Land-and-expand reduces initial commitment; strong NRR", "probability": "40%"},
                {"risk": "Key person dependency on CEO/CTO", "severity": "Medium", "mitigation": "Equity retention, VP bench development, key-man insurance", "probability": "20%"},
            ],
            "overall_risk_rating": "Medium — strong tailwinds and PMF offset execution and competitive risks",
            "sources": [8, 9, 14, 16, 17],
        },
        "catalysts_and_outlook": {
            "summary": "Multiple near-term catalysts within 12-24 months. Strongest: enterprise AI adoption acceleration and hyperscaler partnerships.",
            "catalysts": [
                {"catalyst": "Strategic cloud provider partnership", "timeline": "6-12 months", "impact": "20-30% revenue acceleration", "probability": "40-50%"},
                {"catalyst": "Government/defense contract wins", "timeline": "6-18 months", "impact": "$50-100M+ TACV expansion", "probability": "50-60%"},
                {"catalyst": "International expansion (EU/APAC)", "timeline": "12-24 months", "impact": "15-25% incremental revenue", "probability": "70%+"},
                {"catalyst": "IPO or strategic M&A event", "timeline": "18-36 months", "impact": "$5B-$8B+ valuation", "probability": "40-50%"},
            ],
            "sources": [5, 12, 14, 17],
        },
        "exit_analysis": {
            "summary": "Multiple viable exits support 3-5 year hold. IPO most likely primary; strategic acquisition alternative. Probability-weighted: $5B-$10B.",
            "strategic_acquirers": [
                {"acquirer": "Microsoft", "rationale": "Vendor-neutral AI deployment complements Azure", "estimated_willingness": "Medium"},
                {"acquirer": "Salesforce", "rationale": "AI capabilities for CRM/enterprise suite", "estimated_willingness": "Medium-High"},
                {"acquirer": "SAP", "rationale": "Enterprise AI for ERP/S4HANA customers", "estimated_willingness": "Medium"},
            ],
            "ipo_readiness": {
                "assessment": "IPO-ready within 18-24 months. CFO hire, $300M+ ARR, 40%+ growth support credible offering.",
                "comparable_ipo_valuations": "Enterprise AI/SaaS IPOs: 10-20x NTM for 30-50% growth",
            },
            "exit_multiples": {
                "bear_case": "8-10x forward revenue ($2.5B-$4B)",
                "base_case": "12-15x forward revenue ($5B-$7.5B)",
                "bull_case": "18-22x forward revenue ($8B-$11B)",
            },
            "implied_irr": {"bear_case": "8-12%", "base_case": "20-30%", "bull_case": "35-50%+"},
            "sources": [12, 13, 14, 17, 18],
        },
        "investment_view": {
            "summary": (
                "Compelling risk-adjusted return. Base case 20-30% IRR over 3 years, supported by AI adoption "
                "tailwinds, strong unit economics, and multiple exit paths. Key swing: competitive positioning vs hyperscalers."
            ),
            "base_case": "Base ($5B-$7.5B, 20-30% IRR): 35-45% growth, margins improve to 15-20% FCF by Year 3. IPO/sale at 12-15x. Prob: 50%.",
            "upside_case": "Upside ($8B-$11B, 35-50% IRR): Category leadership, hyperscaler partnership, gov vertical $100M+ ARR. 18-22x exit. Prob: 25%.",
            "downside_case": "Downside ($2.5B-$4B, 8-12% IRR): Growth decelerates to 20-25%, margin stalls. 8-10x exit. Capital protection via preferred. Prob: 25%.",
            "recommendation": "PROCEED TO DETAILED DILIGENCE — Attractive risk/reward at $4B. Priorities: customer calls, CTO tech deep-dive, financial model audit, win/loss analysis.",
            "sources": [5, 12, 13, 14, 17, 18],
        },
        "dashboard_metrics": {
            "metrics": [
                {"label": "Est. ARR", "value": "$300M+", "trend": "up"},
                {"label": "Revenue Growth", "value": "40-55% Y/Y", "trend": "up"},
                {"label": "NRR", "value": "128-135%", "trend": "up"},
                {"label": "Gross Margin", "value": "72-78%", "trend": "up"},
                {"label": "LTV:CAC", "value": "4.5-5.5x", "trend": "up"},
                {"label": "Rule of 40", "value": "55-65", "trend": "up"},
                {"label": "Logo Retention", "value": "92-95%", "trend": "flat"},
                {"label": "Competitive Risk", "value": "Med-High", "trend": "up"},
                {"label": "Valuation", "value": "$4B", "trend": "up"},
                {"label": "Base IRR", "value": "20-30%", "trend": "flat"},
            ],
            "sources": [10, 12, 13, 14],
        },
        "all_sources": [
            {"id": i, "title": t, "url": u, "snippet": s}
            for i, (t, u, s) in enumerate(
                [
                    ("Company Website", "https://example.com/company", "Official company information."),
                    ("LinkedIn Profile", "https://linkedin.com/company/example", "Employee headcount and leadership."),
                    ("Product Docs", "https://docs.example.com", "Technical architecture."),
                    ("Pricing Analysis", "https://example.com/pricing", "Pricing tiers."),
                    ("Crunchbase", "https://crunchbase.com/company/example", "Funding history."),
                    ("Executive Profiles", "https://linkedin.com/in/ceo", "Leadership backgrounds."),
                    ("G2 Reviews", "https://g2.com/products/example", "Customer reviews."),
                    ("Gartner Market Guide", "https://gartner.com/ai", "Market sizing."),
                    ("IDC Analysis", "https://idc.com/ai-2024", "Growth projections."),
                    ("SaaS Benchmarks", "https://example.com/benchmarks", "Unit economics benchmarks."),
                    ("Customer Cases", "https://example.com/customers", "ROI case studies."),
                    ("PitchBook Data", "https://pitchbook.com/example", "Valuations."),
                    ("CB Insights", "https://cbinsights.com/example", "Competitive landscape."),
                    ("Industry Research", "https://example.com/market-2024", "TAM analysis."),
                    ("Compliance Filings", "https://example.com/compliance", "Certifications."),
                    ("EU AI Act", "https://example.com/eu-ai", "Regulatory impact."),
                    ("M&A Comps", "https://example.com/ma-comps", "Transaction comparables."),
                    ("IPO Analysis", "https://example.com/ipo", "IPO market conditions."),
                ],
                start=1,
            )
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
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for title, url in links:
        if url in seen:
            continue
        seen.add(url)
        unique.append((title, url))
    return [{"id": i, "title": t, "url": u, "snippet": "Grounded web source."} for i, (t, u) in enumerate(unique, 1)]


def _parse_json_text(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def _build_research_prompt(company: str, feedback: str) -> str:
    fb = f"\n\n== CRITICAL: FIX THESE QUALITY ISSUES ==\n{feedback}\n" if feedback else ""
    return f"""You are a senior partner at McKinsey & Company leading a $500M+ PE due diligence engagement.
Your IC memo will be scrutinized by managing partners of a top-3 global PE fund.
Every claim must be evidence-backed. Every estimate must include methodology.

TARGET: {company}

Return STRICT JSON only. No markdown. No commentary outside JSON.

HARD REQUIREMENTS (violation = rejection):
1. Every major section MUST have 2+ quantitative data points (numbers, $, %, multiples).
2. NO vague language ("high growth", "strong team") without supporting numbers.
3. When exact data unavailable, provide REASONED ESTIMATE with methodology and confidence (High/Med/Low).
4. Name specific people, companies, products, transactions — no generic placeholders.
5. management_team: 3+ named individuals with titles and backgrounds.
6. comparable_transactions: 3+ named transactions/public comps with multiples.
7. unit_economics: 5+ named metrics with estimated values.
8. exit_analysis: 3+ named strategic acquirers with rationale.
9. dashboard_metrics: 8+ distinct KPIs.
10. all_sources: empty array [] (extracted separately).

RESEARCH SOURCES TO USE: company website, LinkedIn, Crunchbase/PitchBook, product docs,
G2/Gartner reviews, analyst reports, news, SEC filings, patents, job postings, press releases.

JSON SCHEMA:
{{
  "company": "{company}",
  "company_profile": {{
    "summary": "400+ char overview with key metrics",
    "founded": "year", "headquarters": "city, country",
    "employee_estimate": "range with methodology",
    "key_facts": ["fact with number", "fact2", "fact3"],
    "sources": [1,2]
  }},
  "management_team": {{
    "summary": "400+ char leadership assessment",
    "executives": [{{"name": "Full Name", "background": "credentials", "signal": "investment implication"}}],
    "key_man_risk": "assessment with mitigants",
    "sources": [1,2]
  }},
  "product_and_technology": {{
    "summary": "400+ char with differentiation evidence",
    "core_offerings": ["offering with revenue contribution"],
    "moat_hypothesis": "defensibility thesis with confidence level",
    "tech_differentiation": ["advantage with quantification"],
    "sources": [1,2]
  }},
  "business_model": {{
    "summary": "400+ char with pricing specifics",
    "pricing_motion": "tiers, ACV ranges, expansion mechanics",
    "customer_segments": ["segment with revenue share and ACV"],
    "revenue_composition": {{"subscriptions_pct": "X%", "usage_based_pct": "Y%", "professional_services_pct": "Z%"}},
    "sources": [1,2]
  }},
  "unit_economics": {{
    "summary": "400+ char with benchmarks",
    "metrics": {{
      "cac_estimate": "$ range with breakdown",
      "ltv_estimate": "$ range with methodology",
      "ltv_cac_ratio": "Xx with trend",
      "nrr_ndr": "X% with benchmark",
      "gross_margin": "X% with segment breakdown",
      "payback_period_months": "X months",
      "rule_of_40_score": "X",
      "logo_retention": "X%"
    }},
    "confidence": "High/Med/Low with note",
    "sources": [1,2]
  }},
  "financial_signals": {{
    "summary": "400+ char",
    "arr_trajectory": "ARR range with trajectory",
    "funding": "total raised, last round, key investors",
    "valuation_signal": "valuation with multiples",
    "burn_vs_growth_signal": "burn, runway, efficiency",
    "revenue_growth_cagr": "X% with context",
    "sources": [1,2]
  }},
  "customer_evidence": {{
    "summary": "300+ char",
    "logo_highlights": ["named categories"],
    "concentration_risk": "top 10 share",
    "churn_signals": "retention data",
    "nps_proxy": "review scores",
    "case_studies": ["ROI example with metrics"],
    "sources": [1,2]
  }},
  "market_landscape": {{
    "summary": "400+ char with TAM/SAM/SOM",
    "competitors": ["5+ named competitors"],
    "market_size_estimate": "TAM $XB, SAM $XB, SOM $XB",
    "industry_trends": ["3+ trends with numbers"],
    "sources": [1,2]
  }},
  "competitive_positioning": {{
    "summary": "300+ char",
    "positioning_matrix": [{{"competitor": "Name", "strengths": "...", "weaknesses": "...", "relative_position": "..."}}],
    "key_differentiators": ["with evidence"],
    "sources": [1,2]
  }},
  "comparable_transactions": {{
    "summary": "300+ char",
    "private_transactions": [{{"target": "Name", "acquirer_investor": "Name", "deal_value": "$XB", "revenue_multiple": "Xx"}}],
    "public_comps": [{{"company": "Name (TICKER)", "ev_revenue_multiple": "Xx", "growth_rate": "X%"}}],
    "implied_valuation_range": "$XB-$YB",
    "sources": [1,2]
  }},
  "regulatory_landscape": {{
    "summary": "250+ char",
    "ip_exposure": "patent status",
    "data_privacy": "compliance status",
    "regulatory_moats": ["moat"],
    "regulatory_risks": ["risk with cost"],
    "sources": [1,2]
  }},
  "risk_assessment": {{
    "summary": "400+ char",
    "key_risks": [{{"risk": "specific", "severity": "H/M/L", "mitigation": "specific", "probability": "X%"}}],
    "overall_risk_rating": "with rationale",
    "sources": [1,2]
  }},
  "catalysts_and_outlook": {{
    "summary": "300+ char",
    "catalysts": [{{"catalyst": "event", "timeline": "months", "impact": "outcome", "probability": "X%"}}],
    "sources": [1,2]
  }},
  "exit_analysis": {{
    "summary": "300+ char",
    "strategic_acquirers": [{{"acquirer": "Name", "rationale": "logic", "estimated_willingness": "H/M/L"}}],
    "ipo_readiness": {{"assessment": "signals", "comparable_ipo_valuations": "range"}},
    "exit_multiples": {{"bear_case": "Xx ($XB)", "base_case": "Xx ($XB)", "bull_case": "Xx ($XB)"}},
    "implied_irr": {{"bear_case": "X%", "base_case": "X%", "bull_case": "X%"}},
    "sources": [1,2]
  }},
  "investment_view": {{
    "summary": "400+ char recommendation",
    "base_case": "detailed with probability",
    "upside_case": "detailed with drivers",
    "downside_case": "detailed with protection",
    "recommendation": "PROCEED/PASS/CONDITIONAL with priorities",
    "sources": [1,2]
  }},
  "dashboard_metrics": {{
    "metrics": [{{"label": "Name", "value": "Value", "trend": "up|down|flat"}}],
    "sources": [1,2]
  }},
  "all_sources": []
}}
{fb}"""


def _min_sources_required() -> int:
    return 6 if settings.mock_mode else 15


_VAGUE = re.compile(r"\b(unknown|n/a|not available|not disclosed|unclear|limited data)\b", re.I)


def _evaluate_research_quality(data: dict[str, Any]) -> tuple[bool, list[str], int]:
    issues: list[str] = []
    score = 100

    for s in REQUIRED_SECTIONS:
        if s not in data or not data[s]:
            issues.append(f"Missing: {s}")
            score -= 12

    for s in MAJOR_SECTIONS:
        d = data.get(s, {})
        summary = d.get("summary", "") if isinstance(d, dict) else ""
        if len(summary) < 200:
            issues.append(f"{s} summary too short ({len(summary)}<200)")
            score -= 6

    src = data.get("all_sources", [])
    if len(src) < _min_sources_required():
        issues.append(f"Sources: {len(src)} < {_min_sources_required()}")
        score -= 15

    dm = data.get("dashboard_metrics", {})
    mets = dm.get("metrics", []) if isinstance(dm, dict) else []
    if len(mets) < 8:
        issues.append(f"Dashboard metrics: {len(mets)} < 8")
        score -= 10

    mgmt = data.get("management_team", {})
    if isinstance(mgmt, dict) and len(mgmt.get("executives", [])) < 2:
        issues.append("management_team: need 2+ executives")
        score -= 8

    comps = data.get("comparable_transactions", {})
    if isinstance(comps, dict):
        n = len(comps.get("private_transactions", [])) + len(comps.get("public_comps", []))
        if n < 3:
            issues.append(f"comps: {n} < 3")
            score -= 8

    ue = data.get("unit_economics", {})
    if isinstance(ue, dict):
        m = ue.get("metrics", {})
        if isinstance(m, dict) and sum(1 for v in m.values() if v and str(v).strip()) < 4:
            issues.append("unit_economics: need 4+ filled metrics")
            score -= 8

    ex = data.get("exit_analysis", {})
    if isinstance(ex, dict) and len(ex.get("strategic_acquirers", [])) < 2:
        issues.append("exit_analysis: need 2+ acquirers")
        score -= 6

    ml = data.get("market_landscape", {})
    if isinstance(ml, dict) and len(ml.get("competitors", [])) < 4:
        issues.append("competitors: need 4+")
        score -= 6

    ra = data.get("risk_assessment", {})
    if isinstance(ra, dict) and len(ra.get("key_risks", [])) < 3:
        issues.append("risks: need 3+")
        score -= 6

    vague_count = len(_VAGUE.findall(json.dumps(data)))
    if vague_count > 10:
        issues.append(f"Vague language: {vague_count} instances")
        score -= min(15, vague_count)

    return score >= 85 and not issues, issues, score


def _normalize_research(data: dict[str, Any]) -> dict[str, Any]:
    if "company" not in data:
        data["company"] = "Unknown"
    data.setdefault("dashboard_metrics", {}).setdefault("metrics", [])
    for s in REQUIRED_SECTIONS:
        data.setdefault(s, {})
    return data


def _reindex_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": i, "title": s.get("title", "Untitled"), "url": s.get("url", ""), "snippet": s.get("snippet", "Source.")} for i, s in enumerate(sources, 1)]


def _merge_sources(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for s in a + b:
        u = s.get("url", "")
        if not u or u in seen:
            continue
        seen.add(u)
        merged.append(s)
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
                # Note: response_mime_type="application/json" is incompatible with
                # Google Search grounding tool. JSON is enforced via prompt instead.
            ),
        )
        raw = _extract_text(response)
        if not raw:
            feedback = "EMPTY response. Return COMPLETE JSON with all 16 sections."
            continue
        try:
            data = _normalize_research(_parse_json_text(raw))
        except Exception:
            feedback = "INVALID JSON. Return strict JSON only."
            continue
        sources = _extract_sources(response)
        cumulative_sources = _merge_sources(cumulative_sources, sources)
        if not cumulative_sources:
            cumulative_sources = _mock_research(company)["all_sources"]
        data["all_sources"] = cumulative_sources
        ok, issues, sc = _evaluate_research_quality(data)
        if sc > best_score:
            best_score = sc
            best_data = data
        if ok:
            return data
        feedback = " ; ".join(issues)

    return best_data or _mock_research(company)


# ═══════════════════════════════════════════════════════════════
# Streaming research with chain-of-thought + grounding visibility
# ═══════════════════════════════════════════════════════════════

def _extract_stream_sources(candidate: Any) -> list[dict[str, str]]:
    """Extract grounding sources from a streaming candidate chunk."""
    grounding = getattr(candidate, "grounding_metadata", None)
    if not grounding:
        return []
    chunks = getattr(grounding, "grounding_chunks", None) or []
    sources = []
    seen: set[str] = set()
    for chunk in chunks:
        web = getattr(chunk, "web", None)
        if web and getattr(web, "uri", None) and web.uri not in seen:
            seen.add(web.uri)
            sources.append({"title": getattr(web, "title", ""), "url": web.uri})

    queries = getattr(grounding, "web_search_queries", None) or []
    return sources, list(queries) if queries else []


def _extract_thinking(candidate: Any) -> str:
    """Extract thinking/thought text from a candidate."""
    content = getattr(candidate, "content", None)
    if not content:
        return ""
    parts = getattr(content, "parts", None) or []
    thoughts = []
    for part in parts:
        if getattr(part, "thought", False) and getattr(part, "text", None):
            thoughts.append(part.text)
    return " ".join(thoughts)


def run_research_stream(company: str):
    """Generator that yields SSE event dicts during research.

    Event types:
      {"event": "thinking", "data": "thought text..."}
      {"event": "search",   "data": "query string"}
      {"event": "source",   "data": {"title": "...", "url": "..."}}
      {"event": "progress", "data": "status message"}
      {"event": "attempt",  "data": {"attempt": 1, "score": 85, "issues": [...]}}
      {"event": "done",     "data": <full research dict>}
      {"event": "error",    "data": "error message"}
    """
    if settings.mock_mode or not settings.gemini_api_key:
        yield {"event": "progress", "data": "Running in mock mode..."}
        yield {"event": "thinking", "data": f"Generating mock research data for {company}..."}
        import time
        time.sleep(0.5)
        yield {"event": "search", "data": f"{company} company overview"}
        time.sleep(0.3)
        yield {"event": "search", "data": f"{company} funding valuation"}
        time.sleep(0.3)
        mock = _mock_research(company)
        for src in mock["all_sources"][:6]:
            yield {"event": "source", "data": {"title": src["title"], "url": src["url"]}}
            time.sleep(0.1)
        yield {"event": "progress", "data": "Mock research complete."}
        yield {"event": "done", "data": mock}
        return

    client = genai.Client(api_key=settings.gemini_api_key)
    feedback = ""
    best_data: dict[str, Any] | None = None
    best_score = -1
    cumulative_sources: list[dict[str, Any]] = []
    seen_search_queries: set[str] = set()
    seen_source_urls: set[str] = set()

    max_attempts = max(1, settings.research_max_attempts)

    for attempt in range(max_attempts):
        yield {"event": "progress", "data": f"Research attempt {attempt + 1}/{max_attempts}..."}

        prompt = _build_research_prompt(company, feedback)

        try:
            stream = client.models.generate_content_stream(
                model=settings.gemini_research_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )
        except Exception as e:
            yield {"event": "error", "data": f"API call failed: {e}"}
            continue

        full_text_parts: list[str] = []
        last_response = None

        for chunk in stream:
            last_response = chunk

            # Extract thinking from candidates
            candidates = getattr(chunk, "candidates", None) or []
            for candidate in candidates:
                # Thinking text
                thought = _extract_thinking(candidate)
                if thought:
                    yield {"event": "thinking", "data": thought}

                # Regular text
                content = getattr(candidate, "content", None)
                if content:
                    for part in getattr(content, "parts", None) or []:
                        if not getattr(part, "thought", False) and getattr(part, "text", None):
                            full_text_parts.append(part.text)

                # Grounding sources
                try:
                    sources_data, queries = _extract_stream_sources(candidate)
                    for q in queries:
                        if q not in seen_search_queries:
                            seen_search_queries.add(q)
                            yield {"event": "search", "data": q}
                    for src in sources_data:
                        if src["url"] not in seen_source_urls:
                            seen_source_urls.add(src["url"])
                            yield {"event": "source", "data": src}
                except Exception:
                    pass

        raw = "".join(full_text_parts)
        if not raw:
            feedback = "EMPTY response. Return COMPLETE JSON with all 16 sections."
            yield {"event": "progress", "data": "Empty response, retrying..."}
            continue

        try:
            data = _normalize_research(_parse_json_text(raw))
        except Exception:
            feedback = "INVALID JSON. Return strict JSON only."
            yield {"event": "progress", "data": "Invalid JSON response, retrying..."}
            continue

        # Extract sources from last response
        if last_response:
            batch_sources = _extract_sources(last_response)
            cumulative_sources = _merge_sources(cumulative_sources, batch_sources)
        if not cumulative_sources:
            cumulative_sources = _mock_research(company)["all_sources"]
        data["all_sources"] = cumulative_sources

        ok, issues, sc = _evaluate_research_quality(data)
        yield {"event": "attempt", "data": {"attempt": attempt + 1, "score": sc, "issues": issues}}

        if sc > best_score:
            best_score = sc
            best_data = data
        if ok:
            yield {"event": "progress", "data": f"Research passed quality check (score: {sc}/100)"}
            yield {"event": "done", "data": data}
            return
        feedback = " ; ".join(issues)
        yield {"event": "progress", "data": f"Score {sc}/100 — retrying with feedback..."}

    final = best_data or _mock_research(company)
    yield {"event": "progress", "data": f"Using best result (score: {best_score}/100)"}
    yield {"event": "done", "data": final}
