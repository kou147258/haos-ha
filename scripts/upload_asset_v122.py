"""Upload haos_fb-1.2.2.zip to v1.2.2 release."""

import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
TAG = "v1.2.2"
ZIP_PATH = "haos_fb-1.2.2.zip"

# Wait briefly for the release to be created by CI, then create it manually
# if missing — we don't want to block on the CI workflow finishing before
# the user can download the add-on zip.
import time
for attempt in range(8):
    try:
        r = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")
        r.add_header("Authorization", "Bearer " + TOKEN)
        r.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(r, timeout=30) as resp:
            rel = json.loads(resp.read())
            release_id = rel["id"]
            print(f"release exists: id={release_id}  attempt={attempt}")
            break
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        print(f"release not found yet (attempt {attempt}), waiting 10s...")
        time.sleep(10)
else:
    # Create the release ourselves pointing at the tag's commit.
    r = urllib.request.Request(f"https://api.github.com/repos/{REPO}/git/refs/tags/{TAG}")
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(r, timeout=30) as resp:
        tag_ref = json.loads(resp.read())
    target_sha = tag_ref["object"]["sha"]
    r = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases",
                               method="POST",
                               data=json.dumps({
                                   "tag_name": TAG,
                                   "target_commitish": target_sha,
                                   "name": TAG,
                                   "body": "Auto-created fallback release for ad-hoc zip upload.",
                                   "draft": False,
                                   "prerelease": False,
                               }).encode())
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("X-GitHub-Api-Version", "2022-11-28")
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=30) as resp:
        rel = json.loads(resp.read())
    release_id = rel["id"]
    print(f"created release: id={release_id}")

# Upload the asset.
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