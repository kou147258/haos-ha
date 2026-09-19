#!/usr/bin/env bash
# init-git.sh — one-shot bootstrap: git init + initial commit + (optionally)
# create the GitHub repo + push.
#
# Usage:
#   ./init-git.sh                   # just init + commit (no push)
#   ./init-git.sh YOUR_GH_USER       # init + commit + create + push
#
# Requires `gh` CLI for the create+push path.
set -euo pipefail

USER="${1:-}"

# 1) Init if needed
if [ ! -d .git ]; then
    echo "[1/4] git init"
    git init -b main
else
    echo "[1/4] .git already exists — skipping init"
fi

# 2) House-keeping — drop local-only artefacts (preview outputs, caches).
echo "[2/4] cleaning local-only files"
rm -rf .pytest_cache __pycache__ */__pycache__ */*/__pycache__
find . -name '*.pyc' -delete
rm -f dev-overview.png dev-overview-test.png preview_*.png
rm -f pytest-out.log out.log err.log p.log _check_yaml.py _debug_run.py _debug_addon.py

# 3) Stage + commit
echo "[3/4] git add + commit"
git add .
git diff --cached --quiet || git commit -m "Initial commit — HAOS Dashboard for Home Assistant

- HA custom integration: system monitor sensors (CPU / memory / disk /
  network / temperature / info) plus a Supervisor add-on controller.
- HA Supervisor add-on: writes system stats to /dev/fb0 via mmap, with
  PIL+ASCII dual font backend, 6 themes, 12 accent colors, fb lock,
  OFFLINE state preservation.
- --dump-png dev preview (no /dev/fb0 needed)
- Tests (52 pytest cases) covering themes / fonts / coordinator /
  entity value extraction / Supervisor add-on helpers
- CI (lint + pytest + multi-arch Docker + GitHub Release)"

# 4) Push (only if USER provided + gh is installed + remote not set yet)
if [ -n "$USER" ] && command -v gh >/dev/null 2>&1; then
    if git remote get-url origin >/dev/null 2>&1; then
        echo "[4/4] origin already set — skipping gh repo create"
    else
        echo "[4/4] gh repo create $USER/haos-ha --public --source=. --push"
        gh repo create "$USER/haos-ha" --public --source=. --push || {
            echo "gh repo create failed — repo may already exist. Add remote manually:"
            echo "  git remote add origin git@github.com:$USER/haos-ha.git"
            echo "  git push -u origin main"
        }
    fi
elif [ -n "$USER" ]; then
    echo "[4/4] gh CLI not found — push manually:"
    echo "  git remote add origin git@github.com:$USER/haos-ha.git"
    echo "  git push -u origin main"
else
    echo "[4/4] no GitHub user given — push manually:"
    echo "  git remote add origin git@github.com:<YOUR_USER>/haos-ha.git"
    echo "  git push -u origin main"
fi

echo ""
echo "Done. After the first push, also:"
echo "  1) On GitHub: Settings → Branches → protect main"
echo "  2) After first tagged release: GHCR packages → set to Public"
echo "  3) See PUBLISHING.md for the full checklist"