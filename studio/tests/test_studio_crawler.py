"""Testes herméticos para os endpoints de crawling do UXSentinel Studio (UXS-12)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uxsentinel_studio.server import create_app, get_session_token


@pytest.fixture
def project_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configura estrutura hermética de workspace com pastas de cenários."""
    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    generated_dir = scenarios_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    report_dir = tmp_path / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Cria cenário pré-existente
    base_scenario = """version: "1.0"
id: cenario_base
title: "Cenário Base de Teste"
profile: generic
steps:
  - action: goto
    url: "https://exemplo.com.br"
  - action: checkpoint
    name: "chk_base"
    expected_behavior: "Página deve abrir"
"""
    (scenarios_dir / "cenario_base.yaml").write_text(base_scenario, encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(project_workspace: Path) -> TestClient:
    """Instancia TestClient do FastAPI amarrado ao workspace temporário."""
    app = create_app(project_dir=project_workspace)
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Retorna cabeçalho de autenticação válido com o token de sessão do Studio."""
    return {"X-Studio-Token": get_session_token()}


def test_crawl_start_validation(client: TestClient, auth_headers: dict[str, str]):
    """Rejeita inicialização de crawl com URLs inválidas (sem scheme http/https)."""
    # URL vazia
    res = client.post("/api/crawl/start", json={"url": ""}, headers=auth_headers)
    assert res.status_code == 400

    # URL sem protocolo
    res = client.post("/api/crawl/start", json={"url": "ftp://teste.com"}, headers=auth_headers)
    assert res.status_code == 400


def test_crawl_lifecycle(client: TestClient, auth_headers: dict[str, str]):
    """Testa ciclo completo: start, status e cancelamento de um job de crawl."""
    # Mock do crawler.run para evitar abrir navegador real nos testes herméticos da API
    with patch("uxsentinel.crawler.Crawler.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {
            "status": "running",
            "start_url": "https://app.teste.local",
            "current_url": "https://app.teste.local",
            "current_depth": 0,
            "visited_count": 1,
            "queued_count": 0,
            "visited_pages": ["https://app.teste.local"],
            "queued_pages": [],
            "errors": [],
            "generated_scenarios": [],
            "nodes_count": 1,
            "started_at": "2026-09-23T12:00:00Z",
            "finished_at": None,
        }

        # 1. Iniciar Crawl
        start_res = client.post(
            "/api/crawl/start",
            json={
                "url": "https://app.teste.local",
                "max_depth": 2,
                "max_pages": 10,
                "generate_scenarios": True,
            },
            headers=auth_headers,
        )
        assert start_res.status_code == 200
        start_data = start_res.json()
        assert "job_id" in start_data
        assert start_data["status"] == "running"
        job_id = start_data["job_id"]

        # 2. Consultar Status do Job
        status_res = client.get(f"/api/crawl/status/{job_id}", headers=auth_headers)
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["job_id"] == job_id
        assert status_data["start_url"] == "https://app.teste.local"

        # 3. Cancelar Job
        cancel_res = client.post(f"/api/crawl/cancel/{job_id}", headers=auth_headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "cancelled"


def test_crawl_status_and_cancel_not_found(client: TestClient, auth_headers: dict[str, str]):
    """Retorna 404 para jobs inexistentes."""
    res_status = client.get("/api/crawl/status/job_inexistente", headers=auth_headers)
    assert res_status.status_code == 404

    res_cancel = client.post("/api/crawl/cancel/job_inexistente", headers=auth_headers)
    assert res_cancel.status_code == 404


def test_generated_scenarios_appear_in_scenarios_list(
    client: TestClient,
    project_workspace: Path,
    auth_headers: dict[str, str],
):
    """Garante que cenários salvos em 'scenarios/generated/' apareçam na rota GET /api/scenarios."""
    generated_dir = project_workspace / "scenarios" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    crawl_scenario_yaml = """version: "1.0"
id: crawl_dashboard_descoberto
title: "Exploração Autônoma: Dashboard"
profile: generic
tags:
  - crawl
  - autonomo
steps:
  - action: goto
    url: "https://app.teste.local/dashboard"
  - action: wait_until_ready
  - action: checkpoint
    name: "chk_dash"
    expected_behavior: "Dashboard íntegro"
"""
    (generated_dir / "crawl_dashboard_descoberto.yaml").write_text(crawl_scenario_yaml, encoding="utf-8")

    # Chama GET /api/scenarios
    res = client.get("/api/scenarios", headers=auth_headers)
    assert res.status_code == 200
    scenarios = res.json()

    scenario_ids = [s["id"] for s in scenarios]
    assert "cenario_base" in scenario_ids
    assert "crawl_dashboard_descoberto" in scenario_ids
