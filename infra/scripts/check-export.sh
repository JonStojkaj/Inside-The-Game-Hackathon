#!/bin/sh
# azd prepackage hook (run from the repo root): the image bakes data/export/, so refuse to build
# without a complete export of the demo match. azd passes its environment values (DEMO_MATCH_ID).
set -eu

id="${DEMO_MATCH_ID:-}"
if [ -z "$id" ]; then
  echo "DEMO_MATCH_ID is not set. Run: azd env set DEMO_MATCH_ID demo-<n>" >&2
  exit 1
fi

dir="data/export/$id"
for f in match.json frames.json events.json moments.json insights.json stats.json overlays.json; do
  if [ ! -f "$dir/$f" ]; then
    echo "missing $dir/$f. Export first: backend/.venv/bin/python spikes/export_demo.py ... (infra/README.md)" >&2
    exit 1
  fi
done

[ -f frontend/package-lock.json ] || { echo "frontend/package-lock.json missing (npm ci needs it)" >&2; exit 1; }

# warnings only: an empty insights/overlays file or a missing video still deploys
grep -q '^\[\]$' "$dir/insights.json" && echo "warning: $dir/insights.json is empty" >&2
grep -q '^{}$' "$dir/overlays.json" && echo "warning: $dir/overlays.json is empty" >&2
[ -f "$dir/video.mp4" ] || echo "warning: no $dir/video.mp4 (TV view disabled)" >&2
[ -f "$dir/raw.jsonl" ] || echo "warning: no $dir/raw.jsonl (Ask Sliding Doors unavailable; re-run the export or copy spikes/grf/out/matches/$id/raw.jsonl)" >&2

echo "baking into the image:"
du -sh data/export/* 2>/dev/null || true
exit 0
