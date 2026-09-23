"""Testes herméticos para as rotas da API REST e streaming SSE do UXSentinel Studio (UXS-52 / STU-05)."""

import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uxsentinel.core.events import EventType, ExecutionEvent
from uxsentinel.core.models import CheckpointResult, TestReport
from uxsentinel.service import (
    BrowserConfigDTO,
    ConnectionResult,
    JiraSafeDTO,
    ProviderSafeDTO,
    SafeConfigDTO,
)
from uxsentinel.service.config_service import SecretFieldStatus
from uxsentinel_studio.api import EXECUTIONS, publish_execution_event
from uxsentinel_studio.server import create_app, get_session_token


@pytest.fixture
def project_workspace(tmp_path: Path) -> Path:
    """Configura estrutura hermética de workspace com cenários e diretório de relatórios."""
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    report_dir = tmp_path / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Cenário de teste base
    scenario_content = """id: cenario_teste
title: "Cenário de Teste Unitário"
profile: generic
steps:
  - action: goto
    url: "https://exemplo.com.br"
    description: "Navegação inicial"
  - action: checkpoint
    name: "home_renderizada"
    expected_behavior: "Página deve estar acessível"
"""
    (scenarios_dir / "cenario_teste.yaml").write_text(scenario_content, encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(project_workspace: Path) -> TestClient:
    """Instancia TestClient do FastAPI amarrado ao workspace temporário."""
    app = create_app(project_dir=project_workspace)
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Retorna cabeçalho de autorização válido com o token de sessão."""
    return {"X-Studio-Token": get_session_token()}


def _build_mock_safe_config(
    active_provider: str,
    providers: dict[str, ProviderSafeDTO],
) -> SafeConfigDTO:
    """Helper para construir SafeConfigDTO hermético para testes de status de IA."""
    return SafeConfigDTO(
        active_provider=active_provider,
        browser=BrowserConfigDTO(),
        jira=JiraSafeDTO(api_token=SecretFieldStatus(configured=False)),
        providers=providers,
    )


# ==============================================================================
# 1. Status & Liveness
# ==============================================================================


def test_status_endpoint(client: TestClient) -> None:
    """Valida retorno do status público sem autenticação."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "studio_version" in data
    assert "core_version" in data
    assert "project_dir" in data


# ==============================================================================
# 2. Autenticação e Proteção de Rotas
# ==============================================================================


def test_authentication_protection(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Garante que rotas protegidas retornam 401 sem token ou com token inválido."""
    protected_urls = [
        ("GET", "/api/scenarios"),
        ("GET", "/api/config"),
        ("GET", "/api/results"),
        ("POST", "/api/scenarios/validate"),
    ]

    for method, url in protected_urls:
        # Sem cabeçalho -> 401
        r_anon = client.request(method, url)
        assert r_anon.status_code == 401, f"{method} {url} deveria exigir autenticação"

        # Com token errado -> 401
        r_bad = client.request(method, url, headers={"X-Studio-Token": "token_incorreto_xyz"})
        assert r_bad.status_code == 401, f"{method} {url} deveria rejeitar token incorreto"

    # Com token válido -> 200
    r_auth = client.get("/api/scenarios", headers=auth_headers)
    assert r_auth.status_code == 200


# ==============================================================================
# 3. Gestão de Cenários (List, Get, Validate, Create, Update, Delete)
# ==============================================================================


def test_list_and_get_scenarios(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Testa listagem e detalhamento de cenários do projeto e biblioteca."""
    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.yaml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    from uxsentinel.core.config import register_project_scenario

    register_project_scenario(
        scenario_path=Path(client.app.state.project_dir) / "scenarios" / "cenario_teste.yaml",
        scenario_data={"id": "cenario_teste", "name": "Cenário de Teste Unitário"},
        project_name="Workspace Teste",
        config_path=cfg_file,
    )

    # Listagem
    resp = client.get("/api/scenarios", headers=auth_headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    assert isinstance(scenarios, list)
    scenario_ids = [s["id"] for s in scenarios]
    assert "cenario_teste" in scenario_ids

    # Detalhe existente
    resp_detail = client.get("/api/scenarios/cenario_teste", headers=auth_headers)
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["id"] == "cenario_teste"
    assert detail["title"] == "Cenário de Teste Unitário"
    assert "steps" in detail
    assert "raw_yaml" in detail

    # Cenário inexistente -> 404
    resp_404 = client.get("/api/scenarios/nao_existe_xyz", headers=auth_headers)
    assert resp_404.status_code == 404

    # Tentativa de Path Traversal -> 400 ou 404
    resp_traversal = client.get("/api/scenarios/../../etc/passwd", headers=auth_headers)
    assert resp_traversal.status_code in (400, 404)


def test_validate_scenario(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida análise estática de sintaxe e semântica YAML."""
    # YAML Válido
    valid_payload = {
        "yaml_content": """id: cenario_valido
title: "Cenário Válido"
steps:
  - action: goto
    url: "https://example.com"
"""
    }
    resp = client.post("/api/scenarios/validate", json=valid_payload, headers=auth_headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["valid"] is True
    assert len(res_data["errors"]) == 0

    # YAML Inválido (Sintaxe)
    invalid_payload = {"yaml_content": "id: [invalido"}
    resp_err = client.post("/api/scenarios/validate", json=invalid_payload, headers=auth_headers)
    assert resp_err.status_code == 200
    res_err_data = resp_err.json()
    assert res_err_data["valid"] is False
    assert len(res_err_data["errors"]) > 0


def test_create_update_and_delete_scenario(
    client: TestClient, project_workspace: Path, auth_headers: dict[str, str]
) -> None:
    """Testa ciclo de vida completo de escrita, modificação e deleção de cenários."""
    # 1. Criação com sucesso
    create_payload = {
        "filename": "novo_fluxo.yaml",
        "yaml_content": """id: novo_fluxo
title: "Novo Fluxo de Teste"
steps:
  - action: goto
    url: "https://teste.com"
""",
    }
    resp_create = client.post("/api/scenarios", json=create_payload, headers=auth_headers)
    assert resp_create.status_code == 201
    assert resp_create.json()["success"] is True
    assert (project_workspace / "scenarios" / "novo_fluxo.yaml").is_file()

    # 2. Criação com YAML inválido -> 422
    bad_payload = {"filename": "ruim.yaml", "yaml_content": "id: : quebrado"}
    resp_bad = client.post("/api/scenarios", json=bad_payload, headers=auth_headers)
    assert resp_bad.status_code == 422

    # 3. Atualização de cenário existente
    update_payload = {
        "filename": "novo_fluxo.yaml",
        "yaml_content": """id: novo_fluxo
title: "Novo Fluxo Atualizado"
steps:
  - action: goto
    url: "https://teste.com/atualizado"
""",
    }
    resp_update = client.put("/api/scenarios/novo_fluxo", json=update_payload, headers=auth_headers)
    assert resp_update.status_code == 200
    assert resp_update.json()["success"] is True

    # Valida persistência da alteração
    resp_get = client.get("/api/scenarios/novo_fluxo", headers=auth_headers)
    assert resp_get.json()["title"] == "Novo Fluxo Atualizado"

    # 4. Exclusão do cenário
    resp_delete = client.delete("/api/scenarios/novo_fluxo?delete_file=true", headers=auth_headers)
    assert resp_delete.status_code == 200
    assert resp_delete.json()["success"] is True
    assert resp_delete.json()["delete_file"] is True
    assert not (project_workspace / "scenarios" / "novo_fluxo.yaml").exists()

    # 5. Exclusão de cenário inexistente -> 404
    resp_del_404 = client.delete("/api/scenarios/novo_fluxo", headers=auth_headers)
    assert resp_del_404.status_code == 404


def test_duplicate_scenario_api_success(
    client: TestClient,
    auth_headers: dict[str, str],
    project_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Valida duplicação de cenário com sucesso via POST /api/scenarios/{id}/duplicate."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg_dir))

    resp = client.post("/api/scenarios/cenario_teste/duplicate", headers=auth_headers, json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "cenario_teste_copia"
    assert data["title"] == "Cenário de Teste Unitário (Cópia)"

    # Confere que o novo arquivo foi gravado no disco com sufixo _copia
    cloned_file = project_workspace / "scenarios" / "cenario_teste_copia.yaml"
    assert cloned_file.is_file()

    # Confere que pode ser consultado no endpoint GET
    resp_get = client.get("/api/scenarios/cenario_teste_copia", headers=auth_headers)
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == "cenario_teste_copia"


def test_duplicate_scenario_api_custom_payload(
    client: TestClient,
    auth_headers: dict[str, str],
    project_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Valida duplicação com payload customizado (new_id e new_title)."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg_dir))

    payload = {"new_id": "cenario_clonado_custom", "new_title": "Cenário Customizado"}
    resp = client.post(
        "/api/scenarios/cenario_teste/duplicate",
        headers=auth_headers,
        json=payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "cenario_clonado_custom"
    assert data["title"] == "Cenário Customizado"
    assert (project_workspace / "scenarios" / "cenario_clonado_custom.yaml").is_file()


def test_duplicate_scenario_api_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida retorno 404 ao tentar duplicar cenário inexistente."""
    resp = client.post("/api/scenarios/cenario_fantasma/duplicate", headers=auth_headers, json={})
    assert resp.status_code == 404
    assert "não encontrado para duplicação" in resp.json()["detail"]


def test_duplicate_scenario_api_unauthorized(client: TestClient) -> None:
    """Valida que POST /api/scenarios/{id}/duplicate sem token retorna 401."""
    resp = client.post("/api/scenarios/cenario_teste/duplicate", json={})
    assert resp.status_code == 401


def test_duplicate_scenario_api_with_numeric_value(
    client: TestClient,
    auth_headers: dict[str, str],
    project_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Valida duplicação de cenário contendo valor numérico no campo value via API (UXS-78)."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg_dir))

    # Cria cenário contendo value numérico (123456)
    scenarios_dir = project_workspace / "scenarios"
    num_scenario = """id: cenario_numerico
title: "Cenário com Valor Numérico"
profile: generic
steps:
  - action: fill
    selector: "#password"
    value: 123456
"""
    (scenarios_dir / "cenario_numerico.yaml").write_text(num_scenario, encoding="utf-8")

    resp = client.post("/api/scenarios/cenario_numerico/duplicate", headers=auth_headers, json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "cenario_numerico_copia"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["value"] == "123456"


# ==============================================================================
# 4. Configuração Global e Mascaramento de Segredos
# ==============================================================================


def test_get_and_update_config(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Testa leitura de SafeConfigDTO e atualização segura de configurações."""
    # Leitura
    resp = client.get("/api/config", headers=auth_headers)
    assert resp.status_code == 200
    config_data = resp.json()
    assert "active_provider" in config_data
    assert "browser" in config_data
    assert "jira" in config_data
    assert "providers" in config_data

    # Atualização
    update_payload = {
        "active_provider": "gemini_sso",
        "browser": {
            "headless": True,
            "slow_mo_ms": 100,
        },
    }
    with patch("uxsentinel.service.config_service.ConfigService.update_config") as mock_update:
        resp_update = client.post("/api/config", json=update_payload, headers=auth_headers)
        assert resp_update.status_code == 200
        assert resp_update.json()["success"] is True
        mock_update.assert_called_once()


# ==============================================================================
# 5. Assistente IA de Autoria (/generate-scenario)
# ==============================================================================


def test_generate_scenario_assistant(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Testa geração assistida de estrutura YAML de cenário."""
    # Sucesso
    resp = client.post(
        "/api/generate-scenario",
        json={"prompt": "Auditoria do carrinho de compras"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "yaml_content" in data
    assert "auditoria_do_carrinho" in data["yaml_content"]
    assert "Auditoria do carrinho de compras" in data["yaml_content"]

    # Prompt vazio -> 400
    resp_empty = client.post("/api/generate-scenario", json={"prompt": "   "}, headers=auth_headers)
    assert resp_empty.status_code == 400


# ==============================================================================
# 6. Histórico de Resultados e Artefatos (/api/results)
# ==============================================================================


def test_results_and_artifacts(
    client: TestClient, project_workspace: Path, auth_headers: dict[str, str]
) -> None:
    """Testa listagem e recuperação hermética de execuções arquivadas e artefatos."""
    # Inicialmente vazio
    resp = client.get("/api/results", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []

    # Cria execução fictícia em report/
    report_dir = project_workspace / "report"
    report_json_content = """{
  "scenario_id": "cenario_teste",
  "scenario_title": "Cenário de Teste Unitário",
  "started_at": "2026-09-22T10:00:00",
  "finished_at": "2026-09-22T10:00:05",
  "duration_seconds": 5.0,
  "success": true,
  "total_issues": 0,
  "checkpoints": []
}"""
    (report_dir / "cenario_teste_report.json").write_text(report_json_content, encoding="utf-8")
    (report_dir / "relatorio.html").write_text("<html><body>Audit OK</body></html>", encoding="utf-8")

    # Listagem com o resultado
    resp_list = client.get("/api/results", headers=auth_headers)
    assert resp_list.status_code == 200
    results = resp_list.json()
    assert len(results) == 1
    assert results[0]["id"] == "cenario_teste"

    # Detalhe do resultado
    resp_detail = client.get("/api/results/cenario_teste", headers=auth_headers)
    assert resp_detail.status_code == 200
    assert resp_detail.json()["id"] == "cenario_teste"
    assert resp_detail.json()["status"] == "passed"

    # Recuperação do artefato HTML via Header
    resp_artifact = client.get("/api/results/cenario_teste/artifacts/relatorio.html", headers=auth_headers)
    assert resp_artifact.status_code == 200
    assert "Audit OK" in resp_artifact.text

    # Recuperação do artefato HTML via Query Param ?token= sem Header (UXS-74)
    valid_token = get_session_token()
    resp_query_auth = client.get(f"/api/results/cenario_teste/artifacts/relatorio.html?token={valid_token}")
    assert resp_query_auth.status_code == 200
    assert "Audit OK" in resp_query_auth.text

    # Rejeição sem token nem header -> 401
    resp_anon = client.get("/api/results/cenario_teste/artifacts/relatorio.html")
    assert resp_anon.status_code == 401

    # Rejeição com token inválido na query -> 401
    resp_bad_token = client.get(
        "/api/results/cenario_teste/artifacts/relatorio.html?token=token_invalido_xyz"
    )
    assert resp_bad_token.status_code == 401

    # Detalhe inexistente -> 404
    resp_detail_404 = client.get("/api/results/exec_fantasma", headers=auth_headers)
    assert resp_detail_404.status_code == 404


# ==============================================================================
# 7. Execução e Status em Background (/api/execution)
# ==============================================================================


def test_run_execution_and_status(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida disparo de execução assíncrona e consulta de status."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=True,
            )
        },
    )
    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.5,
    )

    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "IA operacional"),
        ),
        patch(
            "uxsentinel.service.execution_service.ExecutionService.run",
            new_callable=AsyncMock,
            return_value=dummy_report,
        ),
    ):
        # Cenário inexistente -> 404
        r_404 = client.post(
            "/api/execution/run",
            json={"scenario_id": "cenario_inexistente"},
            headers=auth_headers,
        )
        assert r_404.status_code == 404

        # Disparo com mock do ExecutionService para manter hermeticidade
        resp_run = client.post(
            "/api/execution/run",
            json={"scenario_id": "cenario_teste"},
            headers=auth_headers,
        )
        assert resp_run.status_code == 202
        run_data = resp_run.json()
        assert "run_id" in run_data
        run_id = run_data["run_id"]

        # Consulta status
        resp_status = client.get(f"/api/execution/{run_id}", headers=auth_headers)
        assert resp_status.status_code == 200
        st = resp_status.json()
        assert st["run_id"] == run_id
        assert st["scenario_id"] == "cenario_teste"
        assert st["status"] in ("running", "completed")

    # Status de execução inexistente -> 404
    resp_st_404 = client.get("/api/execution/inexistente_999", headers=auth_headers)
    assert resp_st_404.status_code == 404


# ==============================================================================
# 8. SSE Streaming em Tempo Real (/api/execution/{run_id}/stream)
# ==============================================================================


def test_execution_stream_auth_and_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida autenticação e 404 no endpoint de streaming SSE."""
    # Sem autenticação -> 401
    r_no_auth = client.get("/api/execution/qualquer_id/stream")
    assert r_no_auth.status_code == 401

    # Execução inexistente com cabeçalho -> 404
    r_404 = client.get("/api/execution/qualquer_id/stream", headers=auth_headers)
    assert r_404.status_code == 404

    # Execução inexistente com query param ?token= -> 404
    token = get_session_token()
    r_404_param = client.get(f"/api/execution/qualquer_id/stream?token={token}")
    assert r_404_param.status_code == 404


@pytest.mark.asyncio
async def test_execution_stream_sse_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida a emissão e encerramento de eventos SSE em tempo real."""
    run_id = "test_run_stream_001"
    main_queue: asyncio.Queue[str | None] = asyncio.Queue()

    EXECUTIONS[run_id] = {
        "run_id": run_id,
        "scenario_id": "cenario_teste",
        "status": "running",
        "current_step": 0,
        "logs": ["Iniciando cenário"],
        "started_at": "2026-09-22T10:00:00Z",
        "result": None,
        "error": None,
        "queue": main_queue,
        "subscribers": [],
        "event_history": [],
    }

    # Publica eventos simulados na fila
    await publish_execution_event(run_id, "log", {"message": "Passo 1 em execução"})
    await publish_execution_event(
        run_id,
        "step",
        {"step_index": 1, "action": "goto", "description": "Abrir página", "status": "passed"},
    )
    await publish_execution_event(
        run_id,
        "checkpoint",
        {"name": "chk_home", "status": "passed", "issues_count": 0},
    )
    await publish_execution_event(
        run_id,
        "completed",
        {"success": True, "total_issues": 0, "duration_seconds": 2.1},
    )
    EXECUTIONS[run_id]["status"] = "completed"

    # Consome stream via TestClient com cabeçalho
    resp = client.get(f"/api/execution/{run_id}/stream", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    body = resp.text
    assert 'data: {"event": "log"' in body
    assert "Passo 1 em execução" in body
    assert 'data: {"event": "step"' in body
    assert 'data: {"event": "checkpoint"' in body
    assert 'data: {"event": "completed"' in body

    # Valida conexão também com query param ?token=
    token = get_session_token()
    resp_token = client.get(f"/api/execution/{run_id}/stream?token={token}")
    assert resp_token.status_code == 200
    assert 'data: {"event": "completed"' in resp_token.text


def test_execute_scenario_task_publishes_all_events(project_workspace: Path) -> None:
    """Valida se _execute_scenario_task orquestra e publica todos os eventos SSE esperados."""
    from uxsentinel.service.execution_service import ExecutionOptions
    from uxsentinel_studio.api import _execute_scenario_task

    run_id = "test_task_events_002"
    main_queue: asyncio.Queue[str | None] = asyncio.Queue()

    EXECUTIONS[run_id] = {
        "run_id": run_id,
        "scenario_id": "cenario_teste",
        "status": "running",
        "current_step": 0,
        "logs": [],
        "started_at": "2026-09-22T10:00:00Z",
        "result": None,
        "error": None,
        "queue": main_queue,
        "subscribers": [],
        "event_history": [],
    }

    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.2,
        checkpoints=[
            CheckpointResult(
                name="home_renderizada",
                status="ok",
                issues=[],
                expected_behavior="Página acessível",
            )
        ],
    )

    scenario_file = project_workspace / "scenarios" / "cenario_teste.yaml"
    options = ExecutionOptions(
        scenario_path=scenario_file,
        output_dir=str(project_workspace / "report"),
    )

    with patch(
        "uxsentinel.service.execution_service.ExecutionService.run",
        new_callable=AsyncMock,
        return_value=dummy_report,
    ):
        asyncio.run(_execute_scenario_task(run_id, options))

    # Verifica se os eventos foram publicados no histórico da execução
    history = EXECUTIONS[run_id]["event_history"]
    assert any('"event": "log"' in item for item in history)
    assert any('"event": "step"' in item for item in history)
    assert any('"event": "checkpoint"' in item for item in history)
    assert any('"event": "completed"' in item for item in history)
    assert EXECUTIONS[run_id]["status"] == "completed"


def test_execute_scenario_task_logs_active_flags(project_workspace: Path) -> None:
    """Valida se _execute_scenario_task registra nos logs SSE a mensagem de flags ativas com headless, devtools, console e inspect."""
    from uxsentinel.service.execution_service import ExecutionOptions
    from uxsentinel_studio.api import _execute_scenario_task

    run_id = "test_task_flags_001"
    main_queue: asyncio.Queue[str | None] = asyncio.Queue()

    EXECUTIONS[run_id] = {
        "run_id": run_id,
        "scenario_id": "cenario_flags",
        "status": "running",
        "current_step": 0,
        "logs": [],
        "started_at": "2026-09-22T10:00:00Z",
        "result": None,
        "error": None,
        "queue": main_queue,
        "subscribers": [],
        "event_history": [],
    }

    dummy_report = TestReport(
        scenario_id="cenario_flags",
        scenario_title="Cenário de Teste Flags",
        success=True,
        total_issues=0,
        duration_seconds=0.5,
    )

    scenario_file = project_workspace / "scenarios" / "cenario_teste.yaml"
    options = ExecutionOptions(
        scenario_path=scenario_file,
        headless=False,
        devtools=True,
        capture_console=True,
        inspect=True,
        output_dir=str(project_workspace / "report"),
    )

    with patch(
        "uxsentinel.service.execution_service.ExecutionService.run",
        new_callable=AsyncMock,
        return_value=dummy_report,
    ):
        asyncio.run(_execute_scenario_task(run_id, options))

    logs = EXECUTIONS[run_id]["logs"]
    expected_flag_msg = "Flags ativas: headless=False, devtools=True, console=True, inspect=True"
    assert any(expected_flag_msg in log for log in logs)


def test_execute_scenario_task_realtime_eventbus_streaming(project_workspace: Path) -> None:
    """Valida a transmissão de eventos em tempo real via EventBus durante a execução."""
    from uxsentinel.service.execution_service import ExecutionOptions
    from uxsentinel_studio.api import _execute_scenario_task

    run_id = "test_eventbus_realtime_001"
    main_queue: asyncio.Queue[str | None] = asyncio.Queue()

    EXECUTIONS[run_id] = {
        "run_id": run_id,
        "scenario_id": "cenario_teste",
        "status": "running",
        "current_step": 0,
        "logs": [],
        "started_at": "2026-09-22T10:00:00Z",
        "result": None,
        "error": None,
        "queue": main_queue,
        "subscribers": [],
        "event_history": [],
    }

    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.8,
        checkpoints=[
            CheckpointResult(
                name="home_renderizada",
                status="ok",
                issues=[],
                expected_behavior="Página acessível",
            )
        ],
    )

    scenario_file = project_workspace / "scenarios" / "cenario_teste.yaml"
    options = ExecutionOptions(
        scenario_path=scenario_file,
        output_dir=str(project_workspace / "report"),
    )

    async def mock_run(opts: ExecutionOptions) -> TestReport:
        # Simula publicação compassada de eventos no barramento durante a execução
        bus = opts.event_bus
        assert bus is not None

        await bus.publish(
            ExecutionEvent(
                event_type=EventType.STEP_STARTED,
                scenario_id="cenario_teste",
                step_index=1,
                action="goto",
                data={"description": "Navegação inicial", "url": "https://exemplo.com.br"},
            )
        )
        await bus.publish(
            ExecutionEvent(
                event_type=EventType.STEP_COMPLETED,
                scenario_id="cenario_teste",
                step_index=1,
                action="goto",
                data={"description": "Navegação inicial"},
            )
        )
        await bus.publish(
            ExecutionEvent(
                event_type=EventType.CHECKPOINT_COMPLETED,
                scenario_id="cenario_teste",
                step_index=2,
                action="checkpoint",
                data={
                    "name": "home_renderizada",
                    "status": "ok",
                    "issues_count": 0,
                    "expected_behavior": "Página acessível",
                    "screenshot_path": "/tmp/screenshot.png",
                },
            )
        )
        return dummy_report

    with patch(
        "uxsentinel.service.execution_service.ExecutionService.run",
        side_effect=mock_run,
    ):
        asyncio.run(_execute_scenario_task(run_id, options))

    history = EXECUTIONS[run_id]["event_history"]
    logs = EXECUTIONS[run_id]["logs"]

    # Valida presença de eventos formatados
    assert any('"event": "step"' in item and '"status": "running"' in item for item in history)
    assert any('"event": "step"' in item and '"status": "passed"' in item for item in history)
    assert any('"event": "checkpoint"' in item and '"name": "home_renderizada"' in item for item in history)
    assert any('"event": "completed"' in item for item in history)
    assert any("[PASSO 1/2] Executando: goto - Navegação inicial" in msg for msg in logs)
    assert any("[PASSO 1/2] ✓ Concluído com sucesso." in msg for msg in logs)
    assert EXECUTIONS[run_id]["status"] == "completed"


def test_execute_scenario_task_ai_error_streaming_and_history(project_workspace: Path) -> None:
    """Valida que erros de conexão de IA são reportados via SSE e gravados no histórico."""
    from uxsentinel.service.execution_service import ExecutionOptions
    from uxsentinel_studio.api import _execute_scenario_task

    run_id = "test_ai_error_002"
    main_queue: asyncio.Queue[str | None] = asyncio.Queue()

    EXECUTIONS[run_id] = {
        "run_id": run_id,
        "scenario_id": "cenario_teste",
        "status": "running",
        "current_step": 0,
        "logs": [],
        "started_at": "2026-09-22T10:00:00Z",
        "result": None,
        "error": None,
        "queue": main_queue,
        "subscribers": [],
        "event_history": [],
    }

    ai_error_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=False,
        error_message="Falha de conexão com a IA: API Key inválida ou expirada",
        duration_seconds=0.5,
    )

    scenario_file = project_workspace / "scenarios" / "cenario_teste.yaml"
    options = ExecutionOptions(
        scenario_path=scenario_file,
        output_dir=str(project_workspace / "report"),
    )

    async def mock_run_ai_error(opts: ExecutionOptions) -> TestReport:
        bus = opts.event_bus
        assert bus is not None
        await bus.publish(
            ExecutionEvent(
                event_type=EventType.SCENARIO_FAILED,
                scenario_id="cenario_teste",
                data={"error": ai_error_report.error_message},
            )
        )
        return ai_error_report

    with patch(
        "uxsentinel.service.execution_service.ExecutionService.run",
        side_effect=mock_run_ai_error,
    ):
        asyncio.run(_execute_scenario_task(run_id, options))

    history = EXECUTIONS[run_id]["event_history"]
    logs = EXECUTIONS[run_id]["logs"]

    assert EXECUTIONS[run_id]["status"] == "failed"
    assert "Falha de conexão com a IA: API Key inválida ou expirada" in EXECUTIONS[run_id]["error"]
    assert any('"event": "error"' in item for item in history)
    assert any("Falha de conexão com a IA" in item for item in history)
    assert any("[ERRO NA EXECUÇÃO]" in msg for msg in logs)


# ==============================================================================
# 9. Testes Herméticos de Conectividade (/api/config/test-jira e test-ai)
# ==============================================================================


def test_connectivity_test_jira(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Testa endpoint hermético de conectividade com o Jira Cloud."""
    payload = {
        "url": "https://empresa.atlassian.net",
        "email": "qa@empresa.com",
        "token": "secret_token",
    }

    # Cenário de Sucesso
    with patch(
        "uxsentinel.service.config_service.ConfigService.test_jira_connection",
        new_callable=AsyncMock,
    ) as mock_jira:
        mock_jira.return_value = ConnectionResult(
            valid=True,
            message="Conectado com sucesso como QA Tester!",
            latency_ms=48,
        )
        resp = client.post("/api/config/test-jira", json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "Conectado com sucesso" in data["message"]
        assert data["latency_ms"] == 48

    # Cenário de Falha (Credenciais Inválidas)
    with patch(
        "uxsentinel.service.config_service.ConfigService.test_jira_connection",
        new_callable=AsyncMock,
    ) as mock_jira_err:
        mock_jira_err.return_value = ConnectionResult(
            valid=False,
            message="Credenciais inválidas ou acesso não autorizado (401/403).",
            latency_ms=52,
        )
        resp_err = client.post("/api/config/test-jira", json=payload, headers=auth_headers)
        assert resp_err.status_code == 200
        data_err = resp_err.json()
        assert data_err["valid"] is False
        assert "Credenciais inválidas" in data_err["message"]


def test_connectivity_test_ai(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Testa endpoint hermético de conectividade com modelo ou gateway de IA."""
    payload = {"provider": "gemini_sso"}

    # Cenário de Sucesso
    with patch(
        "uxsentinel.service.config_service.ConfigService.test_ai_connection",
        new_callable=AsyncMock,
    ) as mock_ai:
        mock_ai.return_value = ConnectionResult(
            valid=True,
            message="Provedor 'gemini_sso' conectado com sucesso!",
            latency_ms=130,
        )
        resp = client.post("/api/config/test-ai", json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "conectado com sucesso" in data["message"]
        assert data["latency_ms"] == 130

    # Cenário de Falha de Provedor
    with patch(
        "uxsentinel.service.config_service.ConfigService.test_ai_connection",
        new_callable=AsyncMock,
    ) as mock_ai_err:
        mock_ai_err.return_value = ConnectionResult(
            valid=False,
            message="Erro ao conectar com provedor 'gemini_sso': Timeout.",
            latency_ms=5000,
        )
        resp_err = client.post("/api/config/test-ai", json=payload, headers=auth_headers)
        assert resp_err.status_code == 200
        data_err = resp_err.json()
        assert data_err["valid"] is False
        assert "Timeout" in data_err["message"]


# ==============================================================================
# 10. Limitação de Retenção de Memória (Cap de 50 Runs - STU-12 / UXS-56)
# ==============================================================================


def test_executions_memory_retention_cap_50() -> None:
    """Valida política FIFO e cap de retenção de 50 execuções em EXECUTIONS (UXS-56 / STU-12)."""
    from uxsentinel_studio.api import (
        EXECUTIONS,
        MAX_RETAINED_EXECUTIONS,
        _register_execution,
    )

    # Limpa estado anterior para teste hermético
    EXECUTIONS.clear()
    assert MAX_RETAINED_EXECUTIONS == 50

    # Cadastra 51 execuções consecutivas
    for i in range(1, 52):
        run_id = f"run_{i:03d}"
        _register_execution(
            run_id,
            {"run_id": run_id, "status": "completed", "logs": []},
        )

    # Validações mandatórias do Card STU-12
    assert len(EXECUTIONS) == 50
    assert "run_001" not in EXECUTIONS, "A primeira execução (run_001) deveria ter sido descartada (FIFO)"
    assert "run_002" in EXECUTIONS, "A segunda execução (run_002) deve ser agora a mais antiga"
    assert "run_051" in EXECUTIONS, "A 51ª execução deve estar presente no registro"


def test_executions_api_endpoint_respects_cap(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida se o endpoint /api/execution/run utiliza _register_execution respeitando o cap."""
    from uxsentinel_studio.api import EXECUTIONS, MAX_RETAINED_EXECUTIONS

    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=True,
            )
        },
    )

    EXECUTIONS.clear()
    for i in range(MAX_RETAINED_EXECUTIONS):
        EXECUTIONS[f"pre_fill_{i}"] = {"run_id": f"pre_fill_{i}", "status": "completed"}

    assert len(EXECUTIONS) == 50
    oldest_id = next(iter(EXECUTIONS))

    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "IA operacional"),
        ),
        patch("uxsentinel.service.execution_service.ExecutionService.run", new_callable=AsyncMock),
    ):
        resp = client.post("/api/execution/run", json={"scenario_id": "cenario_teste"}, headers=auth_headers)
        assert resp.status_code == 202
        new_run_id = resp.json()["run_id"]

    assert len(EXECUTIONS) == 50
    assert oldest_id not in EXECUTIONS
    assert new_run_id in EXECUTIONS


# ==============================================================================
# 9. Gerenciamento e Seletor de Projetos (UXS-66)
# ==============================================================================


def test_list_projects_endpoint(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Valida retorno da lista de projetos cadastrados no catálogo global."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Sem projetos cadastrados, lista é estritamente vazia (sem projetos fantasmas)
    resp = client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []

    # Cadastra um projeto
    proj_dir = tmp_path / "meu_projeto"
    proj_dir.mkdir(parents=True)
    resp_create = client.post(
        "/api/projects",
        json={"name": "Meu Projeto", "path": str(proj_dir)},
        headers=auth_headers,
    )
    assert resp_create.status_code == 201

    resp = client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    active_proj = data[0]
    assert active_proj["is_active"] is True
    assert active_proj["name"] == "Meu Projeto"
    assert "id" in active_proj
    assert "path" in active_proj
    assert "scenarios_count" in active_proj


def test_select_project_endpoint(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Valida alternância do projeto ativo no Studio via /api/projects/select."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Cria diretório de outro projeto
    other_proj = tmp_path / "outro_projeto"
    other_proj.mkdir(parents=True, exist_ok=True)
    (other_proj / "scenarios").mkdir()
    (other_proj / "scenarios" / "login.yaml").write_text("title: Login\nsteps: []\n", encoding="utf-8")

    # Cadastra o projeto
    create_resp = client.post(
        "/api/projects",
        json={"name": "Outro Projeto", "path": str(other_proj)},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201

    # Seleciona o projeto
    sel_resp = client.post(
        "/api/projects/select",
        json={"project_id": "outro-projeto"},
        headers=auth_headers,
    )
    assert sel_resp.status_code == 200
    sel_data = sel_resp.json()
    assert sel_data["success"] is True
    assert sel_data["project_id"] == "outro-projeto"
    assert sel_data["project_name"] == "Outro Projeto"

    # Seleciona projeto inexistente
    err_resp = client.post(
        "/api/projects/select",
        json={"project_id": "projeto-fantasma"},
        headers=auth_headers,
    )
    assert err_resp.status_code == 404


def test_create_project_validation(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Valida erros ao tentar cadastrar diretório inválido de projeto."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    resp = client.post(
        "/api/projects",
        json={"name": "Inválido", "path": str(tmp_path / "pasta_inexistente")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_list_scenarios_includes_project_fields(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Valida se /api/scenarios retorna project_id e project_name preenchidos."""
    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.yaml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    from uxsentinel.core.config import register_project_scenario

    register_project_scenario(
        scenario_path=Path(client.app.state.project_dir) / "scenarios" / "cenario_teste.yaml",
        scenario_data={"id": "cenario_teste", "name": "Cenário de Teste Unitário"},
        project_name="Workspace Teste",
        config_path=cfg_file,
    )

    resp = client.get("/api/scenarios", headers=auth_headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) > 0
    sc = scenarios[0]
    assert "project_id" in sc
    assert "project_name" in sc
    assert sc["project_name"] is not None


def test_list_scenarios_filter_by_project_id(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Valida filtro project_id em GET /api/scenarios?project_id=... (UXS-68)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Cria dois projetos distintos com seus próprios cenários
    p1_dir = tmp_path / "proj1"
    (p1_dir / "scenarios").mkdir(parents=True)
    (p1_dir / "scenarios" / "login.yaml").write_text(
        """version: "1.0"
id: proj1_login
title: "Login Projeto 1"
steps:
  - action: goto
    url: "https://p1.example.com"
""",
        encoding="utf-8",
    )

    p2_dir = tmp_path / "proj2"
    (p2_dir / "scenarios").mkdir(parents=True)
    (p2_dir / "scenarios" / "checkout.yaml").write_text(
        """version: "1.0"
id: proj2_checkout
title: "Checkout Projeto 2"
steps:
  - action: goto
    url: "https://p2.example.com"
""",
        encoding="utf-8",
    )

    # Cadastra ambos via endpoint
    client.post("/api/projects", json={"name": "Projeto Alpha", "path": str(p1_dir)}, headers=auth_headers)
    client.post("/api/projects", json={"name": "Projeto Beta", "path": str(p2_dir)}, headers=auth_headers)

    # 1. Busca cenários com project_id=projeto-alpha
    resp1 = client.get("/api/scenarios?project_id=projeto-alpha", headers=auth_headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1) == 1
    assert data1[0]["id"] == "proj1_login"
    assert data1[0]["project_id"] == "projeto-alpha"

    # 2. Busca cenários com project_id=projeto-beta
    resp2 = client.get("/api/scenarios?project_id=projeto-beta", headers=auth_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2) == 1
    assert data2[0]["id"] == "proj2_checkout"
    assert data2[0]["project_id"] == "projeto-beta"

    # 3. Busca cenários com project_id=library (removida da exibição do Studio)
    resp_lib = client.get("/api/scenarios?project_id=library", headers=auth_headers)
    assert resp_lib.status_code == 200
    data_lib = resp_lib.json()
    assert len(data_lib) == 0


def test_delete_project_unauthorized(client: TestClient) -> None:
    """Garante que DELETE /api/projects/{project_id} rejeita requisição sem token (401)."""
    resp = client.delete("/api/projects/qualquer-projeto")
    assert resp.status_code == 401


def test_delete_project_not_found(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Garante 404 ao tentar excluir projeto inexistente do catálogo."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    resp = client.delete("/api/projects/projeto-fantasma-xyz", headers=auth_headers)
    assert resp.status_code == 404
    assert "não encontrado no catálogo" in resp.json()["detail"]


def test_delete_project_success(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Valida exclusão com sucesso de projeto não-ativo preservando o ativo atual."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Cria duas pastas de projeto
    p1_dir = tmp_path / "projeto_um"
    p1_dir.mkdir(parents=True)
    p2_dir = tmp_path / "projeto_dois"
    p2_dir.mkdir(parents=True)

    client.post("/api/projects", json={"name": "Projeto Um", "path": str(p1_dir)}, headers=auth_headers)
    client.post("/api/projects", json={"name": "Projeto Dois", "path": str(p2_dir)}, headers=auth_headers)

    # Torna o Projeto Um ativo
    client.post("/api/projects/select", json={"project_id": "projeto-um"}, headers=auth_headers)

    # Deleta Projeto Dois
    del_resp = client.delete("/api/projects/projeto-dois", headers=auth_headers)
    assert del_resp.status_code == 200
    data = del_resp.json()
    assert data["success"] is True
    assert data["project_id"] == "projeto-dois"
    assert data["active_project_id"] == "projeto-um"
    assert str(p1_dir.resolve()) in data["active_project_dir"]

    # Verifica que Projeto Dois sumiu de /api/projects
    list_resp = client.get("/api/projects", headers=auth_headers)
    projects = list_resp.json()
    assert not any(p["id"] == "projeto-dois" for p in projects)
    assert any(p["id"] == "projeto-um" for p in projects)


def test_delete_project_active_fallback(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Valida fallback do projeto ativo quando o projeto excluído é o ativo."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    p_a_dir = tmp_path / "proj_alpha"
    p_a_dir.mkdir(parents=True)
    p_b_dir = tmp_path / "proj_beta"
    p_b_dir.mkdir(parents=True)

    client.post("/api/projects", json={"name": "Proj Alpha", "path": str(p_a_dir)}, headers=auth_headers)
    client.post("/api/projects", json={"name": "Proj Beta", "path": str(p_b_dir)}, headers=auth_headers)

    # Ativa Proj Alpha
    client.post("/api/projects/select", json={"project_id": "proj-alpha"}, headers=auth_headers)

    # Exclui o projeto ativo (Alpha) -> fallback para Beta
    del_a = client.delete("/api/projects/proj-alpha", headers=auth_headers)
    assert del_a.status_code == 200
    data_a = del_a.json()
    assert data_a["success"] is True
    assert data_a["project_id"] == "proj-alpha"
    assert data_a["active_project_id"] == "proj-beta"
    assert str(p_b_dir.resolve()) in data_a["active_project_dir"]

    # Exclui o último projeto restante (Beta) -> fallback para None / cwd
    del_b = client.delete("/api/projects/proj-beta", headers=auth_headers)
    assert del_b.status_code == 200
    data_b = del_b.json()
    assert data_b["success"] is True
    assert data_b["project_id"] == "proj-beta"
    assert data_b["active_project_id"] is None


def test_delete_scenario_removes_physical_file_and_catalog_link(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Garante que DELETE /api/scenarios/{id} remove o arquivo físico e desvincula do config.yaml."""
    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "config.yaml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    proj_dir = tmp_path / "meu_projeto_crud"
    (proj_dir / "scenarios").mkdir(parents=True)

    # Cadastra projeto
    resp = client.post(
        "/api/projects",
        json={"name": "Projeto Crud", "path": str(proj_dir)},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Cria cenário
    yaml_content = """version: "1.0"
id: cenario_para_deletar
title: Cenário Para Deletar
steps:
  - action: goto
    url: "https://example.com"
"""
    create_resp = client.post(
        "/api/scenarios",
        json={"filename": "cenario_para_deletar.yaml", "yaml_content": yaml_content},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201

    scen_file = proj_dir / "scenarios" / "cenario_para_deletar.yaml"
    assert scen_file.is_file()

    # Registra no catálogo config.yaml
    from uxsentinel.core.config import register_project_scenario

    register_project_scenario(
        scenario_path=scen_file,
        scenario_data={"id": "cenario_para_deletar", "name": "Cenário Para Deletar"},
        project_name="Projeto Crud",
        config_path=cfg_file,
    )

    import yaml

    cfg_data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert "cenario_para_deletar" in cfg_data["projects"]["projeto-crud"]["scenarios"]

    # Exclui o cenário via API com delete_file=true
    del_resp = client.delete("/api/scenarios/cenario_para_deletar?delete_file=true", headers=auth_headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True
    assert del_resp.json()["delete_file"] is True

    # 1. Arquivo físico deve ter sido removido
    assert not scen_file.exists()

    # 2. Link no config.yaml deve ter sido removido
    cfg_after = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert "cenario_para_deletar" not in cfg_after["projects"]["projeto-crud"]["scenarios"]


def test_delete_scenario_unlink_only_via_api(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Garante que DELETE /api/scenarios/{id}?delete_file=false desvincula do config.yaml e mantém o arquivo no disco."""
    import yaml

    from uxsentinel.core.config import register_project_scenario

    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "config.yaml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    proj_dir = tmp_path / "meu_projeto_unlink"
    (proj_dir / "scenarios").mkdir(parents=True)

    # Cadastra projeto
    resp = client.post(
        "/api/projects",
        json={"name": "Projeto Unlink", "path": str(proj_dir)},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Cria cenário
    yaml_content = """version: "1.0"
id: cenario_para_desvincular
title: Cenário Para Desvincular
steps:
  - action: goto
    url: "https://example.com/unlink"
"""
    create_resp = client.post(
        "/api/scenarios",
        json={"filename": "cenario_para_desvincular.yaml", "yaml_content": yaml_content},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201

    scen_file = proj_dir / "scenarios" / "cenario_para_desvincular.yaml"
    assert scen_file.is_file()

    # Registra no catálogo config.yaml
    register_project_scenario(
        scenario_path=scen_file,
        scenario_data={"id": "cenario_para_desvincular", "name": "Cenário Para Desvincular"},
        project_name="Projeto Unlink",
        config_path=cfg_file,
    )

    cfg_data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert "cenario_para_desvincular" in cfg_data["projects"]["projeto-unlink"]["scenarios"]

    # Desvincula o cenário via API com delete_file=false
    del_resp = client.delete(
        "/api/scenarios/cenario_para_desvincular?delete_file=false", headers=auth_headers
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True
    assert del_resp.json()["delete_file"] is False

    # 2. Link no config.yaml deve ter sido removido
    cfg_after = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert "cenario_para_desvincular" not in cfg_after["projects"]["projeto-unlink"]["scenarios"]


def test_api_scenarios_ignores_non_scenario_yamls_without_steps(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garante que /api/scenarios não lista arquivos YAML arbitrários sem chave steps (UXS-72)."""
    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "config.yaml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    proj_dir = Path(client.app.state.project_dir)

    # 1. Cria workspace.yaml na raiz do projeto (arquivo sem steps gerador do bug)
    workspace_file = proj_dir / "workspace.yaml"
    workspace_file.write_text(
        """name: GoTryx Documentation Platform
project_paths:
  - /mnt/home/alexandre/Projetos
global_settings: {}
""",
        encoding="utf-8",
    )

    # 2. Cria arquivo com steps vazio e arquivo arbitrário de orquestração
    (proj_dir / "scenarios" / "invalido.yaml").write_text("title: Sem steps\n", encoding="utf-8")
    (proj_dir / "scenarios" / "steps_vazio.yaml").write_text("title: Vazio\nsteps: []\n", encoding="utf-8")
    (proj_dir / "docker-compose.yml").write_text("version: '3'\n", encoding="utf-8")

    # 3. Registra projeto no catálogo
    from uxsentinel.core.config import register_project_scenario

    register_project_scenario(
        scenario_path=proj_dir / "scenarios" / "cenario_teste.yaml",
        scenario_data={"id": "cenario_teste", "name": "Cenário de Teste Unitário"},
        project_name="Workspace Teste",
        config_path=cfg_file,
    )

    resp = client.get("/api/scenarios", headers=auth_headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    returned_ids = [s["id"] for s in scenarios]

    assert "cenario_teste" in returned_ids
    assert "workspace" not in returned_ids
    assert "invalido" not in returned_ids
    assert "steps_vazio" not in returned_ids
    assert "docker-compose" not in returned_ids
    assert all(s["step_count"] > 0 for s in scenarios)


def test_api_projects_scenarios_count_reflects_real_disk_scenarios(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valida que GET /api/projects calcula cenários reais no disco ignorando entradas órfãs (UXS-73)."""
    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.yaml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    from uxsentinel.core.config import register_project_scenario

    # 1. Cria projeto com pasta vazia (sem cenários válidos no disco)
    empty_proj_dir = tmp_path / "projeto_vazio"
    empty_proj_dir.mkdir(parents=True, exist_ok=True)

    # Registra no catálogo um cenário fantasma / órfão cujo arquivo físico foi apagado
    ghost_scenario_path = empty_proj_dir / "scenarios" / "apagado.yaml"
    register_project_scenario(
        scenario_path=ghost_scenario_path,
        scenario_data={"id": "cenario_fantasma", "name": "Cenário Fantasma"},
        project_name="Projeto Vazio",
        config_path=cfg_file,
    )

    # Garante que o arquivo físico não existe
    assert not ghost_scenario_path.exists()

    # Faz GET /api/projects -> scenarios_count deve ser 0 (não conta entrada órfã)
    resp = client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    projects = resp.json()
    proj_vazio = next((p for p in projects if p["name"] == "Projeto Vazio"), None)
    assert proj_vazio is not None
    assert proj_vazio["scenarios_count"] == 0

    # 2. Adiciona cenários válidos na pasta do projeto
    scenarios_dir = empty_proj_dir / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    scenario_valid_1 = scenarios_dir / "fluxo_1.yaml"
    scenario_valid_1.write_text(
        """id: fluxo_1
title: Fluxo 1
steps:
  - action: goto
    url: https://example.com
""",
        encoding="utf-8",
    )

    scenario_valid_2 = scenarios_dir / "fluxo_2.yaml"
    scenario_valid_2.write_text(
        """id: fluxo_2
title: Fluxo 2
steps:
  - action: goto
    url: https://example.com
""",
        encoding="utf-8",
    )

    # Cria também um arquivo YAML inválido/sem steps que não deve ser contado
    invalid_yaml = scenarios_dir / "docker-compose.yaml"
    invalid_yaml.write_text("version: '3'\nservices: {}\n", encoding="utf-8")

    # Faz novo GET /api/projects -> scenarios_count deve ser exatamente 2
    resp2 = client.get("/api/projects", headers=auth_headers)
    assert resp2.status_code == 200
    projects2 = resp2.json()
    proj_com_cenarios = next((p for p in projects2 if p["name"] == "Projeto Vazio"), None)
    assert proj_com_cenarios is not None
    assert proj_com_cenarios["scenarios_count"] == 2

    # 3. Registra projeto com diretório inexistente no disco
    non_existent_dir = tmp_path / "diretorio_inexistente"
    register_project_scenario(
        scenario_path=non_existent_dir / "scenarios" / "fantasma.yaml",
        scenario_data={"id": "fantasma", "name": "Fantasma"},
        project_name="Projeto Sem Pasta",
        config_path=cfg_file,
    )
    resp3 = client.get("/api/projects", headers=auth_headers)
    assert resp3.status_code == 200
    projects3 = resp3.json()
    proj_sem_pasta = next((p for p in projects3 if p["name"] == "Projeto Sem Pasta"), None)
    assert proj_sem_pasta is not None
    assert proj_sem_pasta["scenarios_count"] == 0


# ==============================================================================
# 17. Status de IA e Bloqueio Mandatório de Execução (UXS-74 / Passo 2)
# ==============================================================================


def test_ai_status_endpoint_api_key_connected(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida GET /api/config/ai-status com provedor API Key contendo chave válida e conexão operacional."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=True,
            )
        },
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "API Gemini operacional."),
        ),
    ):
        resp = client.get("/api/config/ai-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["provider"] == "gemini_cloud"
        assert "operacional" in data["message"]


def test_ai_status_endpoint_api_key_disconnected(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida GET /api/config/ai-status com provedor API Key sem chave configurada."""
    mock_cfg = _build_mock_safe_config(
        active_provider="openai_cloud",
        providers={
            "openai_cloud": ProviderSafeDTO(
                type="api_key",
                service="openai",
                model="gpt-4o",
                has_api_key=False,
            )
        },
    )
    with patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg):
        resp = client.get("/api/config/ai-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["provider"] == "openai_cloud"
        assert "Chave de API não informada" in data["message"]


def test_ai_status_endpoint_sso_connected_via_cache(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida GET /api/config/ai-status com provedor SSO autenticado via cache e teste bem-sucedido."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_sso",
        providers={
            "gemini_sso": ProviderSafeDTO(
                type="sso",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=False,
            )
        },
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch("uxsentinel_studio.api.get_cached_token", return_value="ya29.mock_oauth_token_valido"),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "Provedor SSO operacional."),
        ),
    ):
        resp = client.get("/api/config/ai-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["provider"] == "gemini_sso"
        assert "operacional" in data["message"]


def test_ai_status_endpoint_sso_disconnected(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida GET /api/config/ai-status com provedor SSO não autenticado."""
    mock_cfg = _build_mock_safe_config(
        active_provider="claude_sso",
        providers={
            "claude_sso": ProviderSafeDTO(
                type="sso",
                service="anthropic",
                model="claude-haiku-4-5",
                has_api_key=False,
            )
        },
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch("uxsentinel_studio.api.get_cached_token", return_value=None),
        patch(
            "uxsentinel_studio.api.get_sso_cache_file", return_value=Path("/tmp/non_existent_sso_cache.json")
        ),
    ):
        resp = client.get("/api/config/ai-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["provider"] == "claude_sso"
        assert "não autenticado" in data["message"]


def test_ai_status_endpoint_local_provider_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida GET /api/config/ai-status com provedor local (Ollama) operacional."""
    mock_cfg = _build_mock_safe_config(
        active_provider="ollama_local",
        providers={
            "ollama_local": ProviderSafeDTO(
                type="local",
                service="ollama",
                model="qwen2-vl:7b",
                has_api_key=False,
            )
        },
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "Ollama local operacional com o modelo 'qwen2-vl:7b'."),
        ),
    ):
        resp = client.get("/api/config/ai-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["provider"] == "ollama_local"
        assert "operacional" in data["message"]


def test_ai_status_endpoint_local_provider_missing_model(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Valida GET /api/config/ai-status com Ollama sem o modelo instalado (UXS-75 causa raiz)."""
    mock_cfg = _build_mock_safe_config(
        active_provider="ollama_local",
        providers={
            "ollama_local": ProviderSafeDTO(
                type="local",
                service="ollama",
                model="qwen2-vl:7b",
                has_api_key=False,
            )
        },
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(
                False,
                "Ollama ativo, mas o modelo 'qwen2-vl:7b' não está instalado. Execute 'ollama pull qwen2-vl:7b'.",
            ),
        ),
    ):
        resp = client.get("/api/config/ai-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["provider"] == "ollama_local"
        assert "não está instalado" in data["message"]


def test_ai_status_endpoint_timeout(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida GET /api/config/ai-status tratando TimeoutError."""
    mock_cfg = _build_mock_safe_config(
        active_provider="ollama_local",
        providers={
            "ollama_local": ProviderSafeDTO(
                type="local",
                service="ollama",
                model="qwen2-vl:7b",
                has_api_key=False,
            )
        },
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            side_effect=TimeoutError(),
        ),
    ):
        resp = client.get("/api/config/ai-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["provider"] == "ollama_local"
        assert "Tempo limite esgotado" in data["message"]


def test_execution_run_blocked_when_ai_disconnected(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Garante que POST /api/execution/run retorna 400 com a mensagem exata se a IA não estiver conectada."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=False,
            )
        },
    )
    with patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg):
        resp = client.post(
            "/api/execution/run",
            json={"scenario_id": "cenario_teste"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "Chave de API não informada para o provedor 'gemini_cloud'." in data["detail"]


def test_execution_run_allowed_when_ai_connected(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Garante que POST /api/execution/run cria execução quando a IA está conectada."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=True,
            )
        },
    )
    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.0,
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "Conectado"),
        ),
        patch(
            "uxsentinel.service.execution_service.ExecutionService.run",
            new_callable=AsyncMock,
            return_value=dummy_report,
        ),
    ):
        resp = client.post(
            "/api/execution/run",
            json={"scenario_id": "cenario_teste"},
            headers=auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"


def test_execution_run_with_headless_and_slowmo_overrides(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Garante que POST /api/execution/run aceita overrides de headless e slowmo e os repassa ao ExecutionService."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=True,
            )
        },
    )
    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.0,
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "Conectado"),
        ),
        patch(
            "uxsentinel.service.execution_service.ExecutionService.run",
            new_callable=AsyncMock,
            return_value=dummy_report,
        ) as mock_run,
    ):
        resp = client.post(
            "/api/execution/run",
            json={
                "scenario_id": "cenario_teste",
                "overrides": {
                    "headless": False,
                    "slowmo": 450,
                },
            },
            headers=auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"

        assert mock_run.call_count == 1
        call_options = mock_run.call_args[0][0]
        assert call_options.headless is False
        assert call_options.slowmo == 450


def test_run_execution_with_devtools_console_inspect_overrides(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Garante que POST /api/execution/run aceita overrides de devtools, capture_console e inspect e os repassa ao ExecutionService."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=True,
            )
        },
    )
    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.0,
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "Conectado"),
        ),
        patch(
            "uxsentinel.service.execution_service.ExecutionService.run",
            new_callable=AsyncMock,
            return_value=dummy_report,
        ) as mock_run,
    ):
        resp = client.post(
            "/api/execution/run",
            json={
                "scenario_id": "cenario_teste",
                "overrides": {
                    "headless": False,
                    "devtools": True,
                    "capture_console": True,
                    "inspect": True,
                    "slowmo": 300,
                },
            },
            headers=auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"

        assert mock_run.call_count == 1
        call_options = mock_run.call_args[0][0]
        assert call_options.headless is False
        assert call_options.devtools is True
        assert call_options.capture_console is True
        assert call_options.inspect is True
        assert call_options.slowmo == 300


def test_run_execution_with_console_alias_override(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Garante que POST /api/execution/run aceita 'console' como alias para 'capture_console'."""
    mock_cfg = _build_mock_safe_config(
        active_provider="gemini_cloud",
        providers={
            "gemini_cloud": ProviderSafeDTO(
                type="api_key",
                service="gemini",
                model="gemini-1.5-pro",
                has_api_key=True,
            )
        },
    )
    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.0,
    )
    with (
        patch("uxsentinel.service.config_service.ConfigService.get_safe_config", return_value=mock_cfg),
        patch(
            "uxsentinel_studio.api.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
            return_value=(True, "Conectado"),
        ),
        patch(
            "uxsentinel.service.execution_service.ExecutionService.run",
            new_callable=AsyncMock,
            return_value=dummy_report,
        ) as mock_run,
    ):
        resp = client.post(
            "/api/execution/run",
            json={
                "scenario_id": "cenario_teste",
                "overrides": {
                    "console": True,
                    "devtools": True,
                    "inspect": True,
                },
            },
            headers=auth_headers,
        )
        assert resp.status_code == 202
        assert mock_run.call_count == 1
        call_options = mock_run.call_args[0][0]
        assert call_options.devtools is True
        assert call_options.capture_console is True
        assert call_options.inspect is True


def test_login_sso_success_claude(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida POST /api/config/login-sso com claude_sso com sucesso hermético."""
    with patch("uxsentinel.cli.handle_login_sso", return_value=0) as mock_handle:
        resp = client.post(
            "/api/config/login-sso",
            json={"provider": "claude_sso"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "claude_sso" in data["message"]
        assert mock_handle.call_count == 1


def test_login_sso_success_gemini(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida POST /api/config/login-sso com gemini_sso com sucesso hermético."""
    with patch("uxsentinel.cli.handle_login_sso", return_value=0) as mock_handle:
        resp = client.post(
            "/api/config/login-sso",
            json={"provider": "gemini_sso"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "gemini_sso" in data["message"]
        assert mock_handle.call_count == 1


def test_login_sso_invalid_provider(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida erro 400 em POST /api/config/login-sso ao informar provedor não SSO."""
    resp = client.post(
        "/api/config/login-sso",
        json={"provider": "openai"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "não é suportado" in data["detail"]


def test_login_sso_unauthorized(client: TestClient) -> None:
    """Valida recusa 401 em POST /api/config/login-sso sem token de autenticação."""
    resp = client.post(
        "/api/config/login-sso",
        json={"provider": "claude_sso"},
    )
    assert resp.status_code == 401


# ==============================================================================
# 16. Configuração e Sincronização de Modo Headless (UXS-76)
# ==============================================================================


def test_get_config_reflects_browser_headless_file_setting(
    client: TestClient, auth_headers: dict[str, str], project_workspace: Path
) -> None:
    """Valida que GET /api/config reflete fielmente o valor de browser.headless do arquivo."""
    cfg_file = project_workspace / "uxsentinel.yaml"

    # 1. Config com headless=True
    cfg_file.write_text(
        "browser:\n  headless: true\n  slow_mo_ms: 150\n",
        encoding="utf-8",
    )
    resp = client.get("/api/config", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["browser"]["headless"] is True

    # 2. Config com headless=False
    cfg_file.write_text(
        "browser:\n  headless: false\n  slow_mo_ms: 300\n",
        encoding="utf-8",
    )
    resp = client.get("/api/config", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["browser"]["headless"] is False


def test_scenario_detail_reflects_headless_setting(
    client: TestClient, auth_headers: dict[str, str], project_workspace: Path
) -> None:
    """Valida que GET /api/scenarios/{id} retorna o valor headless declarado no cenário."""
    scenarios_dir = project_workspace / "scenarios"

    # Cenário com headless: true
    (scenarios_dir / "cenario_headless_true.yaml").write_text(
        """id: cenario_headless_true
title: "Cenário com Headless True"
profile: generic
headless: true
steps:
  - action: goto
    url: "https://exemplo.com.br"
""",
        encoding="utf-8",
    )

    # Cenário com headless: false
    (scenarios_dir / "cenario_headless_false.yaml").write_text(
        """id: cenario_headless_false
title: "Cenário com Headless False"
profile: generic
headless: false
steps:
  - action: goto
    url: "https://exemplo.com.br"
""",
        encoding="utf-8",
    )

    # Cenário sem headless declarado
    (scenarios_dir / "cenario_sem_headless.yaml").write_text(
        """id: cenario_sem_headless
title: "Cenário Sem Headless"
profile: generic
steps:
  - action: goto
    url: "https://exemplo.com.br"
""",
        encoding="utf-8",
    )

    resp_true = client.get("/api/scenarios/cenario_headless_true", headers=auth_headers)
    assert resp_true.status_code == 200
    assert resp_true.json()["headless"] is True

    resp_false = client.get("/api/scenarios/cenario_headless_false", headers=auth_headers)
    assert resp_false.status_code == 200
    assert resp_false.json()["headless"] is False

    resp_none = client.get("/api/scenarios/cenario_sem_headless", headers=auth_headers)
    assert resp_none.status_code == 200
    assert resp_none.json()["headless"] is None


def test_config_update_dto_unpacks_nested_browser_headless(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Garante que POST /api/config desempacota browser.headless de estruturas aninhadas."""
    with patch("uxsentinel.service.config_service.ConfigService.update_config") as mock_update:
        resp = client.post(
            "/api/config",
            json={
                "browser": {
                    "headless": True,
                    "slow_mo_ms": 250,
                }
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        mock_update.assert_called_once()
        called_dto = mock_update.call_args[0][0]
        assert called_dto.browser_headless is True
        assert called_dto.browser_slow_mo_ms == 250


def test_studio_static_app_js_syntax_integrity() -> None:
    """Valida a integridade sintática de app.js usando node --check ou balanceamento de chaves."""
    app_js_path = Path(__file__).resolve().parent.parent / "uxsentinel_studio" / "static" / "app.js"
    assert app_js_path.is_file(), f"Arquivo app.js não encontrado em {app_js_path}"

    node_bin = shutil.which("node")
    if node_bin:
        res = subprocess.run(
            [node_bin, "--check", str(app_js_path)],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Erro de sintaxe em app.js:\n{res.stderr}"
    else:
        content = app_js_path.read_text(encoding="utf-8")
        open_braces = content.count("{")
        close_braces = content.count("}")
        assert open_braces == close_braces, (
            f"Desbalanceamento de chaves em app.js: {open_braces} != {close_braces}"
        )
