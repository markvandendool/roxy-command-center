#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 services/roxy_status_provider.py
