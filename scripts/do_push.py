"""Push current local state to kou147258/haos-ha via REST API."""

import os
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
          "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)
exec(open("scripts/push_via_api.py", encoding="utf-8").read())