# HAOS Dashboard — Home Assistant edition

Generic-Linux system monitor + `/dev/fb0` display renderer, repackaged as a
**HA custom integration** (HACS) and a **HA Supervisor add-on**.

Adapted from [neon9809/haos](https://github.com/neon9809/haos)
with the fnOS-specific parts (FPK packaging, udev rules, CGI gateway, `/vol*`
detection, `.neon-dash` module system) removed — keeping only the two parts
the user wanted:

1. **System monitoring** — CPU, memory, swap, disks, network, temperatures
2. **Display mode** — render those stats straight to `/dev/fb0` via the HA
   Supervisor add-on, so it works on HA OS without giving up frame-buffer
   access.

```
┌──────────────────────┐     sensor states      ┌─────────────────────────┐
│ haos       │ ───────────────────▶  │ haos_fb       │
│ (HA custom component)│   REST /api/states     │ (HA Supervisor add-on)  │
│ psutil /proc polling │                        │ reads /api/states       │
└──────────────────────┘                        │ writes /dev/fb0         │
                                                └─────────────────────────┘
```

---

## Layout

```
haos-ha/
├── custom_components/
│   └── haos/                # HACS-installable HA integration
│       ├── __init__.py                # entry, config reload
│       ├── manifest.json              # domain + iot_class + psutil dep
│       ├── const.py
│       ├── coordinator.py             # /proc snapshot via psutil
│       ├── config_flow.py             # 1-step config + options
│       ├── sensor.py                  # CPU/mem/disk/net/temp/info sensors
│       ├── binary_sensor.py           # "Display running"
│       ├── switch.py                  # "Display enabled" (start/stop addon)
│       ├── addon.py                   # Supervisor API helpers
│       ├── services.yaml
│       ├── diagnostics.py
│       ├── strings.json
│       └── translations/{en,zh-Hans}.json
│
├── haos_fb/                # HA Supervisor add-on
│   ├── config.yaml                    # add-on manifest
│   ├── build.yaml                     # multi-arch build matrix
│   ├── Dockerfile                     # Alpine + Pillow + aiohttp + fonts
│   ├── run.sh                         # bashio entry point
│   ├── fb_render.py                   # main render loop
│   ├── themes.py                      # 6 themes + 12 accent colors
│   └── font.py                        # PIL + 5x7 ASCII bitmap fallback
│
├── tests/                             # placeholder
├── .github/workflows/
│   ├── ci.yml                         # lint + compile-check + smoke render
│   └── release.yml                    # multi-arch Docker + GitHub Release
├── .yamllint.yml                      # yamllint config
├── LICENSE                            # MIT
├── README.md                          # this file
└── .gitignore
```

---

## Installation

### 1. Install the custom integration (HACS)

Easiest is HACS → Custom repositories → add this repo URL → install the
`haos` integration.

Without HACS, copy `custom_components/haos/` into your HA
`config/custom_components/` directory and restart.

### 2. Install the display add-on (HA OS only)

If you're on HA OS:

1. Settings → Add-ons → Add-on Store → ⋮ → **Repositories**
2. Paste this repo's URL, then refresh.
3. Install **HAOS Dashboard Display** (`haos_fb`).
4. Open the add-on's Settings page. Optionally tweak:
   - `theme`: `midnight` / `graphite` / `emerald` / `sunshine` / `cherry` / `cloud`
   - `accent`: blank (use theme default) or one of `cyan purple emerald amber
     rose blue indigo lime orange pink teal yellow` or a `#rrggbb` hex
   - `refresh`: 1–30 seconds (matches the integration's poll rate)
   - `temp_unit`: `C` / `F`
   - `page_interval`: seconds between auto page rotation (0 = off)
   - `pages`: any subset of `status cpu memory network disks info`
5. **Start** the add-on. The Display Running binary sensor in HA will go `on`.

> **HA Core / HA Container users:** skip step 2. The integration still works
> — you'll see all sensors, the display-side binary sensor will simply be
> unavailable because there is no Supervisor to talk to. You can run the
> renderer as a plain Python process on the host if you want the display
> side too:

```bash
export SUPERVISOR_URL="http://homeassistant.local:8123/api"
export SUPERVISOR_TOKEN="<long-lived access token>"
python3 haos_fb/fb_render.py \
    --config haos_fb/options.example.json
```

The renderer only needs read access to `/dev/fb0`.

---

## What you get in HA

After install you'll see one device `HAOS Dashboard` with:

### Sensors (`sensor.*`)

- `sensor.haos_cpu_usage` — overall %
- `sensor.haos_cpu_core_<n>` — one per logical core
- `sensor.haos_cpu_load_1_min`
- `sensor.haos_cpu_frequency` — MHz
- `sensor.haos_cpu_temperature` — °C / °F
- `sensor.haos_memory_usage` — %
- `sensor.haos_memory_used` / `_total` / `_available` — bytes
- `sensor.haos_swap_usage` / `_used` / `_total`
- `sensor.haos_network_upload` / `_download` — KB/s
- `sensor.haos_network_bytes_sent` / `_bytes_received` — total bytes
- `sensor.haos_disk_<mount>_percent` / `_used` / `_free` / `_total`
  — one group per detected mount
- `sensor.haos_temperature_<label>` — one per psutil sensor probe
- `sensor.haos_uptime` — seconds
- `sensor.haos_processes`
- `sensor.haos_hostname`
- `sensor.haos_operating_system`

### Binary sensor + switch

- `binary_sensor.haos_display_running` — add-on state
- `switch.haos_display_enabled` — start/stop the add-on via
  Supervisor API

### Options

Settings → Devices & Services → HAOS Dashboard → **Configure**:

- **Refresh interval** — 1–30 s (default 2 s)
- **Temperature unit** — `C` / `F` (default `C`)

### Services

- `haos.refresh_display` — nudge the renderer
- `haos.reload_themes` — reload integration options

---

## Display add-on: what gets drawn

The add-on pulls the same sensor entities from HA REST every `refresh`
seconds and renders the following pages on `/dev/fb0`:

| Page | Content |
|---|---|
| `status` | 2×2 grid: CPU%, Memory%, Disks, Network + temp + uptime |
| `cpu` | Per-core usage bars, frequency, load avg, all temperature sensors |
| `memory` | RAM and Swap bars with used/total, process count, uptime |
| `network` | Upload/download rates, total bytes sent/received, per-interface state |
| `disks` | One progress bar per mount with used/total |
| `info` | Hostname, OS, kernel, boot time, uptime, process count |

The footer shows a dot indicator + countdown when `page_interval > 0`. If
HA is unreachable the last good frame stays on the display and an `OFFLINE`
badge appears in the corner.

### Fonts

- **PIL** (default) — DejaVu Sans Mono from `ttf-dejavu` for Latin glyphs.
- **5×7 ASCII bitmap** — automatic fallback if Pillow isn't available.
- **CJK glyphs** — drop `NotoSans*.ttf` / `*.ttc` files into the add-on's
  share (`/share/fonts/`) and the renderer picks them up at startup. The
  share is mounted from `/usr/share/hassio/addons/local/<repo>/share/` by
  default.

---

## Security model

- The integration runs **inside the HA container**. It polls `psutil` for
  local system stats — no remote services touched.
- The display add-on runs in its **own Supervisor-managed container** with
  `host_network: false` and `devices: ["/dev/fb0"]`. It talks to HA only
  via the Supervisor proxy (`http://supervisor/core/api`) using the
  injected `SUPERVISOR_TOKEN`, which Supervisor scopes to the add-on.
- The integration talks to Supervisor only for start/stop/state queries on
  its own companion add-on. It never reads other add-ons or HA internals.
- HA token is never written to disk by this code.

---

## Differences vs. the original haos

| Original | This port | Why |
|---|---|---|
| `manifest` + `cmd/` FPK packaging | HA custom integration + Supervisor add-on | Target ecosystem is HA, not the fnOS app store |
| `udev` rules for `/dev/fb0` | Supervisor add-on `devices:` | Supervisor handles device passthrough |
| `index.cgi` 127.0.0.1 reverse-proxy | Supervisor API | HA OS already provides an equivalent |
| `/vol*` mount auto-detection | Generic `psutil.disk_partitions` | Generic Linux, not fnOS |
| `.neon-dash` plugin system + ed25519 | None | HA has its own integrations + HACS |
| Web panel + settings page (`/settings`) | HA options flow + sensors + switch | HA already provides the UI |
| Theme editor UI | Add-on YAML schema | Configuration is rare; YAML is fine |
| Weather + calendar + Plan usage modules | None | Out of scope; HA already covers this |

---

## Development

```bash
# Integration tests (smoke)
python3 -m py_compile custom_components/haos/*.py

# Add-on tests (smoke)
python3 -m py_compile haos_fb/*.py

# Render a single frame to PNG (requires Pillow; works on any platform)
python3 haos_fb/fb_render.py \
    --config haos_fb/options.example.json \
    --dump-png preview.png \
    --width 800 --height 480 \
    --synthetic

# Render all 6 pages as a numbered PNG sequence
python3 haos_fb/fb_render.py \
    --config haos_fb/options.example.json \
    --dump-png preview_%d.png \
    --frames 6 --synthetic
```

The `--dump-png` mode replaces `/dev/fb0` with a PIL-backed in-memory canvas,
so you can iterate on layout / theme / fonts on a laptop without a connected
display. Add `--synthetic` (and skip `--config` env vars) for fully offline
dev work — the renderer will fabricate a realistic-looking snapshot.

## CI

- `.github/workflows/ci.yml` runs on every push / PR: py_compile,
  JSON / YAML validation, yamllint, manifest sanity, and a real
  `fb_render.py --dump-png` smoke render.
- `.github/workflows/release.yml` runs on `v*.*.*` tag push: multi-arch
  Docker build (aarch64 / amd64 / armv7 / armhf / i386) → GHCR push →
  multi-arch manifest → GitHub Release with the integration zip attached.

Tag a release with:

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## License

MIT. See `LICENSE`.

The original [neon9809/haos](https://github.com/neon9809/haos)
project ships without an explicit license — the renderer logic and theme
palette are derivative works from there and re-released here under MIT with
the maintainer's blessing.