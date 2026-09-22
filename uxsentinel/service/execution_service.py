"""Serviço de orquestração e execução desacoplado de interfaces de terminal."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from uxsentinel.core.config import GlobalConfig, load_config
from uxsentinel.core.models import TestReport
from uxsentinel.core.runner import ScenarioRunnerService, ScenarioRunOptions
from uxsentinel.scenarios.parser import load_scenario


class ExecutionOptions(BaseModel):
    """Opções de execução de cenários modeladas com Pydantic v2."""

    scenario_path: str | Path
    provider: str | None = None
    profile: str | None = None
    headless: bool | None = None
    devtools: bool | None = None
    record_video: bool | None = None
    viewports: str | list[str] | None = None
    enable_axe: bool | None = None
    enable_css: bool | None = None
    update_baseline: bool | None = None
    baseline_dir: str | Path | None = None
    diff_threshold: float | None = None
    slowmo: int | None = None
    output_dir: str | Path | None = None
    markdown: bool | None = None
    fail_fast: bool | None = None
    archive: bool | None = None
    archive_dir: str | Path | None = None
    jira: bool | None = None
    jira_project: str | None = None
    fix_prompt: bool | None = None
    event_bus: Any | None = None
    extra_options: dict = Field(default_factory=dict)
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ExecutionService:
    """Serviço de execução universal do UXSentinel para CLI e Web."""

    def __init__(self, config: GlobalConfig | None = None) -> None:
        self.config = config or load_config()
        self.runner = ScenarioRunnerService(self.config)

    async def run(self, options: ExecutionOptions) -> TestReport:
        """Executa um cenário a partir das opções fornecidas."""
        scenario = load_scenario(str(options.scenario_path), auto_register=True)

        runner_options = ScenarioRunOptions(
            provider=options.provider,
            profile=options.profile,
            headless=options.headless,
            devtools=options.devtools,
            record_video=options.record_video,
            viewports=options.viewports,
            enable_axe=options.enable_axe,
            enable_css=options.enable_css,
            update_baseline=options.update_baseline,
            baseline_dir=options.baseline_dir,
            diff_threshold=options.diff_threshold,
            slowmo=options.slowmo,
            output_dir=options.output_dir,
            markdown=options.markdown,
            fail_fast=options.fail_fast,
            archive=options.archive,
            archive_dir=options.archive_dir,
            jira=options.jira,
            jira_project=options.jira_project,
            fix_prompt=options.fix_prompt,
            extra_options=options.extra_options,
        )

        return await self.runner.run_scenario(
            scenario,
            runner_options,
            event_bus=options.event_bus,
        )
