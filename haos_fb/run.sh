#!/usr/bin/with-contenv bashio
# ==============================================================================
# HAOS Dashboard Display — add-on entry point
# Reads the add-on options from the Supervisor and launches the renderer.
# ==============================================================================
set -e

CONFIG_JSON=/data/options.json

if [ ! -f "$CONFIG_JSON" ]; then
    bashio::log.warning "options.json not found at $CONFIG_JSON; using built-in defaults"
    CONFIG_JSON=/opt/haos_fb/defaults.json
fi

bashio::log.info "Starting HAOS Dashboard Display..."
exec python3 /opt/haos_fb/fb_render.py \
    --config "$CONFIG_JSON"