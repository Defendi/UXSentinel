import shutil
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from uxsentinel.browser.actions import ActionContext, default_action_registry
from uxsentinel.browser.axe_runner import (
    AxeRunner,
    calculate_a11y_score,
    convert_violations_to_issues,
)
from uxsentinel.browser.drivers.base_driver import BaseDriver
from uxsentinel.browser.drivers.odoo_driver import OdooDriver
from uxsentinel.browser.healing import SelectorHealer
from uxsentinel.browser.session import open_browser_session
from uxsentinel.browser.som import SetOfMarksManager
from uxsentinel.browser.telemetry import BrowserTelemetryCollector
from uxsentinel.core.config import (
    GlobalConfig,
    resolve_archive_dir,
    resolve_archive_mode,
    resolve_axe_mode,
    resolve_baseline_mode,
    resolve_css_mode,
    resolve_display_mode,
    resolve_fail_fast_mode,
    resolve_markdown_mode,
    resolve_video_mode,
)
from uxsentinel.core.events import EventBus, EventType, ExecutionEvent
from uxsentinel.core.models import (
    CheckpointResult,
    ExecutionResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    ScenarioExceptions,
    StepAction,
    TestReport,
    ViewportConfig,
    VisualDiffResult,
    resolve_viewports,
)
from uxsentinel.reporter.archiver import archive_previous_reports
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.reporter.json_builder import save_json_report
from uxsentinel.reporter.markdown_builder import save_markdown_report
from uxsentinel.reporter.video_helper import create_session_gif, finalize_session_video
from uxsentinel.vision.diff import compare_images
from uxsentinel.vision.inspector import ScreenInspector

console = Console()


class UXSentinelAgent:
    """Agente de QA Visual que executa a navegação e orquestra a auditoria de telas."""

    def __init__(
        self,
        config: GlobalConfig,
        headless_override: bool | None = None,
        record_video_override: bool | None = None,
        viewports_override: str | list[str] | list[ViewportConfig] | None = None,
        enable_axe_override: bool | None = None,
        enable_css_override: bool | None = None,
        update_baseline_override: bool | None = None,
        baseline_dir_override: str | Path | None = None,
        diff_threshold_override: float | None = None,
        markdown_override: bool | None = None,
        devtools_override: bool | None = None,
        archive_override: bool | None = None,
        archive_dir_override: str | Path | None = None,
        fail_fast_override: bool | None = None,
        event_bus: EventBus | None = None,
    ):
        self.config = config
        self.headless_override = headless_override
        self.record_video_override = record_video_override
        self.viewports_override = viewports_override
        self.enable_axe_override = enable_axe_override
        self.enable_css_override = enable_css_override
        self.update_baseline_override = update_baseline_override
        self.baseline_dir_override = baseline_dir_override
        self.diff_threshold_override = diff_threshold_override
        self.markdown_override = markdown_override
        self.devtools_override = devtools_override
        self.archive_override = archive_override
        self.archive_dir_override = archive_dir_override
        self.fail_fast_override = fail_fast_override
        self.event_bus = event_bus or EventBus()
        self.inspector = ScreenInspector(config)
        self.healer = SelectorHealer(
            vision_client=self.inspector.client,
            enabled=self.config.browser.self_healing,
        )
        self.axe_runner = AxeRunner(tags=self.config.browser.axe_tags)
        self._last_execution_result: ExecutionResult | None = None

    @property
    def last_execution_result(self) -> ExecutionResult | None:
        """Propriedade para manter retrocompatibilidade com inspeções externas."""
        return self._last_execution_result

    @last_execution_result.setter
    def last_execution_result(self, value: ExecutionResult | None) -> None:
        self._last_execution_result = value

    async def run_scenario(
        self,
        scenario: Scenario,
        headless_override: bool | None = None,
        record_video_override: bool | None = None,
        viewports_override: str | list[str] | list[ViewportConfig] | None = None,
        enable_axe_override: bool | None = None,
        enable_css_override: bool | None = None,
        update_baseline_override: bool | None = None,
        baseline_dir_override: str | Path | None = None,
        diff_threshold_override: float | None = None,
        markdown_override: bool | None = None,
        devtools_override: bool | None = None,
        archive_override: bool | None = None,
        archive_dir_override: str | Path | None = None,
        fail_fast_override: bool | None = None,
        event_bus: EventBus | None = None,
    ) -> TestReport:
        profile = scenario.profile or "generic"
        start_time = time.time()
        bus = event_bus or self.event_bus
        scenario_failed_emitted = False

        # Determina o modo fail_fast respeitando a hierarquia:
        # CLI Flag > Cenário YAML > Config global > Fallback True
        effective_cli_fail_fast = (
            fail_fast_override if fail_fast_override is not None else self.fail_fast_override
        )
        effective_fail_fast = resolve_fail_fast_mode(
            cli_fail_fast=effective_cli_fail_fast,
            scenario_fail_fast=scenario.fail_fast,
            config_fail_fast=self.config.browser.fail_fast,
        )

        # Determina o modo markdown respeitando a hierarquia:
        # CLI Flag > Cenário YAML > Config global > Fallback False
        effective_cli_markdown = (
            markdown_override if markdown_override is not None else self.markdown_override
        )
        effective_markdown = resolve_markdown_mode(
            cli_markdown=effective_cli_markdown,
            scenario_markdown=scenario.markdown,
            config_markdown=self.config.reporting.generate_markdown,
        )

        # Determina o modo devtools respeitando a hierarquia:
        # CLI Flag > Cenário YAML > Config global > Fallback False
        from uxsentinel.core.config import resolve_devtools_mode

        effective_cli_devtools = (
            devtools_override if devtools_override is not None else self.devtools_override
        )
        effective_devtools = resolve_devtools_mode(
            cli_devtools=effective_cli_devtools,
            scenario_devtools=scenario.devtools,
            config_devtools=self.config.browser.devtools,
        )

        # Determina o modo headless efetivo respeitando a hierarquia:
        # CLI Flag > Cenário YAML > Config global > Fallback False (visível)
        effective_cli_headless = (
            headless_override if headless_override is not None else self.headless_override
        )
        effective_headless = resolve_display_mode(
            cli_headless=effective_cli_headless,
            scenario_headless=scenario.headless,
            config_headless=self.config.browser.headless,
        )

        # Se DevTools estiver ativado, força modo visível (Playwright requer headless=False)
        if effective_devtools:
            effective_headless = False

        # Determina a gravação de vídeo respeitando a hierarquia:
        # CLI Flag > Cenário YAML > Config global > Fallback False
        effective_cli_video = (
            record_video_override if record_video_override is not None else self.record_video_override
        )
        effective_video = resolve_video_mode(
            cli_video=effective_cli_video,
            scenario_video=scenario.video,
            config_video=self.config.browser.record_video,
        )

        # Determina a auditoria de acessibilidade com Axe-Core:
        # CLI Flag > Cenário YAML > Config global > Fallback True
        effective_cli_axe = (
            enable_axe_override if enable_axe_override is not None else self.enable_axe_override
        )
        effective_axe = resolve_axe_mode(
            cli_axe=effective_cli_axe,
            scenario_axe=scenario.axe,
            config_axe=self.config.browser.enable_axe,
        )

        # Determina a auditoria de CSS híbrida:
        # CLI Flag > Cenário YAML > Config global > Fallback True
        effective_cli_css = (
            enable_css_override if enable_css_override is not None else self.enable_css_override
        )
        effective_css = resolve_css_mode(
            cli_css=effective_cli_css,
            scenario_css=scenario.css,
            config_css=self.config.browser.enable_css_audit,
        )

        # Determina a resolução do baseline visual:
        effective_cli_update_baseline = (
            update_baseline_override
            if update_baseline_override is not None
            else self.update_baseline_override
        )
        effective_update_baseline = resolve_baseline_mode(
            cli_update_baseline=effective_cli_update_baseline,
            scenario_update_baseline=scenario.update_baseline,
            config_update_baseline=self.config.baseline.update_baseline,
        )
        effective_baseline_dir = (
            baseline_dir_override
            or self.baseline_dir_override
            or scenario.baseline_dir
            or self.config.baseline.baseline_dir
        )
        effective_diff_threshold = (
            diff_threshold_override
            if diff_threshold_override is not None
            else self.diff_threshold_override
            if self.diff_threshold_override is not None
            else scenario.diff_threshold
            if scenario.diff_threshold is not None
            else self.config.baseline.diff_threshold
        )

        # Determina a lista de viewports a auditar respeitando a hierarquia:
        # CLI Flag (--viewports / --viewport) > Cenário YAML > Config global > Fallback (desktop 1280x800)
        effective_cli_viewports = (
            viewports_override if viewports_override is not None else self.viewports_override
        )
        effective_viewports = resolve_viewports(
            cli_viewports=effective_cli_viewports,
            scenario_viewports=scenario.viewports,
            config_viewports=self.config.browser.viewports,
        )

        # Determina o arquivamento da análise anterior respeitando a hierarquia:
        # CLI Flag > Cenário YAML > Config global > Fallback True
        effective_cli_archive = archive_override if archive_override is not None else self.archive_override
        effective_archive = resolve_archive_mode(
            cli_archive=effective_cli_archive,
            scenario_archive=scenario.archive,
            config_archive=self.config.reporting.archive_previous_reports,
        )
        effective_cli_archive_dir = (
            archive_dir_override if archive_dir_override is not None else self.archive_dir_override
        )
        effective_archive_dir = resolve_archive_dir(
            cli_archive_dir=str(effective_cli_archive_dir) if effective_cli_archive_dir else None,
            scenario_archive_dir=scenario.archive_dir,
            config_archive_dir=self.config.reporting.archive_dir,
        )

        out_dir = Path(self.config.reporting.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        archived_zip_path: Path | None = None
        if effective_archive:
            archived_zip_path = archive_previous_reports(
                output_dir=out_dir,
                archive_dir=effective_archive_dir,
                label=scenario.id,
            )
            if archived_zip_path:
                console.print(
                    f"📦 [bold cyan]Análise anterior arquivada com sucesso em:[/bold cyan] [underline]{archived_zip_path}[/underline]\n"
                )

        videos_dir = out_dir / "videos"
        if effective_video:
            videos_dir.mkdir(parents=True, exist_ok=True)

        initial_vp = effective_viewports[0]
        browser_settings = self.config.browser.model_copy(
            update={
                "headless": effective_headless,
                "record_video": effective_video,
                "record_video_dir": str(videos_dir),
                "viewport_width": initial_vp.width,
                "viewport_height": initial_vp.height,
                "enable_axe": effective_axe,
                "enable_css_audit": effective_css,
                "devtools": effective_devtools,
            }
        )

        console.print(
            f"\n[bold cyan]🛡️ UXSentinel iniciado[/bold cyan] | Cenário: [bold]{scenario.title}[/bold] ([dim]{scenario.id}[/dim])"
        )
        vp_summary_str = ", ".join(vp.label for vp in effective_viewports)
        moe_desc = "Ativo (4 agentes)" if self.config.vision.use_mixture_of_evaluators else "Desativado"
        axe_desc = "Ativo (WCAG 2.2)" if effective_axe else "Desativado"
        css_desc = "Ativo (Híbrido)" if effective_css else "Desativado"
        devtools_desc = "Ativo (Console Aberto)" if effective_devtools else "Desativado"
        baseline_desc = (
            "Atualização (--update-baseline)"
            if effective_update_baseline
            else f"Auditoria Ativa (limiar: {effective_diff_threshold}%)"
        )
        console.print(
            f"   Perfil: [magenta]{profile}[/magenta] | Provedor IA: [yellow]{self.config.active_provider}[/yellow] | MoE: [cyan]{moe_desc}[/cyan] | Axe-Core: [cyan]{axe_desc}[/cyan] | CSS: [cyan]{css_desc}[/cyan] | DevTools: [cyan]{devtools_desc}[/cyan] | Baseline: [cyan]{baseline_desc}[/cyan] | Headless: [blue]{effective_headless}[/blue] | Viewports: [cyan]{vp_summary_str}[/cyan] | Self-Healing: [green]{browser_settings.self_healing}[/green]\n"
        )

        if effective_headless:
            console.print(
                Panel(
                    "[bold yellow]🕶️  MODO HEADLESS ATIVO (Execução sem interface gráfica)[/bold yellow]\n"
                    "[dim]O navegador Chromium está executando em segundo plano.\n"
                    "Acompanhe o status e progresso em tempo real das ações abaixo:[/dim]",
                    title="[bold cyan]UXSentinel Display Mode[/bold cyan]",
                    border_style="yellow",
                )
            )

        report = TestReport(
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            profile=profile,
            provider_used=self.config.active_provider,
            started_at=datetime.now(),
            viewports_tested=[vp.label for vp in effective_viewports],
            archived_report_path=str(archived_zip_path) if archived_zip_path else None,
        )

        await bus.publish(
            ExecutionEvent(
                event_type=EventType.SCENARIO_STARTED,
                scenario_id=scenario.id,
                data={
                    "title": scenario.title,
                    "profile": profile,
                    "viewports": [vp.label for vp in effective_viewports],
                },
            )
        )

        console.print(
            f"🔍 Verificando conectividade com o provedor de IA ([yellow]{self.config.active_provider}[/yellow])..."
        )
        ai_ok, ai_msg = await self.inspector.client.test_connection()
        if not ai_ok:
            console.print(f"\n[bold red]❌ Erro de Conexão com a IA:[/bold red] {ai_msg}")
            console.print(
                "[yellow]Dica:[/yellow] Verifique suas credenciais no arquivo de configuração "
                "ou alterne o provedor com [bold]-p[/bold] (ex: [bold]-p gemini_sso[/bold] ou [bold]-p ollama_local[/bold]).\n"
            )
            report.error_message = f"Falha de conexão com a IA: {ai_msg}"
            report.success = False
            report.finished_at = datetime.now()
            report.duration_seconds = time.time() - start_time
            scenario_failed_emitted = True
            await bus.publish(
                ExecutionEvent(
                    event_type=EventType.SCENARIO_FAILED,
                    scenario_id=scenario.id,
                    data={"error": report.error_message},
                )
            )
            self.last_execution_result = ExecutionResult(
                scenario_id=scenario.id,
                success=False,
                status="erro_conexao_ia",
                report=report,
                error_message=report.error_message,
            )
            return report

        console.print(f"[bold green]✓ Conexão com a IA estabelecida:[/bold green] {ai_msg}\n")

        captured_driver: BaseDriver | None = None
        try:
            async with open_browser_session(
                browser_settings,
                profile=profile,
                healer=self.healer,
                record_video=effective_video,
                record_video_dir=str(videos_dir),
                initial_viewport=initial_vp,
                devtools=effective_devtools,
            ) as driver:
                captured_driver = driver
                from uxsentinel.browser.semantic_actions import SemanticActionExecutor

                driver.semantic_executor = SemanticActionExecutor(
                    page=driver.page,
                    vision_client=self.inspector.client,
                    highlight_clicks=getattr(driver, "highlight_clicks", True),
                )
                multi_vp = len(effective_viewports) > 1
                total_work = len(scenario.steps) * len(effective_viewports)
                interrupted = False

                if effective_headless and total_work > 0:
                    with Progress(
                        SpinnerColumn(style="bold cyan"),
                        TextColumn("[bold cyan]{task.description}"),
                        BarColumn(bar_width=30, style="dim white", complete_style="bold green"),
                        TaskProgressColumn(),
                        TimeElapsedColumn(),
                        console=console,
                        transient=False,
                    ) as progress:
                        task_id = progress.add_task(f"[cyan]Executando {scenario.title}...", total=total_work)
                        for vp in effective_viewports:
                            if interrupted:
                                break
                            if hasattr(driver, "set_viewport"):
                                await driver.set_viewport(vp.width, vp.height)
                            elif hasattr(driver, "page") and hasattr(driver.page, "set_viewport_size"):
                                await driver.page.set_viewport_size({"width": vp.width, "height": vp.height})

                            for idx, step in enumerate(scenario.steps, start=1):
                                action_desc = (
                                    step.description or f"{step.action} {step.selector or step.url or ''}"
                                )
                                vp_tag = f" [{vp.name}]" if multi_vp else ""
                                progress.update(
                                    task_id,
                                    description=f"[cyan]Passo {idx:02d}/{len(scenario.steps):02d}{vp_tag}: [white]{action_desc[:35]}",
                                )
                                should_continue = await self._execute_step_guarded(
                                    idx,
                                    step,
                                    driver,
                                    scenario,
                                    report,
                                    out_dir,
                                    effective_fail_fast=effective_fail_fast,
                                    progress=progress,
                                    task_id=task_id,
                                    current_viewport=vp,
                                    multi_viewport=multi_vp,
                                    effective_axe=effective_axe,
                                    effective_css=effective_css,
                                    effective_baseline_dir=effective_baseline_dir,
                                    effective_update_baseline=effective_update_baseline,
                                    effective_diff_threshold=effective_diff_threshold,
                                    event_bus=bus,
                                )
                                progress.advance(task_id)
                                if not should_continue:
                                    interrupted = True
                                    break
                else:
                    for vp in effective_viewports:
                        if interrupted:
                            break
                        if multi_vp:
                            console.print(
                                f"\n[bold cyan]📱 Alternando Viewport:[/bold cyan] [bold]{vp.label}[/bold]"
                            )
                        if hasattr(driver, "set_viewport"):
                            await driver.set_viewport(vp.width, vp.height)
                        elif hasattr(driver, "page") and hasattr(driver.page, "set_viewport_size"):
                            await driver.page.set_viewport_size({"width": vp.width, "height": vp.height})

                        for idx, step in enumerate(scenario.steps, start=1):
                            should_continue = await self._execute_step_guarded(
                                idx,
                                step,
                                driver,
                                scenario,
                                report,
                                out_dir,
                                effective_fail_fast=effective_fail_fast,
                                current_viewport=vp,
                                multi_viewport=multi_vp,
                                effective_axe=effective_axe,
                                effective_css=effective_css,
                                effective_baseline_dir=effective_baseline_dir,
                                effective_update_baseline=effective_update_baseline,
                                effective_diff_threshold=effective_diff_threshold,
                                event_bus=bus,
                            )
                            if not should_continue:
                                interrupted = True
                                break

        except Exception as exc:
            console.print(f"[bold red]❌ Erro fatal na execução do cenário:[/bold red] {exc}")
            report.error_message = str(exc)
            scenario_failed_emitted = True
            await bus.publish(
                ExecutionEvent(
                    event_type=EventType.SCENARIO_FAILED,
                    scenario_id=scenario.id,
                    data={"error": str(exc)},
                )
            )

        finally:
            # Processa e renomeia o vídeo gravado caso disponível
            raw_video = getattr(captured_driver, "video_path", None)
            if not raw_video and captured_driver and getattr(captured_driver, "session", None):
                raw_video = getattr(captured_driver.session, "video_path", None)

            if raw_video and Path(raw_video).is_file():
                final_video = finalize_session_video(
                    raw_video_path=raw_video,
                    output_dir=videos_dir,
                    scenario_id=scenario.id,
                    try_mp4_conversion=True,
                )
                report.video_path = str(final_video)
                console.print(
                    f"\n[bold green]🎥 Gravação de vídeo da sessão salva em:[/bold green] [underline]{report.video_path}[/underline]"
                )

            # Gera GIF representativo da sessão (via ffmpeg do vídeo ou Pillow das capturas de checkpoints)
            gif_target = videos_dir / f"{scenario.id}_session.gif"
            checkpoint_images = [cp.screenshot_path for cp in report.checkpoints if cp.screenshot_path]
            generated_gif = create_session_gif(
                video_path=report.video_path,
                checkpoint_screenshots=checkpoint_images,
                output_gif=gif_target,
            )
            if generated_gif and generated_gif.is_file():
                report.gif_path = str(generated_gif)
                console.print(
                    f"[bold green]🎞️ GIF animado da sessão gerado em:[/bold green] [underline]{report.gif_path}[/underline]"
                )

            # Coleta logs de console, falhas de rede e métricas do coletor de telemetria
            telemetry_collector = getattr(captured_driver, "telemetry", None)
            if not telemetry_collector and captured_driver and getattr(captured_driver, "session", None):
                telemetry_collector = getattr(captured_driver.session, "telemetry", None)

            if isinstance(telemetry_collector, BrowserTelemetryCollector):
                report.console_logs = list(telemetry_collector.console_logs)
                report.network_failures = list(telemetry_collector.network_failures)
                if telemetry_collector.performance_history:
                    report.performance_metrics = telemetry_collector.performance_history[-1]

            report.finished_at = datetime.now()
            report.duration_seconds = time.time() - start_time
            report.compute_totals()

            self.last_execution_result = ExecutionResult(
                scenario_id=scenario.id,
                success=report.success,
                status="ok" if report.success else "erro",
                healed_events=report.healed_steps,
                report=report,
                error_message=report.error_message,
            )

            if not scenario_failed_emitted:
                if report.success and not report.error_message:
                    await bus.publish(
                        ExecutionEvent(
                            event_type=EventType.SCENARIO_COMPLETED,
                            scenario_id=scenario.id,
                            data={
                                "duration_seconds": report.duration_seconds,
                                "total_checkpoints": len(report.checkpoints),
                                "total_issues": report.total_issues,
                            },
                        )
                    )
                else:
                    await bus.publish(
                        ExecutionEvent(
                            event_type=EventType.SCENARIO_FAILED,
                            scenario_id=scenario.id,
                            data={"error": report.error_message or "Execution failed"},
                        )
                    )

            # Salva relatórios
            if self.config.reporting.generate_json:
                json_path = save_json_report(report, self.config.reporting.output_dir)
                console.print(f"[dim]📄 Relatório JSON salvo em:[/dim] {json_path}")

            if self.config.reporting.generate_html:
                html_path = save_html_report(report, self.config.reporting.output_dir)
                console.print(
                    f"[bold green]📊 Dashboard Visual HTML gerado em:[/bold green] [underline]{html_path}[/underline]"
                )

            if self.config.reporting.generate_fix_prompt:
                from uxsentinel.reporter.prompt_builder import save_fix_prompt

                prompt_path = save_fix_prompt(report, self.config.reporting.output_dir)
                console.print(
                    f"[bold green]🛠️ Documento de Prompt para Correção gerado em:[/bold green] [underline]{prompt_path}[/underline]"
                )

            if effective_markdown:
                md_path = save_markdown_report(report, self.config.reporting.output_dir)
                report.markdown_path = str(md_path)
                console.print(
                    f"[bold green]📝 Relatório MarkText (.md) gerado em:[/bold green] [underline]{md_path}[/underline]"
                )

            if self.config.jira.enabled:
                from uxsentinel.integrations.jira import JiraClient

                jira_client = JiraClient(self.config.jira)
                console.print(
                    "\n[bold cyan]📋 Sincronizando inconformidades com o Atlassian Jira...[/bold cyan]"
                )
                created_cards = await jira_client.create_issues_from_report(report)
                if created_cards:
                    console.print(
                        f"[bold green]✓ {len(created_cards)} card(s) criado(s) no Jira com sucesso![/bold green]"
                    )
                    for card_url in created_cards:
                        console.print(f"  - [link={card_url}]{card_url}[/link]")
                elif report.total_issues == 0:
                    console.print(
                        "[dim]Nenhuma inconformidade encontrada para abertura de cards no Jira.[/dim]"
                    )
                else:
                    console.print(
                        "[yellow]⚠️ Nenhum card foi criado no Jira. Verifique as credenciais e permissões no projeto.[/yellow]"
                    )

            self._print_summary(report)

        return report

    async def _execute_step_guarded(
        self,
        index: int,
        step: StepAction,
        driver: BaseDriver,
        scenario: Scenario,
        report: TestReport,
        out_dir: Path,
        effective_fail_fast: bool = True,
        event_bus: EventBus | None = None,
        **kwargs,
    ) -> bool:
        """Executa um passo. Em caso de falha de execução ou asserção/checkpoint grave:
        - Captura screenshot imediatamente no driver (passo_XX_falha.png) se houve exceção;
        - Se fail-fast estiver ativo, interrompe imediatamente a execução retornando False.
        Retorna True se deve continuar, ou False se a execução deve ser interrompida.
        """
        bus = event_bus or kwargs.get("event_bus") or getattr(self, "event_bus", None)
        current_viewport: ViewportConfig | None = kwargs.get("current_viewport")
        multi_viewport: bool = kwargs.get("multi_viewport", False)
        vp_label = current_viewport.label if current_viewport else None
        desc = step.description or f"{step.action} {step.selector or step.url or step.target or ''}"

        if bus:
            await bus.publish(
                ExecutionEvent(
                    event_type=EventType.STEP_STARTED,
                    scenario_id=scenario.id,
                    viewport=vp_label,
                    step_index=index,
                    action=step.action,
                    data={
                        "description": step.description,
                        "selector": step.selector or step.target,
                        "url": step.url,
                    },
                )
            )

        initial_cp_count = len(report.checkpoints)
        try:
            await self._execute_step(
                index,
                step,
                driver,
                scenario,
                report,
                out_dir,
                event_bus=bus,
                **kwargs,
            )
        except Exception as exc:
            progress: Progress | None = kwargs.get("progress")
            p_console = progress.console if progress is not None else console

            p_console.print(f"    [bold red]❌ FALHA NA EXECUÇÃO DO PASSO {index:02d}:[/bold red] {exc}")

            if bus:
                await bus.publish(
                    ExecutionEvent(
                        event_type=EventType.STEP_FAILED,
                        scenario_id=scenario.id,
                        viewport=vp_label,
                        step_index=index,
                        action=step.action,
                        data={"error": str(exc), "fail_fast": effective_fail_fast},
                    )
                )

            # Captura screenshot do erro imediatamente no driver
            clean_vp = (
                current_viewport.name.replace(":", "_").replace(" ", "_")
                if (multi_viewport and current_viewport)
                else None
            )
            screenshot_name = (
                f"{report.scenario_id}_{clean_vp}_passo_{index:02d}_falha.png"
                if clean_vp
                else f"{report.scenario_id}_passo_{index:02d}_falha.png"
            )
            screenshot_file = out_dir / screenshot_name
            screenshot_saved: str | None = None

            try:
                page_obj = getattr(driver, "page", None)
                if page_obj and hasattr(page_obj, "screenshot"):
                    await page_obj.screenshot(path=str(screenshot_file), full_page=True)
                    if screenshot_file.is_file():
                        screenshot_saved = str(screenshot_file)
            except Exception as ss_exc:
                p_console.print(f"    [dim]⚠️ Não foi possível capturar screenshot de falha: {ss_exc}[/dim]")

            issue = Issue(
                categoria=IssueCategory.OUTRO,
                severidade=IssueSeverity.BLOQUEANTE,
                descricao=f"Falha ao executar o passo {index:02d} ('{step.action}'): {exc}",
                sugestao_correcao="Verifique se o seletor, a URL e o estado da aplicação auditada continuam válidos para este passo.",
                elemento_alvo=step.selector or step.target,
                viewport=vp_label,
                evaluator="step_executor",
            )
            report.checkpoints.append(
                CheckpointResult(
                    name=f"passo_{index:02d}_falha",
                    description=desc,
                    expected_behavior=f"O passo '{step.action}' deveria ser executado com sucesso.",
                    screenshot_path=screenshot_saved,
                    status="erro_execucao",
                    issues=[issue],
                    viewport=vp_label,
                )
            )

            if effective_fail_fast:
                p_console.print(
                    "\n[bold red]⛔ FALHA GRAVE DETECTADA: Interrompendo execução imediatamente (--fail-fast ativo).[/bold red]\n"
                )
                return False
            return True

        # Verifica se o passo executado (ex: assert_*, ai_assert ou checkpoint) gerou falha grave
        new_cps = report.checkpoints[initial_cp_count:]
        if effective_fail_fast and new_cps:
            has_severe_failure = False
            for cp in new_cps:
                if cp.status in ("problemas_encontrados", "erro_execucao"):
                    for iss in cp.issues:
                        if iss.severidade in (IssueSeverity.BLOQUEANTE, IssueSeverity.ALTA):
                            has_severe_failure = True
                            break
                if has_severe_failure:
                    break

            if has_severe_failure:
                if bus:
                    await bus.publish(
                        ExecutionEvent(
                            event_type=EventType.STEP_FAILED,
                            scenario_id=scenario.id,
                            viewport=vp_label,
                            step_index=index,
                            action=step.action,
                            data={
                                "error": "Falha grave detectada em checkpoint ou asserção",
                                "fail_fast": effective_fail_fast,
                            },
                        )
                    )
                progress = kwargs.get("progress")
                p_console = progress.console if progress is not None else console
                p_console.print(
                    "\n[bold red]⛔ FALHA GRAVE DETECTADA: Interrompendo execução imediatamente (--fail-fast ativo).[/bold red]\n"
                )
                return False

        if bus:
            await bus.publish(
                ExecutionEvent(
                    event_type=EventType.STEP_COMPLETED,
                    scenario_id=scenario.id,
                    viewport=vp_label,
                    step_index=index,
                    action=step.action,
                    data={"description": desc},
                )
            )

        return True

    async def _execute_step(
        self,
        index: int,
        step: StepAction,
        driver: BaseDriver,
        scenario: Scenario,
        report: TestReport,
        out_dir: Path,
        progress: Progress | None = None,
        task_id: int | None = None,
        current_viewport: ViewportConfig | None = None,
        multi_viewport: bool = False,
        effective_axe: bool = True,
        effective_css: bool = True,
        effective_baseline_dir: str | Path = "scenarios/baselines",
        effective_update_baseline: bool = False,
        effective_diff_threshold: float = 0.1,
        event_bus: EventBus | None = None,
        **kwargs,
    ) -> None:
        p_console = progress.console if progress is not None else console
        bus = event_bus or kwargs.get("event_bus") or getattr(self, "event_bus", None)
        action = step.action.lower().strip()
        desc = step.description or f"{action} {step.selector or step.url or step.target or ''}"
        vp_tag = f" [dim][{current_viewport.name}][/dim]" if (multi_viewport and current_viewport) else ""
        if step.skip:
            p_console.print(
                f"  [yellow]⏭️ Passo {index:02d} pulado (marcado como exceção/skip):[/yellow] [dim]{desc}[/dim]{vp_tag}"
            )
            return

        if scenario.exceptions:
            target_match = step.selector or step.target or step.ai_click or step.ai_fill or ""
            target_clean = target_match.strip().lower()
            if target_clean:
                if any(
                    s.strip().lower() == target_clean
                    for s in scenario.exceptions.ignored_selectors
                    if s.strip()
                ):
                    p_console.print(
                        f"  [yellow]⏭️ Passo {index:02d} ignorado (seletor '{target_match}' na cláusula de exceções)[/yellow]{vp_tag}"
                    )
                    return
                if any(
                    e.strip().lower() in target_clean or target_clean in e.strip().lower()
                    for e in scenario.exceptions.ignored_elements
                    if e.strip()
                ):
                    p_console.print(
                        f"  [yellow]⏭️ Passo {index:02d} ignorado (elemento '{target_match}' na cláusula de exceções)[/yellow]{vp_tag}"
                    )
                    return

        if action in ("ai_click", "ai_fill", "ai_assert", "ai_action"):
            ai_target = (
                step.ai_click or step.ai_fill or step.ai_assert or step.ai_action or step.target or desc
            )
            p_console.print(f"  [bold magenta]🤖 IA-ACTION: [{ai_target}][/bold magenta]{vp_tag}")
        else:
            p_console.print(f"  [cyan]Passo {index:02d}:[/cyan] [dim]{desc}[/dim]{vp_tag}")

        initial_healing_count = len(driver.healing_events)

        ctx = ActionContext(
            driver=driver,
            scenario=scenario,
            report=report,
            out_dir=out_dir,
            step_index=index,
            step=step,
            progress=progress,
            task_id=task_id,
            current_viewport=current_viewport,
            multi_viewport=multi_viewport,
            effective_axe=effective_axe,
            effective_css=effective_css,
            effective_baseline_dir=effective_baseline_dir,
            effective_update_baseline=effective_update_baseline,
            effective_diff_threshold=effective_diff_threshold,
            scenario_exceptions=scenario.exceptions,
            agent=self,
            event_bus=bus,
        )

        await default_action_registry.execute(ctx)

        # Verifica se ocorreram eventos de self-healing neste passo
        if len(driver.healing_events) > initial_healing_count:
            for ev in driver.healing_events[initial_healing_count:]:
                report.healed_steps.append(ev)
                report.healing_events.append(ev)
                if bus:
                    await bus.publish(
                        ExecutionEvent(
                            event_type=EventType.HEALING_APPLIED,
                            scenario_id=scenario.id,
                            viewport=current_viewport.label if current_viewport else None,
                            step_index=index,
                            action=step.action,
                            data={
                                "original_selector": ev.original_selector,
                                "recovered_selector": ev.recovered_selector,
                                "strategy": ev.strategy,
                                "coordinates": ev.coordinates,
                                "yaml_fix_suggestion": ev.yaml_fix_suggestion,
                            },
                        )
                    )
                strat_label = (
                    "Acessibilidade Semântica" if ev.strategy == "accessibility" else "Visão Multimodal LMM"
                )
                target_recovered = ev.recovered_selector or f"coords {ev.coordinates}"
                p_console.print(
                    f"    [bold yellow]⚡ Self-Healing Ativado:[/bold yellow] Seletor [strikethrough]{ev.original_selector}[/strikethrough] "
                    f"recuperado via [bold magenta]{strat_label}[/bold magenta] -> [bold green]{target_recovered}[/bold green]"
                )
                if ev.yaml_fix_suggestion:
                    p_console.print(
                        f"      [dim]💡 Sugestão para o arquivo YAML: {ev.yaml_fix_suggestion}[/dim]"
                    )

    async def _handle_checkpoint(
        self,
        step: StepAction,
        driver: BaseDriver,
        report: TestReport,
        out_dir: Path,
        progress: Progress | None = None,
        task_id: int | None = None,
        step_index: int | None = None,
        total_steps: int | None = None,
        current_viewport: ViewportConfig | None = None,
        multi_viewport: bool = False,
        effective_axe: bool = True,
        effective_css: bool = True,
        effective_baseline_dir: str | Path = "scenarios/baselines",
        effective_update_baseline: bool = False,
        effective_diff_threshold: float = 0.1,
        scenario_exceptions: ScenarioExceptions | None = None,
        event_bus: EventBus | None = None,
        **kwargs,
    ) -> None:
        p_console = progress.console if progress is not None else console
        bus = event_bus or kwargs.get("event_bus") or getattr(self, "event_bus", None)
        base_cp_name = step.name or f"checkpoint_{len(report.checkpoints) + 1}"
        expected = step.expected_behavior or "A tela deve estar limpa e sem erros."

        combined_exceptions: ScenarioExceptions | None = None
        if scenario_exceptions:
            combined_exceptions = scenario_exceptions
        if step.exceptions:
            combined_exceptions = (
                combined_exceptions.merge(step.exceptions) if combined_exceptions else step.exceptions
            )

        if multi_viewport and current_viewport:
            clean_vp = current_viewport.name.replace(":", "_").replace(" ", "_")
            cp_name = f"{base_cp_name}_{clean_vp}"
            screenshot_file = out_dir / f"{report.scenario_id}_{clean_vp}_{base_cp_name}.png"
        else:
            cp_name = base_cp_name
            screenshot_file = out_dir / f"{report.scenario_id}_{cp_name}.png"

        vp_label = current_viewport.label if current_viewport else None
        vp_suffix = f" [{vp_label}]" if vp_label else ""
        p_console.print(
            f"    [bold yellow]📸 Checkpoint acionado:[/bold yellow] [italic]{cp_name}[/italic]{vp_suffix}"
        )
        if combined_exceptions and not combined_exceptions.is_empty():
            details: list[str] = []
            if combined_exceptions.allowed_texts:
                details.append(f"{len(combined_exceptions.allowed_texts)} texto(s) permitido(s)")
            if combined_exceptions.ignored_selectors:
                details.append(f"{len(combined_exceptions.ignored_selectors)} seletor(es) ignorado(s)")
            if combined_exceptions.custom_rules:
                details.append(f"{len(combined_exceptions.custom_rules)} regra(s)")
            summary_info = f" ({', '.join(details)})" if details else ""
            p_console.print(f"    [dim]🛡️ Cláusula de exceções ativa{summary_info}[/dim]")

        # Set-of-Marks (SoM) opcional para captura de screenshot com identificadores visuais numéricos
        som_enabled = getattr(self.config.vision, "enable_som", False)
        som_manager = SetOfMarksManager() if som_enabled else None

        if som_manager and hasattr(driver, "page") and driver.page:
            async with som_manager.apply_som(driver.page):
                if hasattr(driver.page, "screenshot"):
                    await driver.page.screenshot(path=str(screenshot_file), full_page=True)
        else:
            if hasattr(driver, "page") and hasattr(driver.page, "screenshot"):
                await driver.page.screenshot(path=str(screenshot_file), full_page=True)

        if bus:
            await bus.publish(
                ExecutionEvent(
                    event_type=EventType.CHECKPOINT_CAPTURED,
                    scenario_id=report.scenario_id,
                    viewport=vp_label,
                    step_index=step_index,
                    action="checkpoint",
                    data={
                        "name": cp_name,
                        "screenshot_path": str(screenshot_file),
                        "expected_behavior": expected,
                    },
                )
            )

        # Resolução e Execução do Baseline Visual
        baseline_base = Path(effective_baseline_dir)
        baseline_scenario_dir = baseline_base / report.scenario_id
        baseline_scenario_dir.mkdir(parents=True, exist_ok=True)
        if multi_viewport and current_viewport:
            clean_vp = current_viewport.name.replace(":", "_").replace(" ", "_")
            baseline_file = baseline_scenario_dir / f"{clean_vp}_{base_cp_name}.png"
        else:
            baseline_file = baseline_scenario_dir / f"{cp_name}.png"

        diff_res: VisualDiffResult | None = None
        extra_dom_issues: list[Issue] = []

        if effective_update_baseline:
            if screenshot_file.is_file():
                shutil.copy2(screenshot_file, baseline_file)
            diff_res = VisualDiffResult(
                baseline_path=str(baseline_file),
                current_path=str(screenshot_file),
                diff_image_path=None,
                diff_percentage=0.0,
                has_diff=False,
                threshold=effective_diff_threshold,
                bounding_boxes=[],
                total_pixels=0,
                diff_pixels=0,
            )
            p_console.print(
                f"    [bold cyan]💾 Baseline atualizado:[/bold cyan] [italic]{baseline_file}[/italic]"
            )
        elif baseline_file.is_file() and screenshot_file.is_file():
            diff_file = out_dir / f"{report.scenario_id}_{cp_name}_diff.png"
            try:
                diff_res = compare_images(
                    baseline_path=baseline_file,
                    current_path=screenshot_file,
                    diff_output_path=diff_file,
                    threshold=effective_diff_threshold,
                )
                if diff_res.has_diff:
                    sev = (
                        IssueSeverity.BLOQUEANTE
                        if diff_res.diff_percentage >= 10.0
                        else IssueSeverity.ALTA
                        if diff_res.diff_percentage >= 3.0
                        else IssueSeverity.MEDIA
                    )
                    regress_issue = Issue(
                        categoria=IssueCategory.LAYOUT,
                        severidade=sev,
                        descricao=(
                            f"Regressão visual detectada no checkpoint '{cp_name}': divergência de "
                            f"{diff_res.diff_percentage:.2f}% (limiar tolerado: {effective_diff_threshold}%)."
                        ),
                        sugestao_correcao=(
                            "Verificar alterações recentes de layout/CSS ou homologar uma nova "
                            "referência executando com a flag --update-baseline."
                        ),
                        viewport=vp_label,
                        evaluator="visual-baseline-diff",
                    )
                    extra_dom_issues.append(regress_issue)
                    p_console.print(
                        f"    [bold red]⚠️ Regressão Visual detectada:[/bold red] {diff_res.diff_percentage:.2f}% "
                        f"de divergência visual (limiar: {effective_diff_threshold}%)"
                    )
                else:
                    p_console.print(
                        f"    [bold green]👁️ Baseline visual conforme:[/bold green] {diff_res.diff_percentage:.2f}% "
                        f"de divergência (dentro do limiar de {effective_diff_threshold}%)"
                    )
            except Exception as diff_exc:
                p_console.print(f"    [yellow]⚠️ Falha na comparação de baseline visual: {diff_exc}[/yellow]")
        else:
            p_console.print(
                f"    [dim]ℹ️ Baseline de referência não encontrado em '{baseline_file}'. "
                f"Execute com --update-baseline para homologar.[/dim]"
            )

        # Extrai o texto limpo do DOM
        dom_text = await driver.get_clean_dom_text()

        # Pré-validação determinística no DOM (overflow matemático, truncamento de texto, modais)
        if getattr(self.config.vision, "enable_dom_validation", True) and hasattr(driver, "validate_dom"):
            try:
                dom_anomalies = await driver.validate_dom()
                if dom_anomalies and hasattr(driver, "dom_validator"):
                    dom_summary = driver.dom_validator.format_anomalies_summary(dom_anomalies)
                    dom_text = f"{dom_text}\n\n{dom_summary}".strip()
                    val_issues = driver.dom_validator.anomalies_to_issues(dom_anomalies, viewport=vp_label)
                    if isinstance(val_issues, list):
                        extra_dom_issues.extend(val_issues)
            except Exception:
                pass

        # Execução do motor Axe-Core para auditoria rigorosa de acessibilidade WCAG 2.2
        a11y_violations = []
        cp_a11y_score: float | None = None
        if effective_axe and hasattr(driver, "page") and driver.page:
            p_console.print("    [dim]♿ Executando auditoria de acessibilidade Axe-Core (WCAG 2.2)...[/dim]")
            try:
                a11y_violations = await self.axe_runner.run(driver.page, tags=self.config.browser.axe_tags)
                cp_a11y_score = calculate_a11y_score(a11y_violations)
                # Converte violações graves (critical / serious) em Issue para o fluxo unificado
                a11y_issues = convert_violations_to_issues(a11y_violations, viewport=vp_label)
                extra_dom_issues.extend(a11y_issues)

                score_color = "green" if cp_a11y_score >= 90 else "yellow" if cp_a11y_score >= 70 else "red"
                if a11y_violations:
                    p_console.print(
                        f"    [bold {score_color}]♿ A11y Score: {cp_a11y_score:.1f}%[/bold {score_color}] "
                        f"([red]{len(a11y_violations)} violação(ões) WCAG detectada(s)[/red])"
                    )
                else:
                    p_console.print(
                        "    [bold green]♿ A11y Score: 100.0% (Conforme WCAG 2.2 AA)[/bold green]"
                    )

                if bus:
                    await bus.publish(
                        ExecutionEvent(
                            event_type=EventType.AXE_AUDIT_COMPLETED,
                            scenario_id=report.scenario_id,
                            viewport=vp_label,
                            step_index=step_index,
                            action="checkpoint",
                            data={
                                "score": cp_a11y_score,
                                "violations_count": len(a11y_violations),
                            },
                        )
                    )
            except Exception as a11y_exc:
                p_console.print(
                    f"    [yellow]⚠️ Falha na auditoria de acessibilidade Axe-Core: {a11y_exc}[/yellow]"
                )

        # Execução do motor CSSInspector para auditoria de layout, tipografia e código CSS (UXS-47)
        cp_css_audit = None
        if effective_css and hasattr(driver, "page") and driver.page:
            p_console.print("    [dim]🎨 Executando auditoria híbrida de CSS...[/dim]")
            try:
                from uxsentinel.css.runner import CSSInspector

                cp_css_audit = await CSSInspector.audit_page(driver.page, viewport=vp_label)
                css_issues = cp_css_audit.to_issues(viewport=vp_label)
                extra_dom_issues.extend(css_issues)

                css_score_color = (
                    "green" if cp_css_audit.score >= 90 else "yellow" if cp_css_audit.score >= 70 else "red"
                )
                if cp_css_audit.violations:
                    p_console.print(
                        f"    [bold {css_score_color}]🎨 CSS Score: {cp_css_audit.score:.1f}%[/bold {css_score_color}] "
                        f"([red]{len(cp_css_audit.violations)} violação(ões) CSS detectada(s)[/red])"
                    )
                else:
                    p_console.print(
                        "    [bold green]🎨 CSS Score: 100.0% (Layout e folhas de estilo conformes)[/bold green]"
                    )
            except Exception as css_exc:
                p_console.print(f"    [yellow]⚠️ Falha na auditoria de CSS: {css_exc}[/yellow]")

        # Se for Odoo, checa erros silenciosos
        if isinstance(driver, OdooDriver):
            odoo_errors = await driver.check_unhandled_odoo_errors()
            if odoo_errors:
                dom_text += "\n\n[ERROS DETECTADOS NO ODOO]:\n" + "\n".join(odoo_errors)

        if progress is not None and task_id is not None:
            step_lbl = f"Passo {step_index:02d}/{total_steps:02d}: " if step_index and total_steps else ""
            progress.update(
                task_id,
                description=f"[cyan]{step_lbl}[white]🔍 Invocando IA ({cp_name})...",
            )

        p_console.print("    [dim]🔍 Invocando auditor de visão com IA...[/dim]")
        cp_result = await self.inspector.inspect(
            checkpoint_name=cp_name,
            expected_behavior=expected,
            screenshot_path=str(screenshot_file),
            dom_text=dom_text,
            description=step.description,
            viewport=vp_label,
            extra_issues=extra_dom_issues,
            exceptions=combined_exceptions,
        )

        cp_result.viewport = vp_label
        cp_result.a11y_score = cp_a11y_score
        cp_result.a11y_violations = a11y_violations
        cp_result.visual_diff = diff_res
        cp_result.css_audit = cp_css_audit

        # Anexa telemetria da sessão ao checkpoint
        if hasattr(driver, "telemetry") and isinstance(driver.telemetry, BrowserTelemetryCollector):
            cp_result.console_logs = list(driver.telemetry.console_logs)
            cp_result.network_failures = list(driver.telemetry.network_failures)
            if driver.telemetry.performance_history:
                cp_result.performance_metrics = driver.telemetry.performance_history[-1]

        for issue in cp_result.issues:
            if not issue.viewport:
                issue.viewport = vp_label

        cp_result.healed_events = list(report.healed_steps)
        report.checkpoints.append(cp_result)

        if bus:
            await bus.publish(
                ExecutionEvent(
                    event_type=EventType.AI_INSPECTION_COMPLETED,
                    scenario_id=report.scenario_id,
                    viewport=vp_label,
                    step_index=step_index,
                    action="checkpoint",
                    data={
                        "name": cp_name,
                        "status": cp_result.status,
                        "issues_count": len(cp_result.issues),
                    },
                )
            )

        if cp_result.status == "ok":
            p_console.print("    [bold green]✓ Checkpoint aprovado sem inconformidades![/bold green]")
        else:
            p_console.print(
                f"    [bold red]✗ Checkpoint com problemas ({len(cp_result.issues)} issues encontradas)[/bold red]"
            )
            for issue in cp_result.issues:
                eval_tag = f" [cyan]({issue.evaluator})[/cyan]" if issue.evaluator else ""
                p_console.print(f"      - [{issue.severidade.value.upper()}]{eval_tag} {issue.descricao}")

    def _print_summary(self, report: TestReport) -> None:
        table = Table(title=f"Resumo da Execução - {report.scenario_title}")
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="magenta")

        table.add_row(
            "Status Geral",
            "[bold green]APROVADO[/bold green]" if report.success else "[bold red]REPROVADO[/bold red]",
        )
        table.add_row("Duração", f"{report.duration_seconds:.1f} segundos")
        if report.viewports_tested:
            table.add_row("Viewports Auditadas", ", ".join(report.viewports_tested))
        table.add_row("Checkpoints Avaliados", str(len(report.checkpoints)))
        if report.healed_steps:
            table.add_row(
                "Seletores Auto-Curados (Self-Healing)",
                f"[bold yellow]{len(report.healed_steps)}[/bold yellow]",
            )
        if report.a11y_score is not None:
            score_color = (
                "green" if report.a11y_score >= 90 else "yellow" if report.a11y_score >= 70 else "red"
            )
            table.add_row(
                "A11y Score Médio (WCAG)",
                f"[bold {score_color}]{report.a11y_score:.1f}%[/bold {score_color}]",
            )
        if report.a11y_violations:
            table.add_row(
                "Violações WCAG (Axe-Core)",
                f"[bold red]{len(report.a11y_violations)}[/bold red]",
            )
        diff_count = sum(1 for cp in report.checkpoints if cp.visual_diff and cp.visual_diff.has_diff)
        if any(cp.visual_diff for cp in report.checkpoints):
            diff_label = (
                f"[bold red]{diff_count}[/bold red]" if diff_count > 0 else "[bold green]0[/bold green]"
            )
            table.add_row("Regressões Visuais (Baseline)", diff_label)
        if report.total_console_errors > 0 or report.total_console_warnings > 0:
            err_lbl = (
                f"[bold red]{report.total_console_errors}[/bold red]" if report.total_console_errors else "0"
            )
            warn_lbl = (
                f"[yellow]{report.total_console_warnings}[/yellow]" if report.total_console_warnings else "0"
            )
            table.add_row("Console da Aplicação (JS)", f"Erros: {err_lbl} | Avisos: {warn_lbl}")
        if report.network_failures:
            table.add_row("Falhas de Rede (HTTP)", f"[bold red]{len(report.network_failures)}[/bold red]")
        if report.performance_metrics and report.performance_metrics.load_time_ms > 0:
            table.add_row(
                "Tempo de Carga (Load / TTFB)",
                f"{report.performance_metrics.load_time_ms:.0f}ms / {report.performance_metrics.ttfb_ms:.0f}ms",
            )
        table.add_row("Total de Inconformidades", str(report.total_issues))
        table.add_row("Bloqueantes", f"[red]{report.total_bloqueantes}[/red]")
        table.add_row("Alta Severidade", f"[orange3]{report.total_altas}[/orange3]")
        table.add_row("Média Severidade", f"[yellow]{report.total_medias}[/yellow]")
        table.add_row("Baixa Severidade", f"[blue]{report.total_baixas}[/blue]")
        if report.markdown_path:
            table.add_row("Relatório MarkText (.md)", report.markdown_path)

        console.print("\n", table, "\n")


# Alias semântico e ergonômico
Agent = UXSentinelAgent
