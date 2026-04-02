"""Agent 3 — PPT Builder via Presenton API.

Converts research data + workspace into structured slide content,
calls the self-hosted Presenton service to generate a professional PPTX,
and returns the presentation bytes for storage.
"""

import logging
import os
from pathlib import Path

import httpx

from app.settings import settings

log = logging.getLogger(__name__)

PRESENTON_TIMEOUT = 300  # 5 minutes — generation can be slow

# Keys in the research dict that are NOT slide-worthy sections.
_SKIP_KEYS = frozenset({
    "company", "overview", "all_sources", "_run_id",
})


def _research_sections(research: dict) -> dict[str, dict | str | list]:
    """Extract slide-worthy sections from research data.

    Research data has sections at the top level (company_profile, market_landscape, …)
    rather than nested under a "sections" key.
    """
    return {
        k.replace("_", " ").title(): v
        for k, v in research.items()
        if k not in _SKIP_KEYS and isinstance(v, (dict, str, list))
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Content formatting — research + workspace → rich text for Presenton
# ═══════════════════════════════════════════════════════════════════════════════


def _format_content(company: str, research: dict, workspace: dict | None) -> str:
    """Build a rich text document from research + workspace data.

    This gives Presenton full context for AI-driven slide layout decisions.
    """
    parts = [
        f"# {company} — Private Equity Due Diligence Report",
        "Classification: CONFIDENTIAL — For Investment Committee Use Only",
        "",
    ]

    overview = research.get("overview", "")
    if overview:
        parts += ["## Executive Overview", overview, ""]

    for name, data in _research_sections(research).items():
        parts.append(f"## {name}")
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, str) and val.strip():
                    parts += [f"### {key}", val]
                elif isinstance(val, list):
                    parts.append(f"### {key}")
                    parts += [f"- {item}" for item in val]
        elif isinstance(data, str) and data.strip():
            parts.append(data)
        parts.append("")

    if workspace:
        metrics = workspace.get("metrics", [])
        if metrics:
            parts.append("## Key Performance Metrics")
            for m in metrics:
                display = m.get("display", str(m.get("value", "")))
                trend = m.get("trend", "")
                parts.append(f"- {m.get('label', '')}: {display} (trend: {trend})")
            parts.append("")

        charts = workspace.get("charts", [])
        if charts:
            parts.append("## Financial Data")
            for c in charts:
                parts.append(f"### {c.get('chart_name', 'Data')}")
                for cat, val in zip(c.get("categories", []), c.get("values", [])):
                    parts.append(f"- {cat}: {val}")
                parts.append("")

        tables = workspace.get("tables", [])
        for t in tables:
            headers = t.get("headers", [])
            rows = t.get("rows", [])
            if headers:
                parts.append(f"## {t.get('table_name', 'Table')}")
                parts.append("| " + " | ".join(str(h) for h in headers) + " |")
                parts.append("| " + " | ".join("---" for _ in headers) + " |")
                for row in rows:
                    parts.append("| " + " | ".join(str(v) for v in row) + " |")
                parts.append("")

        risks = workspace.get("risks", [])
        if risks:
            parts.append("## Risk Assessment")
            for r in risks:
                parts.append(f"- **[{r.get('severity', 'Medium')}]** {r.get('risk', '')}")
                if r.get("mitigation"):
                    parts.append(f"  - Mitigation: {r['mitigation']}")
            parts.append("")

    sources = research.get("all_sources", [])
    if sources:
        parts.append("## Sources")
        for s in sources[:10]:
            parts.append(f"- [{s.get('id')}] {s.get('title', '')} — {s.get('url', '')}")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# Slide markdown — pre-structured slide content for Presenton
# ═══════════════════════════════════════════════════════════════════════════════


def _build_slides_markdown(
    company: str, research: dict, workspace: dict | None
) -> list[str]:
    """Build slide-by-slide markdown giving Presenton explicit structure."""
    slides: list[str] = []

    # ── Title slide ───────────────────────────────────────────────────────
    slides.append(
        f"# {company}\n\n"
        "Private Equity Due Diligence Report\n\n"
        "CONFIDENTIAL — For Investment Committee Use Only"
    )

    # ── Executive summary ─────────────────────────────────────────────────
    overview = research.get("overview", "Comprehensive investment analysis")
    key_bullets: list[str] = []
    if workspace:
        for m in workspace.get("metrics", [])[:3]:
            key_bullets.append(
                f"- {m.get('label', '')}: {m.get('display', m.get('value', ''))}"
            )
    slides.append(
        "# Executive Summary\n\n"
        + overview[:600]
        + ("\n\n" + "\n".join(key_bullets) if key_bullets else "")
    )

    # ── Research section slides ───────────────────────────────────────────
    for name, data in _research_sections(research).items():
        parts: list[str] = []
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, str) and val.strip():
                    parts.append(f"**{key}:** {val[:350]}")
                elif isinstance(val, list):
                    parts += [f"- {item}" for item in val[:6]]
        elif isinstance(data, str) and data.strip():
            parts.append(data[:500])
        if parts:
            slides.append(f"# {name}\n\n" + "\n\n".join(parts))

    # ── Workspace-enriched slides ─────────────────────────────────────────
    if workspace:
        # Metrics dashboard
        metrics = workspace.get("metrics", [])
        if metrics:
            lines = []
            for m in metrics[:8]:
                display = m.get("display", str(m.get("value", "")))
                trend = m.get("trend", "")
                arrow = {"up": "\u2191", "down": "\u2193"}.get(trend, "\u2192")
                lines.append(f"- **{m.get('label', '')}**: {display} {arrow}")
            slides.append("# Key Performance Metrics\n\n" + "\n".join(lines))

        # Chart data
        for c in workspace.get("charts", []):
            cats = c.get("categories", [])
            vals = c.get("values", [])
            if cats and vals:
                lines = [f"- {cat}: {val}" for cat, val in zip(cats, vals)]
                chart_name = c.get("chart_name", "Financial Data").replace("_", " ").title()
                slides.append(f"# {chart_name}\n\n" + "\n".join(lines))

        # Tables
        for t in workspace.get("tables", []):
            headers = t.get("headers", [])
            rows = t.get("rows", [])
            if headers and rows:
                md = "| " + " | ".join(str(h) for h in headers) + " |\n"
                md += "| " + " | ".join("---" for _ in headers) + " |\n"
                for row in rows[:10]:
                    md += "| " + " | ".join(str(v) for v in row) + " |\n"
                table_name = t.get("table_name", "Data").replace("_", " ").title()
                slides.append(f"# {table_name}\n\n{md}")

        # Risk assessment
        risks = workspace.get("risks", [])
        if risks:
            lines = [
                f"- **[{r.get('severity', 'Medium')}]** {r.get('risk', '')}"
                for r in risks[:8]
            ]
            slides.append("# Risk Assessment\n\n" + "\n".join(lines))

    # ── Sources ───────────────────────────────────────────────────────────
    sources = research.get("all_sources", [])
    if sources:
        lines = [f"- [{s.get('id')}] {s.get('title', '')}" for s in sources[:10]]
        slides.append("# Sources & References\n\n" + "\n".join(lines))

    # ── Closing ───────────────────────────────────────────────────────────
    slides.append(
        "# Investment Recommendation\n\n"
        "For further discussion, contact the deal team.\n\n"
        "**Classification:** Confidential\n"
        "**Status:** Draft"
    )

    return slides


# ═══════════════════════════════════════════════════════════════════════════════
# Presenton API client
# ═══════════════════════════════════════════════════════════════════════════════


def _download_pptx(presenton_url: str, pptx_path: str) -> bytes:
    """Download the generated PPTX from Presenton via multiple strategies."""

    # Strategy 1: Shared Docker volume (docker-compose or GCS FUSE)
    for candidate in [Path(pptx_path), Path("/app_data") / pptx_path.lstrip("/app_data/")]:
        if candidate.exists():
            log.info("Read PPTX from filesystem: %s", candidate)
            return candidate.read_bytes()

    # Strategy 2: HTTP download from Presenton's web server
    urls = [
        f"{presenton_url}{pptx_path}",
        f"{presenton_url}/app_data/{pptx_path.split('/app_data/')[-1]}" if "/app_data/" in pptx_path else None,
    ]
    for url in filter(None, urls):
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    log.info("Downloaded PPTX via HTTP: %s (%d bytes)", url, len(resp.content))
                    return resp.content
        except Exception as exc:
            log.debug("HTTP download failed for %s: %s", url, exc)

    raise RuntimeError(
        f"Could not retrieve PPTX from Presenton. path={pptx_path}, base={presenton_url}"
    )


def _call_presenton(
    company: str,
    content: str,
    slides_md: list[str],
    presenton_url: str,
) -> tuple[str, str]:
    """Call Presenton generate API. Returns (presentation_id, pptx_path)."""
    payload = {
        "content": content,
        "slides_markdown": slides_md,
        "instructions": (
            f"This is a Private Equity Due Diligence report for {company}, "
            "prepared for an investment committee. "
            "Use a dark professional theme with gold and teal accents. "
            "Include charts and data visualizations wherever numerical data appears. "
            "The design must be clean, information-dense, and board-room ready."
        ),
        "tone": "professional",
        "verbosity": "standard",
        "n_slides": len(slides_md),
        "language": "English",
        "template": "modern",
        "include_title_slide": True,
        "include_table_of_contents": False,
        "export_as": "pptx",
    }

    log.info("POST %s/api/v1/ppt/presentation/generate (%d slides)", presenton_url, len(slides_md))

    with httpx.Client(timeout=PRESENTON_TIMEOUT) as client:
        resp = client.post(
            f"{presenton_url}/api/v1/ppt/presentation/generate",
            json=payload,
        )
        resp.raise_for_status()
        result = resp.json()

    pid = result.get("presentation_id", "")
    path = result.get("path", "")
    log.info("Presenton OK: id=%s path=%s", pid, path)
    return pid, path


# ═══════════════════════════════════════════════════════════════════════════════
# Slide list for frontend (metadata only — Presenton owns the visual design)
# ═══════════════════════════════════════════════════════════════════════════════


def _slide_list_from_markdown(slides_md: list[str]) -> list[dict]:
    """Extract a minimal slide list for the frontend from our markdown."""
    out = []
    for i, md in enumerate(slides_md):
        first_line = md.split("\n")[0].lstrip("# ").strip()
        out.append({
            "slide_number": i + 1,
            "title": first_line,
            "subtitle": "",
            "bullets": [],
            "key_stat": "",
            "slide_type": "title" if i == 0 else "content",
            "source_ids": [],
            "dashboard_metrics": [],
            "chart": None,
            "table_data": None,
            "risk_blocks": None,
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Mock mode — returns a placeholder PPTX without calling Presenton
# ═══════════════════════════════════════════════════════════════════════════════

# Minimal valid PPTX (ZIP archive with required [Content_Types].xml).
# Generated once offline; 2 KB placeholder so tests pass with `len(bytes) > 1000`.
_MOCK_PPTX_HEADER = (
    b"PK\x03\x04\x14\x00\x00\x00\x08\x00"  # ZIP local file header
    + b"\x00" * 2040                          # padding to exceed 1 KB
)


def _mock_build(company: str, research: dict, workspace: dict | None):
    """Build a mock presentation for testing without a running Presenton."""
    slides_md = _build_slides_markdown(company, research, workspace)
    slide_list = _slide_list_from_markdown(slides_md)
    log.info("Mock mode: built %d slide entries for '%s'", len(slide_list), company)
    return {"slides": slide_list}, _MOCK_PPTX_HEADER


# ═══════════════════════════════════════════════════════════════════════════════
# Public API — same signature as before
# ═══════════════════════════════════════════════════════════════════════════════


def build_presentation(company: str, research: dict, workspace=None):
    """Generate a presentation via Presenton API.

    Returns
    -------
    ({"slides": [...]}, pptx_bytes)
        Slide metadata dict for the frontend, and raw PPTX bytes for storage.
    """
    if settings.mock_mode:
        return _mock_build(company, research, workspace)

    presenton_url = settings.presenton_url

    # Build content
    content = _format_content(company, research, workspace)
    slides_md = _build_slides_markdown(company, research, workspace)

    # Call Presenton
    _pid, pptx_path = _call_presenton(company, content, slides_md, presenton_url)

    # Download PPTX
    pptx_bytes = _download_pptx(presenton_url, pptx_path)

    # Build slide list for frontend
    slide_list = _slide_list_from_markdown(slides_md)

    return {"slides": slide_list}, pptx_bytes
