#!/bin/sh
set -e

# Start Dagster Web UI on internal port 8081
uv run --python 3.13 dagster-webserver -h 127.0.0.1 -p 8081 -f orchestration/definitions.py --path-prefix /orchestration --read-only &

# Start ProxyGuard on port 8080 (Cloud Run entry port)
exec python3 deployment/proxy_guard.py
