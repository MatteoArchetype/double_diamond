#!/bin/sh
cd "$(dirname "$0")" || exit 1
python_bin=python3
# Prefer the virtual environment the README creates inside this folder, then a
# shared one beside it, then the system Python.
for candidate in ".venv/bin/python" "../.venv/bin/python"; do
  if [ -x "$candidate" ]; then python_bin="$candidate"; break; fi
done
exec "$python_bin" -m dd_research_runtime.local_app --workspace research-workspace "$@"
