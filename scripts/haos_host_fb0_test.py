#!/usr/bin/env python3
"""HAOS host 端 /dev/fb0 mmap 最小测试

目的：在 HAOS 宿主机（不是 supervisor add-on container）上确认
- /dev/fb0 mmap 是否成功
- /dev/dri/* DRM 节点是否 init
- Python 依赖 (PIL, aiohttp) 是否可用
- HA REST API 是否可达

跑法（HAOS host shell，root 或 sudo）：
    python3 /tmp/host_fb0_test.py

输出：6 段结果，最后一段告诉你 mmap 是否能用
"""
import os
import mmap
import sys
import urllib.request


def banner(s):
    print()
    print("=" * 60)
    print(s)
    print("=" * 60)


def section(n, title):
    print(f"\n[{n}] {title}")


def main():
    banner("HAOS host framebuffer test")
    print(f"uid={os.getuid()} euid={os.geteuid()} pid={os.getpid()}")
    print(f"python={sys.version.split()[0]}")
    print(f"cwd={os.getcwd()}")

    section(1, "/dev/fb0 存在性")
    print(f"exists: {os.path.exists('/dev/fb0')}")
    print(f"is_chr: {os.path.ischr('/dev/fb0')}")
    try:
        st = os.stat("/dev/fb0")
        print(f"stat: mode={oct(st.st_mode)} uid={st.st_uid} gid={st.st_gid} size={st.st_size}")
    except OSError as e:
        print(f"stat FAIL: errno={e.errno} ({e.strerror})")

    section(2, "sysfs framebuffer 元信息")
    for p in [
        "/sys/class/graphics/fb0/name",
        "/sys/class/graphics/fb0/virtual_size",
        "/sys/class/graphics/fb0/bits_per_pixel",
        "/sys/class/graphics/fb0/stride",
        "/sys/class/graphics/fb0/smem_len",
    ]:
        try:
            with open(p) as f:
                print(f"  {p}: {f.read().strip()}")
        except OSError as e:
            print(f"  {p}: FAIL errno={e.errno} ({e.strerror})")

    section(3, "/dev/dri/* DRM 节点")
    try:
        entries = sorted(os.listdir("/dev/dri"))
        print(f"entries: {entries}")
        for e in entries:
            p = f"/dev/dri/{e}"
            try:
                st = os.stat(p)
                print(f"  {p}: mode={oct(st.st_mode)} uid={st.st_uid}")
            except OSError as e:
                print(f"  {p}: stat FAIL errno={e.errno} ({e.strerror})")
    except OSError as e:
        print(f"FAIL errno={e.errno} ({e.strerror})")

    section(4, "尝试 mmap /dev/fb0 (8MB)")
    SIZE = 8 * 1024 * 1024
    try:
        fd = os.open("/dev/fb0", os.O_RDWR)
        print(f"  open: OK fd={fd}")
        try:
            m = mmap.mmap(fd, SIZE, mmap.MAP_SHARED, prot=mmap.PROT_READ | mmap.PROT_WRITE)
            print(f"  mmap: OK len={len(m)}")
            sample = m[:16]
            print(f"  sample head bytes: {sample.hex()}")
            # 试着写一个字节看是否真能写
            try:
                m[0:4] = b"\xff\x00\x00\x00"  # 红色 (32bpp BGRA)
                m.flush()
                print("  write: OK (4 bytes red at offset 0)")
            except OSError as e:
                print(f"  write FAIL: errno={e.errno} ({e.strerror})")
            m.close()
        except OSError as e:
            print(f"  mmap FAIL: errno={e.errno} ({e.strerror})")
        os.close(fd)
    except OSError as e:
        print(f"  open FAIL: errno={e.errno} ({e.strerror})")

    section(5, "Python 依赖可用性")
    for mod_name, attr in [("PIL", "Image"), ("aiohttp", None)]:
        try:
            mod = __import__(mod_name)
            if attr:
                getattr(mod, attr)
            print(f"  {mod_name}: OK" + (f" (has {attr})" if attr else ""))
        except ImportError as e:
            print(f"  {mod_name}: MISSING ({e})")

    section(6, "HA REST API 可达性")
    HA = "http://192.168.9.10:8123"
    try:
        req = urllib.request.Request(f"{HA}/api/", method="GET")
        with urllib.request.urlopen(req, timeout=3) as r:
            print(f"  GET {HA}/api/: status={r.status}")
            body = r.read(200)
            print(f"  body head: {body[:80].decode(errors='replace')}")
    except Exception as e:
        print(f"  HA REST FAIL: {type(e).__name__}: {e}")

    section(7, "检查 pip 是否可用（装 PIL 前提）")
    for p in ["/usr/bin/pip3", "/usr/bin/pip", "/usr/local/bin/pip3"]:
        if os.path.exists(p):
            print(f"  {p}: exists")
        else:
            print(f"  {p}: missing")
    try:
        import subprocess
        out = subprocess.run(["pip3", "--version"], capture_output=True, text=True, timeout=5)
        print(f"  pip3 --version: rc={out.returncode}")
        if out.stdout:
            print(f"  stdout: {out.stdout.strip()}")
        if out.stderr:
            print(f"  stderr: {out.stderr.strip()}")
    except Exception as e:
        print(f"  pip3 probe FAIL: {e}")

    banner("done")
    print()
    print("如果上面 [4] mmap OK，说明 HAOS host 端 mmap /dev/fb0 成功。")
    print("如果 [4] mmap FAIL，那是 kernel LSM 限制（不应该，host 是 root）。")
    print("如果 [5] PIL/aiohttp MISSING，需要装 pip install Pillow aiohttp。")
    print("如果 [6] HA REST FAIL，确认 IP 192.168.9.10:8123 可达。")


if __name__ == "__main__":
    main()