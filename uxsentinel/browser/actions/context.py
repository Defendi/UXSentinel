from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

if TYPE_CHECKING:
    from rich.progress import Progress

    from uxsentinel.browser.drivers.base_driver import BaseDriver
    from uxsentinel.core.models import (
        Scenario,
        ScenarioExceptions,
        StepAction,
        TestReport,
        ViewportConfig,
    )


@dataclass
class ActionContext:
    """Contexto de execução agrupando todas as dependências de um passo."""

    driver: BaseDriver
    scenario: Scenario
    report: TestReport
    out_dir: Path
    step_index: int
    step: StepAction
    progress: Progress | None = None
    task_id: int | None = None
    current_viewport: ViewportConfig | None = None
    multi_viewport: bool = False
    effective_axe: bool = True
    effective_css: bool = True
    effective_fail_fast: bool = True
    effective_baseline_dir: str | Path = "scenarios/baselines"
    effective_update_baseline: bool = False
    effective_diff_threshold: float = 0.1
    scenario_exceptions: ScenarioExceptions | None = None
    agent: Any | None = None
    event_bus: Any | None = None

    @property
    def console(self) -> Console:
        if self.progress is not None:
            return self.progress.console
        from uxsentinel.core.agent import console

        return console


class BaseActionHandler(ABC):
    """Interface abstrata base para executores de ações."""

    @abstractmethod
    async def execute(self, ctx: ActionContext) -> None:
        """Executa a ação correspondente no contexto informado."""
        raise NotImplementedError
