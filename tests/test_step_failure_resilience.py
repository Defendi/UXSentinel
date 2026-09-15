"""Resiliência do agente a falhas de passo.

Uma falha em um passo (seletor quebrado, timeout) não pode abortar o restante da
auditoria: os checkpoints e viewports seguintes precisam ser executados e a falha
precisa aparecer no relatório como inconsistência bloqueante.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    CheckpointResult,
    IssueSeverity,
    Scenario,
    StepAction,
    TestReport,
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
async def test_failed_step_does_not_abort_remaining_checkpoints(tmp_path: Path):
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_com_falha",
        title="Cenario com passo quebrado",
        steps=[
            StepAction(action="click", selector="#nao-existe"),
            StepAction(action="checkpoint", name="depois_da_falha"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="Conteudo da pagina")
    mock_driver.page = AsyncMock()
    mock_driver.validate_dom = AsyncMock(return_value=[])
    mock_driver.click = AsyncMock(side_effect=RuntimeError("seletor #nao-existe nao encontrado"))

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    nomes = [cp.name for cp in report.checkpoints]
    assert "depois_da_falha" in nomes, "o checkpoint seguinte a falha precisa ser executado"

    falhas = [cp for cp in report.checkpoints if cp.status == "erro_execucao"]
    assert len(falhas) == 1
    assert falhas[0].issues[0].severidade == IssueSeverity.BLOQUEANTE
    assert "seletor #nao-existe nao encontrado" in falhas[0].issues[0].descricao
    assert report.success is False


@pytest.mark.asyncio
async def test_modal_that_does_not_close_emits_warning(tmp_path: Path):
    """O retorno False de wait_modal_close nao pode passar despercebido."""
    agent = UXSentinelAgent(GlobalConfig())

    driver = AsyncMock()
    driver.wait_modal_close = AsyncMock(return_value=False)

    report = TestReport(
        scenario_id="cenario_modal",
        scenario_title="Modal preso",
        profile="generic",
        provider_used="ollama_local",
    )

    with patch("uxsentinel.core.agent.console.print") as mock_print:
        await agent._execute_step(
            1,
            StepAction(action="wait_modal_close"),
            driver,
            Scenario(id="cenario_modal", title="Modal preso", steps=[]),
            report,
            tmp_path,
        )

    mensagens = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
    assert "fechado" in mensagens.lower(), f"nenhum aviso sobre modal nao fechado em: {mensagens}"
