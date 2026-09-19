import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json, time
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
TAG = "v1.2.3"

# Find the latest release run.
def api(method, path):
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

# Poll for the v1.2.3 release workflow run.
run_id = None
for attempt in range(30):
    runs = api("GET", f"/repos/{REPO}/actions/runs?per_page=20")["workflow_runs"]
    for r in runs:
        if (r["name"] == "Release" and r["head_branch"] == TAG
                and r["event"] == "workflow_dispatch"):
            run_id = r["id"]
            print(f"found run {run_id} status={r['status']} conclusion={r['conclusion']}")
            break
    if run_id:
        break
    time.sleep(2)

if not run_id:
    print("could not find v1.2.3 release run")
    raise SystemExit(1)

# Poll until completion.
while True:
    r = api("GET", f"/repos/{REPO}/actions/runs/{run_id}")
    status = r["status"]
    conclusion = r["conclusion"]
    print(f"  {status} {conclusion}  url={r['html_url']}")
    if status == "completed":
        break
    time.sleep(15)

# Print job summary.
jobs = api("GET", f"/repos/{REPO}/actions/runs/{run_id}/jobs")["jobs"]
for j in jobs:
    print(f"  job: {j['name']}  {j['status']} {j['conclusion']}")
if conclusion != "success":
    raise SystemExit(2)