import asyncio
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from uxsentinel.browser.drivers.base_driver import BaseDriver
from uxsentinel.browser.drivers.odoo_driver import OdooDriver
from uxsentinel.browser.healing import SelectorHealer
from uxsentinel.browser.session import open_browser_session
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import ExecutionResult, Scenario, StepAction, TestReport
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.reporter.json_builder import save_json_report
from uxsentinel.vision.inspector import ScreenInspector

console = Console()


class UXSentinelAgent:
    """Agente de QA Visual que executa a navegação e orquestra a auditoria de telas."""

    def __init__(self, config: GlobalConfig):
        self.config = config
        self.inspector = ScreenInspector(config)
        self.healer = SelectorHealer(
            vision_client=self.inspector.client,
            enabled=self.config.browser.self_healing,
        )
        self.last_execution_result: ExecutionResult | None = None

    async def run_scenario(self, scenario: Scenario) -> TestReport:
        profile = scenario.profile or "generic"
        start_time = time.time()

        console.print(
            f"\n[bold cyan]🛡️ UXSentinel iniciado[/bold cyan] | Cenário: [bold]{scenario.title}[/bold] ([dim]{scenario.id}[/dim])"
        )
        console.print(
            f"   Perfil: [magenta]{profile}[/magenta] | Provedor IA: [yellow]{self.config.active_provider}[/yellow] | Headless: [blue]{self.config.browser.headless}[/blue] | Self-Healing: [green]{self.config.browser.self_healing}[/green]\n"
        )

        report = TestReport(
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            profile=profile,
            provider_used=self.config.active_provider,
            started_at=datetime.now(),
        )

        out_dir = Path(self.config.reporting.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

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

        try:
            async with open_browser_session(
                self.config.browser, profile=profile, healer=self.healer
            ) as driver:
                for idx, step in enumerate(scenario.steps, start=1):
                    await self._execute_step(idx, step, driver, scenario, report, out_dir)

        except Exception as exc:
            console.print(f"[bold red]❌ Erro fatal na execução do cenário:[/bold red] {exc}")
            report.error_message = str(exc)

        finally:
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
    ) -> None:
        action = step.action.lower().strip()
        desc = step.description or f"{action} {step.selector or step.url or ''}"
        console.print(f"  [cyan]Passo {index:02d}:[/cyan] [dim]{desc}[/dim]")

        initial_healing_count = len(driver.healing_events)

        if action == "goto":
            if not step.url:
                raise ValueError(f"Passo {index}: 'goto' requer 'url'")
            await driver.goto(step.url, timeout=step.timeout or self.config.browser.timeout_ms)

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
                console.print("    [yellow]⚠️ Modal não detectado após timeout.[/yellow]")

        elif action == "wait_modal_close":
            await driver.wait_modal_close(timeout=step.timeout or 10000)

        elif action == "pause":
            duration = int(step.value or 2) if step.value and step.value.isdigit() else 2
            await asyncio.sleep(duration)

        elif action == "checkpoint":
            await self._handle_checkpoint(step, driver, report, out_dir)

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
                console.print(
                    f"    [bold yellow]⚡ Self-Healing Ativado:[/bold yellow] Seletor [strikethrough]{ev.original_selector}[/strikethrough] "
                    f"recuperado via [bold magenta]{strat_label}[/bold magenta] -> [bold green]{target_recovered}[/bold green]"
                )
                if ev.yaml_fix_suggestion:
                    console.print(
                        f"      [dim]💡 Sugestão para o arquivo YAML: {ev.yaml_fix_suggestion}[/dim]"
                    )

    async def _handle_checkpoint(
        self,
        step: StepAction,
        driver: BaseDriver,
        report: TestReport,
        out_dir: Path,
    ) -> None:
        cp_name = step.name or f"checkpoint_{len(report.checkpoints) + 1}"
        expected = step.expected_behavior or "A tela deve estar limpa e sem erros."

        console.print(f"    [bold yellow]📸 Checkpoint acionado:[/bold yellow] [italic]{cp_name}[/italic]")
        screenshot_file = out_dir / f"{report.scenario_id}_{cp_name}.png"

        # Captura screenshot em alta resolução
        await driver.page.screenshot(path=str(screenshot_file), full_page=True)

        # Extrai o texto limpo do DOM
        dom_text = await driver.get_clean_dom_text()

        # Se for Odoo, checa erros silenciosos
        if isinstance(driver, OdooDriver):
            odoo_errors = await driver.check_unhandled_odoo_errors()
            if odoo_errors:
                dom_text += "\n\n[ERROS DETECTADOS NO ODOO]:\n" + "\n".join(odoo_errors)

        console.print("    [dim]🔍 Invocando auditor de visão com IA...[/dim]")
        cp_result = await self.inspector.inspect(
            checkpoint_name=cp_name,
            expected_behavior=expected,
            screenshot_path=str(screenshot_file),
            dom_text=dom_text,
            description=step.description,
        )

        cp_result.healed_events = list(report.healed_steps)
        report.checkpoints.append(cp_result)

        if cp_result.status == "ok":
            console.print("    [bold green]✓ Checkpoint aprovado sem inconformidades![/bold green]")
        else:
            console.print(
                f"    [bold red]✗ Checkpoint com problemas ({len(cp_result.issues)} issues encontradas)[/bold red]"
            )
            for issue in cp_result.issues:
                console.print(f"      - [{issue.severidade.value.upper()}] {issue.descricao}")

    def _print_summary(self, report: TestReport) -> None:
        table = Table(title=f"Resumo da Execução - {report.scenario_title}")
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="magenta")

        table.add_row(
            "Status Geral",
            "[bold green]APROVADO[/bold green]" if report.success else "[bold red]REPROVADO[/bold red]",
        )
        table.add_row("Duração", f"{report.duration_seconds:.1f} segundos")
        table.add_row("Checkpoints Avaliados", str(len(report.checkpoints)))
        if report.healed_steps:
            table.add_row(
                "Seletores Auto-Curados (Self-Healing)",
                f"[bold yellow]{len(report.healed_steps)}[/bold yellow]",
            )
        table.add_row("Total de Inconformidades", str(report.total_issues))
        table.add_row("Bloqueantes", f"[red]{report.total_bloqueantes}[/red]")
        table.add_row("Alta Severidade", f"[orange3]{report.total_altas}[/orange3]")
        table.add_row("Média Severidade", f"[yellow]{report.total_medias}[/yellow]")
        table.add_row("Baixa Severidade", f"[blue]{report.total_baixas}[/blue]")

        console.print("\n", table, "\n")
