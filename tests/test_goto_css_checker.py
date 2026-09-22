"""Testes herméticos para validação de erros críticos de CSS no GotoActionHandler (UXS-47)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.browser.telemetry import BrowserTelemetryCollector
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    CheckpointResult,
    Scenario,
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
async def test_goto_critical_css_overflow_creates_checkpoint_and_halts(tmp_path: Path):
    """Testa que erro crítico de CSS (horizontal-overflow) no goto gera checkpoint de erro e interrompe fluxo com fail-fast."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    cfg.browser.enable_css_audit = True
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_css_overflow",
        title="Cenário Erro CSS Bloqueante",
        fail_fast=True,
        steps=[
            StepAction(action="goto", url="https://app.local/layout"),
            StepAction(action="checkpoint", name="checkpoint_nao_deve_executar"),
        ],
    )

    telemetry = BrowserTelemetryCollector()
    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.telemetry = telemetry
    mock_driver.page = AsyncMock()

    async def fake_screenshot(path, full_page=True):
        Path(path).write_bytes(b"fake_png")

    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)

    # Mock evaluate retornando violação bloqueante de CSS
    mock_driver.page.evaluate = AsyncMock(
        return_value=[
            {
                "rule_id": "horizontal-overflow",
                "category": "overflow",
                "severity": "bloqueante",
                "selector": "div.giant-table",
                "description": "Estouro de layout detectado no carregamento da página.",
                "suggestion": "max-width: 100%",
                "source": "runtime",
            }
        ]
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.name == "goto_css_error"
    assert cp.status == "erro_execucao"
    assert cp.screenshot_path is not None
    assert "goto_css_error.png" in cp.screenshot_path
    assert cp.css_audit is not None
    assert any(v.severity.value == "bloqueante" for v in cp.css_audit.violations)
    assert not report.success


@pytest.mark.asyncio
async def test_goto_css_disabled_skips_audit(tmp_path: Path):
    """Testa que quando CSS audit está desativado (--no-css ou config), nenhuma inspeção de CSS ocorre no goto."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    cfg.browser.enable_css_audit = False
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_no_css",
        title="Cenário Sem Auditoria CSS",
        fail_fast=True,
        steps=[
            StepAction(action="goto", url="https://app.local/dashboard"),
            StepAction(action="checkpoint", name="cp_normal"),
        ],
    )

    telemetry = BrowserTelemetryCollector()
    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.telemetry = telemetry
    mock_driver.page = AsyncMock()

    async def fake_screenshot(path, full_page=True):
        Path(path).write_bytes(b"fake_png")

    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)
    mock_driver.page.evaluate = AsyncMock(return_value=[])

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    # Não deve ter gerado goto_css_error
    cp_names = [cp.name for cp in report.checkpoints]
    assert "goto_css_error" not in cp_names
    assert "cp_normal" in cp_names
