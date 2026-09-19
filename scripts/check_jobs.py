import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
r = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=10")
r.add_header("Authorization", "Bearer " + TOKEN)
r.add_header("Accept", "application/vnd.github+json")
r.add_header("X-GitHub-Api-Version", "2022-11-28")
with urllib.request.urlopen(r, timeout=30) as resp:
    runs = json.loads(resp.read())["workflow_runs"]
for run in runs:
    if (run["name"] == "Release" and run["head_branch"] == "v1.2.1"
            and run["event"] == "workflow_dispatch"):
        run_id = run["id"]
        print(f"run_id={run_id} status={run['status']} conclusion={run['conclusion']}")
        r2 = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs")
        r2.add_header("Authorization", "Bearer " + TOKEN)
        r2.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(r2, timeout=30) as resp2:
            jobs = json.loads(resp2.read())["jobs"]
        for j in jobs:
            print(f"  {j['name']}: status={j['status']}  conclusion={j['conclusion']}")
        break