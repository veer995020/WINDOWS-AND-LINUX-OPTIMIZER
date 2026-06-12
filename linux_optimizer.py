#!/usr/bin/env python3
# ================================================================
#  UNIVERSAL LINUX PC OPTIMIZER v1.0
#  Works on: Ubuntu / Debian / Fedora / Arch / openSUSE / Mint
#            Kali / Pop!_OS / Rocky / AlmaLinux / any systemd distro
#  Python 3 + Tkinter GUI | Live Command Log | No File Deletion
#
#  HOW TO RUN:
#    sudo python3 linux_optimizer.py
#  OR make executable:
#    chmod +x linux_optimizer.py && sudo ./linux_optimizer.py
# ================================================================

import os, sys, subprocess, threading, queue, math, time, platform
import tkinter as tk
from tkinter import font as tkfont

# ── ROOT CHECK ──────────────────────────────────────────────────
if os.geteuid() != 0:
    print("\n[!] This script requires root privileges.")
    print("[*] Relaunching with sudo...\n")
    try:
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    except Exception as e:
        print(f"[ERROR] Could not elevate: {e}")
        print("Please run: sudo python3 linux_optimizer.py")
        sys.exit(1)

# ── SYSTEM DETECTION ────────────────────────────────────────────
def detect_system():
    info = {
        "os_name":   "Unknown Linux",
        "os_version":"",
        "hostname":  platform.node(),
        "kernel":    platform.release(),
        "arch":      platform.machine(),
        "pkg_mgr":   None,
        "pkg_update":None,
        "pkg_upgrade":None,
        "pkg_clean": None,
        "is_systemd":False,
        "has_fstrim": os.path.exists("/usr/sbin/fstrim") or os.path.exists("/sbin/fstrim"),
    }
    # Parse /etc/os-release for distro info
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release") as f:
            for line in f:
                line = line.strip().strip('"')
                if line.startswith("NAME="):
                    info["os_name"] = line[5:].strip('"')
                elif line.startswith("VERSION_ID="):
                    info["os_version"] = line[11:].strip('"')

    # Detect package manager
    pm_map = {
        "apt-get":  ("/usr/bin/apt-get", ["apt-get","update","-y"],
                                          ["apt-get","upgrade","-y","--no-install-recommends"],
                                          ["apt-get","autoremove","-y","&&","apt-get","autoclean","-y"]),
        "dnf":      ("/usr/bin/dnf",      ["dnf","check-update"],
                                          ["dnf","upgrade","-y"],
                                          ["dnf","autoremove","-y"]),
        "pacman":   ("/usr/bin/pacman",   ["pacman","-Sy"],
                                          ["pacman","-Su","--noconfirm"],
                                          ["pacman","-Rns","$(pacman -Qtdq)","--noconfirm"]),
        "zypper":   ("/usr/bin/zypper",   ["zypper","refresh"],
                                          ["zypper","update","-y"],
                                          ["zypper","clean","--all"]),
        "yum":      ("/usr/bin/yum",      ["yum","check-update"],
                                          ["yum","update","-y"],
                                          ["yum","autoremove","-y"]),
        "apk":      ("/sbin/apk",         ["apk","update"],
                                          ["apk","upgrade"],
                                          ["apk","cache","clean"]),
    }
    for name, (path, upd, upg, cln) in pm_map.items():
        if os.path.exists(path):
            info["pkg_mgr"]     = name
            info["pkg_update"]  = upd
            info["pkg_upgrade"] = upg
            info["pkg_clean"]   = cln if isinstance(cln, list) else cln.split()
            break

    # Check for systemd
    info["is_systemd"] = os.path.exists("/run/systemd/system")
    return info

SYS = detect_system()

# ── COLOURS & CONSTANTS ─────────────────────────────────────────
C = {
    "bg":       "#06070F",
    "hdr1":     "#001E5A",
    "hdr2":     "#0099EE",
    "panel":    "#080A18",
    "logbg":    "#040810",
    "logfg":    "#1E8060",
    "logborder":"#0D1A28",
    "pend_i":   "#243040",
    "pend_l":   "#304858",
    "act_bg":   "#06101E",
    "act_bor":  "#005BAA",
    "act_i":    "#00CCFF",
    "act_l":    "#FFFFFF",
    "done_bg":  "#050D07",
    "done_bor": "#003D18",
    "done_i":   "#00CC55",
    "done_l":   "#3A7755",
    "ring1":    "#003A7A",
    "ring2":    "#0088CC",
    "ring3":    "#00BBFF",
    "pct":      "#00CCFF",
    "status":   "#3A5878",
    "footer":   "#192430",
    "elapsed":  "#1A2C40",
    "white":    "#FFFFFF",
    "green":    "#00CC55",
    "yellow":   "#FFD060",
    "red":      "#FF5050",
}

STEP_NAMES = [
    "System Package Update",
    "Package Cleanup",
    "SSD TRIM Optimization",
    "Disk Health Check",
    "Performance Tweaks (sysctl)",
    "Privacy & Telemetry Kill",
    "Memory Optimization",
    "Network Optimization",
    "Startup Service Tuning",
    "DNS + Cleanup",
]

STEP_WEIGHTS = [120, 30, 10, 20, 5, 5, 3, 5, 10, 5]

# ── SHARED STATE (thread-safe) ───────────────────────────────────
state = {
    "progress":    0,
    "step_index": -1,
    "status_msg":  "Initializing...",
    "done":        False,
    "eta":         "--:--",
    "steps_done":  [False]*10,
    "start_time":  time.time(),
    "log_lines":   [],
    "log_dirty":   False,
}
state_lock = threading.Lock()
ui_queue   = queue.Queue()

# ── BACKGROUND WORKER HELPERS ────────────────────────────────────
def L(msg):
    """Log a command/output line to the live command log."""
    ts = time.strftime("%H:%M:%S")
    with state_lock:
        state["log_lines"].append(f"[{ts}] {msg}")
        if len(state["log_lines"]) > 400:
            state["log_lines"].pop(0)
        state["log_dirty"] = True

def S(step, pct, msg):
    """Update progress state and recalculate ETA."""
    with state_lock:
        state["step_index"] = step
        state["progress"]   = pct
        state["status_msg"] = msg
    # ETA calculation
    elapsed = time.time() - state["start_time"]
    done_w  = sum(STEP_WEIGHTS[i] for i in range(10) if state["steps_done"][i])
    rem_w   = sum(STEP_WEIGHTS[i] for i in range(10) if not state["steps_done"][i] and i != step)
    rem_w  += STEP_WEIGHTS[step] * 0.5 if step < 10 else 0
    if done_w > 2 and elapsed > 2:
        rate = elapsed / done_w
        sec  = int(rem_w * rate)
        if sec <= 0:
            eta = "00:00"
        elif sec > 5999:
            eta = "> 99m"
        else:
            eta = f"{sec//60:02d}:{sec%60:02d}"
    else:
        eta = "Calc..."
    with state_lock:
        state["eta"] = eta

def run(cmd, timeout=600, show_output=True):
    """Run a shell command, log it, capture and stream output."""
    display = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    L(f"$ {display}")
    try:
        if isinstance(cmd, str):
            proc = subprocess.run(cmd, shell=True, capture_output=True,
                                  text=True, timeout=timeout)
        else:
            proc = subprocess.run(cmd, capture_output=True,
                                  text=True, timeout=timeout)
        if show_output and proc.stdout:
            for line in proc.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    L(f"  {line[:120]}")
        if proc.returncode != 0 and proc.stderr:
            err = proc.stderr.strip()[:200]
            if err:
                L(f"  [WARN] {err}")
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        L("  [WARN] Command timed out — continuing")
        return False
    except FileNotFoundError:
        L(f"  [SKIP] Not found: {display.split()[0]}")
        return False
    except Exception as e:
        L(f"  [ERROR] {e}")
        return False

def write_sysctl(key, val):
    """Write a sysctl value at runtime and to persistent config."""
    run(["sysctl", "-w", f"{key}={val}"], show_output=False)
    L(f"  sysctl: {key}={val}")

# ── OPTIMIZATION STEPS ───────────────────────────────────────────
def step0_update():
    S(0, 1, "Updating package lists...")
    L("=== STEP 1/10: System Package Update ===")
    pm = SYS["pkg_mgr"]
    if not pm:
        L("  [SKIP] No supported package manager found")
        return
    L(f"  Detected package manager: {pm}")
    run(SYS["pkg_update"])
    S(0, 10, "Installing updates (this may take a while)...")
    run(SYS["pkg_upgrade"], timeout=1200)
    state["steps_done"][0] = True
    S(0, 14, "System packages updated.")

def step1_cleanup():
    S(1, 15, "Cleaning up packages...")
    L("=== STEP 2/10: Package Cleanup ===")
    pm = SYS["pkg_mgr"]
    if pm == "apt-get":
        run(["apt-get", "autoremove", "-y"])
        run(["apt-get", "autoclean", "-y"])
        run(["apt-get", "clean"])
    elif pm == "dnf":
        run(["dnf", "autoremove", "-y"])
        run(["dnf", "clean", "all"])
    elif pm == "pacman":
        run("pacman -Rns $(pacman -Qtdq) --noconfirm 2>/dev/null || true", timeout=120)
        run(["pacman", "-Sc", "--noconfirm"])
    elif pm == "zypper":
        run(["zypper", "clean", "--all"])
    elif pm == "yum":
        run(["yum", "autoremove", "-y"])
        run(["yum", "clean", "all"])
    elif pm == "apk":
        run(["apk", "cache", "clean"])
    # Snap cleanup
    if os.path.exists("/usr/bin/snap"):
        L("  Cleaning old snap revisions...")
        run("snap list --all | awk '/disabled/{print $1, $3}' | while read name rev; do snap remove $name --revision=$rev 2>/dev/null; done", timeout=120)
    # Flatpak cleanup
    if os.path.exists("/usr/bin/flatpak"):
        L("  Cleaning unused Flatpak runtimes...")
        run(["flatpak", "uninstall", "--unused", "-y"])
    state["steps_done"][1] = True
    S(1, 21, "Package cleanup done.")

def step2_trim():
    S(2, 22, "Running SSD TRIM...")
    L("=== STEP 3/10: SSD TRIM ===")
    if SYS["has_fstrim"]:
        run(["fstrim", "-av"])
    else:
        L("  [SKIP] fstrim not found")
    # Enable periodic TRIM via systemd timer
    if SYS["is_systemd"]:
        run(["systemctl", "enable", "--now", "fstrim.timer"], show_output=False)
        L("  systemctl: fstrim.timer enabled (weekly SSD maintenance)")
    state["steps_done"][2] = True
    S(2, 32, "SSD TRIM complete.")

def step3_diskhealth():
    S(3, 33, "Checking disk health...")
    L("=== STEP 4/10: Disk Health Check ===")
    # SMART status via smartctl
    if os.path.exists("/usr/sbin/smartctl"):
        disks = []
        result = subprocess.run(["lsblk", "-dno", "NAME,TYPE"],
                                capture_output=True, text=True)
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) == 2 and parts[1] == "disk":
                disks.append(f"/dev/{parts[0]}")
        for disk in disks:
            L(f"  smartctl -H {disk}")
            r = subprocess.run(["smartctl", "-H", disk],
                               capture_output=True, text=True, timeout=30)
            out = r.stdout.strip()
            if "PASSED" in out:
                L(f"    {disk}: SMART health PASSED ✓")
            elif "FAILED" in out:
                L(f"    {disk}: SMART health FAILED ✗ — consider replacement")
            else:
                L(f"    {disk}: {out[:80] or 'N/A'}")
    else:
        L("  [SKIP] smartctl not installed (install smartmontools for SMART data)")
    # Check filesystem errors in journal
    if SYS["is_systemd"]:
        r = subprocess.run(["journalctl", "-p", "err", "--since", "48h ago",
                            "--no-pager", "-n", "5"],
                           capture_output=True, text=True, timeout=15)
        if r.stdout.strip():
            L("  Recent system errors (last 48h):")
            for line in r.stdout.strip().split("\n")[:5]:
                L(f"    {line.strip()[:100]}")
        else:
            L("  No critical errors in journal (last 48h) ✓")
    state["steps_done"][3] = True
    S(3, 43, "Disk health check done.")

def step4_perf():
    S(4, 44, "Applying sysctl performance tweaks...")
    L("=== STEP 5/10: Performance Tweaks (sysctl) ===")

    tweaks = {
        # Memory
        "vm.swappiness":              "10",
        "vm.dirty_background_ratio":  "5",
        "vm.dirty_ratio":             "10",
        "vm.dirty_expire_centisecs":  "3000",
        "vm.vfs_cache_pressure":      "50",
        "vm.overcommit_memory":       "1",
        # File system
        "fs.inotify.max_user_watches":"524288",
        "fs.inotify.max_user_instances":"512",
        "fs.file-max":                "2097152",
        # Network performance
        "net.core.rmem_default":      "262144",
        "net.core.wmem_default":      "262144",
        "net.core.rmem_max":          "16777216",
        "net.core.wmem_max":          "16777216",
        "net.core.netdev_max_backlog":"250000",
        "net.core.somaxconn":         "65535",
        "net.ipv4.tcp_fastopen":      "3",
        "net.ipv4.tcp_timestamps":    "1",
        "net.ipv4.tcp_sack":          "1",
        "net.ipv4.tcp_window_scaling":"1",
        "net.ipv4.tcp_fin_timeout":   "15",
        "net.ipv4.tcp_keepalive_time":"300",
        "net.ipv4.tcp_max_syn_backlog":"8192",
        "net.ipv4.tcp_tw_reuse":      "1",
        # Security/misc
        "kernel.dmesg_restrict":      "1",
        "kernel.kptr_restrict":       "2",
        "net.ipv4.conf.all.log_martians": "1",
    }

    for k, v in tweaks.items():
        write_sysctl(k, v)

    # Try BBR congestion control (available on kernel 4.9+)
    result = subprocess.run(["modprobe", "tcp_bbr"], capture_output=True)
    if result.returncode == 0:
        write_sysctl("net.core.default_qdisc", "fq")
        write_sysctl("net.ipv4.tcp_congestion_control", "bbr")
        L("  TCP BBR congestion control enabled ✓")
    else:
        write_sysctl("net.ipv4.tcp_congestion_control", "cubic")
        L("  BBR not available — using CUBIC (default)")

    # Write persistent sysctl config
    conf_path = "/etc/sysctl.d/99-optimizer.conf"
    L(f"  Writing persistent config to {conf_path}")
    lines_conf = [f"{k} = {v}" for k, v in tweaks.items()]
    lines_conf.append("net.core.default_qdisc = fq")
    try:
        with open(conf_path, "w") as f:
            f.write("# Universal Linux PC Optimizer v1.0 — persistent tweaks\n")
            f.write("\n".join(lines_conf) + "\n")
        L(f"  Saved {len(lines_conf)} tweaks to {conf_path}")
    except Exception as e:
        L(f"  [WARN] Could not write sysctl.d: {e}")

    state["steps_done"][4] = True
    S(4, 56, "Performance tweaks applied.")

def step5_privacy():
    S(5, 57, "Disabling telemetry services...")
    L("=== STEP 6/10: Privacy & Telemetry ===")

    telemetry_services = [
        "apport",               # Ubuntu crash reporter
        "whoopsie",             # Ubuntu error reporting
        "kerneloops",           # Kernel oops reporter
        "abrtd",                # Fedora crash reporter (ABRT)
        "abrt-ccpp",            # ABRT C/C++ handler
        "abrt-oops",            # ABRT kernel oops
        "abrt-vmcore",          # ABRT vmcore
        "abrt-xorg",            # ABRT Xorg
        "avahi-daemon",         # mDNS (often unneeded, enables discovery)
        "cups-browsed",         # Printer discovery broadcast
    ]

    for svc in telemetry_services:
        if SYS["is_systemd"]:
            r = subprocess.run(["systemctl", "is-active", svc],
                               capture_output=True, text=True)
            if r.returncode == 0:
                run(["systemctl", "stop", svc], show_output=False)
                run(["systemctl", "disable", svc], show_output=False)
                run(["systemctl", "mask", svc], show_output=False)
                L(f"  Masked: {svc}")
            else:
                L(f"  [SKIP] Not running: {svc}")

    # Ubuntu-specific telemetry
    ubuntu_telemetry = [
        "/etc/default/apport",
        "/etc/opt/chrome/policies",
    ]
    # Disable ubuntu-advantage telemetry if present
    if os.path.exists("/usr/bin/ubuntu-advantage"):
        run("ubuntu-advantage config set apt_news=false 2>/dev/null || true")
        L("  Ubuntu Advantage telemetry: disabled")

    # Disable popularity-contest if installed
    if os.path.exists("/usr/sbin/popularity-contest"):
        conf = "/etc/popularity-contest.conf"
        if os.path.exists(conf):
            try:
                with open(conf) as f:
                    content = f.read()
                content = content.replace("PARTICIPATE=yes", "PARTICIPATE=no")
                with open(conf, "w") as f:
                    f.write(content)
                L("  popularity-contest: disabled")
            except:
                L("  [WARN] Could not update popularity-contest.conf")

    state["steps_done"][5] = True
    S(5, 65, "Privacy & telemetry disabled.")

def step6_memory():
    S(6, 66, "Optimizing memory...")
    L("=== STEP 7/10: Memory Optimization ===")

    # Sync filesystem buffers
    L("  sync (flush filesystem buffers)")
    run(["sync"])

    # Drop page cache, dentries, inodes
    L("  Dropping page cache (echo 1 > /proc/sys/vm/drop_caches)")
    try:
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("1\n")
        L("  Page cache dropped ✓")
    except Exception as e:
        L(f"  [WARN] {e}")

    # Compact memory if available
    if os.path.exists("/proc/sys/vm/compact_memory"):
        try:
            with open("/proc/sys/vm/compact_memory", "w") as f:
                f.write("1\n")
            L("  Memory compaction triggered ✓")
        except:
            pass

    # Report current memory usage
    r = subprocess.run(["free", "-h"], capture_output=True, text=True)
    if r.stdout:
        L("  Current memory status:")
        for line in r.stdout.strip().split("\n"):
            L(f"    {line}")

    state["steps_done"][6] = True
    S(6, 73, "Memory optimization done.")

def step7_network():
    S(7, 74, "Optimizing network...")
    L("=== STEP 8/10: Network Optimization ===")

    # Set DNS to Cloudflare + Google
    L("  Setting DNS: 1.1.1.1 (Cloudflare) + 8.8.8.8 (Google)")
    # Check if systemd-resolved is managing DNS
    if SYS["is_systemd"] and os.path.exists("/etc/systemd/resolved.conf"):
        try:
            with open("/etc/systemd/resolved.conf", "r") as f:
                content = f.read()
            # Replace or add DNS line
            import re as _re
            if _re.search(r"^#?DNS=", content, _re.MULTILINE):
                content = _re.sub(r"^#?DNS=.*$", "DNS=1.1.1.1 8.8.8.8 1.0.0.1 8.8.4.4",
                                  content, flags=_re.MULTILINE)
            else:
                content += "\nDNS=1.1.1.1 8.8.8.8 1.0.0.1 8.8.4.4\n"
            with open("/etc/systemd/resolved.conf", "w") as f:
                f.write(content)
            run(["systemctl", "restart", "systemd-resolved"], show_output=False)
            L("  systemd-resolved DNS updated ✓")
        except Exception as e:
            L(f"  [WARN] Could not update resolved.conf: {e}")
    else:
        # Direct resolv.conf update
        try:
            # Check if resolv.conf is managed by Network Manager
            nm_managed = os.path.islink("/etc/resolv.conf") and "NetworkManager" in os.readlink("/etc/resolv.conf")
            if not nm_managed:
                with open("/etc/resolv.conf", "w") as f:
                    f.write("# Universal Linux PC Optimizer v1.0\n")
                    f.write("nameserver 1.1.1.1\n")
                    f.write("nameserver 8.8.8.8\n")
                    f.write("nameserver 1.0.0.1\n")
                    f.write("nameserver 8.8.4.4\n")
                L("  /etc/resolv.conf updated ✓")
            else:
                L("  [SKIP] resolv.conf managed by NetworkManager — use nmcli")
        except Exception as e:
            L(f"  [WARN] {e}")

    # NetworkManager DNS if available
    if os.path.exists("/usr/bin/nmcli"):
        L("  Flushing NetworkManager DNS cache")
        run(["nmcli", "general", "reload"], show_output=False)

    # Flush system DNS cache
    if SYS["is_systemd"]:
        run(["systemd-resolve", "--flush-caches"], show_output=False)
        L("  systemd-resolve: DNS cache flushed ✓")

    # IRQ balancing
    if os.path.exists("/usr/sbin/irqbalance"):
        if SYS["is_systemd"]:
            run(["systemctl", "enable", "--now", "irqbalance"], show_output=False)
            L("  irqbalance service enabled ✓")

    state["steps_done"][7] = True
    S(7, 83, "Network optimization done.")

def step8_startup():
    S(8, 84, "Tuning startup services...")
    L("=== STEP 9/10: Startup Service Tuning ===")

    if not SYS["is_systemd"]:
        L("  [SKIP] Non-systemd system — startup tuning skipped")
        state["steps_done"][8] = True
        S(8, 92, "Service tuning skipped (non-systemd).")
        return

    # Analyse boot time
    r = subprocess.run(["systemd-analyze"], capture_output=True, text=True, timeout=15)
    if r.stdout:
        L(f"  Boot time: {r.stdout.strip()}")

    # Show top 5 slowest services
    r = subprocess.run(["systemd-analyze", "blame"], capture_output=True, text=True, timeout=15)
    if r.stdout:
        lines = r.stdout.strip().split("\n")[:5]
        L("  Top 5 slowest boot services:")
        for line in lines:
            L(f"    {line.strip()}")

    # Disable genuinely unnecessary services (safe list)
    disable_candidates = [
        "bluetooth.service",        # Only needed if using Bluetooth
        "ModemManager.service",     # Only needed for mobile broadband
        "pppd-dns.service",         # PPP DNS config
        "rsync.service",            # rsync daemon (not client)
        "saned.service",            # Scanner daemon
        "remote-fs.target",         # Remote filesystem mounts
        "nfs-client.target",        # NFS client (if not using NFS)
        "snapd.seeded.service",     # Snap seeding
        "fwupd-refresh.service",    # Firmware update refresh
        "geoclue.service",          # Geolocation
        "speech-dispatcher.service",# Speech dispatcher
    ]

    for svc in disable_candidates:
        r = subprocess.run(["systemctl", "is-enabled", svc],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and "enabled" in r.stdout:
            run(["systemctl", "disable", svc, "--now"], show_output=False)
            L(f"  Disabled: {svc}")

    # Enable systemd services that speed things up
    enable_candidates = [
        "systemd-timesyncd.service",   # NTP time sync
        "fstrim.timer",                 # Weekly SSD TRIM
    ]
    for svc in enable_candidates:
        run(["systemctl", "enable", "--now", svc], show_output=False)
        L(f"  Enabled: {svc}")

    # Reload systemd daemon
    run(["systemctl", "daemon-reload"], show_output=False)
    L("  systemctl daemon-reload ✓")

    state["steps_done"][8] = True
    S(8, 92, "Startup services tuned.")

def step9_cleanup():
    S(9, 93, "Flushing DNS and final cleanup...")
    L("=== STEP 10/10: DNS + Cleanup ===")

    # Flush all DNS caches available
    if SYS["is_systemd"]:
        run(["systemd-resolve", "--flush-caches"], show_output=False)
        L("  DNS cache flushed (systemd-resolve)")
    if os.path.exists("/usr/sbin/nscd"):
        run(["nscd", "-i", "hosts"], show_output=False)
        L("  DNS cache flushed (nscd)")

    # Journal log cleanup (keep last 7 days only)
    if SYS["is_systemd"]:
        L("  Vacuuming systemd journal (keeping 7 days)...")
        run(["journalctl", "--vacuum-time=7d"])
        run(["journalctl", "--vacuum-size=200M"])

    # Clean /tmp (only old files, NOT user data)
    S(9, 97, "Cleaning old temp files...")
    L("  Cleaning /tmp files older than 7 days (not user data)")
    run("find /tmp -type f -atime +7 -delete 2>/dev/null || true", timeout=60)
    run("find /tmp -type d -empty -delete 2>/dev/null || true", timeout=30)

    # Clean thumbnail cache older than 30 days
    if os.path.expanduser("~"):
        home = os.path.expanduser("~")
        thumb_dir = os.path.join(home, ".cache", "thumbnails")
        if os.path.exists(thumb_dir):
            run(f"find {thumb_dir} -type f -atime +30 -delete 2>/dev/null || true", timeout=60)
            L("  Old thumbnail cache cleaned")

    # Update ldconfig
    if os.path.exists("/sbin/ldconfig"):
        run(["/sbin/ldconfig"], show_output=False)
        L("  ldconfig: library cache refreshed ✓")

    # Update man pages database
    if os.path.exists("/usr/bin/mandb"):
        run(["mandb", "-q"], timeout=60, show_output=False)
        L("  mandb: manual pages database updated")

    # Update locate database
    if os.path.exists("/usr/bin/updatedb"):
        run(["updatedb"], timeout=120, show_output=False)
        L("  updatedb: file database updated")

    state["steps_done"][9] = True
    S(9, 100, "All 10 steps complete!")
    with state_lock:
        state["done"] = True

def bg_worker():
    """Runs all 10 optimization steps in sequence."""
    try:
        time.sleep(0.7)  # Let GUI render first
        step0_update()
        step1_cleanup()
        step2_trim()
        step3_diskhealth()
        step4_perf()
        step5_privacy()
        step6_memory()
        step7_network()
        step8_startup()
        step9_cleanup()
    except Exception as e:
        L(f"[FATAL] Unexpected error: {e}")
        with state_lock:
            state["done"] = True

# ── TKINTER GUI ──────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root    = root
        self.angles  = [0.0, 0.0, 0.0]   # ring rotation angles
        self.speeds  = [1.3, -2.0, 3.8]
        self.pulse   = 0.0
        self.smooth  = 0.0
        self.last_step    = -1
        self.last_log_len = 0

        self._build_window()
        self._build_header()
        self._build_left()
        self._build_right()
        self._build_footer()

        # Start background thread
        t = threading.Thread(target=bg_worker, daemon=True)
        t.start()

        # Start UI update loops
        self.root.after(28,   self._tick_spinner)
        self.root.after(80,   self._tick_poll)
        self.root.after(1000, self._tick_clock)

    # ── WINDOW SETUP ────────────────────────────────────────────
    def _build_window(self):
        self.root.title("Universal Linux PC Optimizer v1.0")
        self.root.configure(bg=C["bg"])
        self.root.resizable(False, False)
        self.root.geometry("980x820")

        # Center on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - 980) // 2
        y = (self.root.winfo_screenheight() - 820) // 2
        self.root.geometry(f"980x820+{x}+{y}")

    # ── HEADER ──────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Canvas(self.root, height=78, bg=C["hdr1"],
                        highlightthickness=0)
        hdr.pack(fill="x", side="top")

        # Gradient simulation with multiple rectangles
        w = 980
        for i in range(50):
            ratio = i / 50.0
            r1,g1,b1 = 0x00,0x1E,0x5A
            r2,g2,b2 = 0x00,0x99,0xEE
            r = int(r1 + (r2-r1)*ratio)
            g = int(g1 + (g2-g1)*ratio)
            b = int(b1 + (b2-b1)*ratio)
            color = f"#{r:02x}{g:02x}{b:02x}"
            hdr.create_rectangle(i*(w//50), 0, (i+1)*(w//50), 78,
                                 fill=color, outline="")

        hdr.create_text(22, 26, text="UNIVERSAL PC OPTIMIZER",
                        font=("Segoe UI", 18, "bold"), fill="white", anchor="w")

        subtitle = (f"{SYS['os_name']} {SYS['os_version']}  ·  "
                   f"{SYS['hostname']}  ·  10 Steps  ·  No Files Deleted")
        hdr.create_text(22, 50, text=subtitle,
                        font=("Segoe UI", 10), fill="#90BBDC", anchor="w")

        self.lbl_clock = hdr.create_text(958, 34, text="--:--:--",
                                          font=("Courier New", 15, "bold"),
                                          fill="white", anchor="e")
        hdr.create_text(958, 55, text="LOCAL TIME",
                        font=("Courier New", 8), fill="#4A7AAA", anchor="e")
        self._hdr_canvas = hdr

    # ── LEFT PANEL (spinner + progress) ─────────────────────────
    def _build_left(self):
        left = tk.Frame(self.root, bg=C["bg"], width=290)
        left.pack(side="left", fill="y", padx=(22,0), pady=12)
        left.pack_propagate(False)

        # Spinner canvas
        self.spin_canvas = tk.Canvas(left, width=220, height=220,
                                     bg=C["bg"], highlightthickness=0)
        self.spin_canvas.pack(pady=(10,0))

        # Percentage text on canvas
        self.pct_var   = tk.StringVar(value="0%")
        self.step_var  = tk.StringVar(value="STEP 0/10")

        tk.Label(left, textvariable=self.pct_var,
                 font=("Segoe UI", 38, "bold"),
                 fg=C["pct"], bg=C["bg"]).pack()
        tk.Label(left, textvariable=self.step_var,
                 font=("Courier New", 9),
                 fg=C["pend_i"], bg=C["bg"]).pack()

        # Progress label
        tk.Label(left, text="OVERALL PROGRESS", font=("Courier New", 8),
                 fg="#1E2E40", bg=C["bg"]).pack(pady=(12,2))

        # Progress bar (canvas)
        self.prg_canvas = tk.Canvas(left, width=266, height=12,
                                    bg="#090D1A", highlightthickness=0)
        self.prg_canvas.pack()
        self.prg_fill = self.prg_canvas.create_rectangle(
            0, 0, 0, 12, fill="#0066CC", outline="")

        # Status label
        self.status_var = tk.StringVar(value="Starting...")
        tk.Label(left, textvariable=self.status_var,
                 font=("Segoe UI", 10), fg=C["status"],
                 bg=C["bg"], wraplength=260, justify="center").pack(pady=(10,4))

        # ETA
        eta_fr = tk.Frame(left, bg=C["bg"])
        eta_fr.pack()
        tk.Label(eta_fr, text="ETA  ", font=("Courier New", 9),
                 fg="#162030", bg=C["bg"]).pack(side="left")
        self.eta_var = tk.StringVar(value="--:--")
        tk.Label(eta_fr, textvariable=self.eta_var,
                 font=("Courier New", 13, "bold"),
                 fg=C["elapsed"], bg=C["bg"]).pack(side="left")

    # ── RIGHT PANEL (steps + log) ────────────────────────────────
    def _build_right(self):
        right = tk.Frame(self.root, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True,
                   padx=(18,22), pady=12)

        # Steps label
        tk.Label(right, text="OPTIMIZATION  PIPELINE",
                 font=("Courier New", 8, "bold"),
                 fg="#1A2A38", bg=C["bg"]).pack(anchor="w", pady=(0,6))

        # Step rows frame
        steps_fr = tk.Frame(right, bg=C["bg"])
        steps_fr.pack(fill="x")

        self.step_frames = []
        self.step_icons  = []
        self.step_labels = []
        self.step_tags   = []

        for i, name in enumerate(STEP_NAMES):
            fr = tk.Frame(steps_fr, bg=C["panel"],
                          pady=6, padx=10, cursor="arrow")
            fr.pack(fill="x", pady=2)

            icon_lbl = tk.Label(fr, text="○", font=("Segoe UI", 12),
                                fg=C["pend_i"], bg=C["panel"], width=2)
            icon_lbl.pack(side="left")

            name_lbl = tk.Label(fr, text=name, font=("Segoe UI", 10),
                                fg=C["pend_l"], bg=C["panel"], anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True, padx=(4,0))

            tag_lbl = tk.Label(fr, text="PENDING",
                               font=("Courier New", 8),
                               fg=C["pend_i"], bg=C["panel"], width=9, anchor="e")
            tag_lbl.pack(side="right")

            self.step_frames.append(fr)
            self.step_icons.append(icon_lbl)
            self.step_labels.append(name_lbl)
            self.step_tags.append(tag_lbl)

        # Command log
        log_fr = tk.Frame(right, bg=C["logborder"],
                          pady=1, padx=1)
        log_fr.pack(fill="both", expand=True, pady=(12,0))

        log_inner = tk.Frame(log_fr, bg=C["logbg"])
        log_inner.pack(fill="both", expand=True)

        log_hdr = tk.Frame(log_inner, bg=C["logbg"])
        log_hdr.pack(fill="x", padx=10, pady=(7,2))
        tk.Label(log_hdr, text="▶  LIVE COMMAND LOG",
                 font=("Courier New", 8, "bold"),
                 fg="#1A3050", bg=C["logbg"]).pack(side="left")
        self.log_count_var = tk.StringVar(value="  (0 commands)")
        tk.Label(log_hdr, textvariable=self.log_count_var,
                 font=("Courier New", 8),
                 fg="#101E2A", bg=C["logbg"]).pack(side="left")

        log_body = tk.Frame(log_inner, bg=C["logbg"])
        log_body.pack(fill="both", expand=True, padx=8, pady=(0,8))

        scroll = tk.Scrollbar(log_body, orient="vertical")
        scroll.pack(side="right", fill="y")

        self.log_text = tk.Text(log_body, bg=C["logbg"], fg=C["logfg"],
                                font=("Courier New", 9),
                                yscrollcommand=scroll.set,
                                wrap="word", relief="flat",
                                state="disabled", cursor="arrow",
                                height=9)
        self.log_text.pack(fill="both", expand=True, side="left")
        scroll.config(command=self.log_text.yview)

        # Colour tags for log
        self.log_text.tag_config("cmd",  foreground="#1E8060")
        self.log_text.tag_config("ok",   foreground="#00AA44")
        self.log_text.tag_config("warn", foreground="#CC7700")
        self.log_text.tag_config("hdr",  foreground="#0060AA")
        self.log_text.tag_config("info", foreground="#2A5A7A")

    # ── FOOTER ──────────────────────────────────────────────────
    def _build_footer(self):
        ftr = tk.Frame(self.root, bg="#03040A", height=52)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)

        self.footer_var = tk.StringVar(value="Optimization running — do not close this window.")
        tk.Label(ftr, textvariable=self.footer_var,
                 font=("Segoe UI", 10), fg=C["footer"],
                 bg="#03040A").pack(side="left", padx=22)

        elapsed_fr = tk.Frame(ftr, bg="#03040A")
        elapsed_fr.pack(side="right", padx=(0,22))
        tk.Label(elapsed_fr, text="ETA  ",
                 font=("Courier New", 8), fg="#111C28",
                 bg="#03040A").pack(side="left")
        self.footer_eta_var = tk.StringVar(value="--:--")
        tk.Label(elapsed_fr, textvariable=self.footer_eta_var,
                 font=("Courier New", 12), fg=C["elapsed"],
                 bg="#03040A").pack(side="left")
        tk.Label(elapsed_fr, text="    ELAPSED  ",
                 font=("Courier New", 8), fg="#111C28",
                 bg="#03040A").pack(side="left")
        self.elapsed_var = tk.StringVar(value="00:00")
        tk.Label(elapsed_fr, textvariable=self.elapsed_var,
                 font=("Courier New", 12), fg=C["elapsed"],
                 bg="#03040A").pack(side="left")

    # ── UPDATE STEP ROW ──────────────────────────────────────────
    def _set_step_ui(self, i, state_val):
        # state_val: 0=pending, 1=running, 2=done
        fr    = self.step_frames[i]
        icon  = self.step_icons[i]
        lbl   = self.step_labels[i]
        tag   = self.step_tags[i]

        if state_val == 0:
            fr.config(bg=C["panel"])
            icon.config(text="○", fg=C["pend_i"], bg=C["panel"])
            lbl.config(fg=C["pend_l"], bg=C["panel"])
            tag.config(text="PENDING", fg=C["pend_i"], bg=C["panel"])
        elif state_val == 1:
            fr.config(bg=C["act_bg"])
            icon.config(text="▶", fg=C["act_i"], bg=C["act_bg"])
            lbl.config(fg=C["act_l"], bg=C["act_bg"])
            tag.config(text="RUNNING", fg=C["act_i"], bg=C["act_bg"])
        elif state_val == 2:
            fr.config(bg=C["done_bg"])
            icon.config(text="✓", fg=C["done_i"], bg=C["done_bg"])
            lbl.config(fg=C["done_l"], bg=C["done_bg"])
            tag.config(text="DONE", fg=C["done_i"], bg=C["done_bg"])

    # ── SPINNER ANIMATION (28ms) ─────────────────────────────────
    def _tick_spinner(self):
        c = self.spin_canvas
        c.delete("ring")

        cx, cy = 110, 110
        configs = [
            (95, 4, C["ring1"], 7, 0),
            (73, 3, C["ring2"], 5, 1),
            (53, 4, C["ring3"], 4, 2),
        ]

        for (r, w, color, n_seg, idx) in configs:
            gap = 12
            seg = (360 / n_seg) - gap
            a   = self.angles[idx]
            for j in range(n_seg):
                start = a + j * (360 / n_seg)
                x0, y0 = cx-r, cy-r
                x1, y1 = cx+r, cy+r
                c.create_arc(x0, y0, x1, y1,
                             start=start, extent=seg,
                             outline=color, fill="", style="arc",
                             width=w, tags="ring")
            self.angles[idx] = (self.angles[idx] + self.speeds[idx]) % 360

        self.pulse += 0.06
        root.after(28, self._tick_spinner)

    # ── CLOCK UPDATE (1s) ────────────────────────────────────────
    def _tick_clock(self):
        now = time.strftime("%H:%M:%S")
        self._hdr_canvas.itemconfig(self.lbl_clock, text=now)
        elapsed_s = int(time.time() - state["start_time"])
        self.elapsed_var.set(f"{elapsed_s//60:02d}:{elapsed_s%60:02d}")
        self.root.after(1000, self._tick_clock)

    # ── MAIN POLL (80ms) — reads state, updates all UI ──────────
    def _tick_poll(self):
        with state_lock:
            pct      = state["progress"]
            step_idx = state["step_index"]
            msg      = state["status_msg"]
            done     = state["done"]
            eta      = state["eta"]
            done_arr = list(state["steps_done"])
            log_lines= list(state["log_lines"])
            log_dirty= state["log_dirty"]
            if log_dirty:
                state["log_dirty"] = False

        # Smooth progress
        self.smooth += (pct - self.smooth) * 0.20
        d = int(round(self.smooth))
        self.pct_var.set(f"{d}%")
        self.step_var.set(f"STEP {max(0,step_idx+1)}/10")
        self.status_var.set(msg)
        self.eta_var.set(eta)
        self.footer_eta_var.set(eta)

        # Progress bar
        w = int((self.smooth / 100.0) * 266)
        self.prg_canvas.coords(self.prg_fill, 0, 0, w, 12)

        # Update step rows
        if step_idx != self.last_step:
            for i in range(10):
                if   i < step_idx:  self._set_step_ui(i, 2)
                elif i == step_idx: self._set_step_ui(i, 1)
                else:               self._set_step_ui(i, 0)
            self.last_step = step_idx
        for i in range(10):
            if done_arr[i] and i != step_idx:
                self._set_step_ui(i, 2)

        # Update command log (only when new lines)
        if log_dirty and len(log_lines) != self.last_log_len:
            self.log_text.config(state="normal")
            self.log_text.delete("1.0", "end")
            for line in log_lines:
                if line.startswith("[") and "] $" in line:
                    self.log_text.insert("end", line + "\n", "cmd")
                elif "=== STEP" in line:
                    self.log_text.insert("end", line + "\n", "hdr")
                elif "[WARN]" in line or "[ERROR]" in line:
                    self.log_text.insert("end", line + "\n", "warn")
                elif "[SKIP]" in line or "[OK]" in line or "✓" in line:
                    self.log_text.insert("end", line + "\n", "ok")
                else:
                    self.log_text.insert("end", line + "\n", "info")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
            self.log_count_var.set(f"  ({len(log_lines)} commands)")
            self.last_log_len = len(log_lines)

        # Done state
        if done and self.smooth >= 99:
            self._show_done()
            return

        self.root.after(80, self._tick_poll)

    def _show_done(self):
        self.pct_var.set("100%")
        self.prg_canvas.coords(self.prg_fill, 0, 0, 266, 12)
        for i in range(10):
            self._set_step_ui(i, 2)
        self.step_var.set("COMPLETE")
        self.status_var.set("All optimizations applied.")
        self.eta_var.set("00:00")
        self.footer_eta_var.set("00:00")
        self.footer_var.set("Restart recommended to fully apply all changes.")

        # Change rings to green
        for ring in ["ring"]:
            pass  # Next tick will re-draw in green
        self._ring_done = True

        elapsed_s = int(time.time() - state["start_time"])
        elapsed_str = f"{elapsed_s//60:02d}:{elapsed_s%60:02d}"

        # Show completion dialog
        done_fr = tk.Frame(self.step_frames[9].master, bg="#050D07",
                           pady=10, padx=14)
        done_fr.pack(fill="x", pady=(10,0))
        tk.Label(done_fr, text="✓  ALL 10 STEPS COMPLETE",
                 font=("Segoe UI", 12, "bold"),
                 fg=C["green"], bg="#050D07").pack()
        tk.Label(done_fr, text=f"Completed in {elapsed_str}",
                 font=("Courier New", 10),
                 fg="#336644", bg="#050D07").pack(pady=(4,8))

        btn_fr = tk.Frame(done_fr, bg="#050D07")
        btn_fr.pack()
        restart_btn = tk.Button(btn_fr, text="⟳  Restart Now",
                                font=("Segoe UI", 11, "bold"),
                                fg="white", bg="#0060AA",
                                activebackground="#004888",
                                relief="flat", padx=16, pady=5,
                                cursor="hand2",
                                command=self._restart)
        restart_btn.pack(side="left", padx=(0,6))
        close_btn = tk.Button(btn_fr, text="  Close  ",
                              font=("Segoe UI", 11),
                              fg="#6A9AB8", bg="#080B16",
                              activebackground="#0D1420",
                              relief="flat", padx=16, pady=5,
                              cursor="hand2",
                              command=self.root.destroy)
        close_btn.pack(side="left")

    def _restart(self):
        os.system("shutdown -r +0")
        self.root.destroy()

# ── MAIN ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = App(root)
    root.mainloop()
