"""Force-update tag v1.2.3 to current main HEAD and trigger release workflow."""

import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
TAG = "v1.2.3"

def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode()
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

# 1. Look up current main HEAD.
_, ref = api("GET", f"/repos/{REPO}/git/refs/heads/main")
new_sha = ref["object"]["sha"]
print(f"main HEAD = {new_sha}")

# 2. Update tag to point at this sha.
api("PATCH", f"/repos/{REPO}/git/refs/tags/{TAG}", {"sha": new_sha})
print(f"tag {TAG} -> {new_sha}")

# 3. Trigger release workflow.
req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/actions/workflows/release.yml/dispatches",
    method="POST",
    data=json.dumps({"ref": TAG}).encode(),
)
req.add_header("Authorization", "Bearer " + TOKEN)
req.add_header("Accept", "application/vnd.github+json")
req.add_header("X-GitHub-Api-Version", "2022-11-28")
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req, timeout=30) as resp:
    print(f"workflow triggered: {resp.status}")