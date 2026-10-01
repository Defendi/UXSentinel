"""Módulo do gravador interativo de ações no navegador (Modo Assistido)."""

from uxsentinel.browser.recorder.models import (
    RecordedStep,
    RecordedTarget,
    RecordedWorkflow,
    SelectorCandidate,
    SelectorStrategy,
    StepStatus,
)
from uxsentinel.browser.recorder.normalizer import EventNormalizer
from uxsentinel.browser.recorder.resolver import ElementResolver
from uxsentinel.browser.recorder.session import RecorderSession

__all__ = [
    "ElementResolver",
    "EventNormalizer",
    "RecordedStep",
    "RecordedTarget",
    "RecordedWorkflow",
    "RecorderSession",
    "SelectorCandidate",
    "SelectorStrategy",
    "StepStatus",
]
