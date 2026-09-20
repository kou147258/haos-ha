#!/usr/bin/env python3
"""HAOS host efifb unbind 尝试 + amdgpu 接管探测

策略:
  1. 写 /sys/bus/platform/drivers/efi-framebuffer/unbind 让 efifb 释放 fb0
  2. 检查 amdgpu fbdev emulation 是否接管
  3. 重新 mmap /dev/fb0 验证

成功条件:
  - efifb unbind 写入成功
  - /sys/class/graphics/fb0/device/driver 变成 amdgpu
  - /dev/fb0 mmap 成功

失败的话, 同时跑 amdgpu 的参数检查:
  - /sys/module/amdgpu/parameters/modeset
  - 完整 dmesg 里 amdgpu init 的最后几行
"""
import os, subprocess, sys

def line(s=""): print(s, flush=True)
def sh(cmd, timeout=10):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError as e:
        return f"FAIL {e}"

def write(path, content):
    try:
        with open(path, "w") as f:
            f.write(content)
        return True, ""
    except OSError as e:
        return False, f"errno={e.errno} ({e.strerror})"


line("=== efifb unbind 尝试 ===\n")

# 1. 当前 fb0 driver
line("[before] 当前 fb0 driver:")
line(f"  /sys/class/graphics/fb0/device/driver: {read('/sys/class/graphics/fb0/device/driver')}")
line(f"  /sys/class/graphics/fb0/name: {read('/sys/class/graphics/fb0/name')}")
line(f"  /sys/class/graphics/fb0/device/uevent: {read('/sys/class/graphics/fb0/device/uevent')[:200]}")
line("")

# 2. /sys 是不是 read-only? 检查 efi-framebuffer 平台设备
line("[sysfs] /sys/bus/platform/drivers/efi-framebuffer/* :")
rc, out, _ = sh("ls -la /sys/bus/platform/drivers/efi-framebuffer/ 2>&1")
line(out)
line("")

# 平台设备列表
line("[sysfs] /sys/bus/platform/devices/* efi 相关:")
rc, out, _ = sh("ls -la /sys/bus/platform/devices/ 2>&1 | grep -iE 'efi|frame'")
line(out or "(none)")
line("")

# 看看哪些设备绑在 efi-framebuffer
line("[sysfs] 哪个 device 被 efi-framebuffer 驱动 bound:")
rc, out, _ = sh("ls -la /sys/bus/platform/drivers/efi-framebuffer/ 2>&1")
line(out)
line("")

# 3. unbind 路径
line("[try_unbind] 写 efi-framebuffer 设备的 unbind:")
candidates = [
    "/sys/bus/platform/drivers/efi-framebuffer/unbind",
]
# 也试 uevent file 里拿到的 device name
uevent = read("/sys/class/graphics/fb0/device/uevent")
print(f"  uevent:\n{uevent[:300]}\n")
# 从 OF/acpi path 推断
dev_name = None
for token in uevent.split():
    if token.startswith("MODALIAS="):
        mod = token.split("=", 1)[1].strip('"')
        line(f"  MODALIAS: {mod}")
    if "DRIVER=" in token:
        drv = token.split("=", 1)[1].strip('"')
        line(f"  DRIVER: {drv}")
    if "OF_NAME=" in token or "OF_FULLNAME=" in token:
        dev_name = token.split("=", 1)[1].strip('"')

# 试标准 unbind paths
for unbind_path in candidates:
    if not os.path.exists(unbind_path):
        line(f"  {unbind_path}: not present")
        continue
    # 看下 bind 列表 (说明支持的 device name 格式)
    bound_dir = os.path.dirname(unbind_path)
    line(f"\n  {bound_dir}/ :")
    rc, out, _ = sh(f"ls -la {bound_dir}/ 2>&1")
    line(out)
    # 看 uevent
    line(f"  当前 fb0 device uevent (找 device name):")
    line(f"    {uevent[:300]}")

# 4. 写各种可能的 device name
line("\n[try_unbind] 试常见 device name:")
device_names_to_try = [
    "efi-framebuffer.0",
    "efi-framebuffer",
    "PNP0A03:00",  # ACPI 早期常见的 efifb 设备
    "platform:efi-framebuffer",
]

for name in device_names_to_try:
    for unbind_path in candidates:
        if not os.path.exists(unbind_path):
            continue
        line(f"  echo '{name}' > {unbind_path}:")
        ok, err = write(unbind_path, name)
        line(f"    {'OK' if ok else 'FAIL ' + err}")

        # 写完立刻看结果
        new_driver = read("/sys/class/graphics/fb0/device/driver")
        new_name = read("/sys/class/graphics/fb0/name")
        line(f"    → fb0 driver now: {new_driver}")
        line(f"    → fb0 name now: {new_name}")
        if "efi-framebuffer" not in new_driver:
            line(f"    *** efifb UNBOUND! ***")
            break
    else:
        continue
    break

# 5. 重试 mmap
line("\n[retry_mmap] 现在再 mmap /dev/fb0:")
try:
    fd = os.open("/dev/fb0", os.O_RDWR)
    try:
        import mmap
        m = mmap.mmap(fd, 8*1024*1024, mmap.MAP_SHARED,
                      prot=mmap.PROT_READ|mmap.PROT_WRITE)
        m[0:4] = b"\xff\x00\x00\x00"
        m.flush()
        line(f"  mmap OK sample={m[:8].hex()}")
        m.close()
    except OSError as e:
        line(f"  mmap FAIL errno={e.errno} ({e.strerror})")
    os.close(fd)
except OSError as e:
    line(f"  open FAIL errno={e.errno} ({e.strerror})")

# 6. 如果 unbind 失败, 收集诊断信息
line("\n[amdgpu_params] /sys/module/amdgpu/parameters/* 关键参数:")
for p in ["modeset", "fbdev", "ngg", "runpm", "bapm"]:
    fp = f"/sys/module/amdgpu/parameters/{p}"
    if os.path.exists(fp):
        line(f"  {p}: {read(fp)}")
    else:
        line(f"  {p}: (not present)")

line("\n[amdgpu_dmesg] 完整 amdgpu init 消息 (不只 head -25):")
rc, out, _ = sh("dmesg 2>&1 | grep -iE 'amdgpu|amdkfd|atom|fb[0-9]|drm|efifb' | head -60")
line(out or "(empty)")

line("\n[kfd_dmesg] kfd (KFD compute) 是否有:")
rc, out, _ = sh("dmesg 2>&1 | grep -iE 'kfd|kgd' | head -10")
line(out or "(no kfd messages)")

# 7. DRM device 路径
line("\n[drm_full] /sys/class/drm/ 完整内容 (应该有 version + 子目录 if drm init):")
rc, out, _ = sh("ls -la /sys/class/drm/ 2>&1")
line(out)
rc, out, _ = sh("cat /sys/class/drm/version 2>&1")
line(f"  version: {out}")

line("")
line("=== VERDICT ===")
line("  - 如果 [try_unbind] 任何 device name 写入 OK + fb0 driver 变成 amdgpu:")
line("    → 容器能 unbind efifb + amdgpu 接管 → amdgpu fbdev 可以 mmap")
line("  - 如果写入 EPERM/EROFS → /sys read-only, 没办法在容器里 unbind")
line("  - 如果 unbind 后 amdgpu 还不接管 → amdgpu.fbdev 可能默认 0, 改不了 cmdline")