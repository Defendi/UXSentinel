"""Testes herméticos para o ExecutionService (UXS-31)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uxsentinel.core.models import TestReport
from uxsentinel.service.execution_service import ExecutionOptions, ExecutionService


@pytest.mark.asyncio
async def test_execution_service_runs_scenario_successfully():
    """Valida se ExecutionService delega corretamente para ScenarioRunnerService."""
    mock_report = TestReport(
        scenario_id="login_test",
        scenario_title="Teste de Login",
        success=True,
    )

    with patch("uxsentinel.service.execution_service.load_scenario") as mock_load:
        mock_scenario = MagicMock()
        mock_scenario.id = "login_test"
        mock_load.return_value = mock_scenario

        with patch.object(
            ExecutionService,
            "__init__",
            lambda self, config=None: setattr(self, "runner", MagicMock()),
        ):
            service = ExecutionService()
            service.runner.run_scenario = AsyncMock(return_value=mock_report)

            opts = ExecutionOptions(
                scenario_path=Path("scenarios/login.yaml"),
                headless=True,
                slowmo=200,
            )

            result = await service.run(opts)

            assert result.success is True
            assert result.scenario_id == "login_test"
            service.runner.run_scenario.assert_awaited_once()

            # Inspeciona opções repassadas ao ScenarioRunnerService
            args, kwargs = service.runner.run_scenario.await_args
            assert args[0] == mock_scenario
            runner_opts = args[1]
            assert runner_opts.headless is True
            assert runner_opts.slowmo == 200


@pytest.mark.asyncio
async def test_execution_service_handles_fail_fast_flag():
    """Valida repasse correto da flag fail_fast ao ScenarioRunnerService."""
    mock_report = TestReport(
        scenario_id="fail_fast_test",
        scenario_title="Teste Fail Fast",
        success=False,
    )

    with patch("uxsentinel.service.execution_service.load_scenario") as mock_load:
        mock_load.return_value = MagicMock()

        with patch.object(
            ExecutionService,
            "__init__",
            lambda self, config=None: setattr(self, "runner", MagicMock()),
        ):
            service = ExecutionService()
            service.runner.run_scenario = AsyncMock(return_value=mock_report)

            opts = ExecutionOptions(
                scenario_path="scenarios/checkout.yaml",
                fail_fast=True,
                jira=False,
            )

            result = await service.run(opts)
            assert result.success is False

            args, kwargs = service.runner.run_scenario.await_args
            runner_opts = args[1]
            assert runner_opts.fail_fast is True
            assert runner_opts.jira is False
