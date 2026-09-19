"""Push local HEAD to kou147258/haos-ha via GitHub REST API.

Workaround for users whose HTTPS_PROXY (or git HTTP layer) cannot
complete TLS handshake with github.com. Python urllib with no proxy
works; we build a commit object from the local tree and update the
remote ref directly.

Usage (PowerShell):
    $env:GH_TOKEN = 'ghp_...'
    python scripts/push_via_api.py
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.request


# Bypass any HTTP proxy that breaks GitHub TLS handshake.
for _k in [
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy",
]:
    os.environ.pop(_k, None)


REPO = "kou147258/haos-ha"
BRANCH = "main"
TAG = "v1.1.9"
TOKEN = os.environ.get("GH_TOKEN") or sys.exit("GH_TOKEN env var not set")


def api(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "haos-ha-push-via-api/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read()
            return resp.status, json.loads(payload.decode("utf-8"))
    except urllib.error.URLError as exc:
        # Surface the underlying errno and repr so we can tell DNS failure
        # vs proxy failure vs connection reset apart.
        raise RuntimeError(
            f"{method} {path} urlopen failed: {exc!r} "
            f"(reason={exc.reason!r})"
        ) from exc
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {body}") from exc


def git(*args):
    return subprocess.check_output(["git", *args], cwd=".").decode().strip()


def main():
    local_sha = git("rev-parse", "HEAD")
    parent_sha = git("rev-parse", "HEAD~1")
    print(f"local HEAD = {local_sha}")
    print(f"parent     = {parent_sha}")

    # Verify remote main ref points at our parent so we know what's "on top"
    # of what.
    _, ref = api("GET", f"/repos/{REPO}/git/refs/heads/{BRANCH}")
    remote_head = ref["object"]["sha"]
    print(f"remote {BRANCH} = {remote_head}")
    if remote_head != parent_sha:
        sys.exit(
            f"remote main ({remote_head}) is not our parent ({parent_sha}); "
            "fast-forward push would not apply. Refusing to force-overwrite."
        )

    # Collect files that changed vs parent and POST them as blobs.
    changed = git("diff", "--name-only", parent_sha, local_sha).splitlines()
    print(f"changed files: {changed}")
    blobs: dict[str, str] = {}
    for path in changed:
        content = open(path, "rb").read()
        # Detect text vs binary by whether decode as utf-8 round-trips.
        try:
            text = content.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = base64.b64encode(content).decode("ascii")
            encoding = "base64"
        _, blob = api(
            "POST",
            f"/repos/{REPO}/git/blobs",
            {"content": text, "encoding": encoding},
        )
        blobs[path] = blob["sha"]
        print(f"  blob {path} -> {blob['sha']}")

    # Get parent commit's tree (everything that is *not* in our diff stays
    # exactly as-is from the parent commit).
    _, parent_commit = api(
        "GET", f"/repos/{REPO}/git/commits/{parent_sha}"
    )
    parent_tree = parent_commit["tree"]["sha"]

    # Create a new tree with our diffed blobs replacing the parent's entries.
    tree_items = [
        {"path": p, "mode": "100644", "type": "blob", "sha": blobs[p]}
        for p in changed
    ]
    _, tree = api(
        "POST",
        f"/repos/{REPO}/git/trees",
        {"base_tree": parent_tree, "tree": tree_items},
    )
    print(f"new tree = {tree['sha']}")

    # Create commit object.
    _, commit = api(
        "POST",
        f"/repos/{REPO}/git/commits",
        {
            "message": git("log", "-1", "--format=%s"),
            "parents": [parent_sha],
            "tree": tree["sha"],
            "author": {
                "name": "neon9809",
                "email": "neon9809@users.noreply.github.com",
            },
        },
    )
    print(f"new commit = {commit['sha']}")

    # Update the main branch ref to point at the new commit.
    api(
        "PATCH",
        f"/repos/{REPO}/git/refs/heads/{BRANCH}",
        {"sha": commit["sha"]},
    )
    print(f"updated {BRANCH} -> {commit['sha']}")

    # Push the tag (create it on top of the new commit).
    _, _existing = api(
        "GET", f"/repos/{REPO}/git/refs/tags/{TAG}"
    ) if False else (None, None)  # ignore; we'll just POST and let it 422 if exists
    try:
        api(
            "POST",
            f"/repos/{REPO}/git/refs",
            {"ref": f"refs/tags/{TAG}", "sha": commit["sha"]},
        )
        print(f"created tag {TAG}")
    except RuntimeError as exc:
        if "422" in str(exc) and "Reference already exists" in str(exc):
            api(
                "PATCH",
                f"/repos/{REPO}/git/refs/tags/{TAG}",
                {"sha": commit["sha"]},
            )
            print(f"updated existing tag {TAG}")
        else:
            raise


if __name__ == "__main__":
    main()