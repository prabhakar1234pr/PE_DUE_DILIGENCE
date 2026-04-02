"""Image Fetcher — Downloads company logos and assets for PPT slides.

Uses multiple strategies to find company logos:
  1. Clearbit Logo API (free, high-quality, most companies)
  2. Google Favicon API (fallback)
  3. Direct URL download (if LLM provides a URL)

Images are cached in workspace/images/ to avoid re-downloading.
"""

import hashlib
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("workspace/images")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Timeout for all HTTP requests
_TIMEOUT = 10


def _cache_path(url: str) -> Path:
    """Generate a cache file path from URL hash."""
    h = hashlib.md5(url.encode()).hexdigest()[:16]
    return _CACHE_DIR / f"{h}.png"


def _download(url: str) -> bytes | None:
    """Download an image, return bytes or None."""
    try:
        resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "PE-DD-Agent/1.0"})
        if resp.status_code == 200 and len(resp.content) > 500:
            return resp.content
    except Exception as e:
        logger.debug("Download failed for %s: %s", url, e)
    return None


def fetch_company_logo(company: str, domain: str | None = None) -> str | None:
    """Fetch a company logo and return the local file path.

    Args:
        company: Company name
        domain: Company domain (e.g., 'anthropic.com'). If not provided, will guess.

    Returns:
        Local file path to the logo image, or None if not found.
    """
    # Try to determine domain
    if not domain:
        slug = company.lower().replace(" ", "").replace(".", "").replace(",", "")
        domain = f"{slug}.com"

    # Check cache first
    cache_key = _cache_path(f"logo-{domain}")
    if cache_key.exists():
        return str(cache_key)

    # Strategy 1: Clearbit Logo API (128px, high quality, free)
    clearbit_url = f"https://logo.clearbit.com/{domain}?size=256"
    data = _download(clearbit_url)
    if data:
        cache_key.write_bytes(data)
        logger.info("Logo fetched via Clearbit for %s", domain)
        return str(cache_key)

    # Strategy 2: Google Favicon API (lower quality but wider coverage)
    google_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    data = _download(google_url)
    if data:
        cache_key.write_bytes(data)
        logger.info("Logo fetched via Google Favicon for %s", domain)
        return str(cache_key)

    # Strategy 3: Try alternate domain patterns
    for alt in [f"{company.lower().replace(' ', '')}.com",
                f"{company.lower().replace(' ', '-')}.com",
                f"{company.lower().replace(' ', '')}.ai",
                f"{company.lower().replace(' ', '')}.io"]:
        if alt != domain:
            alt_url = f"https://logo.clearbit.com/{alt}?size=256"
            data = _download(alt_url)
            if data:
                cache_key.write_bytes(data)
                logger.info("Logo fetched via Clearbit alt domain %s", alt)
                return str(cache_key)

    logger.info("No logo found for %s", company)
    return None


def fetch_image_from_url(url: str) -> str | None:
    """Download an image from a direct URL and return local path."""
    cache = _cache_path(url)
    if cache.exists():
        return str(cache)

    data = _download(url)
    if data:
        cache.write_bytes(data)
        return str(cache)
    return None


def fetch_competitor_logos(competitors: list[str]) -> dict[str, str | None]:
    """Fetch logos for a list of competitor companies.

    Returns:
        Dict mapping company name → local file path (or None).
    """
    results = {}
    for comp in competitors[:6]:  # Limit to 6 to avoid slowness
        name = comp.strip()
        if not name:
            continue
        results[name] = fetch_company_logo(name)
    return results
