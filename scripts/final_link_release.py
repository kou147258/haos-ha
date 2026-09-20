"""Final: link release 392282413 to the new annotated tag + verify everything."""
import json
import os
import urllib.request

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)

TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()


def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "final-link/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if not raw:
            return r.status, {}
        return r.status, json.loads(raw.decode("utf-8"))


def get_public(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("User-Agent", "final-link/1.0")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# 1. PATCH release: target_commitish = c5d650a (the addback commit)
status, d = api(
    "PATCH", "/repos/kou147258/haos-ha/releases/392282413",
    {"target_commitish": "c5d650a333068581056465efcac0b2831dc8aa38"},
)
print(f"PATCH release status={status}")
print(f"  tag_name:        {d['tag_name']}")
print(f"  target_commitish: {d.get('target_commitish')}")
print(f"  url:             {d['html_url']}")

# 2. Verify by re-fetching via tag
print()
print("=== v1.5.0 release resolved by tag ===")
r = get_public("/repos/kou147258/haos-ha/releases/tags/v1.5.0")
print(f"  tag_name:        {r['tag_name']}")
print(f"  target_commitish: {r.get('target_commitish')}")
print(f"  url:             {r['html_url']}")
print(f"  body_len:        {len(r['body'])}")
print(f"  assets:")
for asset in r.get("assets", []):
    print(f"    - {asset['name']:30} {asset['size']:>8} bytes  {asset['browser_download_url']}")

# 3. Verify tree at v1.5.0
print()
print("=== root tree at v1.5.0 ===")
tree = get_public("/repos/kou147258/haos-ha/git/trees/v1.5.0^{tree}")
names = [t["path"] for t in tree["tree"]]
print(f"  files: {names}")
print(f"  has haos_fb? {'haos_fb' in names}")
print(f"  has custom_components? {'custom_components' in names}")
print(f"  has CHANGELOG.md? {'CHANGELOG.md' in names}")