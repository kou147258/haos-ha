"""Retry: upload haos-1.5.0.zip to release id 392282413."""
import base64
import io
import json
import os
import time
import urllib.request
import zipfile

for _k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(_k, None)

TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()

# Build zip
src = os.path.join(os.getcwd(), "custom_components", "haos")
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(src):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, os.path.join(os.getcwd(), "custom_components"))
            zf.write(full, arc)
zip_bytes = buf.getvalue()
print(f"zip size: {len(zip_bytes)} bytes")


def upload_with_retry(url, data, mime, asset_name, max_retries=5):
    last_exc = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", mime)
        req.add_header("User-Agent", "haos-ha-asset-upload/1.0")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.URLError as exc:
            last_exc = exc
            wait = min(2 ** attempt, 60)
            print(f"  retry {attempt + 1}/{max_retries} after {wait}s: {exc!r}", flush=True)
            time.sleep(wait)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    raise RuntimeError(f"gave up: {last_exc!r}")


# First try: standard URL with ?name=
url1 = (
    "https://uploads.github.com/repos/kou147258/haos-ha/releases/392282413/assets"
    "?name=haos-1.5.0.zip"
)
print(f"uploading to {url1}")
try:
    resp = upload_with_retry(
        url1, zip_bytes, "application/zip", "haos-1.5.0.zip",
    )
    print(f"OK asset {resp.get('name')} ({resp.get('size')} bytes) id={resp.get('id')}")
    print(f"  browser_url: {resp.get('browser_download_url')}")
except Exception as exc:
    print(f"FAIL: {exc}")