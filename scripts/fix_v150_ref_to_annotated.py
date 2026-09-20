"""Repoint refs/tags/v1.5.0 to the annotated tag object (31d39c0c) so release system re-links."""
import json
import os
import urllib.request

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)

TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
REPO = "kou147258/haos-ha"
ANNOTATED_TAG_SHA = "31d39c0cc971deb5726d5673c676df7445ffafb4"  # the annotated tag object


def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "fix-ref/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            if not raw:
                return r.status, {}
            try:
                return r.status, json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return r.status, raw
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {body}") from exc


# 0. Try the GET first to see what the API returns now
import urllib.error
try:
    status, current = api("GET", f"/repos/{REPO}/git/refs/tags/v1.5.0")
    print(f"GET refs/tags/v1.5.0: status={status}")
    if isinstance(current, dict):
        print(f"  current target: {current.get('object', {}).get('sha')}")
except urllib.error.HTTPError as exc:
    print(f"GET err: {exc.code}")
print()

# 1. Delete the lightweight ref
print(f"deleting refs/tags/v1.5.0 (lightweight ref)")
status, _ = api("DELETE", f"/repos/{REPO}/git/refs/tags/v1.5.0")
print(f"  status={status}")

# 2. Create a new ref pointing at the annotated tag object
print(f"creating refs/tags/v1.5.0 -> {ANNOTATED_TAG_SHA}")
status, ref = api(
    "POST", f"/repos/{REPO}/git/refs",
    {"ref": "refs/tags/v1.5.0", "sha": ANNOTATED_TAG_SHA},
)
print(f"  status={status} object={ref.get('object', {}).get('sha')}")

# 3. Verify the release now resolves
print()
print("verifying release by tag...")
status, rel = api("GET", f"/repos/{REPO}/releases/tags/v1.5.0")
print(f"  release tag_name={rel['tag_name']} target={rel.get('target_commitish')}")
print(f"  url={rel['html_url']}")
print(f"  assets:")
for a in rel.get("assets", []):
    print(f"    - {a['name']} ({a['size']} bytes)")