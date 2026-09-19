# PUBLISHING

Everything you need to do once before pushing your first release. Going
through this list takes about 20 minutes. After that, the
[release workflow](.github/workflows/release.yml) does the rest on every
`v*.*.*` tag.

## 1. Create the GitHub repository

- Owner: your personal or org account.
- Visibility: **public** (required for HACS and HA Supervisor to fetch).
- Do **not** initialise with README / .gitignore / license — we already
  have all of those.

```bash
cd haos-ha
git init
git add .
git commit -m "Initial commit — HAOS Dashboard for HA"
gh repo create neon9809/haos-ha --public --source=. --push
# or: git remote add origin git@github.com:neon9809/haos-ha.git
#     git branch -M main
#     git push -u origin main
```

## 2. Repository settings (one-time)

### General

- **Default branch**: `main`
- **Allow squash merging**: on
- **Allow auto-merge**: on

### Branches — branch protection on `main`

- Require a pull request before merging: **on**
- Require approvals: 1
- Dismiss stale pull request approvals when new commits are pushed: on
- Require status checks to pass before merging: on
  - Require branches to be up to date before merging: on
  - Search for `lint`, `test`, `integration-smoke` and select them
- Require linear history: on (optional)

### Secrets

`.github/workflows/release.yml` doesn't need any custom secret — it uses
the built-in `GITHUB_TOKEN` to push images to GHCR. Nothing to set.

If you later add code-signing or signed tags, add those secrets here.

## 3. GitHub Container Registry (GHCR) package visibility

The release workflow pushes images to
`ghcr.io/<OWNER>/haos-fb-<arch>`. By default GHCR packages are
**private** — Home Assistant Supervisor won't be able to pull them.

After the first release run:

1. Open https://github.com/orgs/<ORG>/packages (or your user packages page).
2. Find `haos-fb` (and the `-aarch64` / `-amd64` / `-armv7` /
   `-armhf` / `-i386` siblings).
3. Package settings → **Danger Zone** → **Change package visibility** →
   **Public**.

Repeat for every architecture and for the multi-arch manifest
(`haos-fb` itself).

> Tip: do this **after** the first successful release so the images exist.

## 4. HA Supervisor add-on repository

HA OS discovers the add-on by reading the repo's
`haos_fb/config.yaml` (or pointing at a subdirectory that
contains it). Two ways to register:

### A. Via a GitHub Pages site or repository file

The repo URL you paste into HA Supervisor → Add-ons → ⋮ → Repositories is
literally a Git URL. Examples:

- Public root: `https://github.com/neon9809/haos-ha`
- Branch / subfolder (some people prefer this):
  `https://github.com/neon9809/haos-ha#haos_fb`

Either works. The Supervisor fetches `config.yaml` from the path it
infers; for the second form it appends `haos_fb/` to find it.

### B. Local install (no internet on the NAS)

Drop `haos_fb/` into `/config/addons/haos_fb/` on the
HA host and **Settings → Add-ons → ⋮ → Reload**. The add-on appears under
"Local".

## 5. HACS submission

HACS has two distribution modes:

- **Custom Repository** — added by the user per install. You can document
  this in the README ("Add `https://github.com/neon9809/haos-ha`
  as a Custom Repository in HACS, category Integration"). Users install
  it themselves. No review needed.
- **Default Repository** — listed in HACS by default. Requires a PR
  to https://github.com/hacs/default with the integration details, and
  only accepted if it meets the [HACS quality scale](https://www.hacs.xyz/docs/publish/start)
  (we're targeting that — see `quality_scale: silver` in our manifest).

For first release: ship as Custom Repository only. Promote to Default
after a few weeks of stable feedback.

### HACS validation checklist (before submitting)

- [x] Integration has `config_flow: true`
- [x] `manifest.json` includes `codeowners`, `issue_tracker`, `iot_class`
- [x] Integration passes `hacs-actions/action-hacs-validate` (runs in
      the `lint` job via the `validate-hacs` step in CI; we already
      validate the essentials manually here)
- [x] `info.md` and `README.md` are present at the repo root with the
      install instructions above
- [x] No `print()` calls in production code
- [x] No `dev.py` / `tests/` artifacts in the release ZIP

## 6. First release

```bash
# 1. Make sure version is bumped in haos_fb/config.yaml
#    (also bump custom_components/haos/manifest.json if needed)
git diff                 # sanity check
git add -A
git commit -m "Release v1.0.0"

# 2. Tag and push — the release workflow runs on this tag
git tag v1.0.0
git push origin main v1.0.0

# 3. Watch the workflow
gh run watch

# 4. When done:
#    - GHCR images are public (Section 3)
#    - A Release with the integration zip appears at
#      https://github.com/neon9809/haos-ha/releases/tag/v1.0.0
#    - Users can install via:
#      * HACS Custom Repository
#      * Add-on Store → Repositories → paste the repo URL
```

## 7. Smoke test on a real HA OS install

Before announcing:

1. Fresh HA OS VM (or test rig). Minimum: HDMI-capable host.
2. HACS → add Custom Repository → install.
3. Add-ons → add Repository → paste repo URL → install
   `HAOS Dashboard Display`.
4. Start the add-on; verify `binary_sensor.haos_display_running`
   becomes `on` and the screen shows the dashboard.
5. Verify all 6 pages cycle at the configured interval.
6. Pull the power: screen freezes on last frame with red `OFFLINE`
   badge. Reconnect: green dot returns within a refresh interval.

If any step fails, that's a release blocker — fix and re-tag.

## 8. Post-release housekeeping

- Update `CHANGELOG.md` if you maintain one.
- If you've submitted to HACS default, update the
  [default integration list](https://github.com/hacs/default).
- Pin the release in the GitHub Releases sidebar so users see what's
  latest.
- Share in the
  [fnOS / Home Assistant communities](https://community.home-assistant.io/)
  with screenshots of the dashboard.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `pull access denied` when HA pulls add-on image | GHCR package is still private (Section 3) |
| Add-on shows "No valid add-on repository" | `config.yaml` not found at the expected path; check the URL form in Section 4 |
| `permission denied` opening `/dev/fb0` | Add-on YAML missing `devices:` block, or `run_as: root` not set in the Dockerfile |
| Integration shows no sensors after restart | Check HA logs; psutil sometimes fails on locked-down hosts — `chmod a+rx /proc` or similar |
| HACS validation fails on `no-icon` | Add a `brands/` icon and reference it from `manifest.json` |
| CI release fails on `denied: requested access to the resource is denied` | The `GITHUB_TOKEN` lacks `packages: write`; check the workflow's `permissions:` block |

---

Once this list is done once, every subsequent release is a
`git tag v1.x.y && git push origin v1.x.y` away.