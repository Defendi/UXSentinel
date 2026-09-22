"""Testes unitários para o barramento interno de eventos (UXS-26)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.browser.healing import HealingEvent
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.events import EventBus, EventType, ExecutionEvent
from uxsentinel.core.models import (
    CheckpointResult,
    Scenario,
    StepAction,
)


@pytest.mark.asyncio
async def test_event_bus_subscribe_and_publish_sync():
    """Valida que subscribers síncronos recebem eventos publicados."""
    bus = EventBus()
    received_events: list[ExecutionEvent] = []

    def sync_handler(event: ExecutionEvent) -> None:
        received_events.append(event)

    bus.subscribe(sync_handler)

    test_event = ExecutionEvent(
        event_type=EventType.SCENARIO_STARTED,
        scenario_id="scenario_test",
        data={"title": "Teste"},
    )
    await bus.publish(test_event)

    assert len(received_events) == 1
    assert received_events[0].event_type == EventType.SCENARIO_STARTED
    assert received_events[0].scenario_id == "scenario_test"
    assert received_events[0].data["title"] == "Teste"
    assert isinstance(received_events[0].timestamp, datetime)


@pytest.mark.asyncio
async def test_event_bus_subscribe_and_publish_async():
    """Valida que subscribers assíncronos recebem e aguardam eventos."""
    bus = EventBus()
    received_events: list[ExecutionEvent] = []

    async def async_handler(event: ExecutionEvent) -> None:
        received_events.append(event)

    bus.subscribe(async_handler)

    test_event = ExecutionEvent(
        event_type=EventType.STEP_COMPLETED,
        scenario_id="scenario_test",
        step_index=1,
        action="click",
    )
    await bus.publish(test_event)

    assert len(received_events) == 1
    assert received_events[0].event_type == EventType.STEP_COMPLETED
    assert received_events[0].step_index == 1
    assert received_events[0].action == "click"


@pytest.mark.asyncio
async def test_event_bus_unsubscribe():
    """Valida que assinantes desregistrados não recebem eventos subsequentes."""
    bus = EventBus()
    received_events: list[ExecutionEvent] = []

    def handler(event: ExecutionEvent) -> None:
        received_events.append(event)

    bus.subscribe(handler)
    await bus.publish(ExecutionEvent(event_type=EventType.STEP_STARTED, scenario_id="s1"))
    assert len(received_events) == 1

    bus.unsubscribe(handler)
    await bus.publish(ExecutionEvent(event_type=EventType.STEP_COMPLETED, scenario_id="s1"))
    assert len(received_events) == 1


@pytest.mark.asyncio
async def test_event_bus_isolation_on_subscriber_exception():
    """Garante que falhas em um subscriber não impeçam os demais de receberem o evento."""
    bus = EventBus()
    received_events: list[ExecutionEvent] = []

    def faulty_handler(event: ExecutionEvent) -> None:
        raise RuntimeError("Erro inesperado no handler")

    def safe_handler(event: ExecutionEvent) -> None:
        received_events.append(event)

    bus.subscribe(faulty_handler)
    bus.subscribe(safe_handler)

    test_event = ExecutionEvent(
        event_type=EventType.SCENARIO_STARTED,
        scenario_id="s_err",
    )
    # Não deve levantar exceção
    await bus.publish(test_event)

    assert len(received_events) == 1
    assert received_events[0].scenario_id == "s_err"


@pytest.mark.asyncio
async def test_agent_emits_scenario_lifecycle_events_success(tmp_path: Path):
    """Valida o ciclo de eventos emitidos durante uma execução com sucesso."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "reports")
    bus = EventBus()
    events: list[ExecutionEvent] = []

    bus.subscribe(lambda ev: events.append(ev))

    agent = UXSentinelAgent(cfg, event_bus=bus)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    scenario = Scenario(
        id="scenario_success",
        title="Cenário de Sucesso",
        steps=[
            StepAction(action="sleep", seconds=0.001),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.page = AsyncMock()

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    event_types = [e.event_type for e in events]
    assert event_types == [
        EventType.SCENARIO_STARTED,
        EventType.STEP_STARTED,
        EventType.STEP_COMPLETED,
        EventType.SCENARIO_COMPLETED,
    ]
    assert events[0].scenario_id == "scenario_success"
    assert events[1].step_index == 1
    assert events[1].action == "sleep"
    assert events[3].data["total_checkpoints"] == 0


@pytest.mark.asyncio
async def test_agent_emits_scenario_failed_on_ai_error(tmp_path: Path):
    """Valida que falha na conexão da IA emite scenario_failed."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "reports")
    bus = EventBus()
    events: list[ExecutionEvent] = []

    bus.subscribe(lambda ev: events.append(ev))

    agent = UXSentinelAgent(cfg, event_bus=bus)
    agent.inspector.client.test_connection = AsyncMock(return_value=(False, "Chave de API inválida"))

    scenario = Scenario(
        id="scenario_ai_fail",
        title="Cenário Falha IA",
        steps=[],
    )

    with patch("uxsentinel.core.agent.console.print"):
        report = await agent.run_scenario(scenario)

    assert report.success is False
    event_types = [e.event_type for e in events]
    assert event_types == [
        EventType.SCENARIO_STARTED,
        EventType.SCENARIO_FAILED,
    ]
    assert "Falha de conexão com a IA" in events[1].data["error"]


@pytest.mark.asyncio
async def test_agent_emits_step_failed_and_scenario_failed(tmp_path: Path):
    """Valida emissão de step_failed e scenario_failed quando um passo lança exceção com fail_fast."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "reports")
    bus = EventBus()
    events: list[ExecutionEvent] = []

    bus.subscribe(lambda ev: events.append(ev))

    agent = UXSentinelAgent(cfg, event_bus=bus)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    scenario = Scenario(
        id="scenario_step_fail",
        title="Cenário Passo Falhou",
        fail_fast=True,
        steps=[
            StepAction(action="click", selector="#invalido"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.click = AsyncMock(side_effect=RuntimeError("Elemento não encontrado"))
    mock_driver.page = AsyncMock()

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is False
    event_types = [e.event_type for e in events]
    assert event_types == [
        EventType.SCENARIO_STARTED,
        EventType.STEP_STARTED,
        EventType.STEP_FAILED,
        EventType.SCENARIO_FAILED,
    ]
    failed_step_ev = events[2]
    assert failed_step_ev.action == "click"
    assert "Elemento não encontrado" in failed_step_ev.data["error"]


@pytest.mark.asyncio
async def test_agent_emits_checkpoint_and_ai_inspection_events(tmp_path: Path):
    """Valida emissão de checkpoint_captured e ai_inspection_completed."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "reports")
    bus = EventBus()
    events: list[ExecutionEvent] = []

    bus.subscribe(lambda ev: events.append(ev))

    agent = UXSentinelAgent(cfg, event_bus=bus)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    mock_cp_result = CheckpointResult(
        name="checkpoint_1",
        expected_behavior="Tudo limpo",
        screenshot_path=str(tmp_path / "shot.png"),
        status="ok",
        issues=[],
    )
    agent.inspector.inspect = AsyncMock(return_value=mock_cp_result)
    agent.axe_runner.run = AsyncMock(return_value=[])

    scenario = Scenario(
        id="scenario_cp",
        title="Cenário Checkpoint",
        steps=[
            StepAction(action="checkpoint", name="checkpoint_1"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="<html></html>")
    mock_driver.page = AsyncMock()
    mock_driver.validate_dom = AsyncMock(return_value=[])

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario, enable_axe_override=True)

    assert report.success is True
    event_types = [e.event_type for e in events]
    assert EventType.CHECKPOINT_CAPTURED in event_types
    assert EventType.AXE_AUDIT_COMPLETED in event_types
    assert EventType.AI_INSPECTION_COMPLETED in event_types

    cp_ev = next(e for e in events if e.event_type == EventType.CHECKPOINT_CAPTURED)
    assert cp_ev.data["name"] == "checkpoint_1"

    axe_ev = next(e for e in events if e.event_type == EventType.AXE_AUDIT_COMPLETED)
    assert axe_ev.data["score"] == 100.0

    ai_ev = next(e for e in events if e.event_type == EventType.AI_INSPECTION_COMPLETED)
    assert ai_ev.data["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_emits_healing_applied_event(tmp_path: Path):
    """Valida emissão de healing_applied quando o driver registra autocura."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "reports")
    bus = EventBus()
    events: list[ExecutionEvent] = []

    bus.subscribe(lambda ev: events.append(ev))

    agent = UXSentinelAgent(cfg, event_bus=bus)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    scenario = Scenario(
        id="scenario_healing",
        title="Cenário Healing",
        steps=[
            StepAction(action="click", selector="#btn-old"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.page = AsyncMock()

    async def fake_click(*args, **kwargs):
        mock_driver.healing_events.append(
            HealingEvent(
                action="click",
                original_selector="#btn-old",
                recovered_selector="#btn-new",
                strategy="accessibility",
                confidence=0.95,
                execution_time_ms=120.0,
            )
        )

    mock_driver.click = AsyncMock(side_effect=fake_click)

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        report = await agent.run_scenario(scenario)

    assert report.success is True
    event_types = [e.event_type for e in events]
    assert EventType.HEALING_APPLIED in event_types

    healing_ev = next(e for e in events if e.event_type == EventType.HEALING_APPLIED)
    assert healing_ev.data["original_selector"] == "#btn-old"
    assert healing_ev.data["recovered_selector"] == "#btn-new"
    assert healing_ev.data["strategy"] == "accessibility"


@pytest.mark.asyncio
async def test_run_scenario_override_event_bus(tmp_path: Path):
    """Valida que passar um event_bus para run_scenario tem precedência sobre o padrão do agente."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "reports")
    agent_bus = EventBus()
    scenario_bus = EventBus()

    agent_events: list[ExecutionEvent] = []
    scenario_events: list[ExecutionEvent] = []

    agent_bus.subscribe(lambda ev: agent_events.append(ev))
    scenario_bus.subscribe(lambda ev: scenario_events.append(ev))

    agent = UXSentinelAgent(cfg, event_bus=agent_bus)
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    scenario = Scenario(
        id="scenario_bus_override",
        title="Override Bus",
        steps=[StepAction(action="sleep", seconds=0.001)],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.page = AsyncMock()

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver
        await agent.run_scenario(scenario, event_bus=scenario_bus)

    assert len(agent_events) == 0
    assert len(scenario_events) > 0
    assert scenario_events[0].event_type == EventType.SCENARIO_STARTED
