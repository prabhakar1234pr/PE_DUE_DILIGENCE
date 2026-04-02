"""Analyst Agent — Transforms raw research findings into structured, chart-ready datasets.

Reads from the workspace DB (raw findings from Research Agent)
and writes back structured data:
  - chart_datasets: arrays ready for bar/pie/doughnut/column charts
  - table_datasets: headers + rows for styled tables
  - metrics: individual numeric KPIs with trends
  - risks: structured risk items with severity ratings

The PPT Agent then reads these structured datasets to create immersive visuals.
"""

import json
import re
from typing import Any, Generator

from app.workspace import (
    get_findings,
    get_metrics,
    get_sources_reindexed,
    write_chart,
    write_metric,
    write_risk,
    write_table,
)


def _extract_numeric(s: str) -> float:
    """Extract a numeric value from strings like '$300M+', '42%', '4.5x', '128-135%'."""
    if not s:
        return 0
    # Handle ranges: take the midpoint
    range_match = re.search(r"([\d.]+)\s*[-–]\s*([\d.]+)", str(s).replace(",", ""))
    if range_match:
        return (float(range_match.group(1)) + float(range_match.group(2))) / 2
    m = re.search(r"[\d.]+", str(s).replace(",", ""))
    return float(m.group()) if m else 0


def run_analyst(company: str, run_id: str) -> Generator:
    """Analyze research findings and create structured datasets. Yields stream events."""
    yield {"event": "progress", "data": "Analyst: Reading research workspace..."}

    findings = get_findings(run_id)
    if not findings:
        yield {"event": "error", "data": "Analyst: No research findings in workspace"}
        return

    # Build a lookup: section → parsed data
    sections: dict[str, Any] = {}
    for f in findings:
        try:
            sections[f["section"]] = json.loads(f["content"])
        except (json.JSONDecodeError, TypeError):
            sections[f["section"]] = {"raw": f["content"]}

    yield {"event": "progress", "data": f"Analyst: Found {len(sections)} research sections"}

    # ── Extract metrics ────────────────────────────────────────
    yield {"event": "thinking", "data": "Extracting numeric metrics from research..."}

    bm = sections.get("business_model", {})
    ue = bm.get("unit_economics", {}) if isinstance(bm, dict) else {}
    fin = sections.get("financial_signals", {})
    risk_data = sections.get("risk_and_regulatory", {})

    metric_defs = []
    if isinstance(ue, dict):
        for key, label, unit, trend in [
            ("nrr_ndr", "Net Revenue Retention", "%", "up"),
            ("gross_margin", "Gross Margin", "%", "up"),
            ("ltv_cac_ratio", "LTV:CAC Ratio", "x", "up"),
            ("rule_of_40_score", "Rule of 40", "", "up"),
            ("logo_retention", "Logo Retention", "%", "flat"),
            ("payback_period_months", "Payback Period", "months", "down"),
            ("cac_estimate", "CAC", "$", "flat"),
            ("ltv_estimate", "LTV", "$", "up"),
        ]:
            val_str = str(ue.get(key, ""))
            if val_str:
                num = _extract_numeric(val_str)
                display = val_str[:30]
                metric_defs.append((label, num, display, unit, trend))

    if isinstance(fin, dict):
        arr = fin.get("arr_trajectory", "")
        if arr:
            metric_defs.append(("Est. ARR", _extract_numeric(arr), arr[:30], "$M", "up"))
        growth = fin.get("revenue_growth_cagr", "")
        if growth:
            metric_defs.append(("Revenue Growth", _extract_numeric(growth), growth[:30], "%", "up"))

    for label, val, display, unit, trend in metric_defs:
        write_metric(run_id, company, label, val, display, unit, trend)

    yield {"event": "thinking", "data": f"Extracted {len(metric_defs)} metrics"}

    # ── Build chart datasets ──────────────────────────────────
    yield {"event": "thinking", "data": "Building chart datasets for visualizations..."}
    charts_created = 0

    # Revenue composition pie chart
    if isinstance(bm, dict):
        rev = bm.get("revenue_composition", {})
        if isinstance(rev, dict):
            cats, vals = [], []
            for k, v in rev.items():
                label = k.replace("_pct", "").replace("_", " ").title()
                num = _extract_numeric(str(v))
                if num > 0:
                    cats.append(label)
                    vals.append(num)
            if cats:
                write_chart(run_id, company, "revenue_composition", "pie", cats, vals)
                charts_created += 1

    # KPI comparison bar chart
    if metric_defs:
        kpi_cats = []
        kpi_vals = []
        for label, val, _, _, _ in metric_defs:
            if val > 0 and label not in ("CAC", "LTV", "Est. ARR"):
                kpi_cats.append(label[:15])
                kpi_vals.append(val)
        if kpi_cats:
            write_chart(run_id, company, "kpi_comparison", "bar", kpi_cats[:8], kpi_vals[:8])
            charts_created += 1

    # Exit scenarios doughnut chart
    exit_data = sections.get("exit_and_investment", {})
    if isinstance(exit_data, dict) and exit_data.get("exit_multiples"):
        write_chart(run_id, company, "exit_scenarios", "doughnut",
                    ["Bear Case", "Base Case", "Bull Case"], [25, 50, 25])
        charts_created += 1

    # Funding timeline (if multiple rounds)
    if isinstance(fin, dict):
        rounds = fin.get("funding_rounds", [])
        if len(rounds) >= 2:
            round_cats = []
            round_vals = []
            for r in rounds:
                if isinstance(r, dict):
                    round_cats.append(r.get("round", "")[:10])
                    amt = _extract_numeric(r.get("amount", "0"))
                    round_vals.append(amt)
            if round_cats:
                write_chart(run_id, company, "funding_timeline", "column", round_cats, round_vals)
                charts_created += 1

    # Exec summary bar chart (key headline metrics)
    headline_cats = ["ARR ($M)", "Growth %", "NRR %", "Margin %"]
    headline_vals = []
    arr_val = _extract_numeric(fin.get("arr_trajectory", "0")) if isinstance(fin, dict) else 0
    growth_val = _extract_numeric(fin.get("revenue_growth_cagr", "0")) if isinstance(fin, dict) else 0
    nrr_val = _extract_numeric(ue.get("nrr_ndr", "0")) if isinstance(ue, dict) else 0
    margin_val = _extract_numeric(ue.get("gross_margin", "0")) if isinstance(ue, dict) else 0
    headline_vals = [arr_val, growth_val, nrr_val, margin_val]
    if any(v > 0 for v in headline_vals):
        write_chart(run_id, company, "headline_metrics", "bar", headline_cats, headline_vals)
        charts_created += 1

    yield {"event": "thinking", "data": f"Created {charts_created} chart datasets"}

    # ── Build table datasets ──────────────────────────────────
    yield {"event": "thinking", "data": "Building table datasets..."}
    tables_created = 0

    # Competitive positioning table
    mkt = sections.get("market_and_competition", {})
    if isinstance(mkt, dict):
        matrix = mkt.get("positioning_matrix", [])
        if matrix:
            headers = ["Competitor", "Strengths", "Weaknesses", "Our Position"]
            rows = []
            for p in matrix:
                if isinstance(p, dict):
                    rows.append([
                        p.get("competitor", "")[:25],
                        p.get("strengths", "")[:45],
                        p.get("weaknesses", "")[:45],
                        p.get("vs_target", p.get("relative_position", ""))[:45],
                    ])
            if rows:
                write_table(run_id, company, "competitive_positioning", headers, rows)
                tables_created += 1

    # Comparable transactions table
    comps = sections.get("comparable_transactions", {})
    if isinstance(comps, dict):
        priv = comps.get("private_transactions", [])
        pub = comps.get("public_comps", [])
        if priv or pub:
            headers = ["Company", "Type", "Valuation/Multiple", "Growth/Date"]
            rows = []
            for t in priv:
                if isinstance(t, dict):
                    rows.append([t.get("target", ""), "Private", t.get("deal_value", ""), t.get("revenue_multiple", "")])
            for t in pub:
                if isinstance(t, dict):
                    rows.append([t.get("company", ""), "Public", t.get("ev_revenue_multiple", ""), t.get("growth_rate", "")])
            if rows:
                write_table(run_id, company, "comparable_transactions", headers, rows)
                tables_created += 1

    # Funding rounds table
    if isinstance(fin, dict):
        rounds = fin.get("funding_rounds", [])
        if len(rounds) >= 2:
            headers = ["Round", "Date", "Amount", "Lead Investor", "Valuation"]
            rows = []
            for r in rounds:
                if isinstance(r, dict):
                    rows.append([
                        r.get("round", ""), r.get("date", ""), r.get("amount", ""),
                        r.get("lead_investor", ""), r.get("valuation", ""),
                    ])
            if rows:
                write_table(run_id, company, "funding_rounds", headers, rows)
                tables_created += 1

    # Management team table
    mgmt = sections.get("management_team", {})
    if isinstance(mgmt, dict):
        execs = mgmt.get("executives", [])
        if execs:
            headers = ["Name", "Title", "Background", "Signal"]
            rows = []
            for e in execs:
                if isinstance(e, dict):
                    rows.append([
                        e.get("name", ""), e.get("title", ""),
                        e.get("background", "")[:60], e.get("signal", "")[:40],
                    ])
            if rows:
                write_table(run_id, company, "management_team", headers, rows)
                tables_created += 1

    yield {"event": "thinking", "data": f"Created {tables_created} table datasets"}

    # ── Build risk items ──────────────────────────────────────
    yield {"event": "thinking", "data": "Structuring risk matrix..."}
    risks_created = 0

    if isinstance(risk_data, dict):
        for r in risk_data.get("key_risks", []):
            if isinstance(r, dict):
                write_risk(run_id, company, r.get("risk", ""), r.get("severity", "Medium"),
                           r.get("probability", ""), r.get("mitigation", ""))
                risks_created += 1

    yield {"event": "thinking", "data": f"Structured {risks_created} risk items"}

    # ── Summary ───────────────────────────────────────────────
    total = len(metric_defs) + charts_created + tables_created + risks_created
    yield {"event": "progress", "data": f"Analyst complete: {len(metric_defs)} metrics, {charts_created} charts, {tables_created} tables, {risks_created} risks"}
    yield {"event": "done", "data": {"metrics": len(metric_defs), "charts": charts_created,
                                      "tables": tables_created, "risks": risks_created, "total": total}}
