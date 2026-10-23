# Deploying Sliding Doors to Azure

One command (`azd up`) deploys **one container** to Azure Container Apps: the FastAPI API (REST + WebSocket
replay), the built web player and the exported demo match baked into the image.

```
azd up
 ├─ package   build backend/Dockerfile remotely in Azure Container Registry (no Docker on the Mac)
 ├─ provision infra/main.bicep → rg-slidingdoors (swedencentral)
 │    Log Analytics + Application Insights · Container Registry (Basic)
 │    Container Apps environment (consumption) · container app "web" (scale 0–1, managed identity → AcrPull)
 └─ deploy    point the container app at the new image
```

## What runs in production (and what does not)

The deployed API **only serves pre-computed exports** from `data/export/<match_id>/` (match, frames, events,
moments, insights, stats, overlays, optional `video.mp4`). It makes **no LLM calls**, runs no simulation and
needs no Azure OpenAI credentials; `backend/tests/test_api_production.py` checks that importing the API loads
no agent/LLM code. All agent work happens offline, before the deploy:

| Step | Where | Command (from the repo root) |
|---|---|---|
| explain team (Azure OpenAI, answers cached in `data/cache/llm/`) | dev machine | `LLM_PROVIDER=azure backend/.venv/bin/python spikes/explain_demo.py <match_dir> data/insights/<id>.json` |
| production team (overlays per segment) | dev machine | `spikes/produce_demo.py` (see its docstring) |
| export = the production payload | dev machine | see step 3 below |
| serve | Azure | the container image |

**One live exception: Ask Sliding Doors** (`backend/app/api/ask.py`). A fan's "What if …?" runs the explain team
on Azure OpenAI (Microsoft Agent Framework, deployment `fast`) and the rollout engine on the baked
`data/export/<id>/raw.jsonl`, at request time (~10–15 s). Guard rails: `ASK_ENABLED` (Bicep sets it; default off
without `AZURE_OPENAI_ENDPOINT`), one question at a time, `ASK_MAX_PER_MINUTE` (6), `ASK_TIMEOUT_S` (90), identical
questions answered from an in-memory + LLM cache. Auth is keyless: the container's user-assigned identity gets
**Cognitive Services OpenAI User** on the existing `sllidingdoors-ai-js` in `rg-j.stojkaj-6522`
(`modules/openai-role.bicep`, a cross-resource-group module) and `AZURE_CLIENT_ID` points DefaultAzureCredential
at it. The container has 1 vCPU / 2 GiB for the rollouts. Turn it off: `azd env set ASK_ENABLED false && azd provision`.

Re-running the pipeline with `LLM_CACHE=replay` reproduces the same insights/overlays from the cache without
calling Azure, so a rebuild of the payload is deterministic and free.

## One-time setup

Prerequisites: [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and
[Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
(`brew install azure-cli azd`). Docker is **not** needed (the image is built in ACR).

```bash
az login                      # Azure CLI (used for `az containerapp ...` below)
azd auth login                # Azure Developer CLI
az account show --query id -o tsv            # subscription id for the next line
azd env new slidingdoors --location swedencentral --subscription <subscription-id>
azd env set DEMO_MATCH_ID demo-<n>           # the match the player opens (must exist in data/export/)
```

`azd env new` creates `.azure/` in the repo root (environment values, no secrets). It must not be committed;
`.dockerignore` already keeps it out of the image.

## Deploy

```bash
# 1. payload: export the demo match with insights, overlays and video (id-agnostic, any recording folder)
backend/.venv/bin/python spikes/export_demo.py spikes/grf/out/matches/demo-<n> data/export \
    --insights data/insights/demo-<n>.json --overlays data/overlays/demo-<n>.json \
    --video spikes/grf/out/matches/demo-<n>/video.mp4

# 2. the frontend must build (the image runs `npm ci && npm run build`)
(cd frontend && npm ci && npm run build)

# 3. everything else
azd up

# 4. check
curl -s "$(azd env get-value SERVICE_WEB_URI)/api/health"     # {"status":"ok","matches":1}
curl -s "$(azd env get-value SERVICE_WEB_URI)/api/features"   # {"ask":true}
curl -sN -X POST "$(azd env get-value SERVICE_WEB_URI)/api/matches/demo-<n>/ask" -H 'content-type: application/json' \
    -d '{"frame":1353,"question":"What if Holt had shot instead?"}'   # streamed steps, then the answer
open "$(azd env get-value SERVICE_WEB_URI)"
```

The `prepackage` hook (`infra/scripts/check-export.sh`) stops the build if `DEMO_MATCH_ID` is unset or its
export is incomplete, and warns if insights/overlays are empty or the video is missing. Every other match in
`data/export/` is baked in too and can be opened with `?match=<id>`.

## Redeploy

| Changed | Command |
|---|---|
| code, frontend or `data/export/` | `azd deploy` (new image; ~3–5 min) |
| Bicep in `infra/` | `azd provision` (keeps the deployed image) |
| both / not sure | `azd up` |
| different demo match | `azd env set DEMO_MATCH_ID demo-<m>` then `azd deploy` |

## Before recording the demo: keep it warm

Scale-to-zero means the first request after idle waits for a cold start (~10–20 s). For recording:

```bash
azd env set MIN_REPLICAS 1 && azd provision     # always one replica (costs ~0.5 vCPU while on)
azd env set MIN_REPLICAS 0 && azd provision     # back to scale-to-zero afterwards
```

Logs: `az containerapp logs show -g rg-slidingdoors -n "$(azd env get-value SERVICE_WEB_NAME)" --follow`.
Traces/requests: Application Insights `appi-*` in the portal (connection string is injected as the secret env
var `APPLICATIONINSIGHTS_CONNECTION_STRING`; the API enables Azure Monitor OpenTelemetry when it is set).

## Tear down

```bash
azd down --purge --force      # deletes rg-slidingdoors and everything in it
```

## Cost

| Resource | Idle (scaled to zero) | Notes |
|---|---|---|
| Container App (consumption) | 0 € | free grant 180k vCPU-s + 360k GiB-s + 2M requests / month; demo traffic stays inside it |
| Container Registry Basic | ~0.15 €/day (~5 €/month) | the only fixed cost; billed per day while it exists |
| Log Analytics + App Insights | ~0 € | first 5 GB/month free; ingestion capped at 1 GB/day |

Idle cost is therefore ~0 € compute plus the registry (~5 €/month, covered by the free-account credit).
Run `azd down` after judging to stop it.

## Troubleshooting

- **Remote build refused** (`ACR Tasks ... not allowed for this subscription`, seen on some free-trial
  subscriptions): build locally instead. Set `remoteBuild: false` in `azure.yaml` and run `azd deploy` with
  Docker running (amd64 under emulation on Apple Silicon: slow but one-off; one container, quit OrbStack after).
- **`VITE_MATCH_ID is empty`** during the build: `azd env set DEMO_MATCH_ID demo-<n>`.
- **`data/export/<id>/match.json missing`**: run the export (Deploy step 1); `data/export/` must exist locally,
  it is uploaded as part of the build context (`.dockerignore` keeps everything else in `data/` out).
- **Page loads but no match**: the player opens `DEMO_MATCH_ID`; check `/api/matches` and use `?match=<id>`.
