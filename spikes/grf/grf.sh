#!/usr/bin/env bash
# Run a command in the GRF container with our scenario mounted, a virtual display and the CPU limit.
# Usage (from the repo root):
#   spikes/grf/grf.sh record --seeds 34                 # headless recording (record_match.py)
#   spikes/grf/grf.sh render --seed 34 --match-id demo-34  # video + data in one pass (render_match.py)
# Env: GRF_DURATION (default 3000), GRF_DETERMINISTIC (default 1), GRF_CPUS (default 2, never raise on the dev Mac)
set -euo pipefail
cd "$(dirname "$0")"
mode="$1"; shift
case "$mode" in
  record) cmd="python3 /spike/record_match.py --scenario sliding_doors_full $*" ;;
  render) cmd="python3 /spike/render_match.py $*" ;;
  *) echo "usage: grf.sh record|render ..." >&2; exit 2 ;;
esac
# No DISPLAY on purpose: GRF then renders off-screen, which is reliable. (Xvfb + DISPLAY fails randomly
# under amd64 emulation with "SDL: Video subsystem has not been initialized".)
exec docker run --rm --cpus="${GRF_CPUS:-2}" --platform linux/amd64 \
  -v "$PWD:/spike" \
  -v "$PWD/scenarios/sliding_doors_full.py:/usr/local/lib/python3.8/dist-packages/gfootball/scenarios/sliding_doors_full.py" \
  -e GRF_DURATION="${GRF_DURATION:-3000}" -e GRF_DETERMINISTIC="${GRF_DETERMINISTIC:-1}" -w /spike \
  gfootball:spike sh -c "$cmd"
