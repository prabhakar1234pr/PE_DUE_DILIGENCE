import json
import re
from io import BytesIO
from typing import Any

from google import genai
from google.genai import types
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
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
ACCENT_AMBER = RGBColor(230, 170, 50)
DARK_CARD = RGBColor(20, 38, 65)
MID_GRAY = RGBColor(120, 130, 150)
DARK_CARD_ALT = RGBColor(15, 30, 52)
TABLE_HEADER = RGBColor(25, 50, 85)
TABLE_ROW_ODD = RGBColor(14, 28, 48)
TABLE_ROW_EVEN = RGBColor(18, 35, 60)

SEVERITY_COLORS = {
    "high": ACCENT_RED,
    "medium-high": RGBColor(230, 130, 50),
    "medium": ACCENT_AMBER,
    "medium-low": RGBColor(180, 190, 60),
    "low": ACCENT_TEAL,
}

CHART_SERIES_COLORS = [GOLD, ACCENT_TEAL, ACCENT_RED, ACCENT_AMBER, LIGHT_GRAY, RGBColor(140, 100, 200)]

# ── Slide dimensions (16:9 widescreen) ──────────────────────
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
HEADER_H = Inches(0.55)
ACCENT_W = Inches(0.1)
FOOTER_H = Inches(0.35)
CONTENT_LEFT = Inches(0.65)
CONTENT_TOP = Inches(1.15)
CONTENT_W = Inches(12.0)


# ═══════════════════════════════════════════════════════════════
# Visual toolkit — helpers the LLM can "call" via slide data
# ═══════════════════════════════════════════════════════════════

def _style_chart(chart, transparent_bg: bool = True):
    """Apply dark-theme styling to any chart."""
    chart.has_legend = False
    if transparent_bg:
        chart.chart_style = 2
        plot = chart.plots[0]
        plot.has_data_labels = True
        for series in plot.series:
            series.data_labels.font.size = Pt(10)
            series.data_labels.font.color.rgb = WHITE
    # Axis styling
    if hasattr(chart, "category_axis"):
        ax = chart.category_axis
        ax.tick_labels.font.size = Pt(9)
        ax.tick_labels.font.color.rgb = LIGHT_GRAY
        ax.format.line.fill.background()
        ax.has_major_gridlines = False
    if hasattr(chart, "value_axis"):
        ax = chart.value_axis
        ax.tick_labels.font.size = Pt(9)
        ax.tick_labels.font.color.rgb = LIGHT_GRAY
        ax.format.line.fill.background()
        ax.has_major_gridlines = False
        ax.major_gridlines.format.line.fill.background() if ax.has_major_gridlines else None


def _add_bar_chart(slide, x, y, w, h, categories: list[str], values: list[float],
                   series_name: str = "Value", colors: list[RGBColor] | None = None):
    """Add a styled bar chart."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series(series_name, values)
    graphic = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, x, y, w, h, chart_data)
    chart = graphic.chart
    _style_chart(chart)
    # Color individual bars
    series = chart.series[0]
    if colors:
        for idx, point in enumerate(series.points):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = colors[idx % len(colors)]
    else:
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = GOLD
    return chart


def _add_column_chart(slide, x, y, w, h, categories: list[str],
                      series_data: list[tuple[str, list[float]]],
                      colors: list[RGBColor] | None = None):
    """Add a multi-series column chart."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, vals in series_data:
        chart_data.add_series(name, vals)
    graphic = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, w, h, chart_data)
    chart = graphic.chart
    _style_chart(chart)
    clrs = colors or CHART_SERIES_COLORS
    for i, series in enumerate(chart.series):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = clrs[i % len(clrs)]
    if len(chart.series) > 1:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.font.size = Pt(9)
        chart.legend.font.color.rgb = LIGHT_GRAY
        chart.legend.include_in_layout = False
    return chart


def _add_pie_chart(slide, x, y, w, h, categories: list[str], values: list[float],
                   colors: list[RGBColor] | None = None):
    """Add a styled pie chart."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Share", values)
    graphic = slide.shapes.add_chart(XL_CHART_TYPE.PIE, x, y, w, h, chart_data)
    chart = graphic.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.font.size = Pt(9)
    chart.legend.font.color.rgb = LIGHT_GRAY
    chart.legend.include_in_layout = False
    plot = chart.plots[0]
    plot.has_data_labels = True
    data_labels = plot.data_labels
    data_labels.font.size = Pt(10)
    data_labels.font.color.rgb = WHITE
    data_labels.font.bold = True
    # Color slices
    clrs = colors or CHART_SERIES_COLORS
    for idx, point in enumerate(chart.series[0].points):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = clrs[idx % len(clrs)]
    return chart


def _add_doughnut_chart(slide, x, y, w, h, categories: list[str], values: list[float],
                        colors: list[RGBColor] | None = None):
    """Add a styled doughnut chart."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Share", values)
    graphic = slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, x, y, w, h, chart_data)
    chart = graphic.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.font.size = Pt(9)
    chart.legend.font.color.rgb = LIGHT_GRAY
    chart.legend.include_in_layout = False
    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(11)
    plot.data_labels.font.color.rgb = WHITE
    plot.data_labels.font.bold = True
    clrs = colors or CHART_SERIES_COLORS
    for idx, point in enumerate(chart.series[0].points):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = clrs[idx % len(clrs)]
    return chart


def _add_styled_table(slide, x, y, w, headers: list[str], rows: list[list[str]]):
    """Add a professionally styled table."""
    n_rows = len(rows) + 1  # +1 for header
    n_cols = len(headers)
    row_h = Inches(0.4)
    total_h = row_h * n_rows
    tbl_shape = slide.shapes.add_table(n_rows, n_cols, x, y, w, total_h)
    table = tbl_shape.table

    col_w = int(w / n_cols) if n_cols else w
    for i in range(n_cols):
        table.columns[i].width = col_w

    # Header row
    for j, hdr in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = hdr
        cell.fill.solid()
        cell.fill.fore_color.rgb = TABLE_HEADER
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = GOLD
        p.alignment = PP_ALIGN.LEFT
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Data rows
    for i, row in enumerate(rows):
        bg = TABLE_ROW_ODD if i % 2 == 0 else TABLE_ROW_EVEN
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = str(val) if val else ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(10)
            p.font.color.rgb = WHITE
            p.alignment = PP_ALIGN.LEFT
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    table.first_row = True
    return table


def _add_progress_bar(slide, x, y, w, h, pct: float, label: str = "",
                      fill_color: RGBColor = ACCENT_TEAL):
    """Add a progress bar: background rect + filled portion + label."""
    pct = max(0, min(100, pct))
    # Background
    bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(30, 45, 70)
    bg.line.fill.background()
    # Fill
    fill_w = int(w * (pct / 100))
    if fill_w > 0:
        bar = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, fill_w, h)
        bar.fill.solid()
        bar.fill.fore_color.rgb = fill_color
        bar.line.fill.background()
    # Label
    if label:
        lb = slide.shapes.add_textbox(x, y, w, h)
        lf = lb.text_frame
        lp = lf.paragraphs[0]
        lp.text = f"  {label}: {pct:.0f}%"
        lp.font.size = Pt(9)
        lp.font.bold = True
        lp.font.color.rgb = WHITE
        lp.alignment = PP_ALIGN.LEFT


def _add_risk_block(slide, x, y, w, h, risk_text: str, severity: str):
    """Add a color-coded risk indicator block."""
    color = SEVERITY_COLORS.get(severity.lower(), MID_GRAY)
    block = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    block.fill.solid()
    block.fill.fore_color.rgb = color
    block.line.fill.background()
    tf = block.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = risk_text
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER
    # Severity label
    p2 = tf.add_paragraph()
    p2.text = severity.upper()
    p2.font.size = Pt(8)
    p2.font.color.rgb = WHITE
    p2.alignment = PP_ALIGN.CENTER


# ═══════════════════════════════════════════════════════════════
# Shared slide chrome
# ═══════════════════════════════════════════════════════════════

def _add_background(slide):
    bg = slide.background
    bg.fill.gradient()
    bg.fill.gradient_angle = 135
    stops = bg.fill.gradient_stops
    stops[0].color.rgb = DARK_NAVY
    stops[0].position = 0.0
    stops[1].color.rgb = NAVY_LIGHT
    stops[1].position = 1.0


def _add_header_bar(slide, title: str, subtitle: str):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, HEADER_H)
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY_LIGHT
    bar.line.fill.background()
    tb = slide.shapes.add_textbox(Inches(0.65), Inches(0.06), Inches(9.5), Inches(0.3))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = WHITE
    if subtitle:
        sb = slide.shapes.add_textbox(Inches(0.65), Inches(0.34), Inches(9.5), Inches(0.2))
        sp = sb.text_frame.paragraphs[0]
        sp.text = subtitle
        sp.font.size = Pt(12)
        sp.font.color.rgb = GOLD
        sp.font.italic = True


def _add_accent_bar(slide):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, HEADER_H, ACCENT_W, SLIDE_H - HEADER_H)
    bar.fill.solid()
    bar.fill.fore_color.rgb = GOLD
    bar.line.fill.background()


def _add_footer(slide, company: str, slide_num: int, total: int):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, SLIDE_H - FOOTER_H, SLIDE_W, FOOTER_H)
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY_LIGHT
    bar.line.fill.background()
    for text, x, align in [
        (company, Inches(0.65), PP_ALIGN.LEFT),
        (f"{slide_num} / {total}", Inches(5.5), PP_ALIGN.CENTER),
        ("CONFIDENTIAL", Inches(10.0), PP_ALIGN.RIGHT),
    ]:
        tb = slide.shapes.add_textbox(x, SLIDE_H - FOOTER_H + Inches(0.06), Inches(3.0), Inches(0.22))
        p = tb.text_frame.paragraphs[0]
        p.text = text
        p.font.size = Pt(9 if text != "CONFIDENTIAL" else 8)
        p.font.color.rgb = GOLD if text == "CONFIDENTIAL" else MID_GRAY
        p.font.bold = text == "CONFIDENTIAL"
        p.alignment = align


def _add_chrome(slide, company, title, subtitle, slide_num, total):
    _add_background(slide)
    _add_header_bar(slide, title, subtitle)
    _add_accent_bar(slide)
    _add_footer(slide, company, slide_num, total)


def _add_bullets(slide, bullets: list[str], x=None, y=None, w=None, font_size=16, max_items=6):
    """Add bullet list to slide. Returns final y position."""
    x = x or CONTENT_LEFT
    y = y or CONTENT_TOP
    w = w or CONTENT_W
    for bullet in bullets[:max_items]:
        bb = slide.shapes.add_textbox(x, y, w, Inches(0.4))
        bb.text_frame.word_wrap = True
        bp = bb.text_frame.paragraphs[0]
        bp.text = f"\u25B8  {bullet}"
        bp.font.size = Pt(font_size)
        bp.font.color.rgb = WHITE
        y += Inches(0.42)
    return y


def _add_key_stat_box(slide, text: str, x=None, y=None, w=None):
    if not text:
        return
    x = x or CONTENT_LEFT
    y = y or Inches(5.3)
    w = w or Inches(11.5)
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, Inches(0.5))
    box.fill.solid()
    box.fill.fore_color.rgb = DARK_CARD
    box.line.color.rgb = GOLD
    box.line.width = Pt(1.2)
    p = box.text_frame.paragraphs[0]
    p.text = f"  \u2B50  {text}"
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = GOLD


def _add_source_line(slide, source_ids: list):
    if not source_ids:
        return
    tb = slide.shapes.add_textbox(CONTENT_LEFT, SLIDE_H - FOOTER_H - Inches(0.35), Inches(10), Inches(0.2))
    p = tb.text_frame.paragraphs[0]
    p.text = "Sources: " + "  ".join(f"[{s}]" for s in source_ids)
    p.font.size = Pt(9)
    p.font.color.rgb = MID_GRAY


# ═══════════════════════════════════════════════════════════════
# Slide type renderers — now visual-toolkit-aware
# ═══════════════════════════════════════════════════════════════

def _render_title_slide(slide, company, data, total):
    _add_background(slide)
    _add_accent_bar(slide)
    _add_footer(slide, company, 1, total)
    # Decorative top shape
    deco = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, Inches(0.08))
    deco.fill.solid()
    deco.fill.fore_color.rgb = GOLD
    deco.line.fill.background()
    # Company name
    tb = slide.shapes.add_textbox(Inches(1.5), Inches(2.0), Inches(10.5), Inches(1.2))
    p = tb.text_frame.paragraphs[0]
    p.text = company
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER
    # Subtitle
    sb = slide.shapes.add_textbox(Inches(1.5), Inches(3.3), Inches(10.5), Inches(0.5))
    sp = sb.text_frame.paragraphs[0]
    sp.text = "Private Equity Due Diligence"
    sp.font.size = Pt(24)
    sp.font.color.rgb = GOLD
    sp.alignment = PP_ALIGN.CENTER
    # Divider
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(4.5), Inches(4.1), Inches(4.5), Inches(0.02))
    line.fill.solid()
    line.fill.fore_color.rgb = GOLD
    line.line.fill.background()
    # Confidential
    nb = slide.shapes.add_textbox(Inches(2), Inches(4.5), Inches(9.5), Inches(0.4))
    np_ = nb.text_frame.paragraphs[0]
    np_.text = "CONFIDENTIAL \u2014 For Investment Committee Use Only"
    np_.font.size = Pt(12)
    np_.font.color.rgb = MID_GRAY
    np_.alignment = PP_ALIGN.CENTER
    # Key stat
    ks = data.get("key_stat", "")
    if ks:
        kb = slide.shapes.add_textbox(Inches(2), Inches(5.2), Inches(9.5), Inches(0.35))
        kp = kb.text_frame.paragraphs[0]
        kp.text = ks
        kp.font.size = Pt(14)
        kp.font.color.rgb = LIGHT_GRAY
        kp.alignment = PP_ALIGN.CENTER


def _render_content_slide(slide, company, data, slide_num, total):
    _add_chrome(slide, company, data.get("title", ""), data.get("subtitle", ""), slide_num, total)
    bullets = data.get("bullets", [])
    chart_spec = data.get("chart")
    table_spec = data.get("table_data")
    risk_blocks = data.get("risk_blocks")
    progress_bars_spec = data.get("progress_bars")

    if chart_spec and (table_spec or risk_blocks):
        # Chart + table/risk: split layout
        _add_bullets(slide, bullets[:3], w=Inches(5.5), max_items=3)
        _render_chart_from_spec(slide, chart_spec, Inches(6.5), CONTENT_TOP, Inches(5.8), Inches(3.5))
        if table_spec:
            _render_table_from_spec(slide, table_spec, CONTENT_LEFT, Inches(3.8), Inches(5.5))
    elif chart_spec:
        # Left bullets + right chart
        bw = Inches(5.5)
        _add_bullets(slide, bullets, w=bw, max_items=5)
        _render_chart_from_spec(slide, chart_spec, Inches(6.5), CONTENT_TOP, Inches(6.0), Inches(4.0))
    elif table_spec:
        # Bullets above + table below
        final_y = _add_bullets(slide, bullets[:2], max_items=2)
        _render_table_from_spec(slide, table_spec, CONTENT_LEFT, final_y + Inches(0.1), CONTENT_W)
    elif risk_blocks:
        # Bullets + risk severity blocks
        _add_bullets(slide, bullets[:2], max_items=2)
        _render_risk_blocks(slide, risk_blocks)
    elif progress_bars_spec:
        _add_bullets(slide, bullets[:3], max_items=3)
        _render_progress_bars(slide, progress_bars_spec)
    else:
        # Plain bullets
        _add_bullets(slide, bullets)

    _add_key_stat_box(slide, data.get("key_stat", ""))
    _add_source_line(slide, data.get("source_ids", []))


def _render_dashboard_slide(slide, company, data, slide_num, total):
    _add_chrome(slide, company, data.get("title", "Dashboard"), data.get("subtitle", ""), slide_num, total)
    metrics = data.get("dashboard_metrics", [])[:6]
    chart_spec = data.get("chart")

    if not metrics and not chart_spec:
        _render_content_slide(slide, company, data, slide_num, total)
        return

    # KPI cards in top row
    cols = 3 if len(metrics) > 4 else (2 if len(metrics) > 0 else 0)
    if cols:
        card_w = Inches(3.6)
        card_h = Inches(1.3)
        gap_x = Inches(0.3)
        gap_y = Inches(0.2)
        for i, m in enumerate(metrics):
            col = i % cols
            row = i // cols
            x = CONTENT_LEFT + (card_w + gap_x) * col
            y = CONTENT_TOP + (card_h + gap_y) * row
            card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_w, card_h)
            card.fill.solid()
            card.fill.fore_color.rgb = DARK_CARD
            card.line.color.rgb = RGBColor(30, 50, 80)
            card.line.width = Pt(0.8)
            # Label
            lb = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.12), card_w - Inches(0.4), Inches(0.18))
            lp = lb.text_frame.paragraphs[0]
            lp.text = str(m.get("label", "")).upper()
            lp.font.size = Pt(9)
            lp.font.color.rgb = GOLD
            lp.font.bold = True
            # Value
            vb = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.4), card_w - Inches(0.4), Inches(0.4))
            vp = vb.text_frame.paragraphs[0]
            vp.text = str(m.get("value", "N/A"))
            vp.font.size = Pt(24)
            vp.font.bold = True
            vp.font.color.rgb = WHITE
            # Trend
            trend = str(m.get("trend", "flat"))
            arrow = "\u2191" if trend == "up" else ("\u2193" if trend == "down" else "\u2192")
            color = ACCENT_TEAL if trend == "up" else (ACCENT_RED if trend == "down" else MID_GRAY)
            tb = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.95), card_w - Inches(0.4), Inches(0.2))
            tp = tb.text_frame.paragraphs[0]
            tp.text = f"{arrow}  {trend.upper()}"
            tp.font.size = Pt(10)
            tp.font.bold = True
            tp.font.color.rgb = color

    # Chart below the cards
    if chart_spec:
        chart_y = CONTENT_TOP + Inches(3.0) if cols else CONTENT_TOP
        _render_chart_from_spec(slide, chart_spec, CONTENT_LEFT, chart_y, Inches(11.5), Inches(3.2))
    elif len(metrics) >= 3:
        # Auto-generate a bar chart from the metrics
        cats = []
        vals = []
        for m in metrics:
            cats.append(str(m.get("label", ""))[:15])
            v = _extract_numeric(str(m.get("value", "0")))
            vals.append(v)
        if any(v > 0 for v in vals):
            chart_y = CONTENT_TOP + Inches(3.0) if cols else CONTENT_TOP
            _add_bar_chart(slide, CONTENT_LEFT, chart_y, Inches(11.5), Inches(3.0),
                           cats, vals, "Metrics")

    _add_source_line(slide, data.get("source_ids", []))


def _render_exec_summary(slide, company, data, slide_num, total):
    _add_chrome(slide, company, data.get("title", "Executive Summary"), data.get("subtitle", ""), slide_num, total)
    ks = data.get("key_stat", "Key insight")
    # Left callout
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, CONTENT_LEFT, CONTENT_TOP, Inches(4.0), Inches(2.5))
    box.fill.solid()
    box.fill.fore_color.rgb = DARK_CARD
    box.line.color.rgb = GOLD
    box.line.width = Pt(1.5)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "\u2B50  KEY INSIGHT"
    p.font.size = Pt(10)
    p.font.color.rgb = GOLD
    p.font.bold = True
    vp = tf.add_paragraph()
    vp.text = ks
    vp.font.size = Pt(16)
    vp.font.color.rgb = WHITE
    vp.font.bold = True
    # Right bullets
    _add_bullets(slide, data.get("bullets", []), x=Inches(5.2), w=Inches(7.5), font_size=14, max_items=6)
    # Chart if specified
    chart_spec = data.get("chart")
    if chart_spec:
        _render_chart_from_spec(slide, chart_spec, CONTENT_LEFT, Inches(4.0), Inches(11.5), Inches(2.5))
    _add_source_line(slide, data.get("source_ids", []))


def _render_two_column(slide, company, data, slide_num, total):
    _add_chrome(slide, company, data.get("title", ""), data.get("subtitle", ""), slide_num, total)
    table_spec = data.get("table_data")
    if table_spec:
        bullets = data.get("bullets", [])
        if bullets:
            _add_bullets(slide, bullets[:2], max_items=2, font_size=14)
        _render_table_from_spec(slide, table_spec, CONTENT_LEFT, Inches(2.2), CONTENT_W)
    else:
        bullets = data.get("bullets", [])
        mid = (len(bullets) + 1) // 2
        _add_bullets(slide, bullets[:mid], w=Inches(5.8), max_items=6)
        _add_bullets(slide, bullets[mid:], x=Inches(7.0), w=Inches(5.8), max_items=6)
    _add_key_stat_box(slide, data.get("key_stat", ""))
    _add_source_line(slide, data.get("source_ids", []))


def _render_sources_slide(slide, company, data, slide_num, total):
    _add_chrome(slide, company, "Sources Appendix", "Traceable evidence index", slide_num, total)
    _add_bullets(slide, data.get("bullets", []), max_items=8, font_size=14)
    nb = slide.shapes.add_textbox(CONTENT_LEFT, Inches(5.5), CONTENT_W, Inches(0.3))
    p = nb.text_frame.paragraphs[0]
    p.text = "Cross-reference all source IDs with the source panel for audit-ready citation trails."
    p.font.size = Pt(12)
    p.font.italic = True
    p.font.color.rgb = MID_GRAY


# ═══════════════════════════════════════════════════════════════
# Visual spec renderers — execute LLM-decided visuals
# ═══════════════════════════════════════════════════════════════

def _render_chart_from_spec(slide, spec: dict, x, y, w, h):
    """Render a chart from LLM-provided spec."""
    chart_type = spec.get("type", "bar")
    categories = spec.get("categories", [])
    values = spec.get("values", [])
    series = spec.get("series", [])

    if not categories:
        return

    try:
        if chart_type == "pie":
            _add_pie_chart(slide, x, y, w, h, categories, values or [1] * len(categories))
        elif chart_type == "doughnut":
            _add_doughnut_chart(slide, x, y, w, h, categories, values or [1] * len(categories))
        elif chart_type == "column" and series:
            _add_column_chart(slide, x, y, w, h, categories, [(s.get("name", ""), s.get("values", [])) for s in series])
        elif chart_type == "column":
            _add_column_chart(slide, x, y, w, h, categories, [("Value", values)])
        else:  # bar (default)
            _add_bar_chart(slide, x, y, w, h, categories, values or [1] * len(categories))
    except Exception:
        pass  # Gracefully skip chart on error


def _render_table_from_spec(slide, spec: dict, x, y, w):
    """Render a table from LLM-provided spec."""
    headers = spec.get("headers", [])
    rows = spec.get("rows", [])
    if headers and rows:
        try:
            _add_styled_table(slide, x, y, w, headers, rows[:8])
        except Exception:
            pass


def _render_risk_blocks(slide, blocks: list[dict]):
    """Render color-coded risk blocks."""
    y = Inches(2.8)
    block_w = Inches(3.7)
    block_h = Inches(1.0)
    gap = Inches(0.2)
    for i, block in enumerate(blocks[:6]):
        col = i % 3
        row = i // 3
        x = CONTENT_LEFT + (block_w + gap) * col
        by = y + (block_h + gap) * row
        _add_risk_block(slide, x, by, block_w, block_h,
                        block.get("risk", ""), block.get("severity", "medium"))


def _render_progress_bars(slide, bars: list[dict]):
    """Render progress bars from spec."""
    y = Inches(3.2)
    for bar in bars[:6]:
        pct = bar.get("value", 50)
        label = bar.get("label", "")
        color = ACCENT_TEAL if pct >= 70 else (ACCENT_AMBER if pct >= 40 else ACCENT_RED)
        _add_progress_bar(slide, CONTENT_LEFT, y, Inches(10), Inches(0.3), pct, label, color)
        y += Inches(0.5)


def _extract_numeric(s: str) -> float:
    """Extract a numeric value from a string like '$300M+', '42%', '4.5x'."""
    m = re.search(r"[\d.]+", s.replace(",", ""))
    return float(m.group()) if m else 0


# ═══════════════════════════════════════════════════════════════
# Renderer dispatch
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
# Mock slides — with visual specs for LLM to learn from
# ═══════════════════════════════════════════════════════════════

def _mock_slides(company: str, research: dict[str, Any]) -> dict[str, Any]:
    src = research.get("all_sources", [])
    sids = [s["id"] for s in src[:6]] or [1, 2, 3, 4, 5, 6]
    dm = research.get("dashboard_metrics", {}).get("metrics", [])

    def _g(d, k, default=""):
        return d.get(k, default) if isinstance(d, dict) else default

    def _gl(d, k):
        return d.get(k, []) if isinstance(d, dict) else []

    profile = research.get("company_profile", {})
    mgmt = research.get("management_team", {})
    product = research.get("product_and_technology", {})
    bm = research.get("business_model", {})
    ue = research.get("unit_economics", {})
    fin = research.get("financial_signals", {})
    ml = research.get("market_landscape", {})
    cp = research.get("competitive_positioning", {})
    ce = research.get("customer_evidence", {})
    risk = research.get("risk_assessment", {})
    cat = research.get("catalysts_and_outlook", {})
    iv = research.get("investment_view", {})
    comps = research.get("comparable_transactions", {})
    exit_d = research.get("exit_analysis", {})

    # Build risk blocks
    risk_blocks = []
    for r in _gl(risk, "key_risks")[:4]:
        if isinstance(r, dict):
            risk_blocks.append({"risk": r.get("risk", "")[:60], "severity": r.get("severity", "medium")})

    # Build comp table
    comp_headers = ["Company", "Type", "Valuation", "Multiple"]
    comp_rows = []
    for t in _gl(comps, "private_transactions")[:3]:
        if isinstance(t, dict):
            comp_rows.append([t.get("target", ""), "Private", t.get("deal_value", ""), t.get("revenue_multiple", "")])
    for t in _gl(comps, "public_comps")[:3]:
        if isinstance(t, dict):
            comp_rows.append([t.get("company", ""), "Public", t.get("ev_revenue_multiple", ""), t.get("growth_rate", "")])

    # Build competitive table
    comp_pos_headers = ["Competitor", "Strengths", "Weaknesses", "Our Position"]
    comp_pos_rows = []
    for p in _gl(cp, "positioning_matrix")[:4]:
        if isinstance(p, dict):
            comp_pos_rows.append([p.get("competitor", ""), p.get("strengths", "")[:40], p.get("weaknesses", "")[:40], p.get("relative_position", "")[:40]])

    # Revenue composition for pie chart
    rev = _g(bm, "revenue_composition", {})
    pie_cats = []
    pie_vals = []
    if isinstance(rev, dict):
        for k, v in rev.items():
            label = k.replace("_pct", "").replace("_", " ").title()
            val = _extract_numeric(str(v))
            if val > 0:
                pie_cats.append(label)
                pie_vals.append(val)

    # Exit multiples for doughnut
    exit_mults = _g(exit_d, "exit_multiples", {})

    return {"slides": [
        {"slide_number": 1, "slide_type": "title", "title": company, "subtitle": "PE Due Diligence",
         "bullets": [], "key_stat": f"Est. ARR: {_g(fin, 'arr_trajectory', 'N/A')}", "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 2, "slide_type": "exec_summary", "title": "Executive Summary", "subtitle": "Investment thesis overview",
         "bullets": [_g(profile, "summary"), _g(iv, "base_case"), _g(iv, "recommendation", "Proceed to diligence")],
         "key_stat": _g(iv, "summary", "Compelling risk-adjusted return"),
         "source_ids": sids, "dashboard_metrics": [],
         "chart": {"type": "bar", "categories": ["ARR", "Growth", "NRR", "Margin", "LTV:CAC"],
                   "values": [300, 45, 130, 75, 5]}},

        {"slide_number": 3, "slide_type": "content", "title": "Company Profile", "subtitle": f"Founded {_g(profile, 'founded')} | HQ: {_g(profile, 'headquarters')}",
         "bullets": [_g(profile, "summary"), f"Employees: {_g(profile, 'employee_estimate')}", *_gl(profile, "key_facts")[:3]],
         "key_stat": f"Employees: {_g(profile, 'employee_estimate')}", "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 4, "slide_type": "content", "title": "Management Team", "subtitle": "Leadership quality and depth",
         "bullets": [_g(mgmt, "summary"), *[f"{e.get('name','')}: {e.get('background','')[:80]}" for e in _gl(mgmt, 'executives')[:3]],
                     f"Key-man risk: {_g(mgmt, 'key_man_risk')}"],
         "key_stat": "Repeat founder with prior $300M+ exit", "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 5, "slide_type": "content", "title": "Product & Technology", "subtitle": "Moat and differentiation",
         "bullets": [_g(product, "summary"), *_gl(product, "core_offerings")[:3], _g(product, "moat_hypothesis")[:120]],
         "key_stat": _g(product, "moat_hypothesis", "")[:80], "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 6, "slide_type": "content", "title": "Business Model", "subtitle": "Revenue mechanics and pricing",
         "bullets": [_g(bm, "summary"), f"Pricing: {_g(bm, 'pricing_motion')}", *_gl(bm, "customer_segments")[:2]],
         "key_stat": "Land-and-expand with 130%+ NRR", "source_ids": sids, "dashboard_metrics": [],
         "chart": {"type": "pie", "categories": pie_cats or ["Subscriptions", "Usage", "Services"],
                   "values": pie_vals or [65, 30, 5]} if pie_cats else None},

        {"slide_number": 7, "slide_type": "dashboard", "title": "Unit Economics & KPIs", "subtitle": "Key performance indicators",
         "bullets": [_g(ue, "summary")], "key_stat": "", "source_ids": sids,
         "dashboard_metrics": dm[:6],
         "chart": {"type": "bar", "categories": ["NRR %", "Gross Margin %", "Rule of 40", "Logo Ret %"],
                   "values": [130, 75, 60, 93]}},

        {"slide_number": 8, "slide_type": "dashboard", "title": "Financial Dashboard", "subtitle": "Traction and trajectory",
         "bullets": [_g(fin, "summary")], "key_stat": _g(fin, "arr_trajectory"), "source_ids": sids,
         "dashboard_metrics": dm[:6]},

        {"slide_number": 9, "slide_type": "content", "title": "Market Landscape", "subtitle": f"TAM: {_g(ml, 'market_size_estimate', '')[:50]}",
         "bullets": [_g(ml, "summary"), f"Competitors: {', '.join(_gl(ml, 'competitors')[:5])}", *_gl(ml, "industry_trends")[:3]],
         "key_stat": _g(ml, "market_size_estimate"), "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 10, "slide_type": "two_column", "title": "Competitive Positioning", "subtitle": "Win/loss and differentiation",
         "bullets": [_g(cp, "summary"), *_gl(cp, "key_differentiators")[:3]],
         "key_stat": "Differentiated on hybrid deployment + vendor neutrality", "source_ids": sids, "dashboard_metrics": [],
         "table_data": {"headers": comp_pos_headers, "rows": comp_pos_rows} if comp_pos_rows else None},

        {"slide_number": 11, "slide_type": "content", "title": "Comparable Transactions", "subtitle": "Valuation benchmarks",
         "bullets": [_g(comps, "summary"), f"Implied range: {_g(comps, 'implied_valuation_range')}"],
         "key_stat": _g(comps, "implied_valuation_range"), "source_ids": sids, "dashboard_metrics": [],
         "table_data": {"headers": comp_headers, "rows": comp_rows} if comp_rows else None},

        {"slide_number": 12, "slide_type": "content", "title": "Customer Evidence", "subtitle": "Logo quality and retention",
         "bullets": [_g(ce, "summary"), f"Concentration: {_g(ce, 'concentration_risk')}", f"NPS: {_g(ce, 'nps_proxy')}", *_gl(ce, "case_studies")[:2]],
         "key_stat": f"Logo retention: {_g(ce, 'churn_signals')[:60]}", "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 13, "slide_type": "dashboard", "title": "Risk Heatmap", "subtitle": "Downside scenario analysis",
         "bullets": [_g(risk, "summary")],
         "key_stat": _g(risk, "overall_risk_rating"), "source_ids": sids,
         "dashboard_metrics": dm[:6],
         "risk_blocks": risk_blocks},

        {"slide_number": 14, "slide_type": "content", "title": "Catalysts & Outlook", "subtitle": "Value-creation levers",
         "bullets": [_g(cat, "summary"), *[f"{c.get('catalyst','')}: {c.get('impact','')}" for c in _gl(cat, "catalysts")[:3] if isinstance(c, dict)]],
         "key_stat": "Multiple catalysts within 12-24 months", "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 15, "slide_type": "content", "title": "Exit Analysis", "subtitle": "Strategic acquirers and IPO readiness",
         "bullets": [_g(exit_d, "summary"), *[f"{a.get('acquirer','')}: {a.get('rationale','')[:60]}" for a in _gl(exit_d, "strategic_acquirers")[:3] if isinstance(a, dict)]],
         "key_stat": f"Base IRR: {_g(_g(exit_d, 'implied_irr', {}), 'base_case')}", "source_ids": sids, "dashboard_metrics": [],
         "chart": {"type": "doughnut", "categories": ["Bear Case", "Base Case", "Bull Case"], "values": [25, 50, 25]}},

        {"slide_number": 16, "slide_type": "exec_summary", "title": "Investment Recommendation", "subtitle": "IC decision framework",
         "bullets": [_g(iv, "base_case"), _g(iv, "upside_case"), _g(iv, "downside_case")],
         "key_stat": _g(iv, "recommendation", "PROCEED TO DETAILED DILIGENCE"), "source_ids": sids, "dashboard_metrics": []},

        {"slide_number": 17, "slide_type": "sources", "title": "Sources Appendix", "subtitle": "Traceable evidence index",
         "bullets": ["All evidence points linked in source panel.", "Cross-reference source IDs before IC review.", "Highlight data gaps as follow-ups."],
         "key_stat": f"{len(_gl(research, 'all_sources'))} cited sources", "source_ids": sids, "dashboard_metrics": []},
    ]}


# ═══════════════════════════════════════════════════════════════
# Gemini slide generation — now with visual toolkit
# ═══════════════════════════════════════════════════════════════

def _slides_from_gemini(company: str, research: dict[str, Any]) -> dict[str, Any]:
    if settings.mock_mode or not settings.gemini_api_key:
        return _mock_slides(company, research)

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""You are an elite PE presentation strategist at McKinsey.
Create strict JSON for a high-stakes IC due diligence deck.

Company: {company}
Research: {json.dumps(research)}

You have a VISUAL TOOLKIT. For each slide, you can specify:

1. **chart** (optional): Add a data visualization
   - {{"type": "bar", "categories": ["A","B","C"], "values": [10,20,30]}}
   - {{"type": "pie", "categories": ["Subs","Usage","Services"], "values": [65,30,5]}}
   - {{"type": "doughnut", "categories": ["Bear","Base","Bull"], "values": [25,50,25]}}
   - {{"type": "column", "categories": ["Q1","Q2"], "series": [{{"name": "Rev", "values": [10,20]}}]}}

2. **table_data** (optional): Add a styled table
   - {{"headers": ["Company","Multiple","Growth"], "rows": [["SNOW","12x","30%"],["DDOG","15x","25%"]]}}

3. **risk_blocks** (optional): Color-coded risk severity grid
   - [{{"risk": "Competition from MSFT", "severity": "High"}}, {{"risk": "Margin pressure", "severity": "Medium"}}]

4. **progress_bars** (optional): Metric progress bars
   - [{{"label": "NRR", "value": 85}}, {{"label": "Gross Margin", "value": 75}}]

Return schema:
{{
  "slides": [
    {{
      "slide_number": 1,
      "slide_type": "title|exec_summary|content|dashboard|two_column|sources",
      "title": "...",
      "subtitle": "...",
      "bullets": ["quant-heavy bullet"],
      "key_stat": "most important insight",
      "source_ids": [1,2,3],
      "dashboard_metrics": [{{"label": "...", "value": "...", "trend": "up|down|flat"}}],
      "chart": null,
      "table_data": null,
      "risk_blocks": null,
      "progress_bars": null
    }}
  ]
}}

RULES:
- 14-20 slides.
- Slide 1 = "title", slide 2 = "exec_summary", last = "sources".
- 3+ dashboard slides with dashboard_metrics AND charts.
- USE CHARTS: revenue composition = pie, exit scenarios = doughnut, KPIs = bar, financial trends = column.
- USE TABLES: competitive positioning and comparable transactions MUST use table_data.
- USE RISK BLOCKS: risk assessment slide MUST use risk_blocks.
- Every non-title/sources slide needs 3+ bullets and 2+ source_ids.
- Make it VISUALLY IMMERSIVE — every 2nd slide should have a chart, table, or visual element.
"""
    feedback = ""
    best: dict[str, Any] | None = None
    best_score = -1

    for _ in range(max(1, settings.slide_max_attempts)):
        run_prompt = prompt + (f"\nFix: {feedback}\n" if feedback else "")
        response = client.models.generate_content(
            model=settings.gemini_slide_model,
            contents=run_prompt,
            config=types.GenerateContentConfig(temperature=0.15, response_mime_type="application/json"),
        )
        raw = response.text or ""
        if not raw:
            feedback = "Empty response."
            continue
        try:
            parsed = json.loads(raw.strip().strip("```json").strip("```").strip())
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
            "slide_type": s.get("slide_type") or "content",
            "title": s.get("title") or f"Slide {idx}",
            "subtitle": s.get("subtitle") or "",
            "bullets": [b for b in (s.get("bullets") or []) if b][:8],
            "key_stat": s.get("key_stat") or "",
            "source_ids": [sid for sid in (s.get("source_ids") or []) if sid][:8],
            "dashboard_metrics": (s.get("dashboard_metrics") or [])[:6],
            "chart": s.get("chart"),
            "table_data": s.get("table_data"),
            "risk_blocks": s.get("risk_blocks"),
            "progress_bars": s.get("progress_bars"),
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
    # Count visual elements
    visuals = sum(1 for s in slides if s.get("chart") or s.get("table_data") or s.get("risk_blocks") or s.get("progress_bars"))
    if visuals < 3:
        issues.append(f"Need 3+ slides with visual elements (charts/tables/risk blocks), got {visuals}")
        score -= 10
    for i, s in enumerate(slides, 1):
        stype = s.get("slide_type", "content")
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
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        stype = data.get("slide_type", "content")
        renderer = _RENDERERS.get(stype, _render_content_slide)
        if stype == "title":
            renderer(slide, company, data, total)
        else:
            renderer(slide, company, data, data["slide_number"], total)
    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_presentation(company: str, research: dict[str, Any],
                       workspace: dict[str, Any] | None = None) -> tuple[dict[str, Any], bytes]:
    payload = _slides_from_gemini(company, research)
    slides = _normalize_slides(payload["slides"])

    # Enrich slides with workspace datasets (charts, tables, risks from Analyst agent)
    if workspace:
        slides = _enrich_slides_from_workspace(slides, workspace)

    pptx = _create_pptx(company, slides)
    return {"slides": slides}, pptx


def _enrich_slides_from_workspace(slides: list[dict[str, Any]],
                                  workspace: dict[str, Any]) -> list[dict[str, Any]]:
    """Inject analyst-structured data into slides that don't already have visuals."""
    charts = {c["chart_name"]: c for c in workspace.get("charts", [])}
    tables = {t["table_name"]: t for t in workspace.get("tables", [])}
    risks = workspace.get("risks", [])

    for slide in slides:
        title_lower = (slide.get("title") or "").lower()
        stype = slide.get("slide_type", "content")

        # Skip slides that already have visual specs from Gemini
        if slide.get("chart") or slide.get("table_data") or slide.get("risk_blocks"):
            continue

        # Match charts by slide title keywords
        if "executive summary" in title_lower and "headline_metrics" in charts:
            c = charts["headline_metrics"]
            slide["chart"] = {"type": c["chart_type"], "categories": c["categories"], "values": c["values"]}
        elif ("unit economics" in title_lower or "kpi" in title_lower) and "kpi_comparison" in charts:
            c = charts["kpi_comparison"]
            slide["chart"] = {"type": c["chart_type"], "categories": c["categories"], "values": c["values"]}
        elif "business model" in title_lower and "revenue_composition" in charts:
            c = charts["revenue_composition"]
            slide["chart"] = {"type": c["chart_type"], "categories": c["categories"], "values": c["values"]}
        elif "financial" in title_lower and "funding_timeline" in charts:
            c = charts["funding_timeline"]
            slide["chart"] = {"type": c["chart_type"], "categories": c["categories"], "values": c["values"]}
        elif "exit" in title_lower and "exit_scenarios" in charts:
            c = charts["exit_scenarios"]
            slide["chart"] = {"type": c["chart_type"], "categories": c["categories"], "values": c["values"]}

        # Match tables by slide title keywords
        if "competitive" in title_lower and "competitive_positioning" in tables:
            t = tables["competitive_positioning"]
            slide["table_data"] = {"headers": t["headers"], "rows": t["rows"]}
        elif "comparable" in title_lower and "comparable_transactions" in tables:
            t = tables["comparable_transactions"]
            slide["table_data"] = {"headers": t["headers"], "rows": t["rows"]}
        elif "management" in title_lower and "management_team" in tables:
            t = tables["management_team"]
            slide["table_data"] = {"headers": t["headers"], "rows": t["rows"]}
        elif "funding" in title_lower and "funding_rounds" in tables:
            t = tables["funding_rounds"]
            slide["table_data"] = {"headers": t["headers"], "rows": t["rows"]}

        # Match risk blocks
        if "risk" in title_lower and risks and not slide.get("risk_blocks"):
            slide["risk_blocks"] = [{"risk": r["risk"][:60], "severity": r["severity"]} for r in risks[:6]]

    return slides
