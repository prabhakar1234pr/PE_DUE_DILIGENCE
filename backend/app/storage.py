"""Storage — GCS persistence for PPTX files and response JSON.

Stores two files per research run:
  reports/{slug}-{timestamp}.pptx   — the PowerPoint file
  reports/{slug}-{timestamp}.json   — the full API response (for history reload)

The JSON file enables permanent history across container restarts
and devices. GCS is the source of truth; localStorage is just a cache.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.cloud import storage as gcs

from app.settings import settings

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _get_bucket():
    """Get the GCS bucket client."""
    client = gcs.Client(project=settings.gcp_project_id or None)
    return client.bucket(settings.gcp_bucket_name)


def _gcs_public_url(path: str) -> str:
    return f"https://storage.googleapis.com/{settings.gcp_bucket_name}/{path}"


# ── Save operations ──────────────────────────────────────────

def save_pptx_and_get_url(company: str, pptx_bytes: bytes) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"{_slugify(company)}-{timestamp}.pptx"

    if settings.gcp_bucket_name:
        try:
            bucket = _get_bucket()
            blob = bucket.blob(f"reports/{filename}")
            blob.upload_from_string(
                pptx_bytes,
                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            url = _gcs_public_url(f"reports/{filename}")
            logger.info("PPTX uploaded to %s", url)
            return url
        except Exception as exc:
            logger.warning("GCS PPTX upload failed: %s", exc)

    output_dir = Path("generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_bytes(pptx_bytes)
    return f"/{output_path.as_posix()}"


def save_response_json(company: str, response_data: dict[str, Any]) -> str | None:
    """Save the full API response as a JSON file in GCS for history persistence.

    Returns the GCS path (not full URL) for listing purposes, or None on failure.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"{_slugify(company)}-{timestamp}.json"
    gcs_path = f"reports/{filename}"

    if settings.gcp_bucket_name:
        try:
            bucket = _get_bucket()
            blob = bucket.blob(gcs_path)

            # Add metadata for listing
            blob.metadata = {
                "company": company,
                "generated_at": response_data.get("generated_at", ""),
                "slide_count": str(len(response_data.get("slides", []))),
                "source_count": str(len(response_data.get("sources", []))),
            }

            blob.upload_from_string(
                json.dumps(response_data, default=str),
                content_type="application/json",
            )
            logger.info("Response JSON saved to %s", gcs_path)
            return gcs_path
        except Exception as exc:
            logger.warning("GCS JSON save failed: %s", exc)

    # Fallback: save locally
    try:
        output_dir = Path("generated")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        output_path.write_text(json.dumps(response_data, default=str))
        return str(output_path)
    except Exception:
        return None


# ── Read operations (for history) ────────────────────────────

def list_saved_runs(limit: int = 50) -> list[dict[str, Any]]:
    """List all saved response JSON files from GCS, newest first.

    Returns list of {run_id, company, generated_at, slide_count, source_count, json_path}
    """
    if not settings.gcp_bucket_name:
        return _list_local_runs(limit)

    try:
        bucket = _get_bucket()
        blobs = list(bucket.list_blobs(prefix="reports/", max_results=limit * 2))

        # Filter to JSON files only
        json_blobs = [b for b in blobs if b.name.endswith(".json")]
        # Sort newest first
        json_blobs.sort(key=lambda b: b.time_created or "", reverse=True)

        runs = []
        for blob in json_blobs[:limit]:
            # Reload metadata
            blob.reload()
            meta = blob.metadata or {}

            # Extract company from filename if not in metadata
            name_part = blob.name.replace("reports/", "").replace(".json", "")
            company = meta.get("company", name_part.rsplit("-", 2)[0].replace("-", " ").title())

            runs.append({
                "run_id": name_part,
                "company": company,
                "started_at": meta.get("generated_at", str(blob.time_created or "")),
                "finding_count": int(meta.get("slide_count", 0)),
                "source_count": int(meta.get("source_count", 0)),
                "json_path": blob.name,
            })
        return runs
    except Exception as exc:
        logger.warning("GCS list failed: %s", exc)
        return _list_local_runs(limit)


def load_saved_run(json_path: str) -> dict[str, Any] | None:
    """Load a saved response JSON from GCS.

    Args:
        json_path: The GCS blob path (e.g., "reports/anthropic-20260402-011130.json")

    Returns:
        The full response dict, or None if not found.
    """
    if not settings.gcp_bucket_name:
        return _load_local_run(json_path)

    try:
        bucket = _get_bucket()
        blob = bucket.blob(json_path)
        if not blob.exists():
            return None
        content = blob.download_as_text()
        return json.loads(content)
    except Exception as exc:
        logger.warning("GCS load failed for %s: %s", json_path, exc)
        return _load_local_run(json_path)


# ── Local fallbacks ──────────────────────────────────────────

def _list_local_runs(limit: int) -> list[dict[str, Any]]:
    """List locally saved JSON files."""
    output_dir = Path("generated")
    if not output_dir.exists():
        return []

    json_files = sorted(output_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    runs = []
    for f in json_files[:limit]:
        try:
            data = json.loads(f.read_text())
            name_part = f.stem
            runs.append({
                "run_id": name_part,
                "company": data.get("company", name_part.replace("-", " ").title()),
                "started_at": data.get("generated_at", ""),
                "finding_count": len(data.get("slides", [])),
                "source_count": len(data.get("sources", [])),
                "json_path": str(f),
            })
        except Exception:
            pass
    return runs


def _load_local_run(path: str) -> dict[str, Any] | None:
    """Load a locally saved JSON file."""
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return None
