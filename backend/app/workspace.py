"""SQLite workspace — shared scratch pad for all agents.

Acts as the "rough book" where:
  - Research agent writes raw findings (prose + sources)
  - Analyst agent writes structured datasets (chart-ready arrays, tables, metrics)
  - PPT agent reads everything to build immersive visuals

Each research run gets a unique run_id (company + timestamp).
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DB_DIR = Path("workspace")
_DB_DIR.mkdir(exist_ok=True)
_DB_PATH = _DB_DIR / "research.db"

_local = threading.local()


def _conn() -> sqlite3.Connection:
    """Thread-local connection (SQLite is not thread-safe by default)."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _init_tables(_local.conn)
    return _local.conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS research_findings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL,
        company     TEXT NOT NULL,
        section     TEXT NOT NULL,
        content     TEXT NOT NULL,
        sources     TEXT DEFAULT '[]',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS chart_datasets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL,
        company     TEXT NOT NULL,
        chart_name  TEXT NOT NULL,
        chart_type  TEXT NOT NULL,
        categories  TEXT NOT NULL,
        data_values TEXT NOT NULL,
        series      TEXT DEFAULT '[]',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS table_datasets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL,
        company     TEXT NOT NULL,
        table_name  TEXT NOT NULL,
        headers     TEXT NOT NULL,
        rows_data   TEXT NOT NULL,
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS metrics (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL,
        company     TEXT NOT NULL,
        label       TEXT NOT NULL,
        value       REAL,
        display     TEXT NOT NULL,
        unit        TEXT DEFAULT '',
        trend       TEXT DEFAULT 'flat',
        confidence  TEXT DEFAULT 'Medium',
        source_ref  TEXT DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS risks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL,
        company     TEXT NOT NULL,
        risk        TEXT NOT NULL,
        severity    TEXT NOT NULL,
        probability TEXT DEFAULT '',
        mitigation  TEXT DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sources (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL,
        company     TEXT NOT NULL,
        title       TEXT NOT NULL,
        url         TEXT NOT NULL,
        snippet     TEXT DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_findings_run ON research_findings(run_id);
    CREATE INDEX IF NOT EXISTS idx_charts_run ON chart_datasets(run_id);
    CREATE INDEX IF NOT EXISTS idx_tables_run ON table_datasets(run_id);
    CREATE INDEX IF NOT EXISTS idx_metrics_run ON metrics(run_id);
    CREATE INDEX IF NOT EXISTS idx_risks_run ON risks(run_id);
    CREATE INDEX IF NOT EXISTS idx_sources_run ON sources(run_id);
    """)


def new_run_id(company: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    slug = company.lower().replace(" ", "-")[:30]
    return f"{slug}-{ts}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── Write operations ─────────────────────────────────────────

def write_finding(run_id: str, company: str, section: str, content: str,
                  sources: list[dict] | None = None):
    _conn().execute(
        "INSERT INTO research_findings (run_id, company, section, content, sources, created_at) VALUES (?,?,?,?,?,?)",
        (run_id, company, section, content, json.dumps(sources or []), _now()),
    )
    _conn().commit()


def write_chart(run_id: str, company: str, chart_name: str, chart_type: str,
                categories: list[str], values: list[float],
                series: list[dict] | None = None):
    _conn().execute(
        "INSERT INTO chart_datasets (run_id, company, chart_name, chart_type, categories, data_values, series, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (run_id, company, chart_name, chart_type, json.dumps(categories),
         json.dumps(values), json.dumps(series or []), _now()),
    )
    _conn().commit()


def write_table(run_id: str, company: str, table_name: str,
                headers: list[str], rows: list[list[str]]):
    _conn().execute(
        "INSERT INTO table_datasets (run_id, company, table_name, headers, rows_data, created_at) VALUES (?,?,?,?,?,?)",
        (run_id, company, table_name, json.dumps(headers), json.dumps(rows), _now()),
    )
    _conn().commit()


def write_metric(run_id: str, company: str, label: str, value: float,
                 display: str, unit: str = "", trend: str = "flat",
                 confidence: str = "Medium", source_ref: str = ""):
    _conn().execute(
        "INSERT INTO metrics (run_id, company, label, value, display, unit, trend, confidence, source_ref, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (run_id, company, label, value, display, unit, trend, confidence, source_ref, _now()),
    )
    _conn().commit()


def write_risk(run_id: str, company: str, risk: str, severity: str,
               probability: str = "", mitigation: str = ""):
    _conn().execute(
        "INSERT INTO risks (run_id, company, risk, severity, probability, mitigation, created_at) VALUES (?,?,?,?,?,?,?)",
        (run_id, company, risk, severity, probability, mitigation, _now()),
    )
    _conn().commit()


def write_source(run_id: str, company: str, title: str, url: str, snippet: str = ""):
    # Deduplicate by URL within the same run
    existing = _conn().execute(
        "SELECT id FROM sources WHERE run_id=? AND url=?", (run_id, url)
    ).fetchone()
    if existing:
        return
    _conn().execute(
        "INSERT INTO sources (run_id, company, title, url, snippet, created_at) VALUES (?,?,?,?,?,?)",
        (run_id, company, title, url, snippet, _now()),
    )
    _conn().commit()


# ── Read operations ──────────────────────────────────────────

def get_findings(run_id: str) -> list[dict[str, Any]]:
    rows = _conn().execute(
        "SELECT section, content, sources FROM research_findings WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall()
    return [{"section": r["section"], "content": r["content"],
             "sources": json.loads(r["sources"])} for r in rows]


def get_finding(run_id: str, section: str) -> str | None:
    row = _conn().execute(
        "SELECT content FROM research_findings WHERE run_id=? AND section=? ORDER BY id DESC LIMIT 1",
        (run_id, section),
    ).fetchone()
    return row["content"] if row else None


def get_charts(run_id: str) -> list[dict[str, Any]]:
    rows = _conn().execute(
        "SELECT chart_name, chart_type, categories, data_values, series FROM chart_datasets WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [{
        "chart_name": r["chart_name"],
        "chart_type": r["chart_type"],
        "categories": json.loads(r["categories"]),
        "values": json.loads(r["data_values"]),
        "series": json.loads(r["series"]),
    } for r in rows]


def get_chart(run_id: str, chart_name: str) -> dict[str, Any] | None:
    row = _conn().execute(
        "SELECT chart_type, categories, data_values, series FROM chart_datasets WHERE run_id=? AND chart_name=? ORDER BY id DESC LIMIT 1",
        (run_id, chart_name),
    ).fetchone()
    if not row:
        return None
    return {
        "chart_type": row["chart_type"],
        "categories": json.loads(row["categories"]),
        "values": json.loads(row["data_values"]),
        "series": json.loads(row["series"]),
    }


def get_tables(run_id: str) -> list[dict[str, Any]]:
    rows = _conn().execute(
        "SELECT table_name, headers, rows_data FROM table_datasets WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [{
        "table_name": r["table_name"],
        "headers": json.loads(r["headers"]),
        "rows": json.loads(r["rows_data"]),
    } for r in rows]


def get_table(run_id: str, table_name: str) -> dict[str, Any] | None:
    row = _conn().execute(
        "SELECT headers, rows_data FROM table_datasets WHERE run_id=? AND table_name=? ORDER BY id DESC LIMIT 1",
        (run_id, table_name),
    ).fetchone()
    if not row:
        return None
    return {"headers": json.loads(row["headers"]), "rows": json.loads(row["rows_data"])}


def get_metrics(run_id: str) -> list[dict[str, Any]]:
    rows = _conn().execute(
        "SELECT label, value, display, unit, trend, confidence, source_ref FROM metrics WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_risks(run_id: str) -> list[dict[str, Any]]:
    rows = _conn().execute(
        "SELECT risk, severity, probability, mitigation FROM risks WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_sources(run_id: str) -> list[dict[str, Any]]:
    rows = _conn().execute(
        "SELECT id, title, url, snippet FROM sources WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [{"id": r["id"], "title": r["title"], "url": r["url"], "snippet": r["snippet"]} for r in rows]


def get_sources_reindexed(run_id: str) -> list[dict[str, Any]]:
    """Return sources with sequential 1-based IDs."""
    raw = get_sources(run_id)
    return [{"id": i, "title": s["title"], "url": s["url"], "snippet": s["snippet"]}
            for i, s in enumerate(raw, 1)]


def get_full_workspace(run_id: str) -> dict[str, Any]:
    """Read everything in the workspace for a run — used by PPT agent."""
    return {
        "findings": get_findings(run_id),
        "charts": get_charts(run_id),
        "tables": get_tables(run_id),
        "metrics": get_metrics(run_id),
        "risks": get_risks(run_id),
        "sources": get_sources_reindexed(run_id),
    }


# ── History / session queries ────────────────────────────────

def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """List all research runs, newest first."""
    rows = _conn().execute(
        """SELECT run_id, company, MIN(created_at) as started_at,
                  COUNT(*) as finding_count
           FROM research_findings
           GROUP BY run_id, company
           ORDER BY MIN(created_at) DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    result = []
    for r in rows:
        source_count = _conn().execute(
            "SELECT COUNT(*) FROM sources WHERE run_id=?", (r["run_id"],)
        ).fetchone()[0]
        result.append({
            "run_id": r["run_id"],
            "company": r["company"],
            "started_at": r["started_at"],
            "finding_count": r["finding_count"],
            "source_count": source_count,
        })
    return result


def get_run_company(run_id: str) -> str | None:
    """Get the company name for a given run_id."""
    row = _conn().execute(
        "SELECT company FROM research_findings WHERE run_id=? LIMIT 1", (run_id,)
    ).fetchone()
    return row["company"] if row else None


def run_exists(run_id: str) -> bool:
    """Check if a run_id exists in the workspace."""
    row = _conn().execute(
        "SELECT COUNT(*) FROM research_findings WHERE run_id=?", (run_id,)
    ).fetchone()
    return row[0] > 0
