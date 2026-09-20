# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-09-20

### Removed

- **Supervisor add-on (`haos_fb/`) entirely removed.** The companion
  `/dev/fb0` display renderer is no longer shipped as a HA add-on. The
  attempt to make it work on HAOS x86_64 hit two walls that proved
  structurally unfixable from inside a Supervisor add-on container:

  1. The kernel's LSM rejects user-namespace container `mmap(2)` of the
     efifb framebuffer (`EINVAL`), regardless of capabilities,
     `privileged: true`, `host_network`, `host_pid`, `init: true`, or
     `SYS_RAWIO`.
  2. On Legacy BIOS HAOS, `amdgpu` never claims `/dev/fb0` because
     `efifb` early-binds it; the kernel cmdline is locked and `/sys` is
     read-only in containers, so we can't force `amdgpu.modeset=1` or
     unbind efifb from inside the container.

  See README §"Display mode — why it's gone" for the full diagnosis.
  The pre-removal code (including the `fb_render.py` / themes / fonts
  from the original [neon9809/haos](https://github.com/neon9809/haos)
  project) is preserved in git history through tag `v1.4.2`.

- **`.github/workflows/release.yml` simplified** to drop multi-arch
  Docker build + GHCR push. Release artifact is now only the HACS
  integration zip (`haos-1.5.0.zip`).

- **Debug scripts** (`scripts/check_*.py`, `scripts/verify_v1*.py`,
  `scripts/wait_*.py`, `scripts/force_push_v130.py`,
  `scripts/install_v130.sh`, etc.) removed. The diagnostic scripts that
  documented the display-mode failure
  (`scripts/host_diag_*.py`, `scripts/host_fb0_*.py`) and the
  SSL-bypass force-push helper (`scripts/push_via_api.py`) are kept
  as historical record.

- **`Makefile`, `dev.py`, `PUBLISHING.md`** removed (they only existed
  for the display-mode add-on).

### Changed

- `custom_components/haos/manifest.json`: `version` bumped `1.1.6` →
  `1.5.0`. `documentation` and `issue_tracker` URLs point to
  `kou147258/haos-ha` (the user-owned fork that actually hosts the
  release).
- `repository.yaml` rewritten as a HACS default-repo manifest (the
  previous form was a Supervisor add-on repo manifest).
- `README.md` rewritten end-to-end: HACS-only install, system-monitor
  sensor catalog, full explanation of why display mode is gone,
  working-vs-not matrix across HA install types, version history
  pointing to git history for the removed code.

### Preserved (with caveats documented)

- `binary_sensor.display_running` — retained for backwards
  compatibility; reports `off` (no add-on to track).
- `switch.display_enabled` — retained; switching has no effect.
- `haos.refresh_display` service — retained as a no-op.
- The integration-side reference to `ADDON_SLUG = "haos_fb"` stays so
  these compat entities / services don't churn.

## [1.4.2] - 2026-09-19

Last release that still shipped the Supervisor add-on. Known runtime
failure on HAOS x86_64 + Legacy BIOS — the add-on's `fb_render.py`
falls back to headless PNG output (`/share/haos_fb/snapshot.png`)
because `os.open("/dev/fb0", O_RDWR)` returns `EINVAL` from inside the
container.

## [1.1.6] - 2026-09-19

Last release whose integration code was fully functional. `requirements`
removed from `manifest.json` because the only dep (psutil) is bundled
with HA. Subsequent 1.2.x – 1.4.x bumps were display-mode-only and did
not change the integration.

---

## Earlier releases

See git history. Pre-1.5.0 tags are preserved but not documented here
because the project pivoted away from the display-mode add-on at
v1.5.0.