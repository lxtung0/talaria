#!/bin/bash
# Stage the care finder app into build/app: the app folder plus everything
# recommend() imports (config.py and talaria/care_finder), so a Databricks App
# deploy of that folder is self-contained.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out="$root/build/app"
rm -rf "$out"
mkdir -p "$out/talaria/care_finder"
cp "$root"/app/app.py "$root"/app/app.yaml "$root"/app/requirements.txt "$out"/
cp "$root/config.py" "$out/"
cp "$root/talaria/__init__.py" "$out/talaria/"
# items.py needs Spark and is notebook-only.
find "$root/talaria/care_finder" -maxdepth 1 -name '*.py' ! -name items.py -exec cp {} "$out/talaria/care_finder/" \;
echo "$out"
