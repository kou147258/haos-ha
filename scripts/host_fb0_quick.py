#!/usr/bin/env python3
"""HAOS host 最小 fb0 mmap 测试（精简版）

用法（HAOS host shell，root）：
    python3 /tmp/host_fb0_quick.py

输出 [OK]/[FAIL] 行，最后给结论。
"""
import os, mmap, sys

def line(s): print(s, flush=True)

line("=== HAOS host fb0 quick test ===")
line(f"uid={os.getuid()} euid={os.geteuid()}")

# /dev/fb0 sysfs 元信息
try:
    with open("/sys/class/graphics/fb0/name") as f:
        line(f"[fb0_name] {f.read().strip()}")
except Exception as e:
    line(f"[fb0_name] FAIL {e}")

try:
    with open("/sys/class/graphics/fb0/virtual_size") as f:
        line(f"[fb0_size] {f.read().strip()}")
except Exception as e:
    line(f"[fb0_size] FAIL {e}")

# /dev/dri
try:
    dri = sorted(os.listdir("/dev/dri"))
    line(f"[dri] entries={dri}")
except Exception as e:
    line(f"[dri] FAIL {e}")

# mmap /dev/fb0
fb_ok = False
try:
    fd = os.open("/dev/fb0", os.O_RDWR)
    try:
        m = mmap.mmap(fd, 8*1024*1024, mmap.MAP_SHARED, prot=mmap.PROT_READ|mmap.PROT_WRITE)
        m[0:4] = b"\xff\x00\x00\x00"
        m.flush()
        line(f"[mmap] OK sample={m[:8].hex()}")
        fb_ok = True
        m.close()
    except OSError as e:
        line(f"[mmap] FAIL errno={e.errno} ({e.strerror})")
    os.close(fd)
except OSError as e:
    line(f"[open] FAIL errno={e.errno} ({e.strerror})")

# Python deps
for mod in ["PIL", "aiohttp"]:
    try:
        __import__(mod)
        line(f"[dep:{mod}] OK")
    except ImportError as e:
        line(f"[dep:{mod}] MISSING ({e})")

# pip 可用
try:
    import subprocess
    r = subprocess.run(["pip3","--version"], capture_output=True, text=True, timeout=5)
    line(f"[pip3] rc={r.returncode} out={r.stdout.strip()}")
except Exception as e:
    line(f"[pip3] FAIL {e}")

# HA REST
try:
    import urllib.request
    with urllib.request.urlopen("http://192.168.9.10:8123/api/", timeout=3) as r:
        line(f"[ha_rest] status={r.status}")
except Exception as e:
    line(f"[ha_rest] FAIL {type(e).__name__}: {e}")

line("=== done ===")
line("VERDICT: " + ("host mmap /dev/fb0 OK" if fb_ok else "host mmap /dev/fb0 FAIL"))