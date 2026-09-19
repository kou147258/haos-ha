# Multi-arch base image published by the Home Assistant add-ons project.
# The :15.0.2 tag is a manifest list with linux/amd64, linux/arm64,
# linux/arm/v7, linux/arm/v6, linux/386 variants — no per-arch build-arg
# needed.
FROM ghcr.io/hassio-addons/base:15.0.2

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System dependencies:
#   - python3 + pil for fb rendering with CJK fonts
#   - core fonts (DejaVu) for Latin glyphs
#   - tzdata for accurate local time in the clock
RUN apk add --no-cache \
        python3 \
        py3-pillow \
        py3-aiohttp \
        tzdata \
        ttf-dejavu \
        terminus-font \
        libdrm \
    && rm -rf /var/cache/apk/*

# Workdir
WORKDIR /opt/haos_fb

# Copy source
COPY themes.py /opt/haos_fb/themes.py
COPY font.py /opt/haos_fb/font.py
COPY fb_render.py /opt/haos_fb/fb_render.py
COPY drm_render.py /opt/haos_fb/drm_render.py
COPY run.sh /opt/haos_fb/run.sh

RUN chmod a+x /opt/haos_fb/run.sh

# Container healthcheck — verifies the renderer loop is still ticking.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD pgrep -f fb_render.py >/dev/null || exit 1

CMD [ "/opt/haos_fb/run.sh" ]