import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
import urllib.request, json
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
r = urllib.request.Request("https://api.github.com/repos/kou147258/haos-ha/releases/tags/v1.2.3")
r.add_header("Authorization", "Bearer " + TOKEN)
r.add_header("Accept", "application/vnd.github+json")
with urllib.request.urlopen(r, timeout=30) as resp:
    rel = json.loads(resp.read())
print("=== v1.2.3 ===")
print("published:", rel["published_at"])
for a in rel.get("assets", []):
    print(f"  {a['name']:35s}  {a['size']:6d} bytes  {a['browser_download_url']}")