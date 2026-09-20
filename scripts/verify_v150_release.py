"""Verify v1.5.0 release state on GitHub and compare to v1.4.2."""
import json
import os
import urllib.request

for _k in ("HTTPS_PROXY", "HTTP_PROXY"):
    os.environ.pop(_k, None)


def fetch(path):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("User-Agent", "verify-v150")
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def main():
    repo = fetch("/repos/kou147258/haos-ha")
    print(f"repo: {repo['full_name']} default_branch={repo['default_branch']}")
    print(f"  visibility: {repo['visibility']}, archived: {repo['archived']}")
    print()

    # 1. Tags (all versions in this repo)
    tags = fetch("/repos/kou147258/haos-ha/tags?per_page=100")
    print(f"--- tags ({len(tags)} total) ---")
    for t in tags[:30]:
        print(f"  {t['name']:14}  {t['commit']['sha'][:16]}")
    print()

    # 2. Releases
    rels = fetch("/repos/kou147258/haos-ha/releases?per_page=30")
    print(f"--- releases ({len(rels)} total) ---")
    for r in rels:
        assets = [a['name'] for a in r.get('assets', [])]
        asset_summary = ', '.join(assets) if assets else '(no assets)'
        draft_marker = ' [DRAFT]' if r['draft'] else ''
        print(f"  {r['tag_name']:14}  draft={str(r['draft']):5} prerelease={str(r['prerelease']):5}{draft_marker}")
        print(f"      name: {r['name']}")
        print(f"      assets: {asset_summary}")
        print(f"      published: {r['published_at']}")
    print()

    # 3. v1.5.0 detail
    print("--- v1.5.0 detail ---")
    v150 = fetch("/repos/kou147258/haos-ha/releases/tags/v1.5.0")
    print(f"  tag:        {v150['tag_name']}")
    print(f"  name:       {v150['name']}")
    print(f"  published:  {v150['published_at']}")
    print(f"  html_url:   {v150['html_url']}")
    print(f"  body (first 600 chars):")
    print("    " + v150['body'][:600].replace("\n", "\n    "))
    print()
    print(f"  assets:")
    for a in v150.get('assets', []):
        print(f"    - {a['name']} ({a['size']} bytes)")
        print(f"      browser: {a['browser_download_url']}")
    print()

    # 4. Latest commits on main
    commits = fetch("/repos/kou147258/haos-ha/commits?per_page=5")
    print("--- last 5 commits on main ---")
    for c in commits:
        first_line = c['commit']['message'].splitlines()[0]
        print(f"  {c['sha'][:10]}  {first_line[:90]}")
    print()

    # 5. Root directory listing
    contents = fetch("/repos/kou147258/haos-ha/contents/")
    print(f"--- root directory ({len(contents)} entries) ---")
    for c in contents:
        marker = '/' if c['type'] == 'dir' else ''
        print(f"  {c['name']}{marker}")
    print()

    # 6. Verify haos_fb is gone
    print("--- haos_fb presence check ---")
    has_h = any(c['name'] == 'haos_fb' for c in contents)
    print(f"  haos_fb/ in root? {has_h}  (expect False)")
    has_integration = any(c['name'] == 'custom_components' for c in contents)
    print(f"  custom_components/ in root? {has_integration}  (expect True)")

    # 7. Verify v1.4.2 still has haos_fb (since we kept history intact)
    print()
    print("--- v1.4.2 history check (expect haos_fb still in tree) ---")
    v142_tree = fetch("/repos/kou147258/haos-ha/git/trees/v1.4.2^{tree}")
    v142_names = [t['path'] for t in v142_tree.get('tree', [])]
    print(f"  v1.4.2 root entries: {v142_names[:15]}...")
    print(f"  v1.4.2 has haos_fb? {'haos_fb' in v142_names}  (expect True)")

    # 9. v1.5.0 root tree
    v150_tree = fetch("/repos/kou147258/haos-ha/git/trees/v1.5.0^{tree}")
    v150_names = [t['path'] for t in v150_tree.get('tree', [])]
    print(f"  v1.5.0 root entries: {v150_names}")


if __name__ == "__main__":
    main()