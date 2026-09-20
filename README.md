# HAOS Dashboard — Home Assistant edition

A HACS-installable Home Assistant integration that exposes **HAOS host
system stats** (CPU per-core, memory, swap, disks, network, temperatures,
uptime, processes, hostname, OS) as sensor entities — plus an `info`
sensor summarising HA Core / Supervisor / HAOS / integration versions
and live entity counts.

The repo includes a **Supervisor add-on** (`haos_fb/`) that renders the
sensor data directly to `/dev/fb0` on a directly-attached HDMI / VGA /
DSI panel, **if your HAOS host meets the hardware requirements** (see
[Display mode — when it works](#display-mode--when-it-works) below).
Legacy BIOS + integrated graphics does not satisfy them.

Derived from [neon9809/haos](https://github.com/neon9809/haos). The
fnOS-specific parts (FPK packaging, udev rules, CGI gateway, `/vol*`
detection, `.neon-dash` module system) have been removed.


<details>
<summary><strong>📖 语言 / Language — 点击展开中文 / Click to expand Chinese</strong></summary>


HACS 可装的 Home Assistant 集成，把 **HAOS 主机系统状态**（CPU 每核、内存、
Swap、磁盘、网络、温度、启动时间、进程数、主机名、OS）暴露成 sensor
实体——外加一个 `info` sensor 汇总 HA Core / Supervisor / HAOS / 集成版本
和实时 entity 数量。

本仓库同时提供 **Supervisor 插件** (`haos_fb/`) 把 sensor 数据直接画到
`/dev/fb0`（HDMI / VGA / DSI 直连屏幕），但需要 **HAOS 主机满足硬件要求**
（Legacy BIOS + 集显 **不行**，详见下方"显示器模式——什么时候能用"）。

源自 [neon9809/haos](https://github.com/neon9809/haos)，已删除 fnOS 特有
部分（FPK 打包、udev 规则、CGI 网关、`/vol*` 探测、`.neon-dash` 模块系统）。

</details>

---

## Quick start

### A. HACS Custom Repository (recommended, integration only)

1. HA → **HACS** → **Integrations** → top-right ⋮ → **Custom repositories**
2. Repository: `https://github.com/kou147258/haos-ha`
   Category: `Integration` → **Add**
3. Back to HACS → Integrations → search **HAOS Dashboard** → **Install**
4. **Settings → System → Restart Home Assistant** (HACS doesn't auto-restart)

### B. Supervisor add-on (HAOS only, requires UEFI + discrete GPU)

If your HAOS host meets the hardware requirements in
[Display mode — when it works](#display-mode--when-it-works) below:

1. HA → **Settings → Add-ons → Add-on Store** → bottom-right ⋮ → **Repositories**
2. Paste `https://github.com/kou147258/haos-ha` → **Add**
3. Search **HAOS Dashboard Display** (slug `haos_fb`) → **Install**
4. **Configuration** tab → tune options → **Start**
5. HA Supervisor pulls `ghcr.io/kou147258/haos-fb-{arch}:1.5.0` (or `:latest`)

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

- `binary_sensor.display_running` — add-on state (HAOS only)
- `switch.display_enabled` — start/stop the add-on via Supervisor API
  (HAOS only)

### Options

Settings → Devices & Services → **HAOS Dashboard** → **Configure**:

- **Refresh interval** — 1–30 s (default 2 s)
- **Temperature unit** — `C` / `F` (default `C`)

### Services

- `haos.refresh_display` — nudge the renderer (HAOS only)
- `haos.reload_themes` — reload integration options

---

## Display mode — when it works

The Supervisor add-on (`haos_fb/`) drives `/dev/fb0` from inside a
container using one of two paths:

| Path | When it works | What it needs |
|---|---|---|
| `fb_render.py` (direct fb0 mmap) | Always works **if** `/dev/fb0` is backed by amdgpu's fbdev emulation (page-cache mmap, not iomem) | UEFI boot + amdgpu as primary display + `/dev/fb0` not bound by efifb |
| `drm_render.py` (DRM/KMS via libdrm) | Always works **if** `/dev/dri/card0` exists | UEFI boot + amdgpu init'd (creates `/dev/dri/card0`) |

The add-on's `config.yaml` automatically picks the working path
(`drm_render.py` if `/dev/dri/card0` exists, otherwise `fb_render.py`
on `/dev/fb0`, otherwise headless PNG fallback).

### Hardware requirements (mandatory)

1. **UEFI boot mode** for HAOS. Check with `cat /proc/cmdline | grep
   BOOT_IMAGE`. UEFI shows a path like
   `BOOT_IMAGE=.../EFI/.../...efi`; Legacy shows `BOOT_IMAGE=(hd0,gpt2)/bzImage`
   (GRUB syntax). If you're on Legacy, your motherboard almost
   certainly supports UEFI — change **Boot Mode** to **UEFI** in
   BIOS, then reinstall HAOS preserving `/config`. Without UEFI, the
   `efifb` driver owns `/dev/fb0` and we hit the kernel-LSM wall
   explained below.

2. **A discrete GPU** (AMD or NVIDIA). The motherboard's BIOS must
   list it (PCIe slot). Run `lspci -nn | grep -iE 'VGA|3D'`
   on the host and look for a device with vendor `1002` (AMD) or
   `10de` (NVIDIA). Intel-only iGPUs won't help.

3. **BIOS Primary Display = PEG** (or "PCIe", "Discrete", or
   whatever your board calls the dGPU slot). On boards that expose
   both "IGD" and "PEG" entries, set PEG as primary. Some boards
   also need **IGD Multi-Monitor = Disabled** for the discrete GPU
   to fully take over the framebuffer.

4. After all three settings: reboot. Verify with:
   ```bash
   cat /sys/class/graphics/fb0/name           # expect "amdgpu ..." not "EFI VGA"
   ls /dev/dri/                                # expect "card0 renderD128"
   dmesg | grep -iE 'amdgpu|drm' | head -20    # expect init lines
   ```
   If `fb0` is still `EFI VGA`, the BIOS settings didn't fully
   release the framebuffer — try `IGD Disabled` if your board has
   it, or check for a `Multi-Monitor` option.

### Why Legacy BIOS + integrated graphics doesn't work

On HAOS x86_64 + Legacy BIOS (default) + integrated graphics:

1. The kernel's `efifb` driver early-binds `/dev/fb0` at physical
   address `0xe0000000` (~0.6 s after boot), reserving 3 MiB of
   iomem.
2. Any `mmap(2)` from inside a Supervisor add-on container returns
   `EINVAL` because Linux 6.x LSM rejects user-namespace container
   access to iomem-mapped pages. This is independent of
   `privileged: true`, `host_network`, `host_pid`, `init: true`,
   `SYS_RAWIO`, or any other capability — it's a kernel-level
   container isolation rule.
3. Even if you change BIOS Primary Display to PEG, Legacy BIOS
   still routes the console framebuffer through the integrated GPU
   via VBIOS handover, so `efifb` keeps owning `/dev/fb0` and
   `amdgpu` (which loads later) sees no fb slot and skips DRM init
   (`/dev/dri/card0` stays empty, even though `lsmod` shows
   `amdgpu` loaded).
4. `/sys` is mounted read-only in every container, so you can't
   `echo "efi-framebuffer.0" > /sys/.../unbind` from inside.
5. `/lib/modules` is empty on HAOS (kernel is built-in), so you
   can't `modprobe amdgpu modeset=1`.
6. The kernel cmdline is on a read-only partition, so you can't
   add `amdgpu.fbdev=1 nomodeset video=efifb:off` to it.
7. The only remaining software fix is to switch to UEFI, which
   short-circuits the entire chain: UEFI GOP routes the framebuffer
   to amdgpu directly, `efifb` never binds, amdgpu's fbdev
   emulation creates `/dev/fb0` backed by normal page cache, and
   the container's `mmap(2)` works.

### Software-level escape routes — all blocked on Legacy BIOS

| Attempt | Result | Why |
|---|---|---|
| `modprobe -r efifb` | `modprobe: can't change directory to '/lib/modules'` | HAOS modules are built-in |
| `echo ... > /sys/module/amdgpu/parameters/modeset` | `EROFS` (Read-only file system) | `/sys` mounted read-only in containers |
| `echo ... > /sys/bus/platform/drivers/efi-framebuffer/unbind` | `EROFS` | Same |
| `init: true` + `host_pid: true` on the add-on | Supervisor rejects (init is reserved for ssh/terminal/portainer) | Schema-level guard |
| `privileged: true` + `SYS_RAWIO` + bind-mount `/dev/fb0` | Still `EINVAL` from LSM | LSM is namespace-level, not capability-level |

---

## Architecture

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
        ┌─────────┴──────────┐
        ▼                    ▼
  HA Frontend         ┌──────────────────────────────┐
  (cards)            │ haos_fb/                      │
                     │   Supervisor add-on          │
                     │                              │
                     │   • reads /api/states        │
                     │   • fb_render.py            │
                     │     → /dev/fb0 (1024×768×32) │
                     │     OR drm_render.py        │
                     │     → /dev/dri/card0 (DRM)  │
                     │     OR headless PNG         │
                     │     → /share/haos_fb/snap   │
                     └──────────────────────────────┘
```

---

## Verified working configurations

| HA install type | Integration | Display mode |
|---|---|---|
| HAOS (Supervisor + container, Legacy BIOS) | ✅ | ❌ — needs UEFI fix |
| HAOS (Supervisor + container, UEFI + dGPU + BIOS=PEG) | ✅ | ✅ via drm_render.py or fb_render.py |
| HA Container (Docker, no Supervisor) | ✅ | ❌ (no Supervisor to manage the add-on) |
| HA Core (venv/pip) | ✅ | ❌ |
| HA Supervised (Debian + Supervisor) | ✅ | ✅ if the underlying Debian host has `/dev/fb0` or `/dev/dri/card0` exposed (typical of UEFI installs) |
| Debian / Ubuntu / Arch bare-metal (no HA) | n/a | ✅ — `fb_render.py` works directly against any `/dev/fb0` |

---

## Versioning

| Version | Status | Notes |
|---|---|---|
| 1.0.0 – 1.1.9 | historical | early releases; multiple known regressions |
| 1.2.0 – 1.4.2 | historical | display-mode add-on experiments; each one assumed a different code path that ended up not working on Legacy BIOS |
| **1.5.0** | **current** | both HACS integration and Supervisor add-on; display mode works **only** with the UEFI hardware fix above |

---

## Development

```bash
git clone https://github.com/kou147258/haos-ha
cd haos-ha
pip install 'psutil>=5.9.0,<7.0.0' pytest pillow
pytest tests/ -v
```

`scripts/host_diag_*.py` and `scripts/host_fb0_*.py` are the diagnostic
scripts we ran while diagnosing the display-mode failure modes
across HAOS hardware configurations. They're retained as historical
record.

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