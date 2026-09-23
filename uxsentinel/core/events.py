"""Barramento interno de eventos de execução do UXSentinel (UXS-26)."""

import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    """Tipos de eventos emitidos durante o ciclo de vida da execução de um cenário."""

    SCENARIO_STARTED = "scenario_started"
    SCENARIO_COMPLETED = "scenario_completed"
    SCENARIO_FAILED = "scenario_failed"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    CHECKPOINT_CAPTURED = "checkpoint_captured"
    CHECKPOINT_COMPLETED = "checkpoint_completed"
    AI_INSPECTION_COMPLETED = "ai_inspection_completed"
    HEALING_APPLIED = "healing_applied"
    AXE_AUDIT_COMPLETED = "axe_audit_completed"


class ExecutionEvent(BaseModel):
    """Modelo estruturado de um evento de execução."""

    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scenario_id: str
    viewport: str | None = None
    step_index: int | None = None
    action: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


type Subscriber = Callable[[ExecutionEvent], Awaitable[None] | None]


class EventBus:
    """Barramento desacoplado para publicação e assinatura de eventos de execução."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        """Registra um novo assinante (função síncrona ou assíncrona)."""
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Remove um assinante previamente cadastrado."""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    async def publish(self, event: ExecutionEvent) -> None:
        """Despacha o evento para todos os assinantes isolando exceções individuais."""
        for subscriber in list(self._subscribers):
            try:
                result = subscriber(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as ex:
                logger.warning(
                    "Exceção capturada no assinante de evento %r: %s",
                    subscriber,
                    ex,
                    exc_info=True,
                )


REDACTED = "***REDACTED***"

SENSITIVE_KEYS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "auth",
    "bearer",
    "private_key",
    "privatekey",
)


def _sanitize_string(val: str) -> str:
    """Mascara padrões sensíveis como Bearer tokens em strings soltas."""
    return re.sub(r"(?i)\b(bearer\s+)\S+", rf"\g<1>{REDACTED}", val)


def sanitize_data(data: Any) -> Any:
    """Sanitiza recursivamente dicionários, listas e objetos com dados sensíveis."""
    if isinstance(data, dict):
        sanitized_dict: dict[str, Any] = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in SENSITIVE_KEYS):
                sanitized_dict[k] = REDACTED
            else:
                sanitized_dict[k] = sanitize_data(v)
        return sanitized_dict
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(sanitize_data(item) for item in data)
    elif isinstance(data, set):
        return {sanitize_data(item) for item in data}
    elif isinstance(data, str):
        return _sanitize_string(data)
    elif isinstance(data, BaseModel):
        return sanitize_data(data.model_dump())
    return data


def sanitize_event_data(event: ExecutionEvent) -> ExecutionEvent:
    """Gera uma cópia do evento com os dados de `data` sanitizados recursivamente."""
    sanitized_payload = sanitize_data(event.data)
    return event.model_copy(update={"data": sanitized_payload})


class JsonLinesEventStreamer:
    """Assinante do barramento de eventos que escoa eventos para um arquivo JSON Lines (UXS-27)."""

    def __init__(self, target_path: str | Path) -> None:
        self.target_path = Path(target_path)
        self._file: TextIO | None = None

    def open(self) -> None:
        """Abre o arquivo garantindo diretórios pais."""
        if self._file is not None and not self._file.closed:
            return
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.target_path, "a", encoding="utf-8")  # noqa: SIM115

    def handle_event(self, event: ExecutionEvent) -> None:
        """Sanitiza o evento, serializa em JSON de linha única e executa flush imediato."""
        if not self._file or self._file.closed:
            return
        sanitized_event = sanitize_event_data(event)
        line = sanitized_event.model_dump_json()
        self._file.write(line + "\n")
        self._file.flush()

    def __call__(self, event: ExecutionEvent) -> None:
        """Permite que o streamer seja passado diretamente como assinante do EventBus."""
        self.handle_event(event)

    def close(self) -> None:
        """Fecha com segurança o handle do arquivo."""
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()
            self._file = None

    def __enter__(self) -> "JsonLinesEventStreamer":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
