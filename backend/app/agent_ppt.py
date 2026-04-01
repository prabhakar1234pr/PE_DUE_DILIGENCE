import json
from io import BytesIO
from typing import Any

from google import genai
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt

from app.settings import settings


def _mock_slides(company: str, research: dict[str, Any]) -> dict[str, Any]:
    sources = research.get("all_sources", [])
    source_ids = [src["id"] for src in sources[:5]] or [1, 2, 3, 4, 5]
    dashboard_metrics = research.get("dashboard_metrics", {}).get("metrics", [])
    return {
        "slides": [
            {
                "slide_number": 1,
                "title": "Company Overview",
                "subtitle": f"{company} snapshot",
                "bullets": [
                    research["company_profile"]["summary"],
                    f"Founded: {research['company_profile']['founded']}",
                    f"HQ: {research['company_profile']['headquarters']}",
                ],
                "key_stat": f"Employees: {research['company_profile']['employee_estimate']}",
                "source_ids": source_ids,
            },
            {
                "slide_number": 2,
                "title": "Product and Technology",
                "subtitle": "Moat and product depth",
                "bullets": [
                    research["product_and_technology"]["summary"],
                    "Core offerings: "
                    + ", ".join(research["product_and_technology"]["core_offerings"][:4]),
                    "Moat hypothesis: " + research["product_and_technology"]["moat_hypothesis"],
                ],
                "key_stat": "Technology moat under diligence",
                "source_ids": source_ids,
            },
            {
                "slide_number": 3,
                "title": "Business Model",
                "subtitle": "Revenue mechanics and buyers",
                "bullets": [
                    research["business_model"]["summary"],
                    "Pricing motion: " + research["business_model"]["pricing_motion"],
                    "Segments: " + ", ".join(research["business_model"]["customer_segments"][:4]),
                ],
                "key_stat": "Monetization quality assessment",
                "source_ids": source_ids,
            },
            {
                "slide_number": 4,
                "title": "Financial Signals",
                "subtitle": "Funding, valuation, and burn context",
                "bullets": [
                    research["financial_signals"]["summary"],
                    "Funding: " + research["financial_signals"]["funding"],
                    "Valuation signal: " + research["financial_signals"]["valuation_signal"],
                ],
                "key_stat": research["financial_signals"]["burn_vs_growth_signal"],
                "source_ids": source_ids,
            },
            {
                "slide_number": 5,
                "title": "Market Landscape",
                "subtitle": "Size, trends, and positioning",
                "bullets": [
                    research["market_landscape"]["summary"],
                    "Market size: " + research["market_landscape"]["market_size_estimate"],
                    "Competitors: " + ", ".join(research["market_landscape"]["competitors"][:5]),
                ],
                "key_stat": "Category competition is intense",
                "source_ids": source_ids,
            },
            {
                "slide_number": 6,
                "title": "Dashboard: Company KPIs",
                "subtitle": "Key diligence metrics snapshot",
                "bullets": [
                    "KPI dashboard summarizing traction and risk indicators.",
                    "Use as quick PE memo companion for investment committee discussion.",
                    "Cross-check all metrics with source panel.",
                ],
                "key_stat": "KPI dashboard",
                "source_ids": source_ids,
                "dashboard_metrics": dashboard_metrics[:6],
            },
            {
                "slide_number": 7,
                "title": "Dashboard: Market and Risk Indicators",
                "subtitle": "Macro and competitive pressure view",
                "bullets": [
                    "Tracks market growth, pricing pressure, and moat resilience.",
                    "Supports scenario framing for downside and upside cases.",
                    "Use together with risk slide and investment view.",
                ],
                "key_stat": "Risk heatmap summary",
                "source_ids": source_ids,
                "dashboard_metrics": dashboard_metrics[:6],
            },
            {
                "slide_number": 8,
                "title": "Risk Assessment",
                "subtitle": "Top downside considerations",
                "bullets": [
                    research["risk_assessment"]["summary"],
                    *research["risk_assessment"]["key_risks"][:3],
                ],
                "key_stat": "Downside protection analysis",
                "source_ids": source_ids,
            },
            {
                "slide_number": 9,
                "title": "Catalysts and Outlook",
                "subtitle": "Near and medium term upside levers",
                "bullets": [
                    research["catalysts_and_outlook"]["summary"],
                    *research["catalysts_and_outlook"]["catalysts"][:3],
                ],
                "key_stat": "Catalyst-driven thesis sensitivity",
                "source_ids": source_ids,
            },
            {
                "slide_number": 10,
                "title": "Investment View",
                "subtitle": "Base, upside, downside",
                "bullets": [
                    "Base case: " + research["investment_view"]["base_case"],
                    "Upside case: " + research["investment_view"]["upside_case"],
                    "Downside case: " + research["investment_view"]["downside_case"],
                ],
                "key_stat": f"{len(research.get('all_sources', []))} cited sources",
                "source_ids": source_ids,
            },
            {
                "slide_number": 11,
                "title": "Execution Plan",
                "subtitle": "100-day post-investment priorities",
                "bullets": [
                    "Commercial: prioritize top enterprise logos and expansion motion.",
                    "Product: accelerate roadmap items tied to retention and expansion.",
                    "Finance: enforce disciplined burn control and unit economics tracking.",
                ],
                "key_stat": "Value-creation roadmap",
                "source_ids": source_ids,
            },
            {
                "slide_number": 12,
                "title": "Sources Appendix",
                "subtitle": "Traceable evidence index",
                "bullets": [
                    "All primary evidence points are linked in the source panel.",
                    "Cross-reference source IDs with each slide claim before IC review.",
                    "Highlight unresolved data gaps as diligence follow-ups.",
                ],
                "key_stat": "Audit-ready citation trail",
                "source_ids": source_ids,
            },
        ]
    }


def _slides_from_gemini(company: str, research: dict[str, Any]) -> dict[str, Any]:
    if settings.mock_mode or not settings.gemini_api_key:
        return _mock_slides(company, research)

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""
You are an elite private-equity presentation strategist.
Create a strict JSON object for a high-stakes due diligence deck.
No markdown. No explanation.

Company: {company}
Research JSON:
{json.dumps(research)}

Return schema:
{{
  "slides": [
    {{
      "slide_number": 1,
      "title": "...",
      "subtitle": "...",
      "bullets": ["...", "...", "..."],
      "key_stat": "...",
      "source_ids": [1,2,3],
      "dashboard_metrics": [
        {{"label": "...", "value": "...", "trend": "up|down|flat"}}
      ]
    }}
  ]
}}

Rules:
- Produce 12 to 20 slides, based on content depth.
- Every slide must be investor-grade with quant-heavy bullets.
- Include at least 3 dashboard/analytics slides with dashboard_metrics arrays.
- Every slide must include source_ids from available source IDs.
- Ensure slide flow: overview -> product -> business model -> financials -> market -> competition -> dashboards -> risks -> catalysts -> investment view.
"""
    feedback = ""
    best: dict[str, Any] | None = None
    best_score = -1
    for _ in range(max(1, settings.slide_max_attempts)):
        run_prompt = prompt + (f"\nFix these quality issues: {feedback}\n" if feedback else "")
        response = client.models.generate_content(
            model=settings.gemini_slide_model,
            contents=run_prompt,
        )
        raw_text = response.text or ""
        if not raw_text:
            feedback = "Previous response was empty."
            continue

        try:
            cleaned = raw_text.strip().strip("```json").strip("```").strip()
            parsed = json.loads(cleaned)
        except Exception:
            feedback = "Previous output was invalid JSON."
            continue

        if "slides" not in parsed:
            feedback = "Missing slides array."
            continue
        parsed["slides"] = _normalize_slides(parsed["slides"])
        passed, issues, score = _evaluate_slide_quality(parsed["slides"])
        if score > best_score:
            best = parsed
            best_score = score
        if passed:
            return parsed
        feedback = " ; ".join(issues)

    return best or _mock_slides(company, research)


def _normalize_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not slides:
        return []
    normalized: list[dict[str, Any]] = []
    for idx, slide in enumerate(slides, start=1):
        normalized.append(
            {
                "slide_number": idx,
                "title": slide.get("title", f"Slide {idx}"),
                "subtitle": slide.get("subtitle", ""),
                "bullets": slide.get("bullets", [])[:6],
                "key_stat": slide.get("key_stat", ""),
                "source_ids": slide.get("source_ids", [])[:6],
                "dashboard_metrics": slide.get("dashboard_metrics", [])[:6],
            }
        )
    return normalized[:24]


def _evaluate_slide_quality(slides: list[dict[str, Any]]) -> tuple[bool, list[str], int]:
    issues: list[str] = []
    score = 100

    if len(slides) < 12:
        issues.append("Need at least 12 slides.")
        score -= 20

    dashboard_slides = sum(1 for slide in slides if slide.get("dashboard_metrics"))
    if dashboard_slides < 3:
        issues.append("Need at least 3 dashboard slides.")
        score -= 20

    for idx, slide in enumerate(slides, start=1):
        if len(slide.get("bullets", [])) < 3:
            issues.append(f"Slide {idx} needs at least 3 bullets.")
            score -= 5
        if len(slide.get("source_ids", [])) < 2:
            issues.append(f"Slide {idx} needs at least 2 source IDs.")
            score -= 5
        if not slide.get("key_stat", ""):
            issues.append(f"Slide {idx} missing key_stat.")
            score -= 4

    passed = score >= 80 and not issues
    return passed, issues, score


def _create_pptx(company: str, slides: list[dict[str, Any]]) -> bytes:
    presentation = Presentation()

    dark_navy = RGBColor(10, 22, 40)
    gold = RGBColor(201, 168, 76)
    white = RGBColor(255, 255, 255)

    for slide_data in slides:
        slide_layout = presentation.slide_layouts[6]
        slide = presentation.slides.add_slide(slide_layout)

        background = slide.background
        background.fill.solid()
        background.fill.fore_color.rgb = dark_navy

        title_box = slide.shapes.add_textbox(Pt(24), Pt(18), Pt(820), Pt(48))
        title_tf = title_box.text_frame
        title_tf.text = slide_data["title"]
        title_tf.paragraphs[0].font.size = Pt(30)
        title_tf.paragraphs[0].font.bold = True
        title_tf.paragraphs[0].font.color.rgb = white

        subtitle_box = slide.shapes.add_textbox(Pt(24), Pt(72), Pt(820), Pt(30))
        subtitle_tf = subtitle_box.text_frame
        subtitle_tf.text = slide_data.get("subtitle", "")
        subtitle_tf.paragraphs[0].font.size = Pt(18)
        subtitle_tf.paragraphs[0].font.color.rgb = gold

        bullet_box = slide.shapes.add_textbox(Pt(40), Pt(130), Pt(860), Pt(360))
        bullet_tf = bullet_box.text_frame
        bullet_tf.clear()
        for bullet in slide_data.get("bullets", []):
            p = bullet_tf.add_paragraph()
            p.text = bullet
            p.level = 0
            p.font.size = Pt(20)
            p.font.color.rgb = white

        dashboard_metrics = slide_data.get("dashboard_metrics", [])
        if dashboard_metrics:
            start_x = Pt(40)
            y = Pt(390)
            card_w = Pt(200)
            card_h = Pt(100)
            gap = Pt(12)
            for idx, metric in enumerate(dashboard_metrics[:4]):
                card = slide.shapes.add_textbox(start_x + (card_w + gap) * idx, y, card_w, card_h)
                card_tf = card.text_frame
                card_tf.text = str(metric.get("label", "Metric"))
                card_tf.paragraphs[0].font.size = Pt(12)
                card_tf.paragraphs[0].font.color.rgb = gold

                p_value = card_tf.add_paragraph()
                p_value.text = str(metric.get("value", "N/A"))
                p_value.font.size = Pt(20)
                p_value.font.bold = True
                p_value.font.color.rgb = white

                p_trend = card_tf.add_paragraph()
                p_trend.text = f"Trend: {metric.get('trend', 'flat')}"
                p_trend.font.size = Pt(11)
                p_trend.font.color.rgb = white

        key_stat_box = slide.shapes.add_textbox(Pt(24), Pt(510), Pt(860), Pt(28))
        key_stat_tf = key_stat_box.text_frame
        key_stat_tf.text = f"Key Stat: {slide_data.get('key_stat', '')}"
        key_stat_tf.paragraphs[0].font.size = Pt(14)
        key_stat_tf.paragraphs[0].font.bold = True
        key_stat_tf.paragraphs[0].font.color.rgb = gold

        source_ids = slide_data.get("source_ids", [])
        source_box = slide.shapes.add_textbox(Pt(24), Pt(540), Pt(860), Pt(20))
        source_tf = source_box.text_frame
        source_tf.text = "Sources: " + " ".join([f"[{sid}]" for sid in source_ids])
        source_tf.paragraphs[0].font.size = Pt(11)
        source_tf.paragraphs[0].font.color.rgb = white

    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


def build_presentation(company: str, research: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    slide_payload = _slides_from_gemini(company, research)
    slides = _normalize_slides(slide_payload["slides"])
    pptx_file = _create_pptx(company, slides)
    return {"slides": slides}, pptx_file
