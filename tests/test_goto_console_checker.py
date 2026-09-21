"""Testes herméticos para a validação de erros críticos de console e rede no GotoActionHandler (UXS-45).

Verifica:
1. Ao abrir uma página com erro JS crítico (ex: Uncaught TypeError), uma issue BLOQUEANTE com
   avaliador 'console_checker' e checkpoint 'goto_console_error' é registrada.
2. Com fail_fast=True (padrão), o cenário é interrompido imediatamente após o goto.
3. Erros inofensivos (404 favicon/robots, bloqueio de tracking/analytics) são filtrados e não geram issue.
4. Páginas sem erros de console continuam o fluxo normalmente.
5. Cláusula de exceções do cenário/passo é respeitada para dispensar erros autorizados.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.browser.telemetry import (
    BrowserTelemetryCollector,
    ConsoleLogEntry,
    NetworkFailureEntry,
)
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    CheckpointResult,
    IssueCategory,
    IssueSeverity,
    Scenario,
    ScenarioExceptions,
    StepAction,
)


def _mock_inspect(**kwargs):
    return CheckpointResult(
        name=kwargs["checkpoint_name"],
        expected_behavior=kwargs["expected_behavior"],
        screenshot_path=kwargs.get("screenshot_path"),
        status="ok",
        issues=[],
    )


@pytest.mark.asyncio
async def test_goto_critical_js_error_creates_bloqueante_issue(tmp_path: Path):
    """Testa que ao abrir uma página com erro JS crítico (Uncaught TypeError), uma issue BLOQUEANTE é registrada."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_js_error",
        title="Cenário Erro JS",
        fail_fast=True,
        steps=[
            StepAction(action="goto", url="https://app.local/dashboard"),
            StepAction(action="checkpoint", name="checkpoint_nao_deve_executar"),
        ],
    )

    telemetry = BrowserTelemetryCollector()
    telemetry.console_logs.append(
        ConsoleLogEntry(
            type="error",
            text="Uncaught TypeError: Cannot read properties of undefined (reading 'init')",
            location="https://app.local/assets/app.js:120",
        )
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.telemetry = telemetry
    mock_driver.page = AsyncMock()

    async def fake_screenshot(path, full_page=True):
        Path(path).write_bytes(b"fake_png")

    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print") as mock_print,
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.name == "goto_console_error"
    assert cp.status == "erro_execucao"
    assert cp.screenshot_path is not None
    assert "goto_console_error.png" in cp.screenshot_path

    assert len(cp.issues) == 1
    issue = cp.issues[0]
    assert issue.severidade == IssueSeverity.BLOQUEANTE
    assert issue.evaluator == "console_checker"
    assert issue.categoria == IssueCategory.OUTRO
    assert "Uncaught TypeError" in issue.descricao

    assert report.success is False
    assert report.total_bloqueantes >= 1

    # Verifica se a mensagem no terminal Rich foi impressa
    printed_texts = " ".join(str(call) for call in mock_print.call_args_list)
    assert "ERRO CRÍTICO NO CONSOLE AO ABRIR A PÁGINA" in printed_texts
    assert "FALHA GRAVE DETECTADA" in printed_texts


@pytest.mark.asyncio
async def test_goto_critical_network_5xx_aborts_on_fail_fast(tmp_path: Path):
    """Testa que erro HTTP 500 ou 502 na página inicial é detectado como crítico e interrompe no fail_fast."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_net_500",
        title="Cenário Erro 500",
        fail_fast=True,
        steps=[
            StepAction(action="goto", url="https://app.local/login"),
            StepAction(action="click", selector="#btn-login"),
        ],
    )

    telemetry = BrowserTelemetryCollector()
    telemetry.network_failures.append(
        NetworkFailureEntry(
            url="https://app.local/login",
            method="GET",
            status=500,
            error_text="Internal Server Error",
        )
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.telemetry = telemetry
    mock_driver.page = AsyncMock()

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print") as mock_print,
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    names = [c.name for c in report.checkpoints]
    assert "goto_console_error" in names
    assert report.success is False

    printed_texts = " ".join(str(call) for call in mock_print.call_args_list)
    assert "ERRO CRÍTICO NO CONSOLE AO ABRIR A PÁGINA" in printed_texts
    assert "HTTP 500" in printed_texts


@pytest.mark.asyncio
async def test_goto_ignores_harmless_noise(tmp_path: Path):
    """Testa que erros inofensivos (404 favicon, bloqueio de tracking/analytics) não geram issue nem interrompem."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_noise",
        title="Cenário com Ruídos Inofensivos",
        fail_fast=True,
        steps=[
            StepAction(action="goto", url="https://app.local/home"),
            StepAction(action="checkpoint", name="checkpoint_sucesso"),
        ],
    )

    telemetry = BrowserTelemetryCollector()
    # 1. 404 em favicon
    telemetry.network_failures.append(
        NetworkFailureEntry(
            url="https://app.local/favicon.ico",
            method="GET",
            status=404,
            error_text="net::ERR_ABORTED",
        )
    )
    # 2. Analytics bloqueado
    telemetry.network_failures.append(
        NetworkFailureEntry(
            url="https://www.google-analytics.com/analytics.js",
            method="GET",
            status=None,
            error_text="net::ERR_BLOCKED_BY_CLIENT",
        )
    )
    # 3. Log de console sobre Sentry ou Hotjar
    telemetry.console_logs.append(
        ConsoleLogEntry(
            type="error",
            text="Failed to load resource: net::ERR_BLOCKED_BY_CLIENT (hotjar-12345.js)",
            location="https://static.hotjar.com/c/hotjar-12345.js:1",
        )
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.telemetry = telemetry
    mock_driver.page = AsyncMock()
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")
    mock_driver.validate_dom = AsyncMock(return_value=[])

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    names = [c.name for c in report.checkpoints]
    assert "goto_console_error" not in names
    assert "checkpoint_sucesso" in names
    assert report.success is True
    assert report.total_bloqueantes == 0


@pytest.mark.asyncio
async def test_goto_clean_page_continues_flow(tmp_path: Path):
    """Testa que página sem erros no console continua o fluxo normalmente."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_limpo",
        title="Cenário Limpo",
        steps=[
            StepAction(action="goto", url="https://app.local/clean"),
            StepAction(action="checkpoint", name="cp_limpo"),
        ],
    )

    telemetry = BrowserTelemetryCollector()
    telemetry.console_logs.append(ConsoleLogEntry(type="info", text="App montado com sucesso."))

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.telemetry = telemetry
    mock_driver.page = AsyncMock()
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")
    mock_driver.validate_dom = AsyncMock(return_value=[])

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    names = [c.name for c in report.checkpoints]
    assert "goto_console_error" not in names
    assert "cp_limpo" in names
    assert report.success is True


@pytest.mark.asyncio
async def test_goto_respects_scenario_exceptions(tmp_path: Path):
    """Testa que se o cenário declara allowed_texts para o erro, ele é desconsiderado."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_excecao",
        title="Cenário com Exceção Permitida",
        fail_fast=True,
        exceptions=ScenarioExceptions(
            allowed_texts=["LegacyLibraryError"],
        ),
        steps=[
            StepAction(action="goto", url="https://app.local/legacy"),
            StepAction(action="checkpoint", name="checkpoint_permitido"),
        ],
    )

    telemetry = BrowserTelemetryCollector()
    telemetry.console_logs.append(
        ConsoleLogEntry(
            type="error",
            text="Uncaught ReferenceError: LegacyLibraryError is not defined",
        )
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.telemetry = telemetry
    mock_driver.page = AsyncMock()
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")
    mock_driver.validate_dom = AsyncMock(return_value=[])

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    names = [c.name for c in report.checkpoints]
    assert "goto_console_error" not in names
    assert "checkpoint_permitido" in names
    assert report.success is True
