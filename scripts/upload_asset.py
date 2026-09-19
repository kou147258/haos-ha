"""Upload haos_fb-1.2.1.zip to the existing v1.2.1 GitHub release."""

import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
TAG = "v1.2.1"
ZIP_PATH = "haos_fb-1.2.1.zip"

# 1. Look up the release id for tag.
r = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")
r.add_header("Authorization", "Bearer " + TOKEN)
r.add_header("Accept", "application/vnd.github+json")
with urllib.request.urlopen(r, timeout=30) as resp:
    rel = json.loads(resp.read())
release_id = rel["id"]
upload_url = rel["upload_url"]  # ends with {?name,label}
print(f"release_id={release_id}  upload_url_template={upload_url[:80]}...")

# 2. POST upload. The upload_url is a *template* — append ?name=<asset>
# and ?label=<label> to select the asset slot.
name = os.path.basename(ZIP_PATH)
url = f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name={name}"
size = os.path.getsize(ZIP_PATH)
data = open(ZIP_PATH, "rb").read()
req = urllib.request.Request(url, data=data, method="POST")
req.add_header("Authorization", "Bearer " + TOKEN)
req.add_header("Accept", "application/vnd.github+json")
req.add_header("Content-Type", "application/zip")
req.add_header("Content-Length", str(size))
with urllib.request.urlopen(req, timeout=120) as resp:
    asset = json.loads(resp.read())
print("uploaded:")
print(f"  name: {asset['name']}")
print(f"  size: {asset['size']} bytes")
print(f"  url:  {asset['browser_download_url']}")