"""Tag v1.5.0 + create GitHub release + upload haos-1.5.0.zip."""
import base64
import io
import json
import os
import sys
import urllib.request
import zipfile

for _k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(_k, None)

REPO = "kou147258/haos-ha"
COMMIT = "2444b5618daa098f6e040ec9ac2ef8ea640ea365"
VERSION = "1.5.0"
TAG = f"v{VERSION}"
TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()


def api(method, path, body=None, raw_data=None, raw_mime=None):
    url = f"https://api.github.com{path}"
    if raw_data is not None:
        data = raw_data
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "tag-and-release/1.0")
    if raw_mime is not None:
        req.add_header("Content-Type", raw_mime)
    elif body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, {}
            try:
                return resp.status, json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {body_text}") from exc


def main():
    # 1. Create tag
    tag_data = {
        "tag": TAG,
        "message": (
            f"{TAG} — drop the /dev/fb0 display add-on (HACS integration only)\n\n"
            "Display takeover via a Supervisor add-on proved structurally "
            "infeasible on HAOS x86_64 + Legacy BIOS (kernel LSM rejects "
            "userns container mmap of efifb; amdgpu never claims /dev/fb0 "
            "because efifb early-binds it; /sys read-only prevents kbf-"
            "mode unbind from inside the container). The /dev/fb0 renderer "
            "code is preserved in git history through tag v1.4.2.\n\n"
            "This release ships the HACS integration only."
        ),
        "object": COMMIT,
        "type": "commit",
        "tagger": {
            "name": "neon9809",
            "email": "neon9809@users.noreply.github.com",
        },
    }
    status, tag_resp = api("POST", "/repos/{}/git/tags".format(REPO), tag_data)
    print(f"created tag {TAG} sha={tag_resp.get('sha', '?')}")

    # 2. Create release pointing at the tag
    release_body = (
        "## HAOS Dashboard v1.5.0 — HACS integration only\n\n"
        "The display add-on (`haos_fb/`) has been removed from this release "
        "because the attempt to make `/dev/fb0` mmap work from inside a "
        "Supervisor add-on container hit two walls that proved structurally "
        "unfixable on HAOS x86_64 + Legacy BIOS:\n\n"
        "1. The kernel's LSM rejects user-namespace container `mmap(2)` of "
        "the efifb framebuffer (`EINVAL`), regardless of capabilities, "
        "`privileged: true`, `host_network`, `host_pid`, `init: true`, or "
        "`SYS_RAWIO`.\n"
        "2. On Legacy BIOS HAOS, `amdgpu` never claims `/dev/fb0` because "
        "`efifb` early-binds it; the kernel cmdline is locked and `/sys` "
        "is read-only in containers, so we can't force `amdgpu.modeset=1` "
        "or unbind efifb from inside the container.\n\n"
        "See the README §\"Display mode — why it's gone\" for the full "
        "diagnosis. The pre-removal renderer code (including the original "
        "[neon9809/haos](https://github.com/neon9809/haos) `fb_render.py` "
        "and themes) is preserved in git history through tag `v1.4.2`.\n\n"
        "## What still works\n\n"
        "The HACS-installable `haos` integration is unchanged from v1.1.6 "
        "and provides full HAOS host system monitoring:\n\n"
        "- CPU per-core + load + frequency + temperature\n"
        "- Memory / Swap (GB)\n"
        "- Disks (one set per mount, GB)\n"
        "- Network (rates + cumulative bytes, MB / MB-s)\n"
        "- psutil temperature sensors\n"
        "- Uptime, processes, hostname, OS\n"
        "- `sensor.haos_info` summarising HA Core / Supervisor / HAOS /\n"
        "  integration versions and live entity counts\n\n"
        "## Install\n\n"
        "**Via HACS:**\n\n"
        "1. HA → HACS → Integrations → ⋮ → Custom repositories\n"
        "2. Repository: `https://github.com/kou147258/haos-ha`\n"
        "   Category: `Integration` → Add\n"
        "3. Search **HAOS Dashboard** → Install\n"
        "4. Settings → System → Restart Home Assistant\n\n"
        "**Manual:** download `haos-1.5.0.zip` from this release, unzip to "
        "get `haos/`, copy to `/config/custom_components/haos/`, restart.\n"
    )
    rel_data = {
        "tag_name": TAG,
        "target_commitish": COMMIT,
        "name": f"HAOS Dashboard {TAG} — HACS integration only",
        "body": release_body,
        "draft": False,
        "prerelease": False,
    }
    status, rel_resp = api("POST", "/repos/{}/releases".format(REPO), rel_data)
    print(f"created release {rel_resp.get('tag_name')} id={rel_resp.get('id')}")
    upload_url = rel_resp["upload_url"]
    # upload_url has '{?name,label}' template suffix
    if "{" in upload_url:
        upload_url = upload_url.split("{", 1)[0]

    # 3. Build haos-1.5.0.zip
    src = os.path.join(os.getcwd(), "custom_components", "haos")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, os.path.join(os.getcwd(), "custom_components"))
                zf.write(full, arc)
    zip_bytes = buf.getvalue()
    print(f"built haos-{VERSION}.zip: {len(zip_bytes)} bytes")

    # 4. Upload zip as release asset
    asset_name = f"haos-{VERSION}.zip"
    qs = "?name={}".format(asset_name)
    status, asset_resp = api(
        "POST",
        upload_url + qs,
        raw_data=zip_bytes,
        raw_mime="application/zip",
    )
    print(f"uploaded asset {asset_resp.get('name')} ({asset_resp.get('size')} bytes) id={asset_resp.get('id')}")
    print()
    print("DONE")


if __name__ == "__main__":
    main()