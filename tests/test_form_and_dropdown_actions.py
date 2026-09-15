from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.browser.drivers.base_driver import BaseDriver
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    IssueCategory,
    IssueSeverity,
    Scenario,
    StepAction,
    TestReport,
)


class DummyDriver(BaseDriver):
    """Driver concreto simples para testes herméticos de BaseDriver."""

    async def wait_until_ready(self, timeout: int = 15000) -> None:
        pass

    async def wait_for_modal(self, timeout: int = 10000) -> bool:
        return True

    async def wait_modal_close(self, timeout: int = 10000) -> bool:
        return True


@pytest.mark.asyncio
async def test_driver_clear():
    page_mock = MagicMock()
    page_mock.wait_for_selector = AsyncMock()
    page_mock.fill = AsyncMock()
    page_mock.evaluate = AsyncMock()

    driver = DummyDriver(page=page_mock, highlight_clicks=False)
    await driver.clear("input#nome")

    page_mock.wait_for_selector.assert_called_once_with("input#nome", state="visible", timeout=10000)
    page_mock.fill.assert_called_once_with("input#nome", "", timeout=10000)


@pytest.mark.asyncio
async def test_driver_type_text():
    page_mock = MagicMock()
    page_mock.wait_for_selector = AsyncMock()
    locator_mock = MagicMock()
    first_mock = MagicMock()
    first_mock.focus = AsyncMock()
    first_mock.press_sequentially = AsyncMock()
    locator_mock.first = first_mock
    page_mock.locator = MagicMock(return_value=locator_mock)
    page_mock.evaluate = AsyncMock()

    driver = DummyDriver(page=page_mock, highlight_clicks=False)
    await driver.type_text("input#telefone", "11987654321", delay_ms=30)

    page_mock.wait_for_selector.assert_called_once_with("input#telefone", state="visible", timeout=10000)
    first_mock.focus.assert_called_once()
    first_mock.press_sequentially.assert_called_once_with("11987654321", delay=30, timeout=10000)


@pytest.mark.asyncio
async def test_driver_select_option_native():
    page_mock = MagicMock()
    page_mock.wait_for_selector = AsyncMock()
    page_mock.evaluate = AsyncMock(return_value="select")
    page_mock.select_option = AsyncMock()

    driver = DummyDriver(page=page_mock, highlight_clicks=False)
    await driver.select_option("select#pais", "Brasil")

    page_mock.select_option.assert_called_once_with("select#pais", label="Brasil", timeout=10000)


@pytest.mark.asyncio
async def test_driver_select_option_custom_dropdown():
    page_mock = MagicMock()
    page_mock.wait_for_selector = AsyncMock()
    page_mock.evaluate = AsyncMock(return_value="div")
    page_mock.click = AsyncMock()
    page_mock.wait_for_timeout = AsyncMock()

    opt_locator = MagicMock()
    opt_locator.count = AsyncMock(return_value=1)
    opt_first = MagicMock()
    opt_first.is_visible = AsyncMock(return_value=True)
    opt_first.click = AsyncMock()
    opt_locator.first = opt_first

    page_mock.locator = MagicMock(return_value=opt_locator)

    driver = DummyDriver(page=page_mock, highlight_clicks=False)
    await driver.select_option(".dropdown-paises", "Brasil")

    page_mock.click.assert_called_once_with(".dropdown-paises", timeout=10000)
    opt_first.click.assert_called_once_with(timeout=10000)


@pytest.mark.asyncio
async def test_driver_check_field_required():
    page_mock = MagicMock()
    page_mock.wait_for_selector = AsyncMock()
    page_mock.evaluate = AsyncMock(
        return_value={"required": True, "reason": "Atributo HTML5 'required' presente"}
    )

    driver = DummyDriver(page=page_mock, highlight_clicks=False)
    is_req, reason = await driver.check_field_required("input#email")

    assert is_req is True
    assert "required" in reason


@pytest.mark.asyncio
async def test_driver_check_field_invalid():
    page_mock = MagicMock()
    page_mock.wait_for_selector = AsyncMock()
    page_mock.evaluate = AsyncMock(
        return_value={"invalid": True, "reason": "Classe CSS de erro '.is-invalid' detectada"}
    )

    driver = DummyDriver(page=page_mock, highlight_clicks=False)
    is_inv, reason = await driver.check_field_invalid("input#email")

    assert is_inv is True
    assert "is-invalid" in reason


@pytest.mark.asyncio
async def test_agent_execute_assert_required_success():
    config = GlobalConfig()
    agent = UXSentinelAgent(config)

    mock_driver = MagicMock()
    mock_driver.healing_events = []
    mock_driver.check_field_required = AsyncMock(return_value=(True, "Campo possui required"))

    scenario = Scenario(
        id="cenario_form",
        title="Form Test",
        steps=[StepAction(action="assert_required", selector="input#nome")],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)

    await agent._execute_step(
        index=1,
        step=scenario.steps[0],
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
    )

    mock_driver.check_field_required.assert_called_once_with("input#nome", timeout=5000)
    assert len(report.checkpoints) == 0  # Nenhum erro registrado


@pytest.mark.asyncio
async def test_agent_execute_assert_required_failure_creates_issue():
    config = GlobalConfig()
    agent = UXSentinelAgent(config)

    mock_driver = MagicMock()
    mock_driver.healing_events = []
    mock_driver.check_field_required = AsyncMock(return_value=(False, "Sem indicativo de obrigatoriedade"))

    scenario = Scenario(
        id="cenario_form_fail",
        title="Form Test Fail",
        steps=[StepAction(action="assert_required", selector="input#nome")],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)

    await agent._execute_step(
        index=1,
        step=scenario.steps[0],
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
    )

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.status == "problemas_encontrados"
    assert len(cp.issues) == 1
    issue = cp.issues[0]
    assert issue.categoria == IssueCategory.REGRA_NEGOCIO
    assert issue.severidade == IssueSeverity.ALTA
    assert "Campo obrigatório não sinalizado" in issue.descricao


@pytest.mark.asyncio
async def test_agent_execute_assert_invalid_failure():
    config = GlobalConfig()
    agent = UXSentinelAgent(config)

    mock_driver = MagicMock()
    mock_driver.healing_events = []
    mock_driver.check_field_invalid = AsyncMock(return_value=(False, "Campo está válido"))

    scenario = Scenario(
        id="cenario_invalid_fail",
        title="Form Invalid Fail",
        steps=[StepAction(action="assert_invalid", selector="input#nome")],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)

    await agent._execute_step(
        index=1,
        step=scenario.steps[0],
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
    )

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.status == "problemas_encontrados"
    assert "Campo deveria exibir validação de erro" in cp.issues[0].descricao
