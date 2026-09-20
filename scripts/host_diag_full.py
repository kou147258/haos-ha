#!/usr/bin/env python3
"""HAOS host 综合诊断: cgroup v2 device 白名单 + systemd-logind seat + 网络 + mmap

输出聚焦 5 个关键问题:
  Q1: cgroup v2 device 白名单里有没有 /dev/fb0 (major:29 minor:0)
  Q2: 当前 ssh 进程是否 attached to seat0 (systemd-logind)
  Q3: /dev/fb0 设备节点 owner/group/perms 跟 fs mode
  Q4: host shell 网络到 192.168.9.10:8123 是否可达 (HA REST)
  Q5: 直接 mmap /dev/fb0 在 root ssh 进程下到底失败在哪一层

跑法 (HAOS host shell, root):
    curl -fsSL https://raw.githubusercontent.com/kou147258/haos-ha/main/scripts/host_diag_full.py -o /tmp/diag.py
    python3 /tmp/diag.py
"""
import os, subprocess, sys, socket, struct

def line(s="", **kw):
    print(s, flush=True, **kw)

def sh(cmd, timeout=10):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       shell=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def hr(title):
    line()
    line("=" * 64)
    line(f"  {title}")
    line("=" * 64)


# ============================================================================
hr("Q0  ENV / 身份")
# ============================================================================
line(f"uid={os.getuid()} euid={os.geteuid()} pid={os.getpid()}")
line(f"python={sys.version.split()[0]} cwd={os.getcwd()}")
rc, out, _ = sh("uname -a; cat /etc/os-release 2>/dev/null | head -3")
line(out)
rc, out, _ = sh("id; whoami; ps -p $$ -o comm=")
line(out)


# ============================================================================
hr("Q1  cgroup v2 device 白名单 (fb0 是 c 29:0)")
# ============================================================================
line("当前进程 cgroup (v2 应该是 0::/<slice>):")
try:
    with open("/proc/self/cgroup") as f:
        cgroup = f.read().strip()
        line(f"  /proc/self/cgroup: {cgroup}")
except Exception as e:
    line(f"  FAIL {e}")

# cgroup v2 自己的 cgroup (自从 kernel 5.7 unified)
try:
    cg_self = os.readlink("/proc/self/cgroup")
    line(f"  /proc/self/cgroup symlink: {cg_self}")
except OSError as e:
    line(f"  FAIL {e}")

# 找到 cgroup mount 点
rc, out, _ = sh("mount | grep -E 'cgroup2? ' 2>&1")
line(f"  cgroup mount: {out}")

# 关键: 当前 cgroup 的 device 白名单
# cgroup v2: /sys/fs/cgroup/<cgroup_path>/devices.list (read-only effective set)
candidates = []
for d in [
    "/sys/fs/cgroup/system.slice",
    "/sys/fs/cgroup/user.slice",
    "/sys/fs/cgroup/init.scope",
    "/sys/fs/cgroup",
]:
    if os.path.isdir(d):
        candidates.append(d)

for base in candidates:
    p = f"{base}/devices.list"
    if os.path.exists(p):
        try:
            with open(p) as f:
                content = f.read().strip()
            line(f"  {p}:")
            # fb0 = c 29:0
            fb0_in_list = "29:0" in content
            line(f"    contains fb0 (29:0)? {fb0_in_list}")
            for ln in content.splitlines():
                if any(x in ln for x in ["29:", "195:", "*:*", "fb"]):
                    line(f"    | {ln}")
            # 如果看到 'a *:* rwm' 表示全开
            if "a *:* rwm" in content:
                line("    *** FULL device access (a *:* rwm) ***")
        except OSError as e:
            line(f"  {p} FAIL {e}")
    else:
        line(f"  {p}: (not present)")

# 也检查 devices.allow (写入端)
for base in candidates:
    p = f"{base}/devices.allow"
    if os.path.exists(p):
        rc, out, _ = sh(f"ls -la {p} 2>&1")
        line(f"  {p}:")
        line(f"    {out}")

# 试写一次看权限
write_target = None
for base in candidates:
    p = f"{base}/devices.allow"
    if os.path.exists(p):
        write_target = p
        break

if write_target:
    line(f"\n  尝试写 'c 29:0 rwm' 到 {write_target}:")
    try:
        with open(write_target, "w") as f:
            f.write("c 29:0 rwm\n")
        line(f"    OK 写入成功 (我们有 CAP_SYS_ADMIN)")
        # 再读 devices.list 看是否生效
        list_p = write_target.replace("devices.allow", "devices.list")
        if os.path.exists(list_p):
            with open(list_p) as f:
                line(f"    新 devices.list: {f.read().strip()[:200]}")
    except OSError as e:
        line(f"    FAIL errno={e.errno} ({e.strerror})")

# ========================================================================
hr("Q2  systemd-logind seat / session")
# ========================================================================
rc, out, _ = sh("loginctl 2>&1 | head -20")
line("loginctl:")
line(out or "(empty)")

rc, out, _ = sh("loginctl list-sessions --no-legend 2>&1")
line(f"list-sessions: {out or '(empty)'}")

# 拿当前 ssh session 的 ID 和 seat 关联
session_id = None
rc, out, _ = sh("cat /proc/self/loginuid 2>&1; echo ''")
line(f"loginuid: {out}")

rc, out, _ = sh("loginctl show-session self 2>&1 | head -30")
line(f"show-session self: {out or '(empty / not in logind)'}")

rc, out, _ = sh("ls -la /run/systemd/seats/ 2>&1")
line(f"/run/systemd/seats/: {out}")

rc, out, _ = sh("ls -la /run/systemd/sessions/ 2>&1 | head -5")
line(f"/run/systemd/sessions/: {out}")

# 关键测试: loginctl attach seat0 $$
line("\n尝试 loginctl attach seat0 $$ 拿 console 设备 ACL:")
rc, out, err = sh("loginctl attach seat0 $$ 2>&1")
line(f"  rc={rc} out={out[:200]} err={err[:200]}")

# 立即重试 open /dev/fb0
fb_after_attach = False
try:
    fd = os.open("/dev/fb0", os.O_RDWR)
    line(f"  attach 后 open /dev/fb0: OK fd={fd}")
    fb_after_attach = True
    os.close(fd)
except OSError as e:
    line(f"  attach 后 open /dev/fb0: FAIL errno={e.errno} ({e.strerror})")


# ============================================================================
hr("Q3  /dev/fb0 设备节点")
# ============================================================================
rc, out, _ = sh("ls -l /dev/fb* 2>&1")
line(f"ls -l /dev/fb*: {out}")

try:
    st = os.stat("/dev/fb0")
    line(f"stat /dev/fb0: mode={oct(st.st_mode)} uid={st.st_uid} gid={st.st_gid} "
         f"rdev={oct(os.major(st.st_rdev))}:{oct(os.minor(st.st_rdev))}")
    line(f"  → major={os.major(st.st_rdev)} minor={os.minor(st.st_rdev)}")
    line(f"  → 'c 29:0 rwm' 是 fb0 的 cgroup allow 规则")
except OSError as e:
    line(f"stat FAIL {e}")

# 当前进程在不在 video 组 (gid=28)?
rc, out, _ = sh("getent group video 2>&1")
line(f"getent group video: {out}")
rc, out, _ = sh("id -G 2>&1")
line(f"当前 uid groups: {out}")


# ============================================================================
hr("Q4  host shell 网络")
# ============================================================================
# HA 默认 IP
HA_IPS = ["192.168.9.10", "192.168.9.11", "192.168.10.72"]
HA_PORT = 8123

# 当前主机网络信息
rc, out, _ = sh("ip -4 addr show 2>&1 | grep -E 'inet ' | head -10")
line(f"ip addr: {out}")

rc, out, _ = sh("ip route 2>&1")
line(f"ip route: {out}")

# DNS / resolv.conf
rc, out, _ = sh("cat /etc/resolv.conf 2>&1 | head -5")
line(f"resolv.conf: {out}")

# HA REST 可达性
line("\nHA REST API 可达性:")
for ip in HA_IPS:
    rc, out, _ = sh(f"curl -sS -o /dev/null -w '%{{http_code}}' --connect-timeout 3 "
                    f"http://{ip}:{HA_PORT}/api/ 2>&1")
    line(f"  GET http://{ip}:{HA_PORT}/api/ → {out}")

# 本机 IP 是哪个？(HA WebUI 通常报告 device IP)
rc, out, _ = sh("hostname -I 2>&1")
line(f"hostname -I: {out}")
rc, out, _ = sh("hostname 2>&1")
line(f"hostname: {out}")


# ============================================================================
hr("Q5  mmap /dev/fb0 端到端")
# ============================================================================
line("当前 ssh root 进程直接 mmap /dev/fb0:")
fb_ok = False
try:
    fd = os.open("/dev/fb0", os.O_RDWR)
    try:
        m = __import__("mmap").mmap(fd, 8*1024*1024,
                                     __import__("mmap").MAP_SHARED,
                                     prot=__import__("mmap").PROT_READ
                                          | __import__("mmap").PROT_WRITE)
        m[0:4] = b"\xff\x00\x00\x00"
        m.flush()
        line(f"  mmap OK sample={m[:8].hex()}")
        fb_ok = True
        m.close()
    except OSError as e:
        line(f"  mmap FAIL errno={e.errno} ({e.strerror})")
    os.close(fd)
except OSError as e:
    line(f"  open FAIL errno={e.errno} ({e.strerror})")


# ============================================================================
hr("VERDICT")
# ============================================================================
line()
line("Q1 cgroup v2 device list:")
line("  → 看 'contains fb0 (29:0)?' 行的 True/False")
line("  → 如果 False 且 '尝试写 ... devices.allow' 成功 → 之后可写 'c 29:0 rwm' 解决")
line("  → 如果 False 且写失败 (EACCES/EPERM) → 需要 CAP_SYS_ADMIN 走 dbus 接口")
line()
line("Q2 logind seat:")
line("  → 如果 'attach 后 open OK' → 当前 ssh 进程没 seat0 权限是根因，fb_render 用")
line("    systemd user service (不在 logind 内) 可以绕开")
line("  → 如果 'show-session self: empty' → ssh 进程不在 logind session 里")
line()
line("Q4 HA REST:")
line("  → 看 'GET http://192.168.x.x:8123/api/ → 200' 哪个 IP 通")
line("  → 如果都不通 → host 网络 namespace 隔离，需要走 Supervisor 网络或加路由")
line()
line("Q5 直接 mmap:")
line(f"  → 当前 ssh root: {'OK' if fb_ok else 'FAIL (见 Q1/Q2 分析)'}")


if __name__ == "__main__":
    pass  # all logic at module level for simplicity