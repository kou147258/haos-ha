"""Constants for the HAOS Dashboard integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "haos"
MANUFACTURER = "Generic Linux Host"
DEFAULT_NAME = "HAOS Dashboard"

# Service / addon
ADDON_SLUG = "haos_fb"

# Coordinator polling defaults — matches the original fb_render cadence
DEFAULT_SCAN_INTERVAL = timedelta(seconds=2)
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 30

# Options
CONF_REFRESH_INTERVAL = "refresh_interval"
CONF_TEMP_UNIT = "temp_unit"
DEFAULT_TEMP_UNIT = "C"
TEMP_UNITS = ("C", "F")

# How often to refresh the add-on / Supervisor status
ADDON_STATUS_INTERVAL = timedelta(seconds=10)

# Filesystem types that are not real physical disks to surface as entities.
SKIP_FS_TYPES = frozenset({
    "", "tmpfs", "devtmpfs", "squashfs", "overlay",
    "efivarfs", "autofs", "proc", "sysfs", "cgroup", "cgroup2", "devpts",
})