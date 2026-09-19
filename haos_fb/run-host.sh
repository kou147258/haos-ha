#!/bin/bash
# Bootstrap script: install HAOS Dashboard Display as a host-side systemd
# service on HAOS.
#
# Usage (in HAOS host shell):
#     bash run-host.sh install        # copies files into /data/etc/services/haos_fb
#                                    # + enables + starts the systemd service
#     bash run-host.sh uninstall      # removes service + files
#     bash run-host.sh status         # journalctl -u haos_fb -n 50
#     bash run-host.sh restart        # systemctl restart haos_fb
#
# Why host-side, not add-on container?
# -------------------------------------
# HAOS x86_64 Supervisor's kiosk-mode rejects iomem mmap from user-namespace
# containers even with full_access: true. Running fb_render.py as a host
# systemd service bypasses the user-namespace LSM hook entirely; host root
# can mmap /dev/fb0 directly the same way the original fnos-dashboard
# does on fnOS.

set -euo pipefail

SERVICE_NAME="haos_fb"
INSTALL_DIR="/data/etc/services/${SERVICE_NAME}"
UNIT_SRC="$(cd "$(dirname "$0")" && pwd)/systemd/${SERVICE_NAME}.service"

usage() {
    sed -n '2,30p' "$0"
    exit 1
}

ensure_unit_src() {
    if [[ ! -f "$UNIT_SRC" ]]; then
        echo "Cannot find unit file at: $UNIT_SRC" >&2
        echo "Re-extract haos_fb/systemd/${SERVICE_NAME}.service from the zip first." >&2
        exit 1
    fi
}

install_service() {
    ensure_unit_src
    echo "==> Installing ${SERVICE_NAME} service into ${INSTALL_DIR}"

    # 1. Lay out files in /data/etc/services (the only fully-writable
    #    tree on a HAOS host).
    mkdir -p "${INSTALL_DIR}"
    cp -f "$(dirname "$0")/fb_render.py"    "${INSTALL_DIR}/"
    cp -f "$(dirname "$0")/themes.py"        "${INSTALL_DIR}/"
    cp -f "$(dirname "$0")/font.py"         "${INSTALL_DIR}/"
    cp -f "$(dirname "$0")/options.example.json" "${INSTALL_DIR}/options.json" 2>/dev/null \
        || cp -f "$(dirname "$0")/options.example.json" "${INSTALL_DIR}/"

    chmod +x "${INSTALL_DIR}/fb_render.py"

    # 2. Install the systemd unit. HAOS allows writes to
    #    /etc/systemd/system/ via the supervisor's `ha services` plumbing
    #    in some versions, but a direct symlink from /data works on every
    #    HAOS build I've seen — systemd follows symlinks transparently.
    if [[ -d /etc/systemd/system ]] && [[ -w /etc/systemd/system ]]; then
        ln -sf "${UNIT_SRC}" "/etc/systemd/system/${SERVICE_NAME}.service"
        systemctl daemon-reload
    else
        echo "Cannot write /etc/systemd/system; please symlink manually:"
        echo "    ln -s ${UNIT_SRC} /etc/systemd/system/${SERVICE_NAME}.service"
        echo "    systemctl daemon-reload"
        exit 1
    fi

    # 3. Enable + start.
    systemctl enable "${SERVICE_NAME}.service"
    systemctl restart "${SERVICE_NAME}.service"
    sleep 1
    echo "==> ${SERVICE_NAME} is now running. Check the log:"
    echo "    journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
}

uninstall_service() {
    if [[ -L "/etc/systemd/system/${SERVICE_NAME}.service" ]]; then
        systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
        systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true
        rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
        systemctl daemon-reload
    fi
    rm -rf "${INSTALL_DIR}"
    echo "==> ${SERVICE_NAME} removed."
}

cmd="${1:-}"
case "$cmd" in
    install)   install_service ;;
    uninstall) uninstall_service ;;
    status)    journalctl -u "${SERVICE_NAME}" -n 50 --no-pager ;;
    restart)   systemctl restart "${SERVICE_NAME}.service" ;;
    *)         usage ;;
esac