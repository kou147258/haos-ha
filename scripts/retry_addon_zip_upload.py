"""Retry: upload haos_fb-1.5.0.zip to release 392282413."""
import io
import json
import os
import time
import urllib.request
import zipfile

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)

RELEASE_ID = 392282413
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()


def api_get_release():
    req = urllib.request.Request(
        f"https://api.github.com/repos/kou147258/haos-ha/releases/{RELEASE_ID}"
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "retry-upload/1.0")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def upload(url, data, mime, max_retries=10):
    last_exc = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", mime)
        req.add_header("User-Agent", "retry-upload/1.0")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.URLError as exc:
            last_exc = exc
            wait = min(2 ** attempt, 90)
            print(f"  retry {attempt + 1}/{max_retries} after {wait}s: {exc!r}", flush=True)
            time.sleep(wait)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    raise RuntimeError(f"gave up: {last_exc!r}")


# 1. Get release to find upload URL
rel = api_get_release()
print(f"release id={rel['id']} tag_name={rel['tag_name']}")
upload_url = rel["upload_url"].split("{", 1)[0]
print(f"upload_url={upload_url}")

# 2. Build haos_fb-1.5.0.zip
src = os.path.join(os.getcwd(), "haos_fb")
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(src):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, os.getcwd())
            zf.write(full, arc)
add_on_zip = buf.getvalue()
print(f"haos_fb-1.5.0.zip: {len(add_on_zip)} bytes")

# 3. Upload
asset_url = upload_url + "?name=haos_fb-1.5.0.zip"
asset = upload(asset_url, add_on_zip, "application/zip")
print(f"uploaded {asset['name']} ({asset['size']} bytes) id={asset['id']}")
print(f"browser: {asset['browser_download_url']}")