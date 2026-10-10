"""
Shared helpers used by the Substack and AlphaSpread scripts.

Currently: polite HTTP GET helpers (gzip-aware, with 429/backoff retry) and a
lightweight status probe. Kept dependency-free (stdlib only).
"""

import gzip
import json
import random
import sys
import time
import urllib.error
import urllib.request

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def force_utf8_stdout():
    """Make stdout/stderr tolerate non-ASCII glyphs (✓, −, ↑) on Windows
    consoles that default to cp1252. Safe no-op elsewhere."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _sleep_for_retry(err, attempt, base_delay):
    """Backoff duration, honoring a Retry-After header on 429 when present."""
    ra = None
    if isinstance(err, urllib.error.HTTPError):
        ra = err.headers.get("retry-after")
    if ra and str(ra).strip().isdigit():
        return min(float(ra) + random.uniform(0, 1.5), 120)
    return min(base_delay * (2 ** attempt) + random.uniform(0, 1.5), 120)


def http_get(url, headers=None, timeout=30, retries=4, base_delay=3.0):
    """GET a URL and return the decoded text body.

    - Sends a browser-like User-Agent and accepts gzip.
    - Retries with exponential backoff on HTTP 429 and transient errors.
    - Raises the last exception (e.g. HTTPError 404) if it never succeeds.
    """
    hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=hdrs)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            charset = resp.headers.get_content_charset() or "utf-8"
            return data.decode(charset, "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and attempt < retries:
                time.sleep(_sleep_for_retry(e, attempt, base_delay))
                continue
            raise
        except Exception as e:  # noqa: BLE001  (URLError, timeout, etc.)
            last = e
            if attempt < retries:
                time.sleep(_sleep_for_retry(e, attempt, base_delay))
                continue
            raise
    raise last


def http_get_json(url, headers=None, **kwargs):
    """GET a URL and parse the body as JSON."""
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    return json.loads(http_get(url, headers=h, **kwargs))


def http_status(url, headers=None, timeout=20):
    """Return (status_code, final_url) for a URL, following redirects.
    Returns the HTTP error code (e.g. 404) instead of raising for HTTPErrors."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, url
