"""Final state check for v1.5.0."""
import json
import os
import urllib.request

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)


def get(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("User-Agent", "final-check")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


print("=== final state ===")
tags = get("/repos/kou147258/haos-ha/tags?per_page=5")
for t in tags[:5]:
    print(f"  tag {t['name']} -> {t['commit']['sha'][:16]}")

print()
print("=== v1.5.0 release ===")
r = get("/repos/kou147258/haos-ha/releases/tags/v1.5.0")
print(f"  tag_name:        {r['tag_name']}")
print(f"  name:            {r['name']}")
print(f"  target_commitish: {r['target_commitish']}")
print(f"  published_at:    {r['published_at']}")
print(f"  url:             {r['html_url']}")
print(f"  body len:        {len(r['body'])}")
print(f"  body (first 500):")
for line in r["body"][:500].splitlines():
    print(f"    {line}")
print()
print(f"  assets:")
for a in r.get("assets", []):
    print(f"    - {a['name']:30} {a['size']:>8} bytes  {a['browser_download_url']}")

print()
print("=== root tree at v1.5.0 ===")
tree = get("/repos/kou147258/haos-ha/git/trees/v1.5.0^{tree}")
names = [t["path"] for t in tree["tree"]]
print(f"  files: {names}")
print(f"  has haos_fb? {'haos_fb' in names}")