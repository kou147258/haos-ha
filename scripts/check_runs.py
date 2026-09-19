import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
r = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=5")
r.add_header("Authorization", "Bearer " + TOKEN)
r.add_header("Accept", "application/vnd.github+json")
r.add_header("X-GitHub-Api-Version", "2022-11-28")
with urllib.request.urlopen(r, timeout=30) as resp:
    runs = json.loads(resp.read())["workflow_runs"]
for run in runs[:5]:
    created = run["created_at"]
    name = run["name"]
    status = run["status"]
    conclusion = run["conclusion"]
    event = run["event"]
    head_branch = run["head_branch"]
    print(f"{created}  {name}  status={status}  conclusion={conclusion}  event={event}  branch={head_branch}")