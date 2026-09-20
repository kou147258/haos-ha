"""Remove orphan v1.4.2 zips from v1.5.0 release."""
import json
import os
import urllib.request

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)

TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()

# v1.4.2 asset IDs that ended up in v1.5.0 release after old release deletion
ORPHAN_IDS = [
    575899476,  # haos-1.4.2.zip (from the old release)
    575937605,  # haos_fb-1.4.2.zip (from earlier upload)
]


def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "cleanup/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})


# 1. List current assets
req = urllib.request.Request("https://api.github.com/repos/kou147258/haos-ha/releases/392288408")
req.add_header("Authorization", f"Bearer {TOKEN}")
req.add_header("User-Agent", "cleanup/1.0")
with urllib.request.urlopen(req, timeout=15) as r:
    rel = json.loads(r.read())
    print(f"release id={rel['id']} tag={rel['tag_name']}")
    print("current assets:")
    for a in rel.get("assets", []):
        print(f"  - id={a['id']:>11} {a['name']:30} {a['size']:>8} bytes")

# 2. Delete orphans (anything that's not haos-1.5.0.zip or haos_fb-1.5.0.zip)
print()
print("deleting orphan assets:")
to_delete = []
for a in rel.get("assets", []):
    if a["name"] not in ("haos-1.5.0.zip", "haos_fb-1.5.0.zip"):
        to_delete.append(a)
for a in to_delete:
    print(f"  - {a['name']} (id={a['id']})")
    status, _ = api("DELETE", f"/repos/kou147258/haos-ha/releases/assets/{a['id']}")
    print(f"    status={status}")

# 3. Final state
print()
print("final state:")
req = urllib.request.Request("https://api.github.com/repos/kou147258/haos-ha/releases/392288408")
req.add_header("Authorization", f"Bearer {TOKEN}")
req.add_header("User-Agent", "cleanup/1.0")
with urllib.request.urlopen(req, timeout=15) as r:
    rel = json.loads(r.read())
    for a in rel.get("assets", []):
        print(f"  - {a['name']:30} {a['size']:>8} bytes  {a['browser_download_url']}")