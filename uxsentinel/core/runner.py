"""Serviço de orquestração e execução de cenários de teste do UXSentinel.

Isola a lógica de orquestração de cenários, paralelismo/iteração multi-viewport,
coleta de telemetria, arquivamento automático pré-execução e agregação de relatórios
desacoplando o entrypoint CLI e viabilizando chamadas programáticas e workers em background.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import (
    GlobalConfig,
    resolve_archive_dir,
    resolve_archive_mode,
    resolve_axe_mode,
    resolve_baseline_mode,
    resolve_css_mode,
    resolve_devtools_mode,
    resolve_display_mode,
    resolve_fail_fast_mode,
    resolve_markdown_mode,
    resolve_video_mode,
    resolve_viewports,
)
from uxsentinel.core.models import (
    ExecutionResult,
    Scenario,
    TestReport,
    ViewportConfig,
)
from uxsentinel.reporter.archiver import archive_previous_reports
from uxsentinel.scenarios.parser import load_scenario

console = Console()


@dataclass
class ScenarioRunOptions:
    """Opções de execução de cenários configuráveis pela CLI ou via API."""

    provider: str | None = None
    profile: str | None = None
    headless: bool | None = None
    devtools: bool | None = None
    record_video: bool | None = None
    viewports: str | list[str] | list[ViewportConfig] | None = None
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
    extra_options: dict = field(default_factory=dict)


@dataclass
class MultiScenarioReport:
    """Relatório consolidado de múltiplos cenários executados."""

    reports: list[TestReport] = field(default_factory=list)
    execution_results: list[ExecutionResult] = field(default_factory=list)
    success: bool = True
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    error_scenarios: int = 0

    def compute_summary(self) -> None:
        self.total_scenarios = len(self.reports)
        self.passed_scenarios = sum(1 for r in self.reports if r.success and not r.error_message)
        self.failed_scenarios = sum(1 for r in self.reports if not r.success and not r.error_message)
        self.error_scenarios = sum(1 for r in self.reports if r.error_message)
        self.success = (self.failed_scenarios == 0 and self.error_scenarios == 0) and (
            self.total_scenarios > 0
        )


class ScenarioRunnerService:
    """Serviço central de execução e orquestração de cenários do UXSentinel."""

    def __init__(self, config: GlobalConfig | None = None) -> None:
        self.config = config or GlobalConfig()

    def prepare_config(self, scenario: Scenario, options: ScenarioRunOptions) -> GlobalConfig:
        """Aplica overrides e regras de precedência (CLI > Cenário > Config) retornando cópia configurada."""
        cfg = self.config.model_copy(deep=True)

        if options.provider:
            cfg.active_provider = options.provider
        elif scenario.provider:
            cfg.active_provider = scenario.provider

        if options.profile:
            scenario.profile = options.profile

        if options.fix_prompt is not None:
            cfg.reporting.generate_fix_prompt = options.fix_prompt
        if options.jira is not None:
            cfg.jira.enabled = options.jira
        if options.jira_project:
            cfg.jira.project_key = options.jira_project

        if options.slowmo is not None:
            cfg.browser.slow_mo_ms = options.slowmo

        if options.output_dir:
            cfg.reporting.output_dir = str(options.output_dir)
        elif not cfg.reporting.output_dir or cfg.reporting.output_dir == "report":
            cfg.reporting.output_dir = "scenarios/report"

        # Resolução de modo headless
        cfg.browser.headless = resolve_display_mode(
            cli_headless=options.headless,
            scenario_headless=scenario.headless,
            config_headless=cfg.browser.headless,
        )

        # Resolução de vídeo
        cfg.browser.record_video = resolve_video_mode(
            cli_video=options.record_video,
            scenario_video=scenario.video,
            config_video=cfg.browser.record_video,
        )

        # Resolução de viewports
        cli_vp = options.viewports
        if isinstance(cli_vp, list) and cli_vp and isinstance(cli_vp[0], str):
            cli_vp_spec = ",".join(cli_vp)
        elif isinstance(cli_vp, str):
            cli_vp_spec = cli_vp
        else:
            cli_vp_spec = None

        cfg.browser.viewports = resolve_viewports(
            cli_viewports=cli_vp_spec or (cli_vp if isinstance(cli_vp, list) else None),
            scenario_viewports=scenario.viewports,
            config_viewports=cfg.browser.viewports,
        )

        # Resolução de Axe-Core
        cfg.browser.enable_axe = resolve_axe_mode(
            cli_axe=options.enable_axe,
            scenario_axe=scenario.axe,
            config_axe=cfg.browser.enable_axe,
        )

        # Resolução de Auditoria de CSS Híbrida
        cfg.browser.enable_css_audit = resolve_css_mode(
            cli_css=options.enable_css,
            scenario_css=scenario.css,
            config_css=cfg.browser.enable_css_audit,
        )

        # Resolução de Baseline Visual
        if options.baseline_dir:
            cfg.baseline.baseline_dir = str(options.baseline_dir)
        elif scenario.baseline_dir:
            cfg.baseline.baseline_dir = scenario.baseline_dir

        if options.diff_threshold is not None:
            cfg.baseline.diff_threshold = options.diff_threshold
        elif scenario.diff_threshold is not None:
            cfg.baseline.diff_threshold = scenario.diff_threshold

        cfg.baseline.update_baseline = resolve_baseline_mode(
            cli_update_baseline=options.update_baseline,
            scenario_update_baseline=scenario.update_baseline,
            config_update_baseline=cfg.baseline.update_baseline,
        )

        # Resolução de Markdown
        cfg.reporting.generate_markdown = resolve_markdown_mode(
            cli_markdown=options.markdown,
            scenario_markdown=scenario.markdown,
            config_markdown=cfg.reporting.generate_markdown,
        )

        # Resolução de Fail-Fast
        cfg.browser.fail_fast = resolve_fail_fast_mode(
            cli_fail_fast=options.fail_fast,
            scenario_fail_fast=scenario.fail_fast,
            config_fail_fast=cfg.browser.fail_fast,
        )

        # Resolução de DevTools
        cfg.browser.devtools = resolve_devtools_mode(
            cli_devtools=options.devtools,
            scenario_devtools=scenario.devtools,
            config_devtools=cfg.browser.devtools,
        )
        if cfg.browser.devtools:
            cfg.browser.headless = False

        # Resolução de Arquivamento
        cfg.reporting.archive_previous_reports = resolve_archive_mode(
            cli_archive=options.archive,
            scenario_archive=scenario.archive,
            config_archive=cfg.reporting.archive_previous_reports,
        )
        cfg.reporting.archive_dir = resolve_archive_dir(
            cli_archive_dir=str(options.archive_dir) if options.archive_dir else None,
            scenario_archive_dir=scenario.archive_dir,
            config_archive_dir=cfg.reporting.archive_dir,
        )

        return cfg

    def archive_prior_reports(self, cfg: GlobalConfig, scenario_id: str) -> Path | None:
        """Realiza arquivamento antecipado de relatórios pré-existentes se configurado."""
        if not cfg.reporting.archive_previous_reports:
            return None

        out_dir = Path(cfg.reporting.output_dir)
        if not out_dir.is_dir():
            return None

        archived_zip = archive_previous_reports(
            output_dir=out_dir,
            archive_dir=cfg.reporting.archive_dir,
            label=scenario_id,
        )
        return archived_zip

    async def run_scenario(
        self,
        scenario: Scenario | str | Path,
        options: ScenarioRunOptions | None = None,
    ) -> TestReport:
        """Executa um cenário individual orquestrando configurações, arquivamento e agente."""
        opts = options or ScenarioRunOptions()

        loaded_sc = (
            load_scenario(str(scenario), auto_register=True)
            if isinstance(scenario, (str, Path))
            else scenario
        )

        effective_cfg = self.prepare_config(loaded_sc, opts)

        cli_vp_arg = opts.viewports
        if isinstance(cli_vp_arg, list) and cli_vp_arg and isinstance(cli_vp_arg[0], str):
            cli_vp_arg = ",".join(cli_vp_arg)

        agent = UXSentinelAgent(
            config=effective_cfg,
            headless_override=opts.headless,
            record_video_override=opts.record_video,
            viewports_override=cli_vp_arg,
            enable_axe_override=opts.enable_axe,
            enable_css_override=opts.enable_css,
            update_baseline_override=opts.update_baseline,
            baseline_dir_override=opts.baseline_dir,
            diff_threshold_override=opts.diff_threshold,
            markdown_override=opts.markdown,
            devtools_override=opts.devtools,
            archive_override=opts.archive,
            archive_dir_override=opts.archive_dir,
            fail_fast_override=opts.fail_fast,
        )

        report = await agent.run_scenario(
            loaded_sc,
            headless_override=opts.headless,
            record_video_override=opts.record_video,
            viewports_override=cli_vp_arg,
            enable_axe_override=opts.enable_axe,
            enable_css_override=opts.enable_css,
            update_baseline_override=opts.update_baseline,
            baseline_dir_override=opts.baseline_dir,
            diff_threshold_override=opts.diff_threshold,
            markdown_override=opts.markdown,
            devtools_override=opts.devtools,
            archive_override=opts.archive,
            archive_dir_override=opts.archive_dir,
            fail_fast_override=opts.fail_fast,
        )

        return report

    async def run_with_multi_viewport(
        self,
        scenario: Scenario | str | Path,
        viewports: Sequence[str | ViewportConfig],
        options: ScenarioRunOptions | None = None,
        concurrent: bool = False,
    ) -> list[TestReport]:
        """Executa um cenário sob múltiplos viewports (concorrente ou sequencial).

        Retorna a lista de relatórios gerados para cada viewport avaliada.
        """
        opts = options or ScenarioRunOptions()
        parsed_vps = [
            vp if isinstance(vp, ViewportConfig) else ViewportConfig.model_validate(vp)
            for vp in resolve_viewports(cli_viewports=list(viewports))
        ]

        if not concurrent:
            reports: list[TestReport] = []
            for vp in parsed_vps:
                vp_opts = ScenarioRunOptions(
                    provider=opts.provider,
                    profile=opts.profile,
                    headless=opts.headless,
                    devtools=opts.devtools,
                    record_video=opts.record_video,
                    viewports=[vp],
                    enable_axe=opts.enable_axe,
                    enable_css=opts.enable_css,
                    update_baseline=opts.update_baseline,
                    baseline_dir=opts.baseline_dir,
                    diff_threshold=opts.diff_threshold,
                    slowmo=opts.slowmo,
                    output_dir=opts.output_dir,
                    markdown=opts.markdown,
                    archive=opts.archive if not reports else False,
                    archive_dir=opts.archive_dir,
                    jira=opts.jira,
                    jira_project=opts.jira_project,
                    fix_prompt=opts.fix_prompt,
                    extra_options=opts.extra_options,
                )
                rep = await self.run_scenario(scenario, vp_opts)
                reports.append(rep)
            return reports

        tasks = []
        for i, vp in enumerate(parsed_vps):
            vp_opts = ScenarioRunOptions(
                provider=opts.provider,
                profile=opts.profile,
                headless=opts.headless,
                devtools=opts.devtools,
                record_video=opts.record_video,
                viewports=[vp],
                enable_axe=opts.enable_axe,
                enable_css=opts.enable_css,
                update_baseline=opts.update_baseline,
                baseline_dir=opts.baseline_dir,
                diff_threshold=opts.diff_threshold,
                slowmo=opts.slowmo,
                output_dir=opts.output_dir,
                markdown=opts.markdown,
                archive=opts.archive if i == 0 else False,
                archive_dir=opts.archive_dir,
                jira=opts.jira,
                jira_project=opts.jira_project,
                fix_prompt=opts.fix_prompt,
                extra_options=opts.extra_options,
            )
            tasks.append(self.run_scenario(scenario, vp_opts))

        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    async def run_multiple_scenarios(
        self,
        scenarios: Sequence[Scenario | str | Path],
        options: ScenarioRunOptions | None = None,
        max_concurrency: int = 1,
    ) -> MultiScenarioReport:
        """Executa múltiplos cenários agregando seus relatórios e resultados."""
        opts = options or ScenarioRunOptions()
        multi_rep = MultiScenarioReport()

        if max_concurrency <= 1:
            for i, sc in enumerate(scenarios):
                current_opts = ScenarioRunOptions(
                    provider=opts.provider,
                    profile=opts.profile,
                    headless=opts.headless,
                    devtools=opts.devtools,
                    record_video=opts.record_video,
                    viewports=opts.viewports,
                    enable_axe=opts.enable_axe,
                    enable_css=opts.enable_css,
                    update_baseline=opts.update_baseline,
                    baseline_dir=opts.baseline_dir,
                    diff_threshold=opts.diff_threshold,
                    slowmo=opts.slowmo,
                    output_dir=opts.output_dir,
                    markdown=opts.markdown,
                    archive=opts.archive if i == 0 else False,
                    archive_dir=opts.archive_dir,
                    jira=opts.jira,
                    jira_project=opts.jira_project,
                    fix_prompt=opts.fix_prompt,
                    extra_options=opts.extra_options,
                )
                try:
                    rep = await self.run_scenario(sc, current_opts)
                    multi_rep.reports.append(rep)
                    multi_rep.execution_results.append(
                        ExecutionResult(
                            scenario_id=rep.scenario_id,
                            success=rep.success,
                            status="ok" if rep.success else "erro",
                            healed_events=rep.healed_steps,
                            report=rep,
                            error_message=rep.error_message,
                        )
                    )
                except Exception as exc:
                    sc_id = sc.id if isinstance(sc, Scenario) else Path(sc).stem
                    err_rep = TestReport(
                        scenario_id=sc_id,
                        scenario_title=str(sc),
                        success=False,
                        error_message=str(exc),
                    )
                    multi_rep.reports.append(err_rep)
                    multi_rep.execution_results.append(
                        ExecutionResult(
                            scenario_id=sc_id,
                            success=False,
                            status="erro_execucao",
                            report=err_rep,
                            error_message=str(exc),
                        )
                    )
        else:
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _worker(idx: int, sc_item: Scenario | str | Path) -> TestReport:
                async with semaphore:
                    item_opts = ScenarioRunOptions(
                        provider=opts.provider,
                        profile=opts.profile,
                        headless=opts.headless,
                        devtools=opts.devtools,
                        record_video=opts.record_video,
                        viewports=opts.viewports,
                        enable_axe=opts.enable_axe,
                        enable_css=opts.enable_css,
                        update_baseline=opts.update_baseline,
                        baseline_dir=opts.baseline_dir,
                        diff_threshold=opts.diff_threshold,
                        slowmo=opts.slowmo,
                        output_dir=opts.output_dir,
                        markdown=opts.markdown,
                        archive=opts.archive if idx == 0 else False,
                        archive_dir=opts.archive_dir,
                        jira=opts.jira,
                        jira_project=opts.jira_project,
                        fix_prompt=opts.fix_prompt,
                        extra_options=opts.extra_options,
                    )
                    return await self.run_scenario(sc_item, item_opts)

            tasks = [_worker(i, sc) for i, sc in enumerate(scenarios)]
            done_reports = await asyncio.gather(*tasks, return_exceptions=True)

            for i, res in enumerate(done_reports):
                sc = scenarios[i]
                sc_id = sc.id if isinstance(sc, Scenario) else Path(sc).stem
                if isinstance(res, Exception):
                    err_rep = TestReport(
                        scenario_id=sc_id,
                        scenario_title=str(sc),
                        success=False,
                        error_message=str(res),
                    )
                    multi_rep.reports.append(err_rep)
                    multi_rep.execution_results.append(
                        ExecutionResult(
                            scenario_id=sc_id,
                            success=False,
                            status="erro_execucao",
                            report=err_rep,
                            error_message=str(res),
                        )
                    )
                else:
                    multi_rep.reports.append(res)
                    multi_rep.execution_results.append(
                        ExecutionResult(
                            scenario_id=res.scenario_id,
                            success=res.success,
                            status="ok" if res.success else "erro",
                            healed_events=res.healed_steps,
                            report=res,
                            error_message=res.error_message,
                        )
                    )

        multi_rep.compute_summary()
        return multi_rep
