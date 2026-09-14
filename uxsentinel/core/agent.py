import asyncio
import contextlib
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
    resolve_axe_mode,
    resolve_baseline_mode,
    resolve_display_mode,
    resolve_markdown_mode,
    resolve_video_mode,
)
from uxsentinel.core.models import (
    CheckpointResult,
    ExecutionResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    SemanticStepResult,
    SemanticStrategy,
    StepAction,
    TestReport,
    ViewportConfig,
    VisualDiffResult,
    parse_viewport_spec,
    resolve_viewports,
)
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
        update_baseline_override: bool | None = None,
        baseline_dir_override: str | Path | None = None,
        diff_threshold_override: float | None = None,
        markdown_override: bool | None = None,
        devtools_override: bool | None = None,
    ):
        self.config = config
        self.headless_override = headless_override
        self.record_video_override = record_video_override
        self.viewports_override = viewports_override
        self.enable_axe_override = enable_axe_override
        self.update_baseline_override = update_baseline_override
        self.baseline_dir_override = baseline_dir_override
        self.diff_threshold_override = diff_threshold_override
        self.markdown_override = markdown_override
        self.devtools_override = devtools_override
        self.inspector = ScreenInspector(config)
        self.healer = SelectorHealer(
            vision_client=self.inspector.client,
            enabled=self.config.browser.self_healing,
        )
        self.axe_runner = AxeRunner(tags=self.config.browser.axe_tags)
        self.last_execution_result: ExecutionResult | None = None

    async def run_scenario(
        self,
        scenario: Scenario,
        headless_override: bool | None = None,
        record_video_override: bool | None = None,
        viewports_override: str | list[str] | list[ViewportConfig] | None = None,
        enable_axe_override: bool | None = None,
        update_baseline_override: bool | None = None,
        baseline_dir_override: str | Path | None = None,
        diff_threshold_override: float | None = None,
        markdown_override: bool | None = None,
        devtools_override: bool | None = None,
    ) -> TestReport:
        profile = scenario.profile or "generic"
        start_time = time.time()

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

        out_dir = Path(self.config.reporting.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
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
                "devtools": effective_devtools,
            }
        )

        console.print(
            f"\n[bold cyan]🛡️ UXSentinel iniciado[/bold cyan] | Cenário: [bold]{scenario.title}[/bold] ([dim]{scenario.id}[/dim])"
        )
        vp_summary_str = ", ".join(vp.label for vp in effective_viewports)
        moe_desc = "Ativo (4 agentes)" if self.config.vision.use_mixture_of_evaluators else "Desativado"
        axe_desc = "Ativo (WCAG 2.2)" if effective_axe else "Desativado"
        devtools_desc = "Ativo (Console Aberto)" if effective_devtools else "Desativado"
        baseline_desc = (
            "Atualização (--update-baseline)"
            if effective_update_baseline
            else f"Auditoria Ativa (limiar: {effective_diff_threshold}%)"
        )
        console.print(
            f"   Perfil: [magenta]{profile}[/magenta] | Provedor IA: [yellow]{self.config.active_provider}[/yellow] | MoE: [cyan]{moe_desc}[/cyan] | Axe-Core: [cyan]{axe_desc}[/cyan] | DevTools: [cyan]{devtools_desc}[/cyan] | Baseline: [cyan]{baseline_desc}[/cyan] | Headless: [blue]{effective_headless}[/blue] | Viewports: [cyan]{vp_summary_str}[/cyan] | Self-Healing: [green]{browser_settings.self_healing}[/green]\n"
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
                                await self._execute_step(
                                    idx,
                                    step,
                                    driver,
                                    scenario,
                                    report,
                                    out_dir,
                                    progress=progress,
                                    task_id=task_id,
                                    current_viewport=vp,
                                    multi_viewport=multi_vp,
                                    effective_axe=effective_axe,
                                    effective_baseline_dir=effective_baseline_dir,
                                    effective_update_baseline=effective_update_baseline,
                                    effective_diff_threshold=effective_diff_threshold,
                                )
                                progress.advance(task_id)
                else:
                    for vp in effective_viewports:
                        if multi_vp:
                            console.print(
                                f"\n[bold cyan]📱 Alternando Viewport:[/bold cyan] [bold]{vp.label}[/bold]"
                            )
                        if hasattr(driver, "set_viewport"):
                            await driver.set_viewport(vp.width, vp.height)
                        elif hasattr(driver, "page") and hasattr(driver.page, "set_viewport_size"):
                            await driver.page.set_viewport_size({"width": vp.width, "height": vp.height})

                        for idx, step in enumerate(scenario.steps, start=1):
                            await self._execute_step(
                                idx,
                                step,
                                driver,
                                scenario,
                                report,
                                out_dir,
                                current_viewport=vp,
                                multi_viewport=multi_vp,
                                effective_axe=effective_axe,
                                effective_baseline_dir=effective_baseline_dir,
                                effective_update_baseline=effective_update_baseline,
                                effective_diff_threshold=effective_diff_threshold,
                            )

        except Exception as exc:
            console.print(f"[bold red]❌ Erro fatal na execução do cenário:[/bold red] {exc}")
            report.error_message = str(exc)

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
        effective_baseline_dir: str | Path = "scenarios/baselines",
        effective_update_baseline: bool = False,
        effective_diff_threshold: float = 0.1,
    ) -> None:
        p_console = progress.console if progress is not None else console
        action = step.action.lower().strip()
        desc = step.description or f"{action} {step.selector or step.url or step.target or ''}"
        vp_tag = f" [dim][{current_viewport.name}][/dim]" if (multi_viewport and current_viewport) else ""
        if action in ("ai_click", "ai_fill", "ai_assert", "ai_action"):
            ai_target = (
                step.ai_click or step.ai_fill or step.ai_assert or step.ai_action or step.target or desc
            )
            p_console.print(f"  [bold magenta]🤖 IA-ACTION: [{ai_target}][/bold magenta]{vp_tag}")
        else:
            p_console.print(f"  [cyan]Passo {index:02d}:[/cyan] [dim]{desc}[/dim]{vp_tag}")

        initial_healing_count = len(driver.healing_events)

        if action == "goto":
            if not step.url:
                raise ValueError(f"Passo {index}: 'goto' requer 'url'")
            await driver.goto(step.url, timeout=step.timeout or self.config.browser.timeout_ms)

        elif action == "set_viewport":
            val = step.value or "desktop"
            vp_custom = parse_viewport_spec(val)
            if hasattr(driver, "set_viewport"):
                await driver.set_viewport(vp_custom.width, vp_custom.height)
            elif hasattr(driver, "page") and hasattr(driver.page, "set_viewport_size"):
                await driver.page.set_viewport_size({"width": vp_custom.width, "height": vp_custom.height})
            p_console.print(f"    [dim]Viewport alterada para {vp_custom.label}[/dim]")

        elif action == "click":
            if not step.selector:
                raise ValueError(f"Passo {index}: 'click' requer 'selector'")
            await driver.click(
                step.selector,
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )

        elif action == "fill":
            if not step.selector:
                raise ValueError(f"Passo {index}: 'fill' requer 'selector'")
            await driver.fill(
                step.selector,
                step.value or "",
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )

        elif action == "select":
            if not step.selector:
                raise ValueError(f"Passo {index}: 'select' requer 'selector'")
            await driver.select_option(
                step.selector,
                step.value or "",
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )

        elif action == "press":
            if not step.value:
                raise ValueError(f"Passo {index}: 'press' requer 'value' com o nome da tecla")
            await driver.press(step.value)

        elif action == "hover":
            if not step.selector:
                raise ValueError(f"Passo {index}: 'hover' requer 'selector'")
            await driver.hover(
                step.selector,
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )

        elif action == "scroll":
            direction = step.value or "down"
            await driver.scroll(direction=direction)

        elif action == "wait_until_ready" or action == "wait_odoo_ready" or action == "wait_navigation":
            await driver.wait_until_ready(timeout=step.timeout or 15000)

        elif action == "wait_modal" or action == "wait_for_modal":
            modal_opened = await driver.wait_for_modal(timeout=step.timeout or 10000)
            if not modal_opened:
                p_console.print("    [yellow]⚠️ Modal não detectado após timeout.[/yellow]")

        elif action == "wait_modal_close":
            await driver.wait_modal_close(timeout=step.timeout or 10000)

        elif action == "pause":
            duration = int(step.value or 2) if step.value and step.value.isdigit() else 2
            await asyncio.sleep(duration)

        elif action == "checkpoint":
            await self._handle_checkpoint(
                step,
                driver,
                report,
                out_dir,
                progress=progress,
                task_id=task_id,
                step_index=index,
                total_steps=len(scenario.steps),
                current_viewport=current_viewport,
                multi_viewport=multi_viewport,
                effective_axe=effective_axe,
                effective_baseline_dir=effective_baseline_dir,
                effective_update_baseline=effective_update_baseline,
                effective_diff_threshold=effective_diff_threshold,
            )

        elif action == "ai_click":
            target = step.ai_click or step.target or step.selector or ""
            if not target:
                raise ValueError(f"Passo {index}: 'ai_click' requer alvo descritivo em linguagem natural")
            sem_res = await driver.ai_click(
                target=target,
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )
            report.semantic_steps.append(sem_res)
            strat_label = (
                "Acessibilidade" if sem_res.strategy == SemanticStrategy.ACCESSIBILITY else "Visão LMM"
            )
            loc_label = sem_res.resolved_selector or (
                f"coords {sem_res.coordinates}" if sem_res.coordinates else "ok"
            )
            p_console.print(f"    [green]✔ Alvo clicado via {strat_label}:[/green] [dim]{loc_label}[/dim]")

        elif action == "ai_fill":
            target = step.ai_fill or step.target or step.selector or ""
            if not target:
                raise ValueError(f"Passo {index}: 'ai_fill' requer alvo descritivo em linguagem natural")
            val = step.value or ""
            sem_res = await driver.ai_fill(
                target=target,
                value=val,
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )
            report.semantic_steps.append(sem_res)
            strat_label = (
                "Acessibilidade" if sem_res.strategy == SemanticStrategy.ACCESSIBILITY else "Visão LMM"
            )
            loc_label = sem_res.resolved_selector or (
                f"coords {sem_res.coordinates}" if sem_res.coordinates else "ok"
            )
            p_console.print(
                f"    [green]✔ Campo preenchido via {strat_label}:[/green] [dim]{loc_label}[/dim]"
            )

        elif action == "ai_assert":
            assertion = step.ai_assert or step.target or step.expected_behavior or ""
            if not assertion:
                raise ValueError(f"Passo {index}: 'ai_assert' requer texto da asserção declarativa")
            assert_res = await driver.ai_assert(
                assertion=assertion,
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )
            sem_step = SemanticStepResult(
                step_index=index,
                action="ai_assert",
                target=assertion,
                strategy=SemanticStrategy.LMM_ASSERTION,
                confidence=assert_res.confidence,
                passed=assert_res.passed,
                reasoning=assert_res.reasoning,
            )
            report.semantic_steps.append(sem_step)

            if assert_res.passed:
                p_console.print(
                    f"    [bold green]✅ Asserção Cognitiva Aprovada:[/bold green] [dim]{assert_res.reasoning}[/dim]"
                )
            else:
                p_console.print(
                    f"    [bold red]❌ FALHA NA ASSERÇÃO COGNITIVA:[/bold red] {assert_res.reasoning}"
                )
                issue = Issue(
                    categoria=IssueCategory.REGRA_NEGOCIO,
                    severidade=assert_res.severity,
                    descricao=f"Falha na asserção cognitiva: '{assertion}'. Avaliação LMM: {assert_res.reasoning}",
                    sugestao_correcao=assert_res.suggestion
                    or "Verificar se o estado visual da tela corresponde ao esperado pela asserção declarativa.",
                    viewport=current_viewport.label if current_viewport else None,
                    evaluator="ai_assert",
                )
                # Registra como Issue e marca falha no checkpoint
                if report.checkpoints:
                    target_cp = report.checkpoints[-1]
                    target_cp.issues.append(issue)
                    target_cp.status = "problemas_encontrados"
                else:
                    screenshot_file = out_dir / f"{report.scenario_id}_ai_assert_step_{index}.png"
                    if hasattr(driver, "page") and hasattr(driver.page, "screenshot"):
                        with contextlib.suppress(Exception):
                            await driver.page.screenshot(path=str(screenshot_file), full_page=True)
                    cp = CheckpointResult(
                        name=f"ai_assert_step_{index}",
                        description=f"Validação cognitiva da asserção: {assertion}",
                        expected_behavior=assertion,
                        screenshot_path=str(screenshot_file) if screenshot_file.is_file() else None,
                        status="problemas_encontrados",
                        issues=[issue],
                        viewport=current_viewport.label if current_viewport else None,
                    )
                    report.checkpoints.append(cp)

        elif action == "ai_action":
            instruction = step.ai_action or step.target or step.description or ""
            if not instruction:
                raise ValueError(f"Passo {index}: 'ai_action' requer instrução em linguagem natural")
            sem_res = await driver.ai_action(
                instruction=instruction,
                value=step.value,
                timeout=step.timeout or 10000,
                description=desc,
                step_index=index,
            )
            report.semantic_steps.append(sem_res)
            p_console.print(
                f"    [green]✔ Ação semântica executada:[/green] [dim]{sem_res.reasoning or 'sucesso'}[/dim]"
            )

        else:
            raise ValueError(f"Ação desconhecida: '{action}'")

        # Verifica se ocorreram eventos de self-healing neste passo
        if len(driver.healing_events) > initial_healing_count:
            for ev in driver.healing_events[initial_healing_count:]:
                report.healed_steps.append(ev)
                report.healing_events.append(ev)
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
        effective_baseline_dir: str | Path = "scenarios/baselines",
        effective_update_baseline: bool = False,
        effective_diff_threshold: float = 0.1,
    ) -> None:
        p_console = progress.console if progress is not None else console
        base_cp_name = step.name or f"checkpoint_{len(report.checkpoints) + 1}"
        expected = step.expected_behavior or "A tela deve estar limpa e sem erros."

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
            except Exception as a11y_exc:
                p_console.print(
                    f"    [yellow]⚠️ Falha na auditoria de acessibilidade Axe-Core: {a11y_exc}[/yellow]"
                )

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
        )

        cp_result.viewport = vp_label
        cp_result.a11y_score = cp_a11y_score
        cp_result.a11y_violations = a11y_violations
        cp_result.visual_diff = diff_res

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
