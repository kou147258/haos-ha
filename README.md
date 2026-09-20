# HAOS Dashboard — Home Assistant edition

A HACS-installable Home Assistant integration that exposes **HAOS host
system stats** (CPU per-core, memory, swap, disks, network, temperatures,
uptime, processes, hostname, OS) as sensor entities — plus an `info`
sensor summarising HA Core / Supervisor / HAOS / integration versions
and live entity counts.

Derived from [neon9809/haos](https://github.com/neon9809/haos).
The fnOS-specific parts (FPK packaging, udev rules, CGI gateway,
`/vol*` detection, `.neon-dash` module system) have been removed.


<details>
<summary><strong>📖 语言 / Language — 点击展开中文 / Click to expand Chinese</strong></summary>


HACS 可装的 Home Assistant 集成，把 **HAOS 主机系统状态**（CPU 每核、内存、
Swap、磁盘、网络、温度、启动时间、进程数、主机名、OS）暴露成 sensor
实体——外加一个 `info` sensor 汇总 HA Core / Supervisor / HAOS / 集成版本
和实时 entity 数量。

源自 [neon9809/haos](https://github.com/neon9809/haos)，已删除 fnOS 特有
部分（FPK 打包、udev 规则、CGI 网关、`/vol*` 探测、`.neon-dash` 模块系统）。

</details>

---

## Quick start

### A. HACS Custom Repository (recommended)

1. HA → **HACS** → **Integrations** → top-right ⋮ → **Custom repositories**
2. Repository: `https://github.com/kou147258/haos-ha`
   Category: `Integration` → **Add**
3. Back to HACS → Integrations → search **HAOS Dashboard** → **Install**
4. **Settings → System → Restart Home Assistant** (HACS doesn't auto-restart)

### C. Manual install (no HACS, offline-friendly)

1. Download `haos-1.5.0.zip` from
   [Releases](https://github.com/kou147258/haos-ha/releases)
2. Unzip to get a `haos/` folder
3. Copy to `/config/custom_components/haos/` (use **Samba share**,
   **Studio Code Server**, or `scp` from the SSH/Terminal add-on)
4. Restart HA

---

## What you get

After install you'll see one device `HAOS Dashboard` with:

### Sensors (`sensor.haos_*`)

- `cpu_usage` (overall %), `cpu_core_<n>` (one per logical core),
  `cpu_load_1_min`, `cpu_frequency` (MHz), `cpu_temperature` (°C / °F)
- `memory_usage` / `_used` / `_total` / `_available` (GB)
- `swap_usage` / `_used` / `_total` (GB)
- `network_upload` / `_download` (MB/s), `network_bytes_sent` /
  `_bytes_received` (MB cumulative)
- `disk_<mount>_percent` / `_used` / `_free` / `_total` (one set per mount,
  sizes in GB)
- `temperature_<label>` (one per psutil probe; duplicates distinguished
  by index)
- `uptime`, `processes`, `hostname`, `operating_system`
- `info` — short state `"<HA Core> · <install type> · <entity count>
  entities"`. Full attrs include `ha_core_version`,
  `ha_installation_type`, `ha_arch`, `ha_python_version`,
  `ha_time_zone`, `ha_location_name`, `hassio` (bool),
  `supervisor_version` / `supervisor_healthy` /
  `supervisor_update_available`, `haos_version` / `haos_board`,
  `integration_version` / `integration_loaded_at` /
  `integration_last_refresh`, `addon_slug` / `addon_version` /
  `addon_state`, `entity_count` / `device_count` / `integration_count`.

On **HA Container / HA Core** (no Supervisor): all `supervisor_*` /
`haos_*` / `addon_*` fields are filtered out — that's expected, not a
bug.

### Binary sensor + switch

- `binary_sensor.display_running` — was meant to track the (now-removed)
  display add-on. Remains for backwards compatibility; reports `off`.
- `switch.display_enabled` — start/stop the (now-removed) display add-on
  via Supervisor API. Remains for backwards compatibility; switching has
  no effect.

### Options

Settings → Devices & Services → **HAOS Dashboard** → **Configure**:

- **Refresh interval** — 1–30 s (default 2 s)
- **Temperature unit** — `C` / `F` (default `C`)

### Services

- `haos.refresh_display` — formerly nudged the renderer; remains as a
  no-op for backwards compatibility.
- `haos.reload_themes` — reload integration options

---

## Display mode — why it's gone

Originally this repo shipped a Supervisor add-on that rendered the
sensor data directly to `/dev/fb0` (HDMI / VGA / DSI panel) using the
[neon9809/haos](https://github.com/neon9809/haos) `fb_render.py`. We
attempted to ship it on HAOS x86_64 through 4 release iterations
(v1.2.0 – v1.4.2). Every attempt hit one of two structurally
unfixable walls:

### Wall 1 — kernel LSM rejects container-side mmap of efifb

`/dev/fb0` on HAOS x86_64 is owned by the `efi-framebuffer` driver
(efifb), which reserves iomem at physical address `0xe0000000` very
early in kernel boot (~0.6 s after boot). Any `mmap(2)` from inside a
Supervisor add-on container returns `EINVAL` because Linux 6.x LSM
rejects user-namespace container access to iomem-mapped pages —
regardless of capabilities, `privileged: true`, `host_network`,
`host_pid`, `init: true`, or `SYS_RAWIO`.

### Wall 2 — amdgpu never claims `/dev/fb0` on Legacy BIOS HAOS

On HAOS x86_64 with **Legacy BIOS** and the default kernel cmdline
(`console=tty0` with no `amdgpu.fbdev=1` or `nomodeset`):

1. `efifb` early-binds `/dev/fb0` at 0xe0000000
2. `amdgpu` loads later and sees the fb slot is taken, falls back to
   `modeset=0`
3. Without modeset, amdgpu never calls `drm_dev_register()`, so
   `/dev/dri/cardX` is never created (`ls /dev/dri/` is empty even
   though `lsmod` shows amdgpu is loaded)
5. `/sys/module/amdgpu/parameters/fbdev` is **not present** — the HAOS
   generic kernel was built without `CONFIG_DRM_FBDEV_EMULATION=y`, so
   the fbdev takeover path is structurally unavailable

### Software escape routes — all blocked by HAOS

| Attempt | Result | Why it fails |
|---|---|---|
| `modprobe -r efifb` | `modprobe: can't change directory to '/lib/modules': No such file or directory` | HAOS kernel modules are built-in; no `/lib/modules` |
| Write `/sys/module/amdgpu/parameters/modeset =1` | `EROFS` (Read-only file system) | `/sys` mounted read-only in every container |
| Write `/sys/bus/platform/drivers/efi-framebuffer/unbind` | `EROFS` | Same |
| Bind mount `/sys` read-write in a privileged container | `docker: read-only mount` | `/sys` is from host kernel, not bind-mountable |
| Switch to UEFI and add `amdgpu.fbdev=1` to cmdline | requires editing `/boot/cmdline.gz` | HAOS boot partition is read-only |
| BIOS → Primary Display = PEG + IGD = Disabled | (you already changed Primary Display to PEG; IGD disable was missing) | On Legacy BIOS, PEG alone doesn't fully release the framebuffer from efifb |

The **only** remaining fix is **physical or IPMI access to the host** to
edit the kernel command line — at which point you're no longer using
HAOS in any meaningful sense and might as well install Debian.

### What this means for users

- **System monitoring** (the integration) is fully functional and works
  on every HA install type (HAOS / HA Container / HA Core / Supervised).
- **Display mode** is **not** part of v1.5.0 and is not planned as a
  software fix on HAOS. The previous add-on code is preserved in the
  git history up through tag `v1.4.2` if you want to use it on a
  non-HAOS host (Debian / Ubuntu / Arch on bare metal, or a VM that
  exposes `/dev/fb0` via KVM/QEMU pass-through).

If you need the display mode on HAOS: the path is to boot with
`amdgpu.fbdev=1 nomodeset video=efifb:off` in the kernel command line.
HAOS upstream does not expose this knob; this is by design (HAOS wants
to be a headless appliance).

---

## Verified working configurations

| HA install type | Integration | Display mode |
|---|---|---|
| HAOS (Supervisor + container) | ✅ | ❌ — see above |
| HA Container (Docker, no Supervisor) | ✅ (sensors only) | ❌ |
| HA Core (venv/pip) | ✅ (sensors only) | ❌ |
| HA Supervised (Debian + Supervisor) | ✅ | works if host has `/dev/fb0` exposed |
| Debian / Ubuntu / Arch bare-metal (no HA) | n/a | ✅ — use `fb_render.py` from tag v1.4.2 |

---

## Architecture (v1.5.0)

```
┌─────────────────────────────────────────┐
│ custom_components/haos/                 │
│   HACS-installable HA integration       │
│                                         │
│   • /proc polling via psutil            │
│   • psutil → HA sensor entities         │
│   • /api/states, /api/services polling  │
│     (HA Core + Supervisor info)         │
└─────────────────────────────────────────┘
                  │
                  ▼
        Home Assistant Core
                  │
                  ▼
      HA Frontend (cards, dashboards)
```

Display mode (formerly a separate Supervisor add-on) is intentionally
absent from this release.

---

## Versioning

| Version | Status | Notes |
|---|---|---|
| 1.0.0 – 1.1.9 | historical | early releases; multiple known regressions |
| 1.2.0 – 1.4.2 | historical | display-mode add-on experiment; all known to fail at runtime on HAOS |
| **1.5.0** | **current** | display add-on removed; integration-only release |

---

## Development

```bash
git clone https://github.com/kou147258/haos-ha
cd haos-ha
pip install 'psutil>=5.9.0,<7.0.0' pytest
pytest tests/ -v
```

`scripts/host_diag_*.py` and `scripts/host_fb0_*.py` are the diagnostic
scripts we ran while diagnosing the display-mode failure on HAOS.
They're retained as a historical record. None of them are required for
v1.5.0 to function.

---

## Credits

- Original code: [neon9809/haos](https://github.com/neon9809/haos)
  (display-mode renderer, themes, fb_render.py)
- HA integration adaptation: HACS manifest, config flow, coordinator,
  sensor / switch / binary_sensor entity classes
- Display-mode failure diagnosis: documented in
  `~/.minimax/agents/mavis/memory/MEMORY.md` (private; lessons learned)

## License

MIT. See [LICENSE](LICENSE).