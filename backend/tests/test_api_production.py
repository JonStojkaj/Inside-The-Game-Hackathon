"""Production packaging of the API: serves baked exports only, configured by env vars like in the container,
and the Dockerfile / azd / Bicep files agree with the API (port, health path, service name)."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from conftest import make_match
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.export.exporter import export_match

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
FORBIDDEN = ("app.agents", "app.rollout", "app.overlay", "app.personalization", "openai", "azure.identity")


def test_importing_the_api_loads_no_llm_or_simulation_code(tmp_path):
    code = (
        "import sys, app.api.main\n"
        f"bad = sorted(m for m in sys.modules if m.startswith({FORBIDDEN!r}))\n"
        "print(','.join(bad))\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AZURE_", "LLM_", "APPLICATIONINSIGHTS_"))}
    env |= {"EXPORT_DIR": str(tmp_path), "FRONTEND_DIR": str(tmp_path / "dist")}
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True,
                            check=True)
    assert result.stdout.strip() == ""


def test_env_configured_app_serves_baked_exports_and_frontend(tmp_path, monkeypatch):
    match = make_match()
    match.match_id = "demo-107"
    export_match(match, tmp_path / "export" / "demo-107")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>player</title>")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "export"))
    monkeypatch.setenv("FRONTEND_DIR", str(dist))
    client = TestClient(create_app())

    assert client.get("/api/health").json() == {"status": "ok", "matches": 1}
    assert [m["match_id"] for m in client.get("/api/matches").json()] == ["demo-107"]
    assert client.get("/api/matches/demo-107/match.json").json()["match_id"] == "demo-107"
    assert "player" in client.get("/").text


def test_health_without_exports(tmp_path):
    client = TestClient(create_app(export_dir=tmp_path / "missing", frontend_dir=tmp_path / "dist"))
    assert client.get("/api/health").json() == {"status": "ok", "matches": 0}


def test_dockerfile_azure_yaml_and_bicep_agree():
    dockerfile = (BACKEND / "Dockerfile").read_text()
    azure_yaml = (REPO / "azure.yaml").read_text()
    bicep = (REPO / "infra" / "resources.bicep").read_text()
    params = json.loads((REPO / "infra" / "main.parameters.json").read_text())["parameters"]

    # one port everywhere: Dockerfile PORT, Bicep targetPort and PORT env, health probes on /api/health
    port = re.search(r"PORT=(\d+)", dockerfile)
    assert port
    assert f"targetPort: {port.group(1)}" in bicep or f"var port = {port.group(1)}" in bicep
    assert "/api/health" in dockerfile and "/api/health" in bicep
    assert re.search(r"^USER (?!root)", dockerfile, re.M), "image must run as non-root"
    assert "COPY data/export" in dockerfile

    # azd finds the container app by the service name tag
    service = re.search(r"^services:\n  ([\w-]+):", azure_yaml, re.M)
    assert service
    assert f"'azd-service-name': '{service.group(1)}'" in bicep
    assert "APPLICATIONINSIGHTS_CONNECTION_STRING" in bicep
    assert {"environmentName", "location"} <= set(params)
