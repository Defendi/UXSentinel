"""Suíte de testes herméticos para o Servidor MCP Nativo do UXSentinel (UXS-85).

Testa handshake initialize, ping, tools/list, tools/call (5 ferramentas),
resources/list, resources/read, isolamento de stdio e tratamento de erros JSON-RPC.
"""

import asyncio
import io
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uxsentinel import __version__
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    AxeViolation,
    CheckpointResult,
    TestReport,
)
from uxsentinel.mcp.protocol import (
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)
from uxsentinel.mcp.server import MCPServer


@pytest.fixture
def mcp_server() -> MCPServer:
    """Fixture que fornece uma instância de MCPServer com configuração isolada."""
    cfg = GlobalConfig()
    return MCPServer(config=cfg)


@pytest.mark.asyncio
async def test_mcp_handshake_initialize(mcp_server: MCPServer):
    """Valida o handshake inicial MCP ('initialize') e a notificação 'initialized'."""
    init_line = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
    )

    response_line = await mcp_server.handle_line(init_line)
    assert response_line is not None

    data = json.loads(response_line)
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert "error" not in data

    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    assert result["serverInfo"]["name"] == "uxsentinel"
    assert result["serverInfo"]["version"] == __version__
    assert mcp_server.initialized is True

    # Notificação initialized (sem resposta)
    notif_line = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    notif_resp = await mcp_server.handle_line(notif_line)
    assert notif_resp is None


@pytest.mark.asyncio
async def test_mcp_ping(mcp_server: MCPServer):
    """Valida o método 'ping' para verificação de liveness."""
    ping_line = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    response_line = await mcp_server.handle_line(ping_line)
    assert response_line is not None

    data = json.loads(response_line)
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 2
    assert data["result"] == {}


@pytest.mark.asyncio
async def test_mcp_tools_list(mcp_server: MCPServer):
    """Valida a descoberta de ferramentas ('tools/list') e os schemas das 5 ferramentas."""
    req_line = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    response_line = await mcp_server.handle_line(req_line)
    assert response_line is not None

    data = json.loads(response_line)
    assert data["id"] == 3
    tools = data["result"]["tools"]

    tool_names = [t["name"] for t in tools]
    expected_tools = [
        "list_scenarios",
        "validate_scenario",
        "run_scenario",
        "inspect_url",
        "get_last_report",
    ]
    assert sorted(tool_names) == sorted(expected_tools)

    # Valida estrutura detalhada de schemas
    tools_by_name = {t["name"]: t for t in tools}
    assert "scenario_path" in tools_by_name["validate_scenario"]["inputSchema"]["properties"]
    assert "scenario_path" in tools_by_name["run_scenario"]["inputSchema"]["properties"]
    assert "url" in tools_by_name["inspect_url"]["inputSchema"]["properties"]
    assert "format" in tools_by_name["get_last_report"]["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_mcp_resources_list_and_read(mcp_server: MCPServer):
    """Valida 'resources/list' e 'resources/read' para cenários e relatórios."""
    # 1. resources/list
    list_line = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    list_resp = await mcp_server.handle_line(list_line)
    assert list_resp is not None

    list_data = json.loads(list_resp)
    resources = list_data["result"]["resources"]
    uris = [r["uri"] for r in resources]
    assert "uxsentinel://scenarios" in uris
    assert "uxsentinel://reports/latest" in uris

    # 2. resources/read para uxsentinel://scenarios
    read_scenarios_line = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "uxsentinel://scenarios"},
        }
    )
    read_scenarios_resp = await mcp_server.handle_line(read_scenarios_line)
    assert read_scenarios_resp is not None
    read_scenarios_data = json.loads(read_scenarios_resp)
    contents = read_scenarios_data["result"]["contents"]
    assert len(contents) > 0
    assert contents[0]["uri"] == "uxsentinel://scenarios"
    assert contents[0]["mimeType"] == "application/json"
    scenarios_list = json.loads(contents[0]["text"])
    assert isinstance(scenarios_list, list)

    # 3. resources/read para uxsentinel://reports/latest
    read_report_line = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "resources/read",
            "params": {"uri": "uxsentinel://reports/latest"},
        }
    )
    read_report_resp = await mcp_server.handle_line(read_report_line)
    assert read_report_resp is not None
    read_report_data = json.loads(read_report_resp)
    contents = read_report_data["result"]["contents"]
    assert contents[0]["uri"] == "uxsentinel://reports/latest"


@pytest.mark.asyncio
async def test_mcp_tools_call_list_scenarios(mcp_server: MCPServer):
    """Valida a execução de 'list_scenarios' com e sem filtros."""
    # Listagem geral
    req_line = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "list_scenarios", "arguments": {}},
        }
    )
    resp = await mcp_server.handle_line(req_line)
    assert resp is not None
    data = json.loads(resp)
    assert data["id"] == 7
    result = data["result"]
    assert result["isError"] is False
    scenarios = json.loads(result["content"][0]["text"])
    assert isinstance(scenarios, list)
    assert len(scenarios) > 0

    # Validação com filtro de perfil
    req_filter_line = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "list_scenarios", "arguments": {"profile": "odoo"}},
        }
    )
    resp_filter = await mcp_server.handle_line(req_filter_line)
    assert resp_filter is not None
    data_filter = json.loads(resp_filter)
    filtered_scenarios = json.loads(data_filter["result"]["content"][0]["text"])
    assert all(s["profile"].lower() == "odoo" for s in filtered_scenarios)


@pytest.mark.asyncio
async def test_mcp_tools_call_validate_scenario(tmp_path: Path, mcp_server: MCPServer):
    """Valida 'validate_scenario' com cenário válido e arquivo inválido."""
    # 1. Cenário válido
    valid_yaml = tmp_path / "valid_scenario.yaml"
    valid_yaml.write_text(
        """
id: valid_test
title: Cenário Válido
profile: generic
steps:
  - action: goto
    url: https://example.com
  - action: checkpoint
    name: tela_inicial
""",
        encoding="utf-8",
    )

    req_valid = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "validate_scenario", "arguments": {"scenario_path": str(valid_yaml)}},
        }
    )
    resp_valid = await mcp_server.handle_line(req_valid)
    assert resp_valid is not None
    val_data = json.loads(resp_valid)
    res = json.loads(val_data["result"]["content"][0]["text"])
    assert res["valid"] is True
    assert res["id"] == "valid_test"
    assert res["steps_count"] == 2

    # 2. Cenário inválido (sintaxe YAML corrompida)
    invalid_yaml = tmp_path / "corrupted_scenario.yaml"
    invalid_yaml.write_text("id: teste\nsteps: [invalid: : :", encoding="utf-8")

    req_invalid = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "validate_scenario", "arguments": {"scenario_path": str(invalid_yaml)}},
        }
    )
    resp_invalid = await mcp_server.handle_line(req_invalid)
    assert resp_invalid is not None
    inv_data = json.loads(resp_invalid)
    inv_res = json.loads(inv_data["result"]["content"][0]["text"])
    assert inv_res["valid"] is False
    assert len(inv_res["errors"]) > 0

    # 3. Arquivo inexistente
    req_missing = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "validate_scenario",
                "arguments": {"scenario_path": "arquivo_inexistente.yaml"},
            },
        }
    )
    resp_missing = await mcp_server.handle_line(req_missing)
    assert resp_missing is not None
    missing_data = json.loads(resp_missing)
    assert missing_data["result"]["isError"] is True


@pytest.mark.asyncio
async def test_mcp_tools_call_run_scenario_with_mock_agent(tmp_path: Path, mcp_server: MCPServer):
    """Valida a execução de 'run_scenario' utilizando mock seguro do UXSentinelAgent."""
    scenario_file = tmp_path / "smoke.yaml"
    scenario_file.write_text(
        """
id: smoke_run
title: Smoke Test
steps:
  - action: goto
    url: https://example.local
""",
        encoding="utf-8",
    )

    fake_report = TestReport(
        scenario_id="smoke_run",
        scenario_title="Smoke Test",
        success=True,
        duration_seconds=2.45,
        checkpoints=[
            CheckpointResult(
                name="cp1",
                expected_behavior="Tudo ok",
                status="ok",
                issues=[],
            )
        ],
    )
    fake_report.compute_totals()

    mock_agent_instance = MagicMock()
    mock_agent_instance.run_scenario = AsyncMock(return_value=fake_report)

    with patch("uxsentinel.core.agent.UXSentinelAgent", return_value=mock_agent_instance):
        req_line = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "run_scenario",
                    "arguments": {
                        "scenario_path": str(scenario_file),
                        "headless": True,
                        "slowmo": 0,
                    },
                },
            }
        )
        resp = await mcp_server.handle_line(req_line)
        assert resp is not None

        data = json.loads(resp)
        assert data["id"] == 12
        assert data["result"]["isError"] is False

        run_result = json.loads(data["result"]["content"][0]["text"])
        assert run_result["scenario_id"] == "smoke_run"
        assert run_result["success"] is True
        assert run_result["status"] == "passed"
        assert run_result["duration_seconds"] == 2.45
        assert run_result["checkpoints_count"] == 1
        mock_agent_instance.run_scenario.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_tools_call_inspect_url_with_mock(mcp_server: MCPServer):
    """Valida 'inspect_url' com mock hermético da sessão de navegador e AxeRunner."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.set_viewport_size = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=[])

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = AsyncMock()

    class FakeSessionContext:
        async def __aenter__(self):
            return mock_browser, mock_context

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    fake_violations = [
        AxeViolation(
            id="color-contrast",
            impact="serious",
            description="Contraste de cor insuficiente",
            help="Assegure contraste adequado",
            help_url="https://dequeuniversity.com/rules/axe/4.4/color-contrast",
            tags=["wcag2aa"],
            nodes=[],
        )
    ]

    mock_axe_instance = MagicMock()
    mock_axe_instance.run = AsyncMock(return_value=fake_violations)

    with (
        patch("uxsentinel.browser.session.open_browser_session", return_value=FakeSessionContext()),
        patch("uxsentinel.browser.axe_runner.AxeRunner", return_value=mock_axe_instance),
    ):
        req_line = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {
                    "name": "inspect_url",
                    "arguments": {
                        "url": "https://myapp.local/login",
                        "viewport": "desktop",
                        "check_a11y": True,
                        "check_visual": True,
                    },
                },
            }
        )
        resp = await mcp_server.handle_line(req_line)
        assert resp is not None

        data = json.loads(resp)
        assert data["id"] == 13
        assert data["result"]["isError"] is False

        inspect_res = json.loads(data["result"]["content"][0]["text"])
        assert inspect_res["url"] == "https://myapp.local/login"
        assert inspect_res["a11y_violations_count"] == 1
        assert inspect_res["a11y_violations"][0]["id"] == "color-contrast"
        mock_page.goto.assert_awaited_once_with("https://myapp.local/login", wait_until="load", timeout=30000)

    # Teste de validação para URL inválida
    req_invalid_url = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {"name": "inspect_url", "arguments": {"url": "invalid_url_sem_protocolo"}},
        }
    )
    resp_inv = await mcp_server.handle_line(req_invalid_url)
    assert resp_inv is not None
    data_inv = json.loads(resp_inv)
    assert data_inv["result"]["isError"] is True


@pytest.mark.asyncio
async def test_mcp_tools_call_get_last_report(tmp_path: Path, mcp_server: MCPServer):
    """Valida 'get_last_report' para formatos 'summary', 'json' e 'markdown'."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    fake_report_data = {
        "scenario_id": "fluxo_carrinho",
        "scenario_title": "Fluxo do Carrinho de Compras",
        "success": True,
        "duration_seconds": 5.12,
        "total_issues": 0,
        "total_bloqueantes": 0,
        "total_altas": 0,
        "total_medias": 0,
        "total_baixas": 0,
        "a11y_score": 96.5,
    }
    json_path = reports_dir / "fluxo_carrinho_report.json"
    json_path.write_text(json.dumps(fake_report_data), encoding="utf-8")

    md_path = reports_dir / "fluxo_carrinho_report.md"
    md_path.write_text("# Relatório Markdown de Teste", encoding="utf-8")

    with patch("uxsentinel.mcp.handlers._find_latest_report_file", return_value=json_path):
        # 1. Summary
        req_sum = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 15,
                "method": "tools/call",
                "params": {"name": "get_last_report", "arguments": {"format": "summary"}},
            }
        )
        resp_sum = await mcp_server.handle_line(req_sum)
        assert resp_sum is not None
        data_sum = json.loads(resp_sum)
        text_sum = data_sum["result"]["content"][0]["text"]
        assert "Fluxo do Carrinho de Compras" in text_sum
        assert "APROVADO" in text_sum

        # 2. JSON
        req_json = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 16,
                "method": "tools/call",
                "params": {"name": "get_last_report", "arguments": {"format": "json"}},
            }
        )
        resp_json = await mcp_server.handle_line(req_json)
        assert resp_json is not None
        data_json = json.loads(resp_json)
        json_res = json.loads(data_json["result"]["content"][0]["text"])
        assert json_res["scenario_id"] == "fluxo_carrinho"

        # 3. Markdown
        req_md = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 17,
                "method": "tools/call",
                "params": {"name": "get_last_report", "arguments": {"format": "markdown"}},
            }
        )
        resp_md = await mcp_server.handle_line(req_md)
        assert resp_md is not None
        data_md = json.loads(resp_md)
        assert "# Relatório Markdown de Teste" in data_md["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_unknown_method_error(mcp_server: MCPServer):
    """Valida o código de erro -32601 ao invocar um método desconhecido."""
    req_line = json.dumps({"jsonrpc": "2.0", "id": 18, "method": "metodo_fantasma_404"})
    resp = await mcp_server.handle_line(req_line)
    assert resp is not None

    data = json.loads(resp)
    assert data["id"] == 18
    assert data["error"]["code"] == METHOD_NOT_FOUND
    assert "não suportado" in data["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_invalid_json_parse_error(mcp_server: MCPServer):
    """Valida o código de erro -32700 para sintaxe JSON corrompida."""
    resp = await mcp_server.handle_line("{jsonrpc: 2.0, invalido")
    assert resp is not None

    data = json.loads(resp)
    assert data["error"]["code"] == PARSE_ERROR


@pytest.mark.asyncio
async def test_mcp_stdout_isolation_and_sanitization(mcp_server: MCPServer):
    """Valida que saídas espúrias em stdout são redirecionadas e não corrompem o canal JSON-RPC."""
    # Cria reader com mensagens válidas
    init_msg = json.dumps({"jsonrpc": "2.0", "id": 19, "method": "ping"}) + "\n"
    reader = asyncio.StreamReader()
    reader.feed_data(init_msg.encode("utf-8"))
    reader.feed_eof()

    class MockStreamWriter:
        def __init__(self):
            self.buffer = bytearray()

        def write(self, data: bytes):
            self.buffer.extend(data)

        async def drain(self):
            pass

    mock_writer = MockStreamWriter()
    original_stdout = sys.stdout

    # Redireciona stderr temporariamente para capturar os logs espúrios
    captured_stderr = io.StringIO()
    with patch("sys.stderr", captured_stderr):
        # Executa run_stdio com os streams simulados
        exit_code = await mcp_server.run_stdio(reader=reader, writer=mock_writer)  # type: ignore

    assert exit_code == 0
    # sys.stdout original deve ser restaurado
    assert sys.stdout is original_stdout

    # O writer do protocolo MCP só deve conter a resposta JSON-RPC válida
    output_lines = mock_writer.buffer.decode("utf-8").strip().splitlines()
    assert len(output_lines) == 1
    resp_obj = json.loads(output_lines[0])
    assert resp_obj["id"] == 19
    assert resp_obj["result"] == {}
