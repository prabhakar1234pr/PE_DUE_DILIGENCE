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
    source_ids = [src["id"] for src in sources[:3]] or [1, 2, 3]
    return {
        "slides": [
            {
                "slide_number": 1,
                "title": "Company Overview",
                "subtitle": f"{company} snapshot",
                "bullets": [
                    research["overview"]["summary"],
                    f"Founded: {research['overview']['founded']}",
                    f"Funding: {research['overview']['funding']}",
                ],
                "key_stat": research["overview"]["funding"],
                "source_ids": source_ids,
            },
            {
                "slide_number": 2,
                "title": "Market Landscape",
                "subtitle": "Growth and positioning",
                "bullets": [
                    research["market"]["summary"],
                    f"Market Size: {research['market']['market_size']}",
                    "Top competitors: " + ", ".join(research["market"]["competitors"][:4]),
                ],
                "key_stat": research["market"]["market_size"],
                "source_ids": source_ids,
            },
            {
                "slide_number": 3,
                "title": "Competitive Analysis",
                "subtitle": "Relative strengths",
                "bullets": [
                    "Strength: focused AI execution.",
                    "Watchout: aggressive incumbents.",
                    "Differentiation depends on product velocity.",
                ],
                "key_stat": "Top 5 competitor pressure",
                "source_ids": source_ids,
            },
            {
                "slide_number": 4,
                "title": "Risk Factors",
                "subtitle": "Execution and market risks",
                "bullets": [
                    research["risks"]["summary"],
                    "Capital intensity risk in model and infra costs.",
                    "Go-to-market risk in enterprise adoption cycles.",
                ],
                "key_stat": "High competitive intensity",
                "source_ids": source_ids,
            },
            {
                "slide_number": 5,
                "title": "Key Metrics and Sources",
                "subtitle": "Due diligence snapshot",
                "bullets": [
                    f"Company: {company}",
                    f"Sources referenced: {len(research.get('all_sources', []))}",
                    "All cited links listed in source panel.",
                ],
                "key_stat": f"{len(research.get('all_sources', []))} sources",
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
Create a strict JSON object with exactly 5 slides.
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
      "source_ids": [1,2,3]
    }}
  ]
}}

Rules:
- Exactly 5 slides.
- Bullet points must be concise and investor-oriented.
- Every slide must include source_ids from available source IDs.
"""
    response = client.models.generate_content(
        model=settings.gemini_slide_model,
        contents=prompt,
    )
    raw_text = response.text or ""
    if not raw_text:
        return _mock_slides(company, research)

    cleaned = raw_text.strip().strip("```json").strip("```").strip()
    parsed = json.loads(cleaned)
    if "slides" not in parsed:
        return _mock_slides(company, research)
    return parsed


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
    slides = slide_payload["slides"]
    pptx_file = _create_pptx(company, slides)
    return slide_payload, pptx_file
