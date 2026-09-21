"""Testes de conformidade e hermeticidade para o mecanismo Fail-Fast (UXS-44).

Verifica:
1. Resolução hierárquica de `resolve_fail_fast_mode` (CLI > Cenário > Config > Fallback True);
2. Parsing de `fail_fast` e `abort_on_error` a partir do YAML do cenário;
3. Que por padrão (`fail_fast=True`), um passo com erro aborta os passos e viewports subsequentes;
4. Que a screenshot de falha é salva no driver (`passo_XX_falha.png`) e anexada ao checkpoint;
5. Que o relatório final é gerado com `report.success == False`;
6. Que asserções com falha grave abortam a execução quando `fail_fast=True`;
7. Que com `--no-fail-fast` ou `fail_fast=False`, a execução continua normalmente.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import (
    GlobalConfig,
    resolve_fail_fast_mode,
)
from uxsentinel.core.models import (
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    StepAction,
)
from uxsentinel.core.runner import ScenarioRunnerService, ScenarioRunOptions
from uxsentinel.scenarios.parser import load_scenario


def _mock_inspect(**kwargs):
    return CheckpointResult(
        name=kwargs["checkpoint_name"],
        expected_behavior=kwargs["expected_behavior"],
        screenshot_path=kwargs.get("screenshot_path"),
        status="ok",
        issues=[],
    )


def _load_scenario_from_yaml(content: str) -> Scenario:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        return load_scenario(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_resolve_fail_fast_hierarchy():
    """Testa a precedência estrita: CLI > Cenário > Config > Fallback True."""
    # 1. Fallback padrão: True
    assert resolve_fail_fast_mode() is True
    assert resolve_fail_fast_mode(None, None, None) is True

    # 2. Config global
    assert resolve_fail_fast_mode(None, None, False) is False
    assert resolve_fail_fast_mode(None, None, True) is True

    # 3. Cenário sobrepõe config
    assert resolve_fail_fast_mode(None, False, True) is False
    assert resolve_fail_fast_mode(None, True, False) is True

    # 4. CLI sobrepõe cenário e config
    assert resolve_fail_fast_mode(False, True, True) is False
    assert resolve_fail_fast_mode(True, False, False) is True


def test_scenario_yaml_parser_fail_fast():
    """Testa o parsing de fail_fast e abort_on_error em YAML."""
    yaml_fail_fast = """
id: teste_fail_fast
title: Teste Fail Fast
fail_fast: false
steps:
  - action: goto
    url: https://example.com
"""
    sc = _load_scenario_from_yaml(yaml_fail_fast)
    assert sc.fail_fast is False

    yaml_abort_on_error = """
id: teste_abort
title: Teste Abort
abort_on_error: true
steps:
  - action: goto
    url: https://example.com
"""
    sc2 = _load_scenario_from_yaml(yaml_abort_on_error)
    assert sc2.fail_fast is True

    yaml_default = """
id: teste_default
title: Teste Default
steps:
  - action: goto
    url: https://example.com
"""
    sc3 = _load_scenario_from_yaml(yaml_default)
    assert sc3.fail_fast is None


def test_runner_service_prepares_fail_fast_config():
    """Verifica que o ScenarioRunnerService resolve adequadamente as opções."""
    runner = ScenarioRunnerService(GlobalConfig())
    sc = Scenario(id="sc1", title="SC1", fail_fast=False)

    # Cenário define False
    cfg = runner.prepare_config(sc, ScenarioRunOptions())
    assert cfg.browser.fail_fast is False

    # CLI com --fail-fast sobrepõe cenário
    cfg2 = runner.prepare_config(sc, ScenarioRunOptions(fail_fast=True))
    assert cfg2.browser.fail_fast is True


@pytest.mark.asyncio
async def test_fail_fast_default_aborts_subsequent_steps_and_viewports(tmp_path: Path):
    """Por padrão (fail_fast=True), um erro de execução interrompe os passos subsequentes."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_fail_fast",
        title="Cenário com Fail Fast Ativo",
        # fail_fast=None -> fallback True
        steps=[
            StepAction(action="click", selector="#btn-quebrado"),
            StepAction(action="checkpoint", name="passo_que_nao_deve_rodar"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="Conteúdo")
    mock_driver.page = AsyncMock()
    mock_driver.click = AsyncMock(side_effect=RuntimeError("Elemento #btn-quebrado inexistente"))

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print") as mock_print,
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    names = [cp.name for cp in report.checkpoints]
    assert "passo_que_nao_deve_rodar" not in names
    assert "passo_01_falha" in names

    assert report.success is False
    assert report.total_bloqueantes >= 1

    # Verifica se a mensagem de interrupção visual foi emitida
    printed_texts = " ".join(str(call) for call in mock_print.call_args_list)
    assert "FALHA GRAVE DETECTADA" in printed_texts
    assert "--fail-fast ativo" in printed_texts


@pytest.mark.asyncio
async def test_fail_fast_captures_screenshot_on_failure(tmp_path: Path):
    """Verifica que a screenshot de falha é salva no driver e associada ao checkpoint de erro."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    scenario = Scenario(
        id="cenario_screenshot",
        title="Cenário Teste Screenshot",
        fail_fast=True,
        steps=[
            StepAction(action="click", selector="#elemento-falho"),
        ],
    )

    async def fake_screenshot(path, full_page=True):
        Path(path).write_bytes(b"fake_png_data")

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.page = AsyncMock()
    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)
    mock_driver.click = AsyncMock(side_effect=TimeoutError("Timeout aguardando elemento"))

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.status == "erro_execucao"
    assert cp.screenshot_path is not None
    assert Path(cp.screenshot_path).is_file()
    assert "passo_01_falha.png" in cp.screenshot_path
    assert report.success is False


@pytest.mark.asyncio
async def test_fail_fast_aborts_on_severe_validation_checkpoint(tmp_path: Path):
    """Verifica que uma issue BLOQUEANTE ou ALTA em checkpoint aborta os passos subsequentes quando fail_fast=True."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    # Inspector mockado retornando uma issue ALTA
    def _mock_inspect_severe(**kwargs):
        return CheckpointResult(
            name=kwargs["checkpoint_name"],
            expected_behavior=kwargs["expected_behavior"],
            screenshot_path=kwargs.get("screenshot_path"),
            status="problemas_encontrados",
            issues=[
                Issue(
                    categoria=IssueCategory.REGRA_NEGOCIO,
                    severidade=IssueSeverity.ALTA,
                    descricao="Botão de pagamento invisível",
                    sugestao_correcao="Exibir botão",
                )
            ],
        )

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect_severe)

    scenario = Scenario(
        id="cenario_validacao_falha",
        title="Cenário Validação Severa",
        fail_fast=True,
        steps=[
            StepAction(action="checkpoint", name="checkpoint_inicial"),
            StepAction(action="checkpoint", name="checkpoint_posterior"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")
    mock_driver.page = AsyncMock()
    mock_driver.validate_dom = AsyncMock(return_value=[])

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print") as mock_print,
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    names = [cp.name for cp in report.checkpoints]
    assert "checkpoint_inicial" in names
    assert "checkpoint_posterior" not in names
    assert report.success is False

    printed_texts = " ".join(str(call) for call in mock_print.call_args_list)
    assert "FALHA GRAVE DETECTADA" in printed_texts


@pytest.mark.asyncio
async def test_no_fail_fast_continues_through_errors(tmp_path: Path):
    """Com fail_fast=False, o agente executa todos os passos mesmo havendo erros."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = GlobalConfig()
    cfg.browser.fail_fast = False
    cfg.reporting.output_dir = str(out_dir)
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))
    agent.inspector.inspect = AsyncMock(side_effect=_mock_inspect)

    scenario = Scenario(
        id="cenario_continua",
        title="Cenário Sem Fail Fast",
        steps=[
            StepAction(action="click", selector="#falha"),
            StepAction(action="checkpoint", name="passo_dois"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")
    mock_driver.page = AsyncMock()
    mock_driver.validate_dom = AsyncMock(return_value=[])
    mock_driver.click = AsyncMock(side_effect=RuntimeError("Falhou click"))

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    names = [cp.name for cp in report.checkpoints]
    assert "passo_01_falha" in names
    assert "passo_dois" in names
    assert report.success is False
