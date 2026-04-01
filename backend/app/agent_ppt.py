import json
from io import BytesIO
from typing import Any

from google import genai
from google.genai import types
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.settings import settings

# ── Color palette ────────────────────────────────────────────
DARK_NAVY = RGBColor(10, 22, 40)
NAVY_LIGHT = RGBColor(18, 35, 60)
GOLD = RGBColor(201, 168, 76)
WHITE = RGBColor(255, 255, 255)
LIGHT_GRAY = RGBColor(180, 180, 195)
ACCENT_TEAL = RGBColor(56, 189, 170)
ACCENT_RED = RGBColor(220, 80, 80)
DARK_CARD = RGBColor(20, 38, 65)
MID_GRAY = RGBColor(120, 130, 150)

# ── Slide dimensions (16:9 widescreen) ──────────────────────
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# ── Layout constants ─────────────────────────────────────────
HEADER_H = Inches(0.55)
ACCENT_W = Inches(0.1)
FOOTER_H = Inches(0.35)
CONTENT_LEFT = Inches(0.65)
CONTENT_TOP = Inches(1.15)
CONTENT_W = Inches(12.0)
CONTENT_BOTTOM = SLIDE_H - FOOTER_H - Inches(0.2)


# ═══════════════════════════════════════════════════════════════
# Shared slide chrome
# ═══════════════════════════════════════════════════════════════

def _add_background(slide):
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = DARK_NAVY


def _add_header_bar(slide, title: str, subtitle: str):
    """Top band with title and subtitle."""
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, HEADER_H)
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY_LIGHT
    bar.line.fill.background()

    # Title
    tb = slide.shapes.add_textbox(Inches(0.65), Inches(0.06), Inches(9.5), Inches(0.3))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = WHITE

    # Subtitle
    if subtitle:
        sb = slide.shapes.add_textbox(Inches(0.65), Inches(0.34), Inches(9.5), Inches(0.2))
        sf = sb.text_frame
        sp = sf.paragraphs[0]
        sp.text = subtitle
        sp.font.size = Pt(12)
        sp.font.color.rgb = GOLD
        sp.font.italic = True


def _add_accent_bar(slide):
    """Thin gold vertical bar on the left."""
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, HEADER_H, ACCENT_W, SLIDE_H - HEADER_H
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = GOLD
    bar.line.fill.background()


def _add_footer(slide, company: str, slide_num: int, total: int):
    """Bottom bar with company, slide counter, confidential label."""
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, SLIDE_H - FOOTER_H, SLIDE_W, FOOTER_H
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY_LIGHT
    bar.line.fill.background()

    # Company name (left)
    lb = slide.shapes.add_textbox(Inches(0.65), SLIDE_H - FOOTER_H + Inches(0.06), Inches(4), Inches(0.22))
    lf = lb.text_frame
    lp = lf.paragraphs[0]
    lp.text = company
    lp.font.size = Pt(9)
    lp.font.color.rgb = MID_GRAY

    # Slide number (center)
    cb = slide.shapes.add_textbox(Inches(5.5), SLIDE_H - FOOTER_H + Inches(0.06), Inches(2.5), Inches(0.22))
    cf = cb.text_frame
    cp = cf.paragraphs[0]
    cp.text = f"{slide_num} / {total}"
    cp.font.size = Pt(9)
    cp.font.color.rgb = MID_GRAY
    cp.alignment = PP_ALIGN.CENTER

    # Confidential (right)
    rb = slide.shapes.add_textbox(Inches(10.0), SLIDE_H - FOOTER_H + Inches(0.06), Inches(3.0), Inches(0.22))
    rf = rb.text_frame
    rp = rf.paragraphs[0]
    rp.text = "CONFIDENTIAL"
    rp.font.size = Pt(8)
    rp.font.color.rgb = GOLD
    rp.font.bold = True
    rp.alignment = PP_ALIGN.RIGHT


def _add_chrome(slide, company: str, title: str, subtitle: str, slide_num: int, total: int):
    _add_background(slide)
    _add_header_bar(slide, title, subtitle)
    _add_accent_bar(slide)
    _add_footer(slide, company, slide_num, total)


# ═══════════════════════════════════════════════════════════════
# Slide type renderers
# ═══════════════════════════════════════════════════════════════

def _render_title_slide(slide, company: str, data: dict, total: int):
    _add_background(slide)
    _add_accent_bar(slide)
    _add_footer(slide, company, 1, total)

    # Company name large centered
    tb = slide.shapes.add_textbox(Inches(1.5), Inches(2.0), Inches(10.5), Inches(1.2))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    p.text = company
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER

    # Subtitle
    sb = slide.shapes.add_textbox(Inches(1.5), Inches(3.3), Inches(10.5), Inches(0.5))
    sf = sb.text_frame
    sp = sf.paragraphs[0]
    sp.text = "Private Equity Due Diligence"
    sp.font.size = Pt(24)
    sp.font.color.rgb = GOLD
    sp.alignment = PP_ALIGN.CENTER

    # Divider line
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(4.5), Inches(4.1), Inches(4.5), Inches(0.02))
    line.fill.solid()
    line.fill.fore_color.rgb = GOLD
    line.line.fill.background()

    # Confidential notice
    nb = slide.shapes.add_textbox(Inches(2), Inches(4.5), Inches(9.5), Inches(0.4))
    nf = nb.text_frame
    np_ = nf.paragraphs[0]
    np_.text = "CONFIDENTIAL \u2014 For Investment Committee Use Only"
    np_.font.size = Pt(12)
    np_.font.color.rgb = MID_GRAY
    np_.alignment = PP_ALIGN.CENTER

    # Key stat if available
    ks = data.get("key_stat", "")
    if ks:
        kb = slide.shapes.add_textbox(Inches(2), Inches(5.2), Inches(9.5), Inches(0.35))
        kf = kb.text_frame
        kp = kf.paragraphs[0]
        kp.text = ks
        kp.font.size = Pt(14)
        kp.font.color.rgb = LIGHT_GRAY
        kp.alignment = PP_ALIGN.CENTER


def _render_content_slide(slide, company: str, data: dict, slide_num: int, total: int):
    _add_chrome(slide, company, data.get("title", ""), data.get("subtitle", ""), slide_num, total)

    bullets = data.get("bullets", [])
    y = CONTENT_TOP
    for bullet in bullets[:6]:
        bb = slide.shapes.add_textbox(CONTENT_LEFT, y, CONTENT_W, Inches(0.4))
        bf = bb.text_frame
        bf.word_wrap = True
        bp = bf.paragraphs[0]
        bp.text = f"\u25B8  {bullet}"
        bp.font.size = Pt(16)
        bp.font.color.rgb = WHITE
        y += Inches(0.45)

    # Key stat callout box
    ks = data.get("key_stat", "")
    if ks:
        box_y = max(y + Inches(0.2), Inches(5.0))
        box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            CONTENT_LEFT, box_y, Inches(11.5), Inches(0.55)
        )
        box.fill.solid()
        box.fill.fore_color.rgb = DARK_CARD
        box.line.color.rgb = GOLD
        box.line.width = Pt(1.2)

        kt = box.text_frame
        kp = kt.paragraphs[0]
        kp.text = f"  \u2B50  {ks}"
        kp.font.size = Pt(13)
        kp.font.bold = True
        kp.font.color.rgb = GOLD
        kp.alignment = PP_ALIGN.LEFT

    # Source IDs
    sids = data.get("source_ids", [])
    if sids:
        stb = slide.shapes.add_textbox(
            CONTENT_LEFT, SLIDE_H - FOOTER_H - Inches(0.35), Inches(10), Inches(0.2)
        )
        sf = stb.text_frame
        sp = sf.paragraphs[0]
        sp.text = "Sources: " + "  ".join(f"[{s}]" for s in sids)
        sp.font.size = Pt(9)
        sp.font.color.rgb = MID_GRAY


def _render_dashboard_slide(slide, company: str, data: dict, slide_num: int, total: int):
    _add_chrome(slide, company, data.get("title", "Dashboard"), data.get("subtitle", ""), slide_num, total)

    metrics = data.get("dashboard_metrics", [])[:6]
    if not metrics:
        _render_content_slide(slide, company, data, slide_num, total)
        return

    cols = 3 if len(metrics) > 4 else 2
    card_w = Inches(3.6)
    card_h = Inches(1.6)
    gap_x = Inches(0.3)
    gap_y = Inches(0.25)
    start_x = CONTENT_LEFT
    start_y = CONTENT_TOP + Inches(0.1)

    for i, metric in enumerate(metrics):
        col = i % cols
        row = i // cols
        x = start_x + (card_w + gap_x) * col
        y = start_y + (card_h + gap_y) * row

        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_w, card_h)
        card.fill.solid()
        card.fill.fore_color.rgb = DARK_CARD
        card.line.color.rgb = RGBColor(30, 50, 80)
        card.line.width = Pt(0.8)

        # Label
        lb = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.15), card_w - Inches(0.4), Inches(0.2))
        lf = lb.text_frame
        lp = lf.paragraphs[0]
        lp.text = str(metric.get("label", "Metric")).upper()
        lp.font.size = Pt(10)
        lp.font.color.rgb = GOLD
        lp.font.bold = True

        # Value
        vb = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.5), card_w - Inches(0.4), Inches(0.45))
        vf = vb.text_frame
        vp = vf.paragraphs[0]
        vp.text = str(metric.get("value", "N/A"))
        vp.font.size = Pt(26)
        vp.font.bold = True
        vp.font.color.rgb = WHITE

        # Trend
        trend = str(metric.get("trend", "flat"))
        arrow = "\u2191" if trend == "up" else ("\u2193" if trend == "down" else "\u2192")
        color = ACCENT_TEAL if trend == "up" else (ACCENT_RED if trend == "down" else MID_GRAY)

        tb = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(1.1), card_w - Inches(0.4), Inches(0.25))
        ttf = tb.text_frame
        tp = ttf.paragraphs[0]
        tp.text = f"{arrow}  {trend.upper()}"
        tp.font.size = Pt(11)
        tp.font.bold = True
        tp.font.color.rgb = color

    # Bullets below cards if any
    bullets = data.get("bullets", [])
    if bullets:
        by = start_y + (card_h + gap_y) * (((len(metrics) - 1) // cols) + 1) + Inches(0.15)
        for b in bullets[:3]:
            bb = slide.shapes.add_textbox(CONTENT_LEFT, by, CONTENT_W, Inches(0.3))
            bf = bb.text_frame
            bp = bf.paragraphs[0]
            bp.text = f"\u25B8  {b}"
            bp.font.size = Pt(13)
            bp.font.color.rgb = LIGHT_GRAY
            by += Inches(0.35)


def _render_exec_summary(slide, company: str, data: dict, slide_num: int, total: int):
    _add_chrome(slide, company, data.get("title", "Executive Summary"), data.get("subtitle", ""), slide_num, total)

    # Left callout box (35% width)
    ks = data.get("key_stat", "Key insight")
    box = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        CONTENT_LEFT, CONTENT_TOP, Inches(4.0), Inches(2.5)
    )
    box.fill.solid()
    box.fill.fore_color.rgb = DARK_CARD
    box.line.color.rgb = GOLD
    box.line.width = Pt(1.5)

    kt = box.text_frame
    kt.word_wrap = True
    kp = kt.paragraphs[0]
    kp.text = "\u2B50  KEY INSIGHT"
    kp.font.size = Pt(10)
    kp.font.color.rgb = GOLD
    kp.font.bold = True

    vp = kt.add_paragraph()
    vp.text = ks
    vp.font.size = Pt(18)
    vp.font.color.rgb = WHITE
    vp.font.bold = True

    # Right bullets (60% width)
    bullets = data.get("bullets", [])
    y = CONTENT_TOP
    for bullet in bullets[:6]:
        bb = slide.shapes.add_textbox(Inches(5.2), y, Inches(7.5), Inches(0.4))
        bf = bb.text_frame
        bf.word_wrap = True
        bp = bf.paragraphs[0]
        bp.text = f"\u25B8  {bullet}"
        bp.font.size = Pt(15)
        bp.font.color.rgb = WHITE
        y += Inches(0.45)


def _render_two_column(slide, company: str, data: dict, slide_num: int, total: int):
    _add_chrome(slide, company, data.get("title", ""), data.get("subtitle", ""), slide_num, total)

    bullets = data.get("bullets", [])
    mid = (len(bullets) + 1) // 2
    left_bullets = bullets[:mid]
    right_bullets = bullets[mid:]

    # Left column
    y = CONTENT_TOP
    for b in left_bullets:
        bb = slide.shapes.add_textbox(CONTENT_LEFT, y, Inches(5.8), Inches(0.4))
        bf = bb.text_frame
        bf.word_wrap = True
        bp = bf.paragraphs[0]
        bp.text = f"\u25B8  {b}"
        bp.font.size = Pt(15)
        bp.font.color.rgb = WHITE
        y += Inches(0.45)

    # Right column
    y = CONTENT_TOP
    for b in right_bullets:
        bb = slide.shapes.add_textbox(Inches(7.0), y, Inches(5.8), Inches(0.4))
        bf = bb.text_frame
        bf.word_wrap = True
        bp = bf.paragraphs[0]
        bp.text = f"\u25B8  {b}"
        bp.font.size = Pt(15)
        bp.font.color.rgb = WHITE
        y += Inches(0.45)

    # Key stat
    ks = data.get("key_stat", "")
    if ks:
        box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            CONTENT_LEFT, Inches(5.2), Inches(11.5), Inches(0.55)
        )
        box.fill.solid()
        box.fill.fore_color.rgb = DARK_CARD
        box.line.color.rgb = GOLD
        box.line.width = Pt(1)
        kt = box.text_frame
        kp = kt.paragraphs[0]
        kp.text = f"  \u2B50  {ks}"
        kp.font.size = Pt(13)
        kp.font.bold = True
        kp.font.color.rgb = GOLD


def _render_sources_slide(slide, company: str, data: dict, slide_num: int, total: int):
    _add_chrome(slide, company, "Sources Appendix", "Traceable evidence index", slide_num, total)

    bullets = data.get("bullets", [])
    y = CONTENT_TOP
    for b in bullets[:8]:
        bb = slide.shapes.add_textbox(CONTENT_LEFT, y, CONTENT_W, Inches(0.35))
        bf = bb.text_frame
        bp = bf.paragraphs[0]
        bp.text = f"\u25B8  {b}"
        bp.font.size = Pt(14)
        bp.font.color.rgb = LIGHT_GRAY
        y += Inches(0.4)

    # Audit note
    nb = slide.shapes.add_textbox(CONTENT_LEFT, Inches(5.5), CONTENT_W, Inches(0.3))
    nf = nb.text_frame
    np_ = nf.paragraphs[0]
    np_.text = "Cross-reference all source IDs with the source panel for audit-ready citation trails."
    np_.font.size = Pt(12)
    np_.font.italic = True
    np_.font.color.rgb = MID_GRAY


# ═══════════════════════════════════════════════════════════════
# Slide dispatcher
# ═══════════════════════════════════════════════════════════════

_RENDERERS = {
    "title": _render_title_slide,
    "exec_summary": _render_exec_summary,
    "dashboard": _render_dashboard_slide,
    "two_column": _render_two_column,
    "sources": _render_sources_slide,
    "content": _render_content_slide,
}


# ═══════════════════════════════════════════════════════════════
# Mock slides
# ═══════════════════════════════════════════════════════════════

def _mock_slides(company: str, research: dict[str, Any]) -> dict[str, Any]:
    sources = research.get("all_sources", [])
    sids = [s["id"] for s in sources[:6]] or [1, 2, 3, 4, 5, 6]
    dm = research.get("dashboard_metrics", {}).get("metrics", [])

    profile = research.get("company_profile", {})
    product = research.get("product_and_technology", {})
    bm = research.get("business_model", {})
    fin = research.get("financial_signals", {})
    ue = research.get("unit_economics", {})
    ml = research.get("market_landscape", {})
    cp = research.get("competitive_positioning", {})
    ce = research.get("customer_evidence", {})
    risk = research.get("risk_assessment", {})
    cat = research.get("catalysts_and_outlook", {})
    iv = research.get("investment_view", {})
    mgmt = research.get("management_team", {})
    comps = research.get("comparable_transactions", {})
    exit_d = research.get("exit_analysis", {})

    def _get(d, k, default=""):
        return d.get(k, default) if isinstance(d, dict) else default

    def _get_list(d, k):
        return d.get(k, []) if isinstance(d, dict) else []

    # Build risk bullets
    risk_bullets = [_get(risk, "summary")]
    for r in _get_list(risk, "key_risks")[:3]:
        if isinstance(r, dict):
            risk_bullets.append(f"{r.get('risk', '')} (Severity: {r.get('severity', 'N/A')}, Prob: {r.get('probability', 'N/A')})")
        else:
            risk_bullets.append(str(r))

    cat_bullets = [_get(cat, "summary")]
    for c in _get_list(cat, "catalysts")[:3]:
        if isinstance(c, dict):
            cat_bullets.append(f"{c.get('catalyst', '')} — {c.get('timeline', '')}, Impact: {c.get('impact', '')}")
        else:
            cat_bullets.append(str(c))

    return {"slides": [
        {"slide_number": 1, "slide_type": "title", "title": company, "subtitle": "PE Due Diligence", "bullets": [], "key_stat": f"Est. ARR: {_get(fin, 'arr_trajectory', 'N/A')}", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 2, "slide_type": "exec_summary", "title": "Executive Summary", "subtitle": "Investment thesis overview", "bullets": [_get(profile, "summary"), _get(iv, "base_case"), _get(iv, "recommendation", "Proceed to detailed diligence")], "key_stat": _get(iv, "summary", "Compelling risk-adjusted return profile"), "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 3, "slide_type": "content", "title": "Company Profile", "subtitle": f"Founded {_get(profile, 'founded')} | HQ: {_get(profile, 'headquarters')}", "bullets": [_get(profile, "summary"), f"Employees: {_get(profile, 'employee_estimate')}", *_get_list(profile, "key_facts")[:3]], "key_stat": f"Employees: {_get(profile, 'employee_estimate')}", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 4, "slide_type": "content", "title": "Management Team", "subtitle": "Leadership quality and depth", "bullets": [_get(mgmt, "summary"), *[f"{e.get('name','')}: {e.get('background','')}" for e in _get_list(mgmt, 'executives')[:3]], f"Key-man risk: {_get(mgmt, 'key_man_risk')}"], "key_stat": "Repeat founder with prior exit", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 5, "slide_type": "content", "title": "Product & Technology", "subtitle": "Moat and differentiation analysis", "bullets": [_get(product, "summary"), *_get_list(product, "core_offerings")[:3], _get(product, "moat_hypothesis")], "key_stat": _get(product, "moat_hypothesis", "")[:80], "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 6, "slide_type": "content", "title": "Business Model", "subtitle": "Revenue mechanics and pricing", "bullets": [_get(bm, "summary"), f"Pricing: {_get(bm, 'pricing_motion')}", *_get_list(bm, "customer_segments")[:3]], "key_stat": "Land-and-expand with 130%+ NRR", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 7, "slide_type": "dashboard", "title": "Unit Economics & KPIs", "subtitle": "Key performance indicators", "bullets": [_get(ue, "summary")], "key_stat": "", "source_ids": sids, "dashboard_metrics": dm[:6]},
        {"slide_number": 8, "slide_type": "dashboard", "title": "Financial Dashboard", "subtitle": "Traction signals and trajectory", "bullets": [_get(fin, "summary")], "key_stat": _get(fin, "arr_trajectory"), "source_ids": sids, "dashboard_metrics": dm[:6]},
        {"slide_number": 9, "slide_type": "content", "title": "Market Landscape", "subtitle": f"TAM: {_get(ml, 'market_size_estimate', 'N/A')[:50]}", "bullets": [_get(ml, "summary"), f"Competitors: {', '.join(_get_list(ml, 'competitors')[:5])}", *_get_list(ml, "industry_trends")[:3]], "key_stat": _get(ml, "market_size_estimate"), "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 10, "slide_type": "two_column", "title": "Competitive Positioning", "subtitle": "Win/loss dynamics and differentiation", "bullets": [_get(cp, "summary"), *_get_list(cp, "key_differentiators")[:3], *[f"vs {p.get('competitor','')}: {p.get('relative_position','')}" for p in _get_list(cp, "positioning_matrix")[:3]]], "key_stat": "Differentiated on hybrid deployment + vendor neutrality", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 11, "slide_type": "content", "title": "Customer Evidence", "subtitle": "Logo quality and retention signals", "bullets": [_get(ce, "summary"), f"Concentration: {_get(ce, 'concentration_risk')}", f"NPS proxy: {_get(ce, 'nps_proxy')}", *_get_list(ce, "case_studies")[:2]], "key_stat": f"Logo retention: {_get(ce, 'churn_signals')[:60]}", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 12, "slide_type": "dashboard", "title": "Risk & Competitive Heatmap", "subtitle": "Downside scenario analysis", "bullets": risk_bullets[:2], "key_stat": _get(risk, "overall_risk_rating"), "source_ids": sids, "dashboard_metrics": dm[:6]},
        {"slide_number": 13, "slide_type": "content", "title": "Catalysts & Outlook", "subtitle": "Value-creation levers", "bullets": cat_bullets, "key_stat": "Multiple catalysts within 12-24 month horizon", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 14, "slide_type": "content", "title": "Exit Analysis", "subtitle": "Strategic acquirers and IPO readiness", "bullets": [_get(exit_d, "summary"), *[f"{a.get('acquirer','')}: {a.get('rationale','')}" for a in _get_list(exit_d, "strategic_acquirers")[:3]], f"Bear: {_get(_get(exit_d, 'exit_multiples', {}), 'bear_case')}", f"Base: {_get(_get(exit_d, 'exit_multiples', {}), 'base_case')}", f"Bull: {_get(_get(exit_d, 'exit_multiples', {}), 'bull_case')}"], "key_stat": f"Base IRR: {_get(_get(exit_d, 'implied_irr', {}), 'base_case')}", "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 15, "slide_type": "exec_summary", "title": "Investment Recommendation", "subtitle": "IC decision framework", "bullets": [_get(iv, "base_case"), _get(iv, "upside_case"), _get(iv, "downside_case")], "key_stat": _get(iv, "recommendation", "PROCEED TO DETAILED DILIGENCE"), "source_ids": sids, "dashboard_metrics": []},
        {"slide_number": 16, "slide_type": "sources", "title": "Sources Appendix", "subtitle": "Traceable evidence index", "bullets": ["All evidence points linked in the source panel.", "Cross-reference source IDs with each slide claim before IC review.", "Highlight unresolved data gaps as diligence follow-ups."], "key_stat": f"{len(_get_list(research, 'all_sources'))} cited sources", "source_ids": sids, "dashboard_metrics": []},
    ]}


# ═══════════════════════════════════════════════════════════════
# Gemini slide generation
# ═══════════════════════════════════════════════════════════════

def _slides_from_gemini(company: str, research: dict[str, Any]) -> dict[str, Any]:
    if settings.mock_mode or not settings.gemini_api_key:
        return _mock_slides(company, research)

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""You are an elite private-equity presentation strategist at McKinsey.
Create strict JSON for a high-stakes IC due diligence deck.

Company: {company}
Research: {json.dumps(research)}

Return schema:
{{
  "slides": [
    {{
      "slide_number": 1,
      "slide_type": "title|exec_summary|content|dashboard|two_column|sources",
      "title": "...",
      "subtitle": "...",
      "bullets": ["quant-heavy bullet", "...", "..."],
      "key_stat": "most important insight",
      "source_ids": [1,2,3],
      "dashboard_metrics": [{{"label": "...", "value": "...", "trend": "up|down|flat"}}]
    }}
  ]
}}

RULES:
- 14 to 20 slides.
- slide_type assignments: slide 1 = "title", slide 2 = "exec_summary", last = "sources",
  any slide with 4+ KPI metrics = "dashboard" (need 3+ dashboard slides),
  competitive analysis = "two_column", investment recommendation = "exec_summary", rest = "content".
- Every bullet must be quantitative and investor-grade.
- Every slide needs 3+ bullets and 2+ source_ids.
- dashboard_metrics only on dashboard slides (4-6 metrics each).
- Ensure flow: title -> exec summary -> profile -> mgmt -> product -> business model ->
  unit economics -> financials -> market -> competition -> customers -> dashboards -> risks ->
  catalysts -> exit -> investment view -> sources.
"""
    feedback = ""
    best: dict[str, Any] | None = None
    best_score = -1

    for _ in range(max(1, settings.slide_max_attempts)):
        run_prompt = prompt + (f"\nFix: {feedback}\n" if feedback else "")
        response = client.models.generate_content(
            model=settings.gemini_slide_model,
            contents=run_prompt,
            config=types.GenerateContentConfig(
                temperature=0.15,
                response_mime_type="application/json",
            ),
        )
        raw = response.text or ""
        if not raw:
            feedback = "Empty response."
            continue
        try:
            cleaned = raw.strip().strip("```json").strip("```").strip()
            parsed = json.loads(cleaned)
        except Exception:
            feedback = "Invalid JSON."
            continue
        if "slides" not in parsed:
            feedback = "Missing slides array."
            continue
        parsed["slides"] = _normalize_slides(parsed["slides"])
        ok, issues, score = _evaluate_slide_quality(parsed["slides"])
        if score > best_score:
            best = parsed
            best_score = score
        if ok:
            return parsed
        feedback = " ; ".join(issues)

    return best or _mock_slides(company, research)


def _normalize_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not slides:
        return []
    out: list[dict[str, Any]] = []
    for idx, s in enumerate(slides, 1):
        out.append({
            "slide_number": idx,
            "slide_type": s.get("slide_type", "content"),
            "title": s.get("title", f"Slide {idx}"),
            "subtitle": s.get("subtitle", ""),
            "bullets": s.get("bullets", [])[:8],
            "key_stat": s.get("key_stat", ""),
            "source_ids": s.get("source_ids", [])[:8],
            "dashboard_metrics": s.get("dashboard_metrics", [])[:6],
        })
    return out[:24]


def _evaluate_slide_quality(slides: list[dict[str, Any]]) -> tuple[bool, list[str], int]:
    issues: list[str] = []
    score = 100
    if len(slides) < 14:
        issues.append(f"Need 14+ slides, got {len(slides)}")
        score -= 20
    dash = sum(1 for s in slides if s.get("dashboard_metrics"))
    if dash < 3:
        issues.append(f"Need 3+ dashboard slides, got {dash}")
        score -= 15
    for i, s in enumerate(slides, 1):
        stype = s.get("slide_type", "content")
        # Title and sources slides are exempt from bullet/source requirements
        if stype in ("title", "sources"):
            continue
        if len(s.get("bullets", [])) < 2:
            issues.append(f"Slide {i}: need 2+ bullets")
            score -= 4
        if len(s.get("source_ids", [])) < 1:
            issues.append(f"Slide {i}: need source_ids")
            score -= 3
    return score >= 80 and not issues, issues, score


# ═══════════════════════════════════════════════════════════════
# PPTX builder
# ═══════════════════════════════════════════════════════════════

def _create_pptx(company: str, slides: list[dict[str, Any]]) -> bytes:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    total = len(slides)
    for data in slides:
        slide_layout = prs.slide_layouts[6]  # blank
        slide = prs.slides.add_slide(slide_layout)

        stype = data.get("slide_type", "content")
        renderer = _RENDERERS.get(stype, _render_content_slide)

        if stype == "title":
            renderer(slide, company, data, total)
        else:
            renderer(slide, company, data, data["slide_number"], total)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_presentation(company: str, research: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    payload = _slides_from_gemini(company, research)
    slides = _normalize_slides(payload["slides"])
    pptx = _create_pptx(company, slides)
    return {"slides": slides}, pptx
