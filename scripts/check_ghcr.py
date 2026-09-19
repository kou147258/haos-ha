import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = (
    os.environ.get("GH_TOKEN")
    or os.environ.get("GITHUB_TOKEN")
    or open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
)
for pkg in ["aarch64", "amd64", "armv7", "armhf", "i386"]:
    r = urllib.request.Request(
        f"https://api.github.com/users/kou147258/packages/container/haos-fb-{pkg}/versions?per_page=4"
    )
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(r, timeout=30) as resp:
        v = json.loads(resp.read())
    versions = [(ver["metadata"]["container"]["tags"], ver["created_at"]) for ver in v]
    print(f"{pkg}:")
    for tags, ts in versions:
        print(f"  {ts}  tags={tags}")