"""Testes unitários e de integração herméticos para o ScenarioRunnerService."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    StepAction,
    TestReport,
)
from uxsentinel.core.runner import (
    ScenarioRunnerService,
    ScenarioRunOptions,
)


@pytest.fixture
def mock_scenario(tmp_path: Path) -> Scenario:
    sc = Scenario(
        id="sc_test_runner",
        title="Cenário de Teste do Runner",
        steps=[
            StepAction(action="goto", url="https://example.com"),
            StepAction(action="checkpoint", name="cp1"),
        ],
    )
    return sc


def test_prepare_config_precedence(mock_scenario: Scenario):
    """Valida que prepare_config aplica as opções com precedência correta."""
    cfg = GlobalConfig()
    cfg.browser.headless = False
    cfg.browser.record_video = False

    runner = ScenarioRunnerService(cfg)
    options = ScenarioRunOptions(
        provider="gemini_sso",
        profile="odoo",
        headless=True,
        record_video=True,
        viewports="mobile",
        slowmo=500,
        markdown=True,
        devtools=True,
        archive=False,
    )

    resolved_cfg = runner.prepare_config(mock_scenario, options)

    assert resolved_cfg.active_provider == "gemini_sso"
    assert mock_scenario.profile == "odoo"
    # DevTools ativado força headless=False mesmo que options.headless fosse True
    assert resolved_cfg.browser.devtools is True
    assert resolved_cfg.browser.headless is False
    assert resolved_cfg.browser.record_video is True
    assert resolved_cfg.browser.slow_mo_ms == 500
    assert resolved_cfg.reporting.generate_markdown is True
    assert resolved_cfg.reporting.archive_previous_reports is False
    assert len(resolved_cfg.browser.viewports) == 1
    assert resolved_cfg.browser.viewports[0].name == "mobile"


@pytest.mark.asyncio
async def test_runner_run_scenario(mock_scenario: Scenario, tmp_path: Path):
    """Valida a execução de um cenário via ScenarioRunnerService delegando ao UXSentinelAgent."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    runner = ScenarioRunnerService(cfg)

    fake_report = TestReport(
        scenario_id=mock_scenario.id,
        scenario_title=mock_scenario.title,
        success=True,
        checkpoints=[
            CheckpointResult(
                name="cp1",
                expected_behavior="OK",
                status="ok",
                issues=[],
            )
        ],
    )

    with patch("uxsentinel.core.runner.UXSentinelAgent") as mock_agent_cls:
        mock_agent = AsyncMock()
        mock_agent.run_scenario.return_value = fake_report
        mock_agent_cls.return_value = mock_agent

        report = await runner.run_scenario(mock_scenario, ScenarioRunOptions(headless=True))

        assert report.success is True
        assert report.scenario_id == mock_scenario.id
        mock_agent.run_scenario.assert_called_once()


@pytest.mark.asyncio
async def test_runner_run_with_multi_viewport(mock_scenario: Scenario, tmp_path: Path):
    """Valida run_with_multi_viewport tanto em modo sequencial quanto concorrente."""
    cfg = GlobalConfig()
    runner = ScenarioRunnerService(cfg)

    def create_fake_report(sc, opts=None):
        vp_label = opts.viewports[0].name if opts and opts.viewports else "default"
        return TestReport(
            scenario_id=mock_scenario.id,
            scenario_title=mock_scenario.title,
            viewports_tested=[vp_label],
            success=True,
        )

    with patch.object(runner, "run_scenario", side_effect=create_fake_report) as mock_run:
        # 1. Sequencial
        reports_seq = await runner.run_with_multi_viewport(
            mock_scenario,
            viewports=["desktop", "mobile"],
            concurrent=False,
        )
        assert len(reports_seq) == 2
        assert mock_run.call_count == 2

        # 2. Concorrente
        mock_run.reset_mock()
        reports_conc = await runner.run_with_multi_viewport(
            mock_scenario,
            viewports=["desktop", "tablet", "mobile"],
            concurrent=True,
        )
        assert len(reports_conc) == 3
        assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_runner_run_multiple_scenarios(tmp_path: Path):
    """Valida execução agregada de múltiplos cenários gerando MultiScenarioReport."""
    cfg = GlobalConfig()
    runner = ScenarioRunnerService(cfg)

    sc1 = Scenario(id="sc1", title="Cenário 1", steps=[])
    sc2 = Scenario(id="sc2", title="Cenário 2", steps=[])

    rep1 = TestReport(scenario_id="sc1", scenario_title="Cenário 1", success=True)
    rep2 = TestReport(
        scenario_id="sc2",
        scenario_title="Cenário 2",
        success=False,
        checkpoints=[
            CheckpointResult(
                name="cp_fail",
                expected_behavior="Layout correto",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.LAYOUT_MODAL,
                        severidade=IssueSeverity.BLOQUEANTE,
                        descricao="Erro crítico de layout",
                    )
                ],
            )
        ],
    )
    rep2.compute_totals()

    async def mock_run_scenario(sc, opts=None):
        return rep1 if sc.id == "sc1" else rep2

    with patch.object(runner, "run_scenario", side_effect=mock_run_scenario):
        # 1. Sequencial
        multi_rep = await runner.run_multiple_scenarios([sc1, sc2], max_concurrency=1)
        assert multi_rep.total_scenarios == 2
        assert multi_rep.passed_scenarios == 1
        assert multi_rep.failed_scenarios == 1
        assert multi_rep.success is False

        # 2. Concorrente
        multi_rep_conc = await runner.run_multiple_scenarios([sc1, sc2], max_concurrency=2)
        assert multi_rep_conc.total_scenarios == 2
        assert multi_rep_conc.passed_scenarios == 1
        assert multi_rep_conc.failed_scenarios == 1
        assert multi_rep_conc.success is False
