#!/usr/bin/env python3
"""HAOS host fb0 EPERM 根因诊断

在 SSH 进来的 root shell 跑这个，看 EPERM 是 logind seat / device cgroup /
udev ACL / 哪个层挡的。

输出关键行：[dev_perm], [udev], [cgroup_dev], [seats], [loginctl]
"""
import os, subprocess, sys

def line(s): print(s, flush=True)

def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True, **kw)
    return r.returncode, r.stdout, r.stderr

line("=== HAOS host fb0 EPERM 诊断 ===")
line(f"uid={os.getuid()} euid={os.geteuid()} pid={os.getpid()}")
line("")

# 1. 当前 session / seat 信息
line("[seats] loginctl show-session / show-seat")
for cmd in [
    "loginctl 2>&1 | head -20",
    "loginctl show-seat seat0 2>&1",
    "loginctl list-sessions 2>&1 | head -10",
    "loginctl show-session $(loginctl list-sessions --no-legend | awk '{print $1}' | head -1) 2>&1",
]:
    rc, out, err = sh(cmd)
    if out.strip():
        line(f"  $ {cmd}")
        for ln in out.strip().splitlines()[:8]:
            line(f"    {ln}")
        if err.strip():
            line(f"    (stderr) {err.strip()[:200]}")
line("")

# 2. /dev/fb0 权限和设备号
line("[dev_perm] ls -l /dev/fb*")
rc, out, _ = sh("ls -l /dev/fb* 2>&1")
for ln in out.splitlines():
    line(f"  {ln}")
line("")

line("[dev_node] stat /dev/fb0 + major:minor")
rc, out, _ = sh("stat /dev/fb0 2>&1; cat /proc/misc 2>&1 | grep -i fb")
for ln in out.splitlines()[:6]:
    line(f"  {ln}")
line("")

# 3. 当前进程在哪个 cgroup? 有没有 device cgroup 限制?
line("[cgroup_self] /proc/self/cgroup + cgroup device list")
try:
    with open("/proc/self/cgroup") as f:
        line(f"  cgroup: {f.read().strip()[:300]}")
except Exception as e:
    line(f"  FAIL {e}")

# 检查 systemd 风格的 cgroup v2 device list
for path in [
    "/sys/fs/cgroup/system.slice/devices.list",  # v1
    "/sys/fs/cgroup/devices.list",               # v1 root
    "/sys/fs/cgroup/system.slice/devices.allow",  # legacy
]:
    if os.path.exists(path):
        try:
            with open(path) as f:
                line(f"  {path}: {f.read().strip()[:200]}")
        except OSError as e:
            line(f"  {path}: FAIL {e}")
    else:
        line(f"  {path}: (not present)")
line("")

# cgroup v2: 当前进程所在的 cgroup + device 限制
try:
    cg = os.readlink("/proc/self/cgroup")
    line(f"  /proc/self/cgroup symlink: {cg}")
except OSError as e:
    line(f"  /proc/self/cgroup symlink FAIL {e}")
# cgroup v2 自有 device controller
for p in [
    "/sys/fs/cgroup/system.slice/devices",
    "/sys/fs/cgroup/user.slice/devices",
]:
    if os.path.exists(p):
        try:
            files = sorted(os.listdir(p))
            line(f"  {p}/: {files[:20]}")
            for f in ["devices.list", "devices.allow", "devices.deny"]:
                fp = f"{p}/{f}"
                if os.path.exists(fp):
                    with open(fp) as fh:
                        line(f"    {fp}: {fh.read().strip()[:200]}")
        except OSError as e:
            line(f"  {p}/ FAIL {e}")
line("")

# 4. udev rules for fb0
line("[udev] udevadm info /sys/class/graphics/fb0")
rc, out, _ = sh("udevadm info /sys/class/graphics/fb0 2>&1 | head -30")
for ln in out.splitlines()[:25]:
    line(f"  {ln}")
line("")

# 5. 当前进程 group + 是否 video / tty / systemd-journal
line("[groups] id + groups")
rc, out, _ = sh("id 2>&1")
line(f"  {out.strip()}")
for grp in ["video", "tty", "input", "render", "kvm", "disk"]:
    rc, out, _ = sh(f"getent group {grp} 2>&1")
    if out.strip():
        line(f"  {grp}: {out.strip()}")
line("")

# 6. systemd-logind 当前状态（active?）
line("[logind] systemctl status systemd-logind")
rc, out, _ = sh("systemctl is-active systemd-logind 2>&1; systemctl status systemd-logind --no-pager 2>&1 | head -10")
for ln in out.splitlines()[:8]:
    line(f"  {ln}")
line("")

# 7. 关键对照：用 setsid 拿新 session 试试？或者用脚本打开？
line("[*] 试试用 su -l root 重新登录拿新 session 跑 mmap")
rc, out, _ = sh("su -l root -c 'python3 -c \"import os, mmap; "
                "fd=os.open(\\\"/dev/fb0\\\", os.O_RDWR); "
                "m=mmap.mmap(fd, 8*1024*1024, mmap.MAP_SHARED, prot=mmap.PROT_READ|mmap.PROT_WRITE); "
                "print(\\\"OK sample=\\\", m[:8].hex()); m.close()\\\"' 2>&1")
line(f"  $ su -l root -c '...mmap /dev/fb0...'")
for ln in out.splitlines()[:8]:
    line(f"    {ln}")
line("")

# 8. dbus / seat assignment
line("[dbus_seat] loginctl seat-status / can ssh see seat0?")
rc, out, _ = sh("ls -la /run/systemd/seats/ 2>&1")
for ln in out.splitlines()[:5]:
    line(f"  /run/systemd/seats/: {ln}")
rc, out, _ = sh("loginctl attach seat0 $$ 2>&1; echo rc=$?")
line(f"  loginctl attach seat0 $$: {out.strip()[:200]}")

line("")
line("=== done ===")
line("重点看：")
line("  - [seats] 当前 ssh shell 是不是 attached to seat0")
line("  - [cgroup_*] 有没有 device cgroup 限制 (a *:* rwm 之类)")
line("  - [dev_perm] /dev/fb0 是 root:video 还是其他")
line("  - [groups] 当前 uid 在哪个 group")
line("  - [*] su -l root 跑 mmap 能不能成功（如果能，问题就在 ssh 进程跟 console session 区别）")