#!/usr/bin/env python3
"""HAOS host PEG 接管诊断

确认:
  - 机器有没有独立显卡 (PCIe GPU)
  - amdgpu 模块是否加载
  - dmesg 里 amdgpu / efifb 状态
  - /sys/class/graphics/* 全部 entry
  - fb0 vs amdgpu 谁占主导
"""
import os, subprocess

def line(s=""): print(s, flush=True)
def sh(cmd, timeout=10):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


line("=== PEG 接管深度诊断 ===\n")

# 1. 当前 fb0 + 所有 fb* + DRM 设备
line("[fb_cards] /sys/class/graphics/ 全部 entry:")
rc, out, _ = sh("ls -la /sys/class/graphics/ 2>&1")
line(out)
line("")

line("[fb_cards] /sys/class/drm/ 全部 entry (如果有):")
rc, out, _ = sh("ls -la /sys/class/drm/ 2>&1 | head -10")
line(out or "(not present)")
line("")

# 2. 当前 fb0 详细信息
line("[fb0_info] /sys/class/graphics/fb0/* 全部属性:")
try:
    for entry in sorted(os.listdir("/sys/class/graphics/fb0")):
        p = f"/sys/class/graphics/fb0/{entry}"
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    v = f.read().strip()
                line(f"  {entry}: {v[:120]}")
            except OSError:
                pass
except OSError as e:
    line(f"  FAIL {e}")
line("")

# 3. 设备驱动归属 (fb0 的 driver)
line("[fb0_driver] /sys/class/graphics/fb0/device/driver:")
rc, out, _ = sh("readlink /sys/class/graphics/fb0/device/driver 2>&1; basename $(readlink /sys/class/graphics/fb0/device/driver) 2>&1")
line(f"  driver: {out}")
line("")

# 4. PCIe 设备 - 有没有独立显卡
line("[pci_vga] lspci VGA 类设备:")
rc, out, _ = sh("lspci 2>&1 | grep -iE 'VGA|3D|Display' | head -10")
line(out or "(lspci not found or no VGA devices)")
line("")

# /sys/bus/pci/devices 看 class=0x0300 (VGA) / 0x0302 (3D)
line("[pci_class] /sys/bus/pci/devices/*/class 找 0x03 (display):")
rc, out, _ = sh("for d in /sys/bus/pci/devices/*/; do "
                "  cls=$(cat $d/class 2>/dev/null); "
                "  case $cls in 0x03*) "
                "    echo \"$(basename $d) class=$cls vendor=$(cat $d/vendor 2>/dev/null) device=$(cat $d/device 2>/dev/null)\"; "
                "  esac; "
                "done 2>&1 | head -10")
line(out or "(no display class devices)")
line("")

# 5. amdgpu 模块状态
line("[modules] lsmod | grep -E 'amdgpu|drm|efi' | head -10:")
rc, out, _ = sh("lsmod 2>&1 | grep -E 'amdgpu|drm|efifb' | head -10")
line(out or "(lsmod not found / empty)")
line("")

# 6. dmesg amdgpu / efifb
line("[dmesg] dmesg | grep -iE 'amdgpu|drm.*init|efifb|framebuffer' | head -25:")
rc, out, _ = sh("dmesg 2>&1 | grep -iE 'amdgpu|drm|efifb|framebuffer' | head -25")
line(out or "(dmesg not readable)")
line("")

# 7. /dev/dri 详细
line("[dri] /dev/dri* 检查 (没 mount 时是 ENOENT):")
rc, out, _ = sh("ls -la /dev/dri* 2>&1; echo '---'; ls -la /dev/ | grep -E 'dri|fb'")
line(out)
line("")

# 8. 关键: amdgpu loaded 但 DRM core 没 init - 检查 drm device class
line("[drm_class] /sys/class/drm 是否存在:")
rc, out, _ = sh("test -d /sys/class/drm && echo 'EXISTS' || echo 'NO drm class dir'")
line(f"  /sys/class/drm: {out}")

# 9. 加载参数 (cmdline)
line("[cmdline] /proc/cmdline efifb / amdgpu 相关参数:")
try:
    with open("/proc/cmdline") as f:
        cmdline = f.read().strip()
    line(f"  {cmdline}")
    for token in cmdline.split():
        if any(x in token for x in ["video=", "nomodeset", "amdgpu.", "drm."]):
            line(f"  → relevant: {token}")
except Exception as e:
    line(f"  FAIL {e}")
line("")

# 10. 试 modprobe -r efifb 看能不能让它退出
line("[try_unload] 尝试 modprobe -r efifb:")
rc, out, err = sh("modprobe -r efifb 2>&1; echo rc=$?")
line(f"  rc={rc} out={out[:200]} err={err[:200]}")
if rc == 0:
    line("  efifb unloaded! Re-check fb0:")
    rc, out, _ = sh("cat /sys/class/graphics/fb0/name 2>&1")
    line(f"  /sys/class/graphics/fb0/name: {out}")

line("")
line("=== VERDICT ===")
line("  重点看:")
line("  - [pci_class] 有几个 0x03 class 设备 (1=IGD 集成, 2+=有独显)")
line("  - [fb0_driver] driver 是 efifb 还是 amdgpu")
line("  - [modules] amdgpu 加载了吗")
line("  - [dmesg] amdgpu init 信息里 'kfd' 'drm' 'ATOM' 'fb' 关键词")
line("  - [try_unload] 如果 efifb 卸载成功 + amdgpu 接管 fb0 = 修好")
line("  - 如果 efifb 卸载失败 (lock / busy / not loaded) = 需要别的方法")