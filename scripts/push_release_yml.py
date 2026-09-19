"""Commit the .github/workflows/release.yml change and push it via API."""

import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
BRANCH = "main"

def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {body}") from exc

# Read parent (current main head)
_, ref = api("GET", f"/repos/{REPO}/git/refs/heads/{BRANCH}")
parent_sha = ref["object"]["sha"]
print(f"current {BRANCH} = {parent_sha}")

# Read parent's tree base
_, parent_commit = api("GET", f"/repos/{REPO}/git/commits/{parent_sha}")
parent_tree = parent_commit["tree"]["sha"]

# Read the release.yml file from disk and create blob
path = ".github/workflows/release.yml"
content = open(path, "rb").read()
try:
    text = content.decode("utf-8")
    encoding = "utf-8"
except UnicodeDecodeError:
    text = base64.b64encode(content).decode("ascii")
    encoding = "base64"
_, blob = api("POST", f"/repos/{REPO}/git/blobs", {"content": text, "encoding": encoding})
print(f"  blob {path} -> {blob['sha']}")

# Create tree with this single file change
_, tree = api("POST", f"/repos/{REPO}/git/trees", {
    "base_tree": parent_tree,
    "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}],
})
print(f"  tree {tree['sha']}")

# Create commit
_, commit = api("POST", f"/repos/{REPO}/git/commits", {
    "message": "ci(release): also package haos_fb/ as a Supervisor local-install zip",
    "parents": [parent_sha],
    "tree": tree["sha"],
    "author": {"name": "neon9809", "email": "neon9809@users.noreply.github.com"},
})
print(f"  commit {commit['sha']}")

# Update main ref
api("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}", {"sha": commit["sha"]})
print(f"updated {BRANCH} -> {commit['sha']}")