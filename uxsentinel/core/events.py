"""Barramento interno de eventos de execução do UXSentinel (UXS-26)."""

import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

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
