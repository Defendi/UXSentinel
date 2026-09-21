from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.browser.actions import (
    ActionContext,
    ActionRegistry,
    BaseActionHandler,
    default_action_registry,
)
from uxsentinel.core.models import Scenario, StepAction, TestReport


class CustomTestHandler(BaseActionHandler):
    def __init__(self):
        self.called = False

    async def execute(self, ctx: ActionContext) -> None:
        self.called = True


@pytest.mark.asyncio
async def test_action_registry_custom_registration():
    registry = ActionRegistry()
    handler = CustomTestHandler()
    registry.register(["custom_action", "acao_custom"], handler)

    assert registry.get("custom_action") is handler
    assert registry.get("ACAO_CUSTOM") is handler
    assert registry.get("desconhecido") is None

    mock_driver = MagicMock()
    scenario = Scenario(id="test_reg", title="Test Registry", steps=[StepAction(action="custom_action")])
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)
    ctx = ActionContext(
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
        step_index=1,
        step=scenario.steps[0],
    )

    await registry.execute(ctx)
    assert handler.called is True


@pytest.mark.asyncio
async def test_action_registry_unknown_action_raises():
    registry = ActionRegistry()
    mock_driver = MagicMock()
    scenario = Scenario(
        id="test_reg", title="Test Registry", steps=[StepAction(action="acao_inexistente_xyz")]
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)
    ctx = ActionContext(
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
        step_index=1,
        step=scenario.steps[0],
    )

    with pytest.raises(ValueError, match="Ação desconhecida: 'acao_inexistente_xyz'"):
        await registry.execute(ctx)


@pytest.mark.asyncio
async def test_drag_and_drop_action_handler():
    handler = default_action_registry.get("drag_and_drop")
    assert handler is not None

    mock_driver = MagicMock()
    mock_driver.drag_and_drop = AsyncMock()

    scenario = Scenario(
        id="test_drag",
        title="Test Drag",
        steps=[StepAction(action="drag_and_drop", selector="#item1", target="#dropzone")],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)
    ctx = ActionContext(
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
        step_index=1,
        step=scenario.steps[0],
    )

    await handler.execute(ctx)
    mock_driver.drag_and_drop.assert_awaited_once_with("#item1", "#dropzone", timeout=10000)


@pytest.mark.asyncio
async def test_upload_file_action_handler():
    handler = default_action_registry.get("upload_file")
    assert handler is not None

    mock_driver = MagicMock()
    mock_driver.set_input_files = AsyncMock()
    mock_driver.wait_until_ready = AsyncMock()

    scenario = Scenario(
        id="test_upload",
        title="Test Upload",
        steps=[StepAction(action="upload_file", selector="input[type='file']", value="/tmp/fake.pdf")],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)
    ctx = ActionContext(
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
        step_index=1,
        step=scenario.steps[0],
    )

    await handler.execute(ctx)
    mock_driver.set_input_files.assert_awaited_once_with("input[type='file']", "/tmp/fake.pdf", timeout=10000)
    mock_driver.wait_until_ready.assert_awaited_once()


@pytest.mark.asyncio
async def test_assert_readonly_and_options_handlers():
    readonly_handler = default_action_registry.get("assert_readonly")
    options_handler = default_action_registry.get("assert_options")
    assert readonly_handler is not None
    assert options_handler is not None

    mock_driver = MagicMock()
    mock_driver.page = MagicMock()
    mock_driver.page.wait_for_selector = AsyncMock()
    mock_driver.page.evaluate = AsyncMock(
        side_effect=[
            {"readonly": True, "reason": "Atributo 'readonly' presente"},
            ["Opção 1", "Opção 2"],
        ]
    )

    scenario = Scenario(
        id="test_asserts",
        title="Test Asserts",
        steps=[
            StepAction(action="assert_readonly", selector="#readonly_input"),
            StepAction(action="assert_options", selector="#my_select", criteria=["Opção 1"]),
        ],
    )
    report = TestReport(scenario_id=scenario.id, scenario_title=scenario.title)

    ctx1 = ActionContext(
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
        step_index=1,
        step=scenario.steps[0],
    )
    await readonly_handler.execute(ctx1)

    ctx2 = ActionContext(
        driver=mock_driver,
        scenario=scenario,
        report=report,
        out_dir=Path("/tmp"),
        step_index=2,
        step=scenario.steps[1],
    )
    await options_handler.execute(ctx2)

    assert len(report.checkpoints) == 0
