from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from uxsentinel.browser.actions.context import ActionContext, BaseActionHandler
from uxsentinel.core.models import (
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    ScenarioExceptions,
    parse_viewport_spec,
)

if TYPE_CHECKING:
    pass

# Padrões comuns de tracking, analytics e métricas bloqueados por adblockers/extensões
IGNORED_TRACKING_PATTERNS = (
    "google-analytics",
    "googletagmanager",
    "doubleclick",
    "hotjar",
    "sentry",
    "mixpanel",
    "segment.io",
    "clarity.ms",
    "facebook.net",
    "connect.facebook",
    "analytics",
)

# Recursos estáticos inofensivos que podem resultar em 404 sem comprometer a aplicação
IGNORED_PATH_PATTERNS = (
    "/favicon.ico",
    "/robots.txt",
    "/apple-touch-icon",
)

# Padrões de exceção de runtime JS considerados críticos
CRITICAL_JS_PATTERNS = (
    "uncaught",
    "typeerror",
    "referenceerror",
    "syntaxerror",
    "rangeerror",
    "evalerror",
    "urierror",
    "unhandled",
    "pageerror",
    "window.onerror",
    "exceção não tratada",
)


def _is_ignorable_noise(text: str, url: str | None = None) -> bool:
    """Verifica se o erro é falso positivo conhecido de analytics/tracking ou asset inofensivo."""
    text_lower = text.lower()
    url_lower = (url or "").lower()

    if any(pattern in url_lower or pattern in text_lower for pattern in IGNORED_TRACKING_PATTERNS):
        return True

    return any(pattern in url_lower or pattern in text_lower for pattern in IGNORED_PATH_PATTERNS)


def _is_critical_console_log(text: str) -> bool:
    """Identifica se uma mensagem de erro do console representa uma falha de runtime crítica."""
    text_lower = text.lower()
    return any(p in text_lower for p in CRITICAL_JS_PATTERNS)


def _is_critical_network_failure(entry, target_url: str) -> bool:
    """Verifica se uma falha de rede é crítica (ex: 5xx ou falha de conexão na página principal)."""
    # Se for ruído conhecido, desconsidera
    if _is_ignorable_noise(entry.error_text or "", entry.url):
        return False

    # Erros de servidor HTTP 5xx sempre são críticos
    if entry.status and entry.status >= 500:
        return True

    # Falha na requisição principal do documento (mesma rota base ou host)
    try:
        t_parsed = urlparse(target_url)
        e_parsed = urlparse(entry.url)
        if (
            t_parsed.netloc
            and e_parsed.netloc
            and t_parsed.netloc == e_parsed.netloc
            and t_parsed.path.rstrip("/") == e_parsed.path.rstrip("/")
        ):
            return True
    except Exception:
        pass

    return False


class GotoActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.url:
            raise ValueError(f"Passo {index}: 'goto' requer 'url'")
        timeout = step.timeout
        if timeout is None and ctx.agent and hasattr(ctx.agent, "config"):
            timeout = ctx.agent.config.browser.timeout_ms
        await driver.goto(step.url, timeout=timeout or 30000)
        if hasattr(driver, "wait_until_ready"):
            await driver.wait_until_ready()

        # Inspeção de telemetria do console e falhas de rede (UXS-45)
        telemetry = getattr(driver, "telemetry", None)
        if not telemetry and hasattr(driver, "session") and driver.session:
            telemetry = getattr(driver.session, "telemetry", None)

        from uxsentinel.browser.telemetry import BrowserTelemetryCollector

        if not isinstance(telemetry, BrowserTelemetryCollector):
            return

        critical_reasons: list[str] = []

        # 1. Avalia erros do console (JS runtime e pageerror)
        console_errors = telemetry.get_errors()
        for err in console_errors:
            err_text = err.text or ""
            if _is_ignorable_noise(err_text, err.location):
                continue
            if _is_critical_console_log(err_text):
                loc_info = f" ({err.location})" if err.location else ""
                critical_reasons.append(f"Exceção JS: {err_text}{loc_info}")

        # 2. Avalia falhas de rede (HTTP 5xx ou falha de conexão na página principal)
        network_failures = getattr(telemetry, "network_failures", [])
        for net in network_failures:
            if _is_critical_network_failure(net, step.url):
                status_info = f" [HTTP {net.status}]" if net.status else ""
                critical_reasons.append(f"Falha de rede{status_info} ao acessar {net.url}: {net.error_text}")

        if not critical_reasons:
            return

        # Cláusula de exceções do cenário e do passo
        combined_exceptions: ScenarioExceptions | None = ctx.scenario_exceptions or (
            ctx.scenario.exceptions if ctx.scenario else None
        )
        if step.exceptions:
            combined_exceptions = (
                combined_exceptions.merge(step.exceptions) if combined_exceptions else step.exceptions
            )

        # Filtra motivos permitidos por exceções
        filtered_reasons: list[str] = []
        for reason in critical_reasons:
            candidate_issue = Issue(
                categoria=IssueCategory.OUTRO,
                severidade=IssueSeverity.BLOQUEANTE,
                descricao=reason,
                evaluator="console_checker",
            )
            if combined_exceptions and combined_exceptions.matches_issue(candidate_issue):
                continue
            filtered_reasons.append(reason)

        if not filtered_reasons:
            return

        # Emissão de mensagem no terminal Rich
        details_str = " | ".join(filtered_reasons)
        ctx.console.print(
            f"    [bold red]❌ ERRO CRÍTICO NO CONSOLE AO ABRIR A PÁGINA:[/bold red] {details_str}"
        )

        # Captura screenshot da página de erro
        report = ctx.report
        out_dir = ctx.out_dir
        current_viewport = ctx.current_viewport
        clean_vp = (
            current_viewport.name.replace(":", "_").replace(" ", "_")
            if (ctx.multi_viewport and current_viewport)
            else (current_viewport.name if current_viewport else None)
        )

        screenshot_name = (
            f"{report.scenario_id}_{clean_vp}_goto_console_error.png"
            if clean_vp
            else f"{report.scenario_id}_goto_console_error.png"
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
            ctx.console.print(
                f"    [dim]⚠️ Não foi possível capturar screenshot de erro de console: {ss_exc}[/dim]"
            )

        # Cria issues e CheckpointResult de erro
        vp_label = current_viewport.label if current_viewport else None
        issues_list: list[Issue] = []
        for r in filtered_reasons:
            issues_list.append(
                Issue(
                    categoria=IssueCategory.OUTRO,
                    severidade=IssueSeverity.BLOQUEANTE,
                    descricao=f"Erro crítico no console ao abrir '{step.url}': {r}",
                    sugestao_correcao="Inspecione os scripts front-end ou a integridade dos serviços HTTP no momento do carregamento inicial.",
                    elemento_alvo=step.url,
                    viewport=vp_label,
                    evaluator="console_checker",
                )
            )

        cp = CheckpointResult(
            name="goto_console_error",
            description=f"Validação de integridade do console e rede ao abrir {step.url}",
            expected_behavior="A página deve carregar sem exceções críticas de JavaScript ou falhas HTTP 5xx.",
            screenshot_path=screenshot_saved,
            status="erro_execucao",
            issues=issues_list,
            viewport=vp_label,
        )
        report.checkpoints.append(cp)


class SetViewportActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        driver = ctx.driver
        val = step.value or "desktop"
        vp_custom = parse_viewport_spec(val)
        if hasattr(driver, "set_viewport"):
            await driver.set_viewport(vp_custom.width, vp_custom.height)
        elif hasattr(driver, "page") and hasattr(driver.page, "set_viewport_size"):
            await driver.page.set_viewport_size({"width": vp_custom.width, "height": vp_custom.height})
        ctx.console.print(f"    [dim]Viewport alterada para {vp_custom.label}[/dim]")


class ScrollActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        driver = ctx.driver
        direction = step.value or "down"
        await driver.scroll(direction=direction)


class HoverActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.selector:
            raise ValueError(f"Passo {index}: 'hover' requer 'selector'")
        desc = step.description or f"hover {step.selector}"
        await driver.hover(
            step.selector,
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )


class DragAndDropActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        source = step.selector
        target = step.target or step.value
        if not source or not target:
            raise ValueError(
                f"Passo {index}: 'drag_and_drop' requer 'selector' (origem) e 'target'/'value' (destino)"
            )
        timeout = step.timeout or 10000
        if hasattr(driver, "drag_and_drop"):
            await driver.drag_and_drop(source, target, timeout=timeout)
        elif hasattr(driver, "page") and hasattr(driver.page, "drag_and_drop"):
            await driver.page.drag_and_drop(source, target, timeout=timeout)
        else:
            raise NotImplementedError("Driver não suporta 'drag_and_drop'")


class KeyboardActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.value:
            raise ValueError(f"Passo {index}: 'press' requer 'value' com o nome da tecla")
        await driver.press(step.value)


class WaitUntilReadyActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        driver = ctx.driver
        await driver.wait_until_ready(timeout=step.timeout or 15000)


class WaitModalActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        driver = ctx.driver
        modal_opened = await driver.wait_for_modal(timeout=step.timeout or 10000)
        if not modal_opened:
            ctx.console.print("    [yellow]⚠️ Modal não detectado após timeout.[/yellow]")


class WaitModalCloseActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        driver = ctx.driver
        modal_closed = await driver.wait_modal_close(timeout=step.timeout or 10000)
        if not modal_closed:
            ctx.console.print(
                "    [yellow]⚠️ Modal não foi fechado (ou backdrop permaneceu) após timeout.[/yellow]"
            )


class PauseActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        duration = int(step.value or 2) if step.value and step.value.isdigit() else 2
        await asyncio.sleep(duration)
