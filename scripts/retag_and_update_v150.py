"""Re-tag v1.5.0 to point at the addback commit + update release body + upload add-on zip."""
import base64
import io
import json
import os
import sys
import time
import urllib.request
import zipfile

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)

REPO = "kou147258/haos-ha"
OLD_TAG_SHA = "7c517616c00020fa0a919355413b23c2a0513e8b"  # tag v1.5.0 currently points at 2444b56
NEW_COMMIT = "c5d650a333068581056465efcac0b2831dc8aa38"     # the addback commit
RELEASE_ID = 392282413  # the existing release

TOKEN = open(os.path.expanduser("~/.gh_token"), encoding="utf-8-sig").read().strip()


def api(method, path, body=None, raw_data=None, raw_mime=None, max_retries=8):
    url = f"https://api.github.com{path}"
    if raw_data is not None:
        data = raw_data
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    last_exc = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "retag-v150/1.0")
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
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_exc = exc
            wait = min(2 ** attempt, 60)
            print(f"  retry {attempt + 1}/{max_retries} after {wait}s: {exc!r}", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{method} {path}: gave up after {max_retries} retries: {last_exc!r}")


def main():
    # 1. Delete the old v1.5.0 tag (currently at 7c51761...)
    print(f"deleting old tag refs/tags/v1.5.0 ({OLD_TAG_SHA})")
    status, _ = api("DELETE", f"/repos/{REPO}/git/refs/tags/v1.5.0")
    print(f"  status={status}")

    # 2. Create the new v1.5.0 tag at the addback commit
    tag_data = {
        "tag": "v1.5.0",
        "message": (
            "v1.5.0 — HACS integration + Supervisor add-on (UEFI + dGPU path)\n\n"
            "After the initial v1.5.0 (HACS-only) release, the Supervisor\n"
            "add-on was restored under a corrected hardware diagnosis:\n"
            "display-mode takeover works on HAOS, but ONLY when the host is\n"
            "booted in UEFI mode with a discrete GPU set as primary in BIOS.\n"
            "On Legacy BIOS + integrated graphics (HAOS default), the kernel's\n"
            "LSM rejects user-namespace container mmap of the efifb\n"
            "framebuffer — see README §\"Display mode — when it works\"."
        ),
        "object": NEW_COMMIT,
        "type": "commit",
        "tagger": {
            "name": "neon9809",
            "email": "neon9809@users.noreply.github.com",
        },
    }
    status, tag_resp = api("POST", f"/repos/{REPO}/git/tags", tag_data)
    print(f"created new tag v1.5.0 sha={tag_resp['sha']}")

    # 3. Update the existing release's body + target_commitish
    new_body = (
        "## HAOS Dashboard v1.5.0 — HACS integration + Supervisor add-on\n\n"
        "This release re-adds the Supervisor add-on (`haos_fb/`) that was\n"
        "removed in the first v1.5.0 cut. The add-on can drive a\n"
        "directly-attached display **on HAOS hosts that satisfy all three\n"
        "of these hardware requirements**:\n\n"
        "1. **UEFI boot mode** for HAOS. Check with\n"
        "   `cat /proc/cmdline | grep BOOT_IMAGE`. UEFI shows a path like\n"
        "   `BOOT_IMAGE=.../EFI/.../...efi`; Legacy shows\n"
        "   `BOOT_IMAGE=(hd0,gpt2)/bzImage` (GRUB syntax).\n"
        "2. **A discrete GPU** (AMD or NVIDIA). On boards that expose both\n"
        "   \"IGD\" and \"PEG\" entries, the dGPU must be PCIe-attached.\n"
        "3. **BIOS Primary Display = PEG** (or board-specific equivalent) +\n"
        "   **IGD Multi-Monitor = Disabled** if available.\n\n"
        "With all three, UEFI GOP hands the framebuffer to amdgpu\n"
        "directly:\n"
        "- `/sys/class/graphics/fb0/name` becomes `amdgpu ...` (not\n"
        "  `EFI VGA`)\n"
        "- `/dev/dri/card0` appears\n"
        "- amdgpu's fbdev emulation backs `/dev/fb0` with normal page\n"
        "  cache (no iomem, no kernel-LSM rejection)\n\n"
        "The add-on picks the render path automatically:\n"
        "- `drm_render.py` if `/dev/dri/card0` exists (preferred)\n"
        "- `fb_render.py` if `/dev/fb0` is normal page cache\n"
        "- headless PNG fallback otherwise (writes to\n"
        "  `/share/haos_fb/snapshot.png`)\n\n"
        "On **Legacy BIOS + integrated graphics** (HAOS default), the\n"
        "add-on falls back to the headless PNG output because `efifb`\n"
        "early-binds `/dev/fb0` and the kernel's LSM rejects mmap from\n"
        "inside the Supervisor add-on container. To enable the display\n"
        "in that configuration, change BIOS Boot Mode to **UEFI** +\n"
        "follow the requirements above.\n\n"
        "## Install\n\n"
        "**Integration (HACS):**\n\n"
        "1. HA → HACS → Integrations → ⋮ → Custom repositories\n"
        "2. Repository: `https://github.com/kou147258/haos-ha`,\n"
        "   Category: `Integration` → Add\n"
        "3. Search **HAOS Dashboard** → Install\n"
        "4. Settings → System → Restart Home Assistant\n\n"
        "**Display add-on (HAOS only):**\n\n"
        "1. Settings → Add-ons → Add-on Store → ⋮ → Repositories\n"
        "2. Paste `https://github.com/kou147258/haos-ha` → Add\n"
        "3. Install **HAOS Dashboard Display** (slug `haos_fb`)\n"
        "4. Configuration tab → tune options → Start\n\n"
        "## What's in this release\n\n"
        "- `custom_components/haos/` — HACS integration (system monitor\n"
        "  sensors: CPU per-core, memory, swap, disks, network,\n"
        "  temperatures, uptime, processes, hostname, OS; plus the\n"
        "  `info` sensor summarising HA Core / Supervisor / HAOS /\n"
        "  integration versions and live entity counts)\n"
        "- `haos_fb/` — Supervisor add-on (Dockerfile, build.yaml,\n"
        "  config.yaml, run.sh, fb_render.py, drm_render.py,\n"
        "  themes.py, font.py, options.example.json, run-host.sh,\n"
        "  systemd/haos_fb.service)\n"
        "- Multi-arch Docker images at\n"
        "  `ghcr.io/kou147258/haos-fb-{aarch64,amd64,armv7,armhf,i386}`\n\n"
        "## Why v1.5.0 was published twice\n\n"
        "The first v1.5.0 cut removed `haos_fb/` entirely after a series\n"
        "of add-on release attempts (v1.2.0 – v1.4.2) failed on the\n"
        "author's Legacy-BIOS test host. After publication, the user\n"
        "pointed out their hardware actually has an AMD discrete GPU,\n"
        "which the agent's diagnosis had under-weighted. The corrected\n"
        "analysis: the add-on **can** drive a display on HAOS, but only\n"
        "when the host is in UEFI mode. The tag was force-pushed to\n"
        "the addback commit (`{NEW_COMMIT[:10]}`) without renaming the\n"
        "version because the integration version (1.5.0) is unchanged.\n\n"
        "See the CHANGELOG for the full revision history."
    )
    status, rel_resp = api(
        "PATCH", f"/repos/{REPO}/releases/{RELEASE_ID}",
        {"body": new_body, "target_commitish": NEW_COMMIT},
    )
    print(f"updated release id={rel_resp['id']} tag={rel_resp['tag_name']} body_len={len(new_body)}")
    upload_url = rel_resp["upload_url"]
    if "{" in upload_url:
        upload_url = upload_url.split("{", 1)[0]

    # 4. Build haos_fb-1.5.0.zip (add-on bundle for local Supervisor install)
    src = os.path.join(os.getcwd(), "haos_fb")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, os.getcwd())
                zf.write(full, arc)
    add_on_zip = buf.getvalue()
    print(f"built haos_fb-1.5.0.zip: {len(add_on_zip)} bytes")

    # 5. Upload as release asset
    qs = "?name=haos_fb-1.5.0.zip"
    status, asset_resp = api(
        "POST",
        upload_url + qs,
        raw_data=add_on_zip,
        raw_mime="application/zip",
    )
    print(f"uploaded {asset_resp['name']} ({asset_resp['size']} bytes) id={asset_resp['id']}")
    print()
    print("DONE")


if __name__ == "__main__":
    main()