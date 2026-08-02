#!/bin/sh
set -e

# Start Malloy Publisher on internal port 8081
npx @malloy-publisher/server --config analytics/malloy-config.json --port 8081 --host 127.0.0.1 &

# Start ProxyGuard on port 8080 (Cloud Run entry port)
exec node deployment/proxy_guard.js
