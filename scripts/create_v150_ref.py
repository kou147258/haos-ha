"""Create refs/tags/v1.5.0 → commit c5d650a + try upload again."""
import json
import os
import time
import urllib.request

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)

REPO = "kou147258/haos-ha"
NEW_COMMIT = "c5d650a333068581056465efcac0b2831dc8aa38"
TAG = "v1.5.0"
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()


def api(method, path, body=None, max_retries=8):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    last_exc = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "create-ref-v150/1.0")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                if not raw:
                    return resp.status, {}
                return resp.status, json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"{method} {path} -> {exc.code}: {body_text}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_exc = exc
            wait = min(2 ** attempt, 60)
            print(f"  retry {attempt + 1}/{max_retries} after {wait}s: {exc!r}", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{method} {path}: gave up: {last_exc!r}")


# 1. Create refs/tags/v1.5.0 → commit c5d650a (lightweight-style, pointing at commit)
status, ref = api(
    "POST", f"/repos/{REPO}/git/refs",
    {"ref": f"refs/tags/{TAG}", "sha": NEW_COMMIT},
)
print(f"created ref status={status} sha={ref.get('object', {}).get('sha')}")

# 2. Verify
status, head_ref = api("GET", f"/repos/{REPO}/git/refs/tags/{TAG}")
print(f"verified {TAG} → {head_ref.get('object', {}).get('sha')}")