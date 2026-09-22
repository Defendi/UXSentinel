"""Testes herméticos para as rotas da API REST e streaming SSE do UXSentinel Studio (UXS-52 / STU-05)."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uxsentinel.core.models import CheckpointResult, TestReport
from uxsentinel.service import ConnectionResult
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


def test_list_and_get_scenarios(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Testa listagem e detalhamento de cenários do projeto e biblioteca."""
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
    resp_delete = client.delete("/api/scenarios/novo_fluxo", headers=auth_headers)
    assert resp_delete.status_code == 200
    assert resp_delete.json()["success"] is True
    assert not (project_workspace / "scenarios" / "novo_fluxo.yaml").exists()

    # 5. Exclusão de cenário inexistente -> 404
    resp_del_404 = client.delete("/api/scenarios/novo_fluxo", headers=auth_headers)
    assert resp_del_404.status_code == 404


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

    # Recuperação do artefato HTML
    resp_artifact = client.get("/api/results/cenario_teste/artifacts/relatorio.html", headers=auth_headers)
    assert resp_artifact.status_code == 200
    assert "Audit OK" in resp_artifact.text

    # Detalhe inexistente -> 404
    resp_detail_404 = client.get("/api/results/exec_fantasma", headers=auth_headers)
    assert resp_detail_404.status_code == 404


# ==============================================================================
# 7. Execução e Status em Background (/api/execution)
# ==============================================================================


def test_run_execution_and_status(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Valida disparo de execução assíncrona e consulta de status."""
    # Cenário inexistente -> 404
    r_404 = client.post(
        "/api/execution/run",
        json={"scenario_id": "cenario_inexistente"},
        headers=auth_headers,
    )
    assert r_404.status_code == 404

    # Disparo com mock do ExecutionService para manter hermeticidade
    dummy_report = TestReport(
        scenario_id="cenario_teste",
        scenario_title="Cenário de Teste Unitário",
        success=True,
        total_issues=0,
        duration_seconds=1.5,
    )

    with patch(
        "uxsentinel.service.execution_service.ExecutionService.run",
        new_callable=AsyncMock,
        return_value=dummy_report,
    ):
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

    EXECUTIONS.clear()
    for i in range(MAX_RETAINED_EXECUTIONS):
        EXECUTIONS[f"pre_fill_{i}"] = {"run_id": f"pre_fill_{i}", "status": "completed"}

    assert len(EXECUTIONS) == 50
    oldest_id = next(iter(EXECUTIONS))

    with patch("uxsentinel.service.execution_service.ExecutionService.run", new_callable=AsyncMock):
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

    resp = client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    active_proj = next((p for p in data if p["is_active"]), None)
    assert active_proj is not None
    assert "id" in active_proj
    assert "name" in active_proj
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
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    resp = client.get("/api/scenarios", headers=auth_headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) > 0
    sc = scenarios[0]
    assert "project_id" in sc
    assert "project_name" in sc
    assert sc["project_name"] is not None
