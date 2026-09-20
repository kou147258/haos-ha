"""Upload haos-1.5.0.zip and haos_fb-1.5.0.zip to release 392288408."""
import io
import json
import os
import time
import urllib.request
import zipfile

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)

RELEASE_ID = 392288408
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()


def get_release():
    req = urllib.request.Request(
        f"https://api.github.com/repos/kou147258/haos-ha/releases/{RELEASE_ID}"
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "upload-assets/1.0")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def upload(url, data, mime, max_retries=10):
    last_exc = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", mime)
        req.add_header("User-Agent", "upload-assets/1.0")
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


def build_zip(src_dir):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src_dir):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, os.getcwd())
                zf.write(full, arc)
    return buf.getvalue()


# 1. Get release upload URL
rel = get_release()
print(f"release id={rel['id']} tag_name={rel['tag_name']}")
upload_url = rel["upload_url"].split("{", 1)[0]
print(f"upload_url={upload_url}")

# 2. Build zips
haos_zip = build_zip("custom_components/haos")
print(f"haos-1.5.0.zip: {len(haos_zip)} bytes")
addon_zip = build_zip("haos_fb")
print(f"haos_fb-1.5.0.zip: {len(addon_zip)} bytes")

# 3. Upload both
for name, data in [("haos-1.5.0.zip", haos_zip), ("haos_fb-1.5.0.zip", addon_zip)]:
    print(f"uploading {name}...")
    asset = upload(upload_url + f"?name={name}", data, "application/zip")
    print(f"  OK id={asset['id']} ({asset['size']} bytes) {asset['browser_download_url']}")