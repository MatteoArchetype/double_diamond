#!/bin/sh
cd "$(dirname "$0")" || exit 1
python_bin=python3
if [ -x "../.venv/bin/python" ]; then python_bin="../.venv/bin/python"; fi
exec "$python_bin" -m dd_research_runtime.local_app --workspace research-workspace "$@"
