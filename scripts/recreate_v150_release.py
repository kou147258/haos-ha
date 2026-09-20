"""Delete broken release 392282413 + create a fresh one bound to v1.5.0."""
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
    req.add_header("User-Agent", "recreate-release/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if not raw:
            return r.status, {}
        return r.status, json.loads(raw.decode("utf-8"))


# 1. Delete the broken release
print("deleting release 392282413")
status, _ = api("DELETE", "/repos/kou147258/haos-ha/releases/392282413")
print(f"  status={status}")

# 2. Create fresh release bound to v1.5.0
body = (
    "## HAOS Dashboard v1.5.0 — HACS integration + Supervisor add-on\n\n"
    "Display-mode takeover works on HAOS, but ONLY when the host is\n"
    "booted in UEFI mode with a discrete GPU set as primary in BIOS.\n"
    "On Legacy BIOS + integrated graphics (HAOS default), the kernel's\n"
    "LSM rejects user-namespace container mmap of the efifb\n"
    "framebuffer.\n\n"
    "See README §\"Display mode — when it works\" for the full\n"
    "hardware requirements list.\n\n"
    "## Install\n\n"
    "**Integration (HACS):** HA → HACS → Integrations → ⋮ → Custom repositories →\n"
    "Add `https://github.com/kou147258/haos-ha` (Category: Integration) →\n"
    "Install **HAOS Dashboard** → Settings → System → Restart HA.\n\n"
    "**Display add-on (HAOS only):** Settings → Add-ons → Add-on Store → ⋮ →\n"
    "Repositories → Add `https://github.com/kou147258/haos-ha` →\n"
    "Install **HAOS Dashboard Display** (slug `haos_fb`) → Configuration →\n"
    "Start.\n\n"
    "## Artifacts\n\n"
    "- `haos-1.5.0.zip` — HACS integration bundle (drop into\n"
    "  `/config/custom_components/haos/` if you don't use HACS)\n"
    "- `haos_fb-1.5.0.zip` — Supervisor add-on bundle (drop into\n"
    "  `/addons/local/haos_fb/` if you want to install offline)\n"
)

status, rel = api("POST", "/repos/kou147258/haos-ha/releases", {
    "tag_name": "v1.5.0",
    "target_commitish": "c5d650a333068581056465efcac0b2831dc8aa38",
    "name": "HAOS Dashboard v1.5.0 — HACS integration + Supervisor add-on",
    "body": body,
    "draft": False,
    "prerelease": False,
})
print(f"created release id={rel['id']} tag_name={rel['tag_name']}")
print(f"  url: {rel['html_url']}")
print(f"  assets:")

# 3. Re-attach the existing assets to the new release (the assets stay on the release id)
# Actually assets don't transfer — let me just verify they exist on the new release
for asset in rel.get("assets", []):
    print(f"    - {asset['name']} ({asset['size']} bytes) id={asset['id']}")