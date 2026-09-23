"""Testes unitários herméticos para JsonLinesEventStreamer e exportação de eventos (UXS-27)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.cli import build_arg_parser
from uxsentinel.core.events import (
    REDACTED,
    EventBus,
    EventType,
    ExecutionEvent,
    JsonLinesEventStreamer,
    sanitize_data,
    sanitize_event_data,
)
from uxsentinel.service.execution_service import ExecutionOptions, ExecutionService


@pytest.mark.asyncio
async def test_streamer_jsonl_format_and_loads(tmp_path: Path):
    """Valida que cada linha gerada pelo streamer é um JSON estritamente válido e independente."""
    target_file = tmp_path / "events.jsonl"
    bus = EventBus()

    with JsonLinesEventStreamer(target_file) as streamer:
        bus.subscribe(streamer)

        await bus.publish(
            ExecutionEvent(
                event_type=EventType.SCENARIO_STARTED,
                scenario_id="login_fluxo",
                data={"title": "Login Principal"},
            )
        )
        await bus.publish(
            ExecutionEvent(
                event_type=EventType.STEP_STARTED,
                scenario_id="login_fluxo",
                step_index=1,
                action="fill",
                data={"selector": "#usuario"},
            )
        )
        await bus.publish(
            ExecutionEvent(
                event_type=EventType.STEP_COMPLETED,
                scenario_id="login_fluxo",
                step_index=1,
                action="fill",
                data={"duration_ms": 120},
            )
        )
        await bus.publish(
            ExecutionEvent(
                event_type=EventType.AI_INSPECTION_COMPLETED,
                scenario_id="login_fluxo",
                step_index=2,
                action="inspect",
                data={"verdict": "APROVADO", "observations": "Layout íntegro"},
            )
        )
        await bus.publish(
            ExecutionEvent(
                event_type=EventType.SCENARIO_COMPLETED,
                scenario_id="login_fluxo",
                data={"status": "PASS"},
            )
        )

    assert target_file.is_file()
    lines = target_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5

    parsed_events = [json.loads(line) for line in lines]
    assert parsed_events[0]["event_type"] == "scenario_started"
    assert parsed_events[0]["scenario_id"] == "login_fluxo"
    assert parsed_events[0]["data"]["title"] == "Login Principal"

    assert parsed_events[1]["event_type"] == "step_started"
    assert parsed_events[1]["step_index"] == 1
    assert parsed_events[1]["action"] == "fill"

    assert parsed_events[2]["event_type"] == "step_completed"
    assert parsed_events[2]["data"]["duration_ms"] == 120

    assert parsed_events[3]["event_type"] == "ai_inspection_completed"
    assert parsed_events[3]["data"]["verdict"] == "APROVADO"

    assert parsed_events[4]["event_type"] == "scenario_completed"
    assert parsed_events[4]["data"]["status"] == "PASS"


def test_streamer_synchronous_flush(tmp_path: Path):
    """Garante escrita física com flush() síncrono antes do fechamento do streamer."""
    target_file = tmp_path / "realtime.jsonl"
    streamer = JsonLinesEventStreamer(target_file)
    streamer.open()

    try:
        event = ExecutionEvent(
            event_type=EventType.STEP_STARTED,
            scenario_id="realtime_scen",
            step_index=1,
            action="click",
            data={"target": "#btn-enviar"},
        )
        streamer.handle_event(event)

        # Lê diretamente do disco enquanto o streamer ainda está aberto
        with open(target_file, encoding="utf-8") as f:
            disk_content = f.read()

        assert disk_content != ""
        record = json.loads(disk_content.strip())
        assert record["event_type"] == "step_started"
        assert record["data"]["target"] == "#btn-enviar"
    finally:
        streamer.close()


def test_sanitize_data_and_event_masking():
    """Valida mascaramento recursivo de credenciais e termos sensíveis."""
    raw_data = {
        "api_key": "secret_ai_token_12345",
        "nested": {
            "password": "super_secret_password",
            "token": "bearer_jwt_string",
            "user": "safe_username",
            "auth": "auth_code_xyz",
        },
        "headers": {
            "Authorization": "Bearer sensitive_token_abc",
        },
        "items": [
            {"client_secret": "my_client_secret", "normal_key": "ok"},
            "Token no meio Bearer xyz12345",
        ],
        "private_key": "-----BEGIN PRIVATE KEY-----",
        "public_info": "safe_data",
    }

    sanitized = sanitize_data(raw_data)

    assert sanitized["api_key"] == REDACTED
    assert sanitized["nested"]["password"] == REDACTED
    assert sanitized["nested"]["token"] == REDACTED
    assert sanitized["nested"]["auth"] == REDACTED
    assert sanitized["nested"]["user"] == "safe_username"
    assert sanitized["headers"]["Authorization"] == REDACTED
    assert sanitized["items"][0]["client_secret"] == REDACTED
    assert sanitized["items"][0]["normal_key"] == "ok"
    assert sanitized["items"][1] == f"Token no meio Bearer {REDACTED}"
    assert sanitized["private_key"] == REDACTED
    assert sanitized["public_info"] == "safe_data"

    # Testa sanitize_event_data mantendo campos do evento e alterando apenas data
    ev = ExecutionEvent(
        event_type=EventType.SCENARIO_STARTED,
        scenario_id="scen_sec",
        data=raw_data,
    )
    sanitized_ev = sanitize_event_data(ev)
    assert sanitized_ev.scenario_id == "scen_sec"
    assert sanitized_ev.data["api_key"] == REDACTED
    assert sanitized_ev.data["nested"]["password"] == REDACTED


def test_streamer_context_manager_and_mkdirs(tmp_path: Path):
    """Valida suporte a context manager e criação automática de diretórios pais."""
    nested_dir = tmp_path / "deep" / "nested" / "path"
    target_file = nested_dir / "stream.jsonl"

    assert not nested_dir.exists()

    with JsonLinesEventStreamer(target_file) as streamer:
        assert nested_dir.exists()
        assert target_file.exists()
        streamer.handle_event(
            ExecutionEvent(
                event_type=EventType.SCENARIO_STARTED,
                scenario_id="s1",
            )
        )

    # Após fechar, arquivo deve estar fechado e handle_event não deve falhar
    streamer.handle_event(
        ExecutionEvent(
            event_type=EventType.SCENARIO_COMPLETED,
            scenario_id="s1",
        )
    )
    lines = target_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_cli_stream_events_argument():
    """Valida o parsing do argumento --stream-events no CLI."""
    parser = build_arg_parser()

    # Com a flag
    args = parser.parse_args(["-s", "scenarios/login.yaml", "--stream-events", "output/events.jsonl"])
    assert args.stream_events == Path("output/events.jsonl")

    # Sem a flag (padrão deve ser None)
    args_default = parser.parse_args(["-s", "scenarios/login.yaml"])
    assert args_default.stream_events is None


@pytest.mark.asyncio
async def test_execution_service_stream_events_lifecycle(tmp_path: Path):
    """Valida que ExecutionService configura e desanexa o streamer ao executar um cenário."""
    stream_file = tmp_path / "service_stream.jsonl"
    service = ExecutionService()

    fake_report = AsyncMock()
    fake_report.success = True

    async def fake_run_scenario(scenario, runner_options, event_bus=None):
        if event_bus is not None:
            await event_bus.publish(
                ExecutionEvent(
                    event_type=EventType.SCENARIO_STARTED,
                    scenario_id="service_scen",
                    data={"apiKey": "secret_key_123"},
                )
            )
            await event_bus.publish(
                ExecutionEvent(
                    event_type=EventType.SCENARIO_COMPLETED,
                    scenario_id="service_scen",
                )
            )
        return fake_report

    service.runner.run_scenario = AsyncMock(side_effect=fake_run_scenario)

    with patch("uxsentinel.service.execution_service.load_scenario") as mock_load:
        mock_load.return_value = AsyncMock()
        options = ExecutionOptions(
            scenario_path=tmp_path / "dummy.yaml",
            stream_events=stream_file,
        )
        report = await service.run(options)

    assert report.success is True
    assert stream_file.is_file()
    lines = stream_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    ev1 = json.loads(lines[0])
    assert ev1["event_type"] == "scenario_started"
    assert ev1["data"]["apiKey"] == REDACTED

    ev2 = json.loads(lines[1])
    assert ev2["event_type"] == "scenario_completed"


@pytest.mark.asyncio
async def test_execution_without_stream_events_creates_no_file(tmp_path: Path):
    """Garante que sem stream_events nenhum arquivo é criado."""
    service = ExecutionService()
    fake_report = AsyncMock()
    fake_report.success = True
    service.runner.run_scenario = AsyncMock(return_value=fake_report)

    with patch("uxsentinel.service.execution_service.load_scenario") as mock_load:
        mock_load.return_value = AsyncMock()
        options = ExecutionOptions(
            scenario_path=tmp_path / "dummy.yaml",
            stream_events=None,
        )
        report = await service.run(options)

    assert report.success is True
    # Nenhum arquivo .jsonl criado em tmp_path
    assert list(tmp_path.glob("*.jsonl")) == []
