#!/usr/bin/env python3
"""Push local HEAD tree to remote by extracting files from git objects.

Reads blobs from the local git object database (not from the working
copy), so it works correctly even after files have been deleted from
the working tree but the deletion is staged in the commit we want to
push.

Usage (PowerShell):
    python scripts/push_whole_tree.py
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request

# Bypass proxy that breaks GitHub TLS handshake.
for _k in [
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy",
]:
    os.environ.pop(_k, None)

REPO = "kou147258/haos-ha"
BRANCH = "main"
TOKEN = (
    os.environ.get("GH_TOKEN")
    or os.environ.get("GITHUB_TOKEN")
    or open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()
)
if not TOKEN:
    sys.exit("GH_TOKEN env var not set (also tried GITHUB_TOKEN and ~/.gh_token)")


def api(method, path, body=None, max_retries=8):
    """API call with retry on transient network errors.

    Retries on RemoteDisconnected, URLError, TimeoutError — these are
    GitHub's load balancer occasionally dropping idle connections.
    Exponential backoff: 2s, 4s, 8s, 16s, 32s, capped at 60s.
    """
    url = f"https://api.github.com{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    last_exc = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "haos-ha-push-whole-tree/2.0")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"{method} {path} -> {exc.code}: {body}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_exc = exc
            wait = min(2 ** attempt, 60)
            print(f"  retry {attempt + 1}/{max_retries} after {wait}s: {exc!r}", flush=True)
            import time as _t
            _t.sleep(wait)
    raise RuntimeError(f"{method} {path}: gave up after {max_retries} retries: {last_exc!r}")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=".").decode().strip()


def git_blob_sha(path: str) -> str:
    """Return the git blob sha for ``path`` at HEAD."""
    return subprocess.check_output(
        ["git", "rev-parse", f"HEAD:{path}"], cwd="."
    ).decode().strip()


def git_blob_content(blob_sha: str) -> bytes:
    """Return raw bytes of a git blob."""
    return subprocess.check_output(
        ["git", "cat-file", "-p", blob_sha], cwd="."
    )


def git_tree_files(tree_sha: str, prefix: str = "") -> list[tuple[str, str]]:
    """Recursively list (path, blob_sha) for every file in ``tree_sha``.

    Skips submodules (mode 160000) because we don't push those.
    """
    out = []
    raw = subprocess.check_output(
        ["git", "cat-file", "-p", tree_sha], cwd="."
    ).decode("utf-8", errors="replace")
    for line in raw.splitlines():
        # Format: "<mode> <type> <sha>\t<name>"
        meta, _, name = line.partition("\t")
        parts = meta.split(" ", 2)
        if len(parts) != 3:
            continue
        mode, obj_type, obj_sha = parts
        path = f"{prefix}{name}"
        if obj_type == "blob":
            out.append((path, obj_sha))
        elif obj_type == "tree":
            out.extend(git_tree_files(obj_sha, prefix=f"{path}/"))
        # skip submodules
    return out


def main():
    local_head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD~1")
    print(f"local HEAD = {local_head}")
    print(f"parent     = {parent}")

    _, remote_ref = api("GET", f"/repos/{REPO}/git/refs/heads/{BRANCH}")
    remote_head = remote_ref["object"]["sha"]
    print(f"remote {BRANCH} = {remote_head}")

    base_sha = remote_head if remote_head != parent else parent
    print(f"base for new commit = {base_sha}")

    # 1. Enumerate every file in the local HEAD tree.
    local_tree_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd="."
    ).decode().strip()
    print(f"local HEAD tree = {local_tree_sha}")

    files = git_tree_files(local_tree_sha)
    print(f"file count = {len(files)}")

    # 2. POST every blob (text → utf-8, binary → base64).
    blobs: dict[str, str] = {}
    for i, (path, blob_sha) in enumerate(files, 1):
        content = git_blob_content(blob_sha)
        try:
            text = content.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = base64.b64encode(content).decode("ascii")
            encoding = "base64"
        _, posted = api(
            "POST", f"/repos/{REPO}/git/blobs",
            {"content": text, "encoding": encoding},
        )
        blobs[path] = posted["sha"]
        if i % 10 == 0 or i == len(files):
            print(f"  blob {i}/{len(files)}: {path} -> {posted['sha']}")

    # 3. POST a tree that mirrors the local tree exactly.
    tree_items = [
        {"path": p, "mode": "100644", "type": "blob", "sha": blobs[p]}
        for p, _ in files
    ]
    _, new_tree = api(
        "POST", f"/repos/{REPO}/git/trees",
        {"base_tree": base_sha + "^{tree}", "tree": tree_items} if False else
        # base_tree is informational; we list every file explicitly so the
        # remote tree ends up identical to local HEAD's tree.
        {"tree": tree_items},
    )
    print(f"new tree = {new_tree['sha']}")

    # 4. POST the commit.
    _, new_commit = api(
        "POST", f"/repos/{REPO}/git/commits",
        {
            "message": git("log", "-1", "--format=%s"),
            "parents": [base_sha],
            "tree": new_tree["sha"],
            "author": {
                "name": "neon9809",
                "email": "neon9809@users.noreply.github.com",
            },
        },
    )
    print(f"new commit = {new_commit['sha']}")

    # 5. Fast-forward main.
    api(
        "PATCH",
        f"/repos/{REPO}/git/refs/heads/{BRANCH}",
        {"sha": new_commit["sha"]},
    )
    print(f"updated {BRANCH} -> {new_commit['sha']}")


if __name__ == "__main__":
    main()