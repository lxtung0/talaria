#!/bin/bash
# Deploy the care finder as the Databricks App `talaria-care-finder` (ticket #30).
#
#   ./scripts/deploy_app.sh            # create if missing, grant, sync, deploy, start
#
# Uses the DEFAULT Databricks CLI profile. Stop the app afterwards to save quota:
#   databricks apps stop talaria-care-finder
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
app=talaria-care-finder

if ! databricks apps get "$app" >/dev/null 2>&1; then
  echo "Creating $app"
  databricks apps create "$app" --no-compute --description "Care finder: find facilities offering a service, with evidence" >/dev/null
fi

# App resources (warehouse, serving endpoints) and the Unity Catalog / Vector Search grants.
uv run --project "$root" python "$root/scripts/app_permissions.py"

out=$("$root/scripts/build_app.sh")
me=$(databricks current-user me -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')
dest="/Workspace/Users/$me/apps/$app"
databricks sync --full "$out" "$dest"

state=$(databricks apps get "$app" -o json | python3 -c 'import json,sys;print(json.load(sys.stdin).get("compute_status",{}).get("state",""))')
if [ "$state" != "ACTIVE" ]; then
  echo "Starting $app compute ($state)"
  databricks apps start "$app" >/dev/null
fi
databricks apps deploy "$app" --source-code-path "$dest"
databricks apps get "$app" -o json | python3 -c 'import json,sys;d=json.load(sys.stdin);print("URL:", d.get("url"))'
