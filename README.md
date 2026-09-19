# HAOS Dashboard — Home Assistant edition

Generic-Linux system monitor + `/dev/fb0` display renderer, repackaged as a
**HA custom integration** (HACS) and a **HA Supervisor add-on**.



<details>
<summary><strong>📖 Language / 语言 — 点击展开中文 / Click to expand Chinese</strong></summary>


通用 Linux 系统监控 + `/dev/fb0` 显示器渲染器，打包成 **HA 自定义集成**（HACS）+ **HA Supervisor 插件**（仅 HAOS 用）。

源自 [neon9809/haos](https://github.com/neon9809/haos)，去掉了 fnOS 特有的 FPK 打包 / udev 规则 / CGI 网关 / `/vol*` 探测 / `.neon-dash` 模块系统，**只保留**两件事：

1. **系统监控** — CPU / 内存 / Swap / 磁盘 / 网络 / 温度 / 启动时间 / 进程数 / 主机名 / OS
2. **显示器模式** — 把这些数据实时画到 `/dev/fb0`（HAOS 专用，走 Supervisor 插件）

### 要求

- **Home Assistant 2026.8 或更高**（用了 `async_get_system_info` + HA 2026.8 引入的 frozen `SensorEntityDescription` + `FrozenOrThawed` metaclass）
- 显示器模式只在 **HAOS / Supervised** 可用（需要 Supervisor）；Container / Core 部署只能装集成

> **⚠️ 网络受限？** 如果 HACS / HAOS add-on store 走 HTTPS 拉 GitHub 时报 `OpenSSL SSL_read: ... unexpected EOF while reading` —— 这是 HAOS 到 GitHub 的 TLS 链路被中间设备打断，**不是代码 bug**。**直接看下文 "Fix A：手动放 `/addons/local/`"**（最下面"add-on 装不上 / 拉 repo SSL 错误"段），下 `haos-1.1.4.zip` + `v1.1.4.zip` 拷文件就行，不必修网络。

### 装集成 `haos`（2 选 1）

**方法 A：HACS Custom Repository（推荐）**

1. HA → **HACS** → **Integrations** → 右上 ⋮ → **Custom repositories**
2. Repository 填 `https://github.com/kou147258/haos-ha`，Category 选 `Integration`，点 **Add**
3. 回到 HACS → Integrations → 搜 **`HAOS Dashboard`** → **Install**
4. **Settings → System → Restart Home Assistant**（HACS 装完**不自动重启**）

**方法 B：手动（不用 HACS）**

1. 从 https://github.com/kou147258/haos-ha/releases 下载 `haos-1.1.3.zip`
2. 解压得到 `haos/` 文件夹，拷贝到 HA 配置目录的 `custom_components/`：
   - HAOS：`/config/custom_components/haos/`
   - 也可通过 **Samba add-on** 或 **Studio Code Server** 拖进去
3. 重启 HA（同上）

### 装 add-on `HAOS Dashboard Display`（仅 HAOS / Supervised）

显示器模式——把上面那些数据画到 `/dev/fb0`。

1. **Settings → Add-ons → Add-on Store** → 底部 ⋮ → **Repositories**
2. 粘贴 `https://github.com/kou147258/haos-ha`，**Add**
3. 列表里搜 **HAOS Dashboard Display**（slug 是 `haos_fb`）→ **Install**
4. **Configuration** 页签调参数（见下表）→ **Start**
5. HA Supervisor 自动从 `ghcr.io/kou147258/haos-fb-{arch}:1.1.3` 拉镜像，`{arch}` 替换成宿主机架构（amd64 / aarch64 / armv7 / armhf / i386）

### 验证 `sensor.haos_info`

**Developer Tools → States** → 搜 `sensor.haos_info`：

- **State**：`2026.8.0 · OS · 234 entities`（HAOS 用户，Container / Core 部署类似）
- **Attributes** 展开能看到：
  - `ha_core_version` / `ha_installation_type` / `ha_arch` / `ha_python_version` / `ha_time_zone` / `ha_location_name`
  - `hassio`（bool，是否有 Supervisor）
  - `supervisor_version` / `supervisor_healthy` / `supervisor_update_available`（HAOS 才有）
  - `haos_version` / `haos_board`（HAOS 才有）
  - `integration_version` / `integration_loaded_at` / `integration_last_refresh`
  - `addon_slug` / `addon_version` / `addon_state`
  - `entity_count` / `device_count` / `integration_count`（跟随 coordinator 主刷新）

**Container / Core 部署**：所有 `supervisor_*` / `haos_*` / `addon_*` 字段会缺失（被 `build_attributes` 过滤掉 None），**属于正常**——不是 bug。

### 集成版本与 HA 版本对应

| 集成版本 | 状态 | 说明 |
|---|---|---|
| 1.0.0 | 早期 release | 未在真机验证 |
| 1.1.0 | 早期 release | 加了 `sensor.haos_info`，未在真机验证 |
| 1.1.1 | ⚠️ **加载失败** | frozen dataclass 不接受 `value_fn` kwarg |
| 1.1.2 | ⚠️ **加载失败** | 修 frozen 但用了 subclass，仍被 metaclass 拒绝 |
| **1.1.3** | ✅ **可用** | 去掉 SensorEntityDescription subclass，温度 sensor unique_id 用 `(group, index)` |

如果 HA 版本 < 2026.8，看 **Developer Tools → About** 升级。

### add-on 装不上 / 拉 repo SSL 错误

```
Cmd('git') failed due to: exit code(128)
stderr: 'fatal: unable to access 'https://github.com/...': OpenSSL SSL_read:
error:0A000126:SSL routines::unexpected eof while reading'
```

这是 **HAOS 容器到 GitHub 的 TLS 握手被中间设备打断**——公司网关 / VPN / 防火墙 / GFW / MTU 不匹配，**不是代码 bug**。

**Fix A：手动放 `/addons/local/`（最快，5 分钟搞定）**

1. 浏览器下载 https://github.com/kou147258/haos-ha/archive/refs/tags/v1.1.3.zip
2. 解压后只取 `haos-ha-1.1.3/haos_fb/` 整个文件夹
3. 通过 Samba / SSH 拷到 HAOS 的 `/addons/local/haos_fb/`
4. **Settings → Add-ons → Add-on Store** → **⋮ → Reload** → 顶部出现 **Local add-ons** → Install `HAOS Dashboard Display`

> 集成部分也是同样手动法：`haos-1.1.3.zip` 解压得到 `haos/` 拷到 `/config/custom_components/haos/`。

**Fix B：改用 SSH URL（HAOS 标准做法）**

1. HAOS SSH 里 `ssh-keygen -t ed25519 -C "haos-supervisor"`
2. `cat ~/.ssh/id_ed25519.pub` 把公钥加到 GitHub → Settings → SSH and GPG keys
3. add-on repo 改填 `git@github.com:kou147258/haos-ha.git`

**Fix C：调 MTU（如果是 Hyper-V / VirtualBox 上的 HAOS）**

```bash
echo 'interface eth0
  mtu 1400' >> /etc/dhcpcd.conf
reboot
```

**诊断命令**（把输出贴出来能精准定根因）：

```bash
date                                          # 时间对吗
nslookup github.com                           # DNS 解析对吗
curl -vI https://github.com 2>&1 | head -30   # HTTPS 握手能完成吗
git clone https://github.com/kou147258/haos-ha /tmp/test --depth=1 2>&1 | tail -10
```

### add-on 配置项

**Configuration** 页签（YAML 格式）：

| 字段 | 取值 | 默认 |
|---|---|---|
| `theme` | `midnight` / `graphite` / `emerald` / `sunshine` / `cherry` / `cloud` | `midnight` |
| `accent` | 空（用主题默认）/`cyan purple emerald amber rose blue indigo lime orange pink teal yellow` / `#rrggbb` | 空 |
| `refresh` | 1–30 秒 | `2` |
| `temp_unit` | `C` / `F` | `C` |
| `page_interval` | 0 = 不自动翻页，>0 = 间隔秒数 | `0` |
| `pages` | 任意子集：`status` `cpu` `memory` `network` `disks` `info` | 全部 |

### 显示哪些 entity

装完会出现一个 **HAOS Dashboard** 设备，下属这些实体：

**Sensors（`sensor.haos_*`）**

- `cpu_usage` / `cpu_core_<n>`（每核一个） / `cpu_load_1_min` / `cpu_frequency` / `cpu_temperature`
- `memory_usage` / `memory_used` / `_total` / `_available`（**显示 GB**）
- `swap_usage` / `swap_used` / `swap_total`（**显示 GB**）
- `network_upload` / `_download`（**显示 MB/s**）/ `network_bytes_sent` / `_bytes_received`（累计，**显示 MB**）
- `disk_<mount>_percent` / `_used` / `_free` / `_total`（每个挂载点一组，size 用 **GB**）
- `temperature_<label>`（每个 psutil 温度探头一个，**含同名重复**——用 index 区分）
- `uptime` / `processes` / `hostname` / `operating_system`
- `info` — 短摘要 `"<版本> · <安装类型> · <实体数> entities"`，完整 attrs 见 `extra_state_attributes`

**显示精度**：整数 / 字节类（内存、磁盘、网络累计、CPU 频率、uptime、进程数、主机名、OS）= **0 位小数**；百分比 / 温度 / 速率（CPU%、内存%、温度、上下行速率）= **1 位小数**；`load_1` = **2 位小数**。

**单位固定为 GB / MB / MB-s**——不走 HA 自动换算（切 Imperial / Metric 不会改变仪表盘显示）。

**Binary sensor + Switch**

- `binary_sensor.display_running` — add-on 是否在跑（HAOS 才有数据）
- `switch.display_enabled` — 通过 Supervisor API 启停 add-on

**Services**

- `haos.refresh_display` — 强制 add-on 立即重绘
- `haos.reload_themes` — 重载集成选项

### 集成 vs add-on 关系

- **只装集成**：全部 sensor 可用，但显示器黑屏。**适合不需要外接屏的用户。**
- **只装 add-on**：白装——add-on 拉的是 `sensor.haos_*` entities，没集成就没数据源。
- **两个都装**：全功能。

### 常见问题

| 症状 | 排查 |
|---|---|
| HACS 找不到 `HAOS Dashboard` | 没正确加 Custom Repository。重新加 `https://github.com/kou147258/haos-ha` 选 Integration |
| `Home Assistant version is not supported` | HA < 2026.8，Settings → About 查版本升级 |
| `sensor.haos_info` state 是 `unknown` / `unavailable` | 看 log：`async_collect_info` 失败。Logger → `custom_components.haos` |
| 所有 supervisor / haos 字段缺失 | 你在 Container / Core 部署，不是 HAOS |
| add-on 拉镜像失败 / GHCR 401 | GitHub PAT 没 `read:packages` scope。HACS 用你账号 token 拉包 |
| HACS 装完 sensor 全 unavailable | 重启 HA（HACS 装完**不自动重启**） |
| 显示器没画面但 add-on 在跑 | `/dev/fb0` 没暴露给 HAOS 容器。add-on config.yaml 已配 `devices: /dev/fb0`，但需要 HAOS 主机本身有 `/dev/fb0` |
| `Platform haos does not generate unique IDs` | 你的 HA 版本太低装的是 1.1.0 / 1.1.1。**装 1.1.3** |


</details>

---

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

1. HA → **HACS** → **Integrations** (top tab) → top-right ⋮ → **Custom repositories**.
2. The dialog asks for two fields:
   - **Repository**: `https://github.com/kou147258/haos-ha`
   - **Category**: `Integration`
3. Click **Add**. The repo now appears in the list — open it and install
   the **`HAOS Dashboard`** integration (current version: 1.1.4).
4. **Settings → System → Restart Home Assistant**. HACS does **not**
   auto-restart on a custom-component install.

Without HACS at all, copy `custom_components/haos/` into your HA
`config/custom_components/` directory and restart. If HACS fails to
clone this repo (SSL handshake errors are common on networks with
middleboxes), skip HACS entirely and use
[§3. Manual install](#3-manual-install-offline-friendly-no-git) below.

### 2. Install the display add-on (HA OS only)

The display mode is a Supervisor add-on so it requires **HA OS** or
**Supervised**. On HA Core / Container, skip this section (the
integration still works; the display just has no host process to drive
`/dev/fb0`).

1. **Settings → Add-ons → Add-on Store** → bottom-right ⋮ → **Repositories**.
2. Paste `https://github.com/kou147258/haos-ha` (the Repository dialog
   here has **no category field** — unlike HACS, Supervisor add-on
   stores don't differentiate) → **Add**.
3. The store list reloads. Search **HAOS Dashboard Display** (slug
   `haos_fb`) → **Install**.
4. Open the add-on's **Configuration** tab. Optionally tweak:
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

### 3. Manual install (offline-friendly, no git)

If the standard HACS / add-on Store install fails with

```
fatal: unable to access 'https://github.com/...': OpenSSL SSL_read:
error:0A000126:SSL routines::unexpected eof while reading
```

(typical when a middlebox on the HAOS → GitHub path resets the TLS
handshake), skip both `git clone` paths. Same end state as the HACS /
Store routes, no network fix required.

**3a. Integration (no HACS)**

1. Download `haos-1.1.4.zip` from
   [Releases → v1.1.4](https://github.com/kou147258/haos-ha/releases/tag/v1.1.4).
2. Unzip — you get a `haos/` folder.
3. Copy `haos/` into your HA config directory:
   - HAOS / Supervised: `/config/custom_components/haos/`
   - Easiest path from Windows: install the **Samba share** add-on
     (`\\<haos-ip>\config\` becomes a normal network drive) or the
     **Studio Code Server** add-on (drag-and-drop in its file tree).
4. **Settings → System → Restart Home Assistant** (HACS restarts for you
   automatically; the manual install does not).

**3b. Display add-on (HAOS only, no Store)**

1. Download the source archive:
   `https://github.com/kou147258/haos-ha/archive/refs/tags/v1.1.4.zip`
2. Unzip — take only the `haos_fb/` folder.
3. Get it onto the HAOS host:
   - **Samba share** add-on → drop `haos_fb/` into `/config/`
   - **Advanced SSH & Web Terminal** add-on → `scp` or paste via shell
4. Move it into the local-addon path:
   ```bash
   # HAOS host shell
   mv /config/haos_fb /addons/local/haos_fb
   ```
5. **Settings → Add-ons → Add-on Store** → ⋮ → **Reload**.
6. The top of the page now shows a **Local add-ons** section with
   **HAOS Dashboard Display** → **Install** → **Start**.

**If you'd rather diagnose the SSL error** so future installs just work,
run these in the HAOS shell and post the output:

```bash
date
nslookup github.com
curl -vI https://github.com 2>&1 | head -30
git clone https://github.com/kou147258/haos-ha /tmp/test --depth=1 2>&1 | tail -10
```

Common fixes once we know which layer fails: NTP time drift, wrong DNS,
MTU 1400 on Hyper-V / VirtualBox, or switching to SSH URL after adding
the host key to GitHub.

## What you get in HA

After install you'll see one device `HAOS Dashboard` with:

### Sensors (`sensor.*`)

- `sensor.haos_cpu_usage` — overall %
- `sensor.haos_cpu_core_<n>` — one per logical core
- `sensor.haos_cpu_load_1_min`
- `sensor.haos_cpu_frequency` — MHz
- `sensor.haos_cpu_temperature` — °C / °F
- `sensor.haos_memory_usage` — %
- `sensor.haos_memory_used` / `_total` / `_available` — GB
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
- `sensor.haos_info` — single sensor summarising HA / Supervisor / HAOS /
  integration / add-on versions plus live entity / device / integration
  counts. State is a short string like `"2026.8.0 · OS · 234 entities"`;
  everything else lives in `extra_state_attributes`.

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

---

