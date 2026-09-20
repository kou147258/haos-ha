"""Force-push v1.3.0 commit to main + update tag + trigger release."""
import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json, base64, subprocess
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"

local = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
parent = subprocess.check_output(["git", "rev-parse", "HEAD~1"]).decode().strip()
print(f"local = {local}")
print(f"parent = {parent}")

# Look up remote main.
r = urllib.request.Request(f"https://api.github.com/repos/{REPO}/git/refs/heads/main")
r.add_header("Authorization", "Bearer " + TOKEN)
r.add_header("Accept", "application/vnd.github+json")
r.add_header("X-GitHub-Api-Version", "2022-11-28")
with urllib.request.urlopen(r, timeout=30) as resp:
    remote = json.loads(resp.read())["object"]["sha"]
print(f"remote = {remote}")

if remote == local:
    print("remote already at local HEAD")
    exit(0)


def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"{method} {path} -> {exc.code}: {exc.read().decode()}"
        ) from exc


# Get base tree from remote.
_, pc = api("GET", f"/repos/{REPO}/git/commits/{remote}")
base_tree = pc["tree"]["sha"]

# Push all changed files as blobs.
changed = subprocess.check_output(
    ["git", "diff", "--name-only", parent, local]
).decode().splitlines()
print(f"changed: {changed}")
blobs = {}
for path in changed:
    content = open(path, "rb").read()
    try:
        text = content.decode("utf-8")
        enc = "utf-8"
    except UnicodeDecodeError:
        text = base64.b64encode(content).decode("ascii")
        enc = "base64"
    _, b = api("POST", f"/repos/{REPO}/git/blobs",
               {"content": text, "encoding": enc})
    blobs[path] = b["sha"]
    print(f"  blob {path} -> {b['sha']}")

# New tree.
_, tree = api(
    "POST", f"/repos/{REPO}/git/trees",
    {
        "base_tree": base_tree,
        "tree": [{"path": p, "mode": "100644", "type": "blob", "sha": blobs[p]}
                 for p in changed],
    },
)
print(f"new tree {tree['sha']}")

# New commit (re-rooted on remote main).
_, commit = api(
    "POST", f"/repos/{REPO}/git/commits",
    {
        "message": subprocess.check_output(
            ["git", "log", "-1", "--format=%s"]
        ).decode().strip(),
        "parents": [remote],
        "tree": tree["sha"],
        "author": {
            "name": "neon9809",
            "email": "neon9809@users.noreply.github.com",
        },
    },
)
print(f"new commit {commit['sha']}")

# Update main ref.
api("PATCH", f"/repos/{REPO}/git/refs/heads/main", {"sha": commit["sha"]})
print(f"main -> {commit['sha']}")

# Update v1.3.0 tag.
api("PATCH", f"/repos/{REPO}/git/refs/tags/v1.3.0", {"sha": commit["sha"]})
print(f"tag v1.3.0 -> {commit['sha']}")

# Trigger release workflow.
req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/actions/workflows/release.yml/dispatches",
    method="POST",
    data=json.dumps({"ref": "v1.3.0"}).encode(),
)
req.add_header("Authorization", "Bearer " + TOKEN)
req.add_header("Accept", "application/vnd.github+json")
req.add_header("X-GitHub-Api-Version", "2022-11-28")
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req, timeout=30) as resp:
    print(f"workflow triggered: {resp.status}")