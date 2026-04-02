import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import storage

from app.settings import settings

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def save_pptx_and_get_url(company: str, pptx_bytes: bytes) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"{_slugify(company)}-{timestamp}.pptx"

    if settings.gcp_bucket_name:
        try:
            client = storage.Client(project=settings.gcp_project_id or None)
            bucket = client.bucket(settings.gcp_bucket_name)
            blob = bucket.blob(f"reports/{filename}")
            blob.upload_from_string(
                pptx_bytes,
                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            # Use the direct public URL (bucket must have public access or allUsers reader)
            # This avoids signed URLs which require a private key not available on Cloud Run
            url = f"https://storage.googleapis.com/{settings.gcp_bucket_name}/reports/{filename}"
            logger.info("PPTX uploaded to %s", url)
            return url
        except Exception as exc:
            logger.warning("GCS upload failed: %s — falling back to local storage", exc)

    # Fallback: save locally
    output_dir = Path("generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_bytes(pptx_bytes)
    return f"/{output_path.as_posix()}"
