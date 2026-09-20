# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-09-20

### Why this release is interesting

The release notes for v1.5.0 changed once after the tag was first
published. Originally the add-on was removed entirely (HACS-only).
After the user pointed out their hardware has an AMD discrete GPU
(`0000:01:00.0 vendor=0x1002 device=0x6778`), the add-on was restored
under a corrected diagnosis.

The fundamental finding: **the add-on can drive a directly-attached
display, but only if HAOS is booted in UEFI mode with a discrete GPU
set as primary**. On Legacy BIOS + integrated graphics (the HAOS
default), `efifb` early-binds `/dev/fb0` and the kernel's LSM
rejects mmap from inside the add-on container. On UEFI, UEFI GOP
hands the framebuffer to amdgpu directly, `efifb` never binds, and
amdgpu's fbdev emulation creates `/dev/fb0` backed by normal page
cache (no iomem, no LSM rejection). The add-on's render path picks
DRM/KMS if `/dev/dri/card0` exists, otherwise direct fb0 mmap.

### Added (restored after v1.5.0 first release)

- **`haos_fb/` Supervisor add-on** restored from v1.4.2:
  - `Dockerfile`, `config.yaml`, `build.yaml`, `run.sh`,
    `options.example.json` (add-on container image)
  - `drm_render.py` (DRM/KMS path via libdrm; chosen when
    `/dev/dri/card0` exists)
  - `fb_render.py` (direct fb0 mmap; chosen when amdgpu fbdev
    emulation provides `/dev/fb0` as normal page cache)
  - `themes.py`, `font.py` (theme palette + bitmap font fallback)
  - `run-host.sh` (host-side launcher; runs fb_render.py on a
    non-HAOS Debian host with `/dev/fb0` exposed)
  - `systemd/haos_fb.service` (host-side systemd user service unit
    for the run-host.sh path)
- **`.github/workflows/release.yml`** — multi-arch Docker build
  + GHCR push for `ghcr.io/kou147258/haos-fb-{arch}` (aarch64 /
  amd64 / armv7 / armhf / i386)
- **`.github/workflows/ci.yml`** — `verify add-on manifest
  essentials` step + `Render addon --dump-png` smoke test
- **`repository.yaml`** reverted to HA Supervisor custom-repo
  manifest (`slug: haos_fb`)
- **README §"Display mode — when it works"** — full hardware
  requirements list (UEFI + discrete GPU + BIOS=PEG), why Legacy
  BIOS + iGPU doesn't work (kernel LSM rejects iomem mmap), and
  the working-vs-not matrix across HA install types

### Changed

- README rewritten end-to-end: HACS install + add-on install +
  manual install + sensor catalog + display-mode hardware
  requirements + verified-vs-not matrix + dev workflow
- `custom_components/haos/manifest.json`: `version` `1.1.6` →
  `1.5.0`, URLs stay at `kou147258/haos-ha`
- `.gitignore` — added `.gh_token` / `gh_token*` patterns after a
  near-miss where the GitHub access token was briefly staged in a
  local commit (was caught before push; the token has never been
  on the remote, but the pattern is now ignored)

### Removed (cleanup, not rebuilt)

These were deleted in the first v1.5.0 commit and stay deleted:

- `Makefile`, `dev.py`, `PUBLISHING.md` (only existed for the
  add-on dev workflow; no users depended on them)
- 26 obsolete scripts (`scripts/check_*.py`, `verify_v1*.py`,
  `wait_*.py`, `force_push_v130.py`, `install_v130.sh`, etc.) —
  the diagnostics that proved useful are preserved in
  `scripts/host_diag_*.py` and `scripts/host_fb0_*.py`
- 4 built `haos_fb-*.zip` artifacts from the workspace root

### Added (new helpers)

- `scripts/push_whole_tree.py` — pushes local HEAD tree to remote
  via the GitHub REST API, reading blob content from the local git
  object database (works correctly when files have been deleted
  from the working copy but the deletion is recorded in the commit
  being pushed). The original `push_via_api.py` chokes on
  diffs that include deleted files.
- `scripts/tag_and_release_v150.py` — creates annotated tag +
  GitHub Release + bundles `custom_components/haos/` into
  `haos-1.5.0.zip` as a release asset.
- `scripts/retry_upload_v150_asset.py` — one-off retry of the
  release asset upload that hit a transient DNS resolution error
  on `uploads.github.com` during the first v1.5.0 release attempt.

## [1.4.2] - 2026-09-19

Last release whose add-on code shipped to GHCR (5 architecture
images). Runtime failure on HAOS x86_64 + Legacy BIOS — the add-on's
`fb_render.py` falls back to headless PNG output because
`os.open("/dev/fb0", O_RDWR)` returns `EINVAL` from inside the
container. `init:true` rejected by Supervisor (init is reserved for
ssh/terminal/portainer); rolled back to direct fb0 mmap.

## [1.1.6] - 2026-09-19

Last release whose integration code was fully functional. `requirements`
removed from `manifest.json` because the only dep (psutil) is bundled
with HA. Subsequent 1.2.x – 1.4.x bumps were display-mode-only and did
not change the integration.

---

## Earlier releases

See git history. Pre-1.5.0 tags are preserved but not documented here
because the project settled on its final shape at v1.5.0.