from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from uxsentinel.browser.actions.context import ActionContext, BaseActionHandler
from uxsentinel.core.models import (
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
)

if TYPE_CHECKING:
    pass


class AssertRequiredActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        action = step.action.lower().strip()
        report = ctx.report
        out_dir = ctx.out_dir
        current_viewport = ctx.current_viewport

        targets = [step.selector] if step.selector else (step.criteria or [])
        if not targets:
            raise ValueError(f"Passo {index}: '{action}' requer 'selector' ou lista em 'criteria'")
        for tgt in targets:
            is_req, reason = await driver.check_field_required(tgt, timeout=step.timeout or 5000)
            if not is_req:
                ctx.console.print(f"    [bold red]❌ FALHA EM CAMPO OBRIGATÓRIO:[/bold red] [{tgt}] {reason}")
                issue = Issue(
                    categoria=IssueCategory.REGRA_NEGOCIO,
                    severidade=IssueSeverity.ALTA,
                    descricao=f"Campo obrigatório não sinalizado adequadamente no seletor '{tgt}'. Motivo: {reason}",
                    sugestao_correcao=f"Adicionar atributo 'required', 'aria-required=\"true\"' ou asterisco (*) no label do campo '{tgt}'.",
                    elemento_alvo=tgt,
                    viewport=current_viewport.label if current_viewport else None,
                    evaluator="assert_required",
                )
                if report.checkpoints:
                    target_cp = report.checkpoints[-1]
                    target_cp.issues.append(issue)
                    target_cp.status = "problemas_encontrados"
                else:
                    screenshot_file = out_dir / f"{report.scenario_id}_required_step_{index}.png"
                    if hasattr(driver, "page") and hasattr(driver.page, "screenshot"):
                        with contextlib.suppress(Exception):
                            await driver.page.screenshot(path=str(screenshot_file), full_page=True)
                    cp = CheckpointResult(
                        name=f"required_step_{index}",
                        description=f"Validação de obrigatoriedade do campo: {tgt}",
                        expected_behavior=f"O campo '{tgt}' deve ser obrigatório",
                        screenshot_path=str(screenshot_file) if screenshot_file.is_file() else None,
                        status="problemas_encontrados",
                        issues=[issue],
                        viewport=current_viewport.label if current_viewport else None,
                    )
                    report.checkpoints.append(cp)
            else:
                ctx.console.print(
                    f"    [bold green]✅ Campo obrigatório validado:[/bold green] [{tgt}] [dim]{reason}[/dim]"
                )


class AssertInvalidActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        action = step.action.lower().strip()
        report = ctx.report
        out_dir = ctx.out_dir
        current_viewport = ctx.current_viewport

        if not step.selector:
            raise ValueError(f"Passo {index}: '{action}' requer 'selector'")
        is_inv, reason = await driver.check_field_invalid(step.selector, timeout=step.timeout or 5000)
        if not is_inv:
            ctx.console.print(
                f"    [bold red]❌ CAMPO DEVERIA ESTAR EM ESTADO DE ERRO:[/bold red] [{step.selector}] {reason}"
            )
            issue = Issue(
                categoria=IssueCategory.REGRA_NEGOCIO,
                severidade=IssueSeverity.ALTA,
                descricao=f"Campo deveria exibir validação de erro após submissão: seletor '{step.selector}'. Motivo: {reason}",
                sugestao_correcao=f"Garantir que a tentativa de submissão sem preenchimento ative ':invalid' ou exiba alerta em '{step.selector}'.",
                elemento_alvo=step.selector,
                viewport=current_viewport.label if current_viewport else None,
                evaluator="assert_invalid",
            )
            if report.checkpoints:
                target_cp = report.checkpoints[-1]
                target_cp.issues.append(issue)
                target_cp.status = "problemas_encontrados"
            else:
                screenshot_file = out_dir / f"{report.scenario_id}_invalid_step_{index}.png"
                if hasattr(driver, "page") and hasattr(driver.page, "screenshot"):
                    with contextlib.suppress(Exception):
                        await driver.page.screenshot(path=str(screenshot_file), full_page=True)
                cp = CheckpointResult(
                    name=f"invalid_step_{index}",
                    description=f"Validação de estado de erro do campo: {step.selector}",
                    expected_behavior=f"O campo '{step.selector}' deve acusar erro",
                    screenshot_path=str(screenshot_file) if screenshot_file.is_file() else None,
                    status="problemas_encontrados",
                    issues=[issue],
                    viewport=current_viewport.label if current_viewport else None,
                )
                report.checkpoints.append(cp)
        else:
            ctx.console.print(
                f"    [bold green]✅ Validação de erro confirmada no campo:[/bold green] [{step.selector}] [dim]{reason}[/dim]"
            )


class AssertReadonlyActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        action = step.action.lower().strip()
        report = ctx.report
        out_dir = ctx.out_dir
        current_viewport = ctx.current_viewport

        if not step.selector:
            raise ValueError(f"Passo {index}: '{action}' requer 'selector'")

        timeout = step.timeout or 5000
        await driver.page.wait_for_selector(step.selector, timeout=timeout)
        result = await driver.page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return { readonly: false, reason: "Elemento não localizado" };
                if (el.readOnly || el.disabled) {
                    return { readonly: true, reason: el.disabled ? "Atributo 'disabled' presente" : "Atributo 'readonly' presente" };
                }
                if (el.getAttribute("aria-readonly") === "true" || el.getAttribute("aria-disabled") === "true") {
                    return { readonly: true, reason: "Atributo ARIA readonly/disabled ativo" };
                }
                const classes = Array.from(el.classList || []);
                if (classes.some(c => ["readonly", "disabled", "o_readonly_modifier"].includes(c))) {
                    return { readonly: true, reason: "Classe CSS indicando somente-leitura presente" };
                }
                return { readonly: false, reason: "Campo não possui atributos ou classes de somente-leitura" };
            }""",
            step.selector,
        )
        is_readonly = bool(result.get("readonly"))
        reason = str(result.get("reason"))

        if not is_readonly:
            ctx.console.print(
                f"    [bold red]❌ CAMPO DEVERIA SER SOMENTE LEITURA:[/bold red] [{step.selector}] {reason}"
            )
            issue = Issue(
                categoria=IssueCategory.REGRA_NEGOCIO,
                severidade=IssueSeverity.ALTA,
                descricao=f"Campo deveria ser somente leitura: seletor '{step.selector}'. Motivo: {reason}",
                sugestao_correcao=f"Configurar atributo 'readonly' ou 'disabled' em '{step.selector}'.",
                elemento_alvo=step.selector,
                viewport=current_viewport.label if current_viewport else None,
                evaluator="assert_readonly",
            )
            if report.checkpoints:
                target_cp = report.checkpoints[-1]
                target_cp.issues.append(issue)
                target_cp.status = "problemas_encontrados"
            else:
                screenshot_file = out_dir / f"{report.scenario_id}_readonly_step_{index}.png"
                if hasattr(driver, "page") and hasattr(driver.page, "screenshot"):
                    with contextlib.suppress(Exception):
                        await driver.page.screenshot(path=str(screenshot_file), full_page=True)
                cp = CheckpointResult(
                    name=f"readonly_step_{index}",
                    description=f"Validação de somente leitura do campo: {step.selector}",
                    expected_behavior=f"O campo '{step.selector}' deve ser somente leitura",
                    screenshot_path=str(screenshot_file) if screenshot_file.is_file() else None,
                    status="problemas_encontrados",
                    issues=[issue],
                    viewport=current_viewport.label if current_viewport else None,
                )
                report.checkpoints.append(cp)
        else:
            ctx.console.print(
                f"    [bold green]✅ Validação de somente leitura confirmada:[/bold green] [{step.selector}] [dim]{reason}[/dim]"
            )


class AssertOptionsActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        action = step.action.lower().strip()
        report = ctx.report
        out_dir = ctx.out_dir
        current_viewport = ctx.current_viewport

        if not step.selector:
            raise ValueError(f"Passo {index}: '{action}' requer 'selector'")
        expected_opts = step.criteria or ([step.value] if step.value else [])
        if not expected_opts:
            raise ValueError(f"Passo {index}: '{action}' requer opções esperadas em 'criteria' ou 'value'")

        timeout = step.timeout or 5000
        await driver.page.wait_for_selector(step.selector, timeout=timeout)
        options = await driver.page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return [];
                if (el.tagName.toLowerCase() === 'select') {
                    return Array.from(el.options).map(o => o.text.trim());
                }
                const items = el.querySelectorAll("option, [role='option'], .dropdown-item, li");
                return Array.from(items).map(i => i.innerText.trim());
            }""",
            step.selector,
        )

        missing = [opt for opt in expected_opts if opt not in options]
        if missing:
            ctx.console.print(
                f"    [bold red]❌ OPÇÕES ESPERADAS AUSENTES:[/bold red] [{step.selector}] Ausentes: {missing}"
            )
            issue = Issue(
                categoria=IssueCategory.REGRA_NEGOCIO,
                severidade=IssueSeverity.MEDIA,
                descricao=f"Opções esperadas ausentes no elemento '{step.selector}': {missing}. Encontradas: {options}",
                sugestao_correcao="Verificar se os dados do dropdown foram carregados corretamente.",
                elemento_alvo=step.selector,
                viewport=current_viewport.label if current_viewport else None,
                evaluator="assert_options",
            )
            if report.checkpoints:
                target_cp = report.checkpoints[-1]
                target_cp.issues.append(issue)
                target_cp.status = "problemas_encontrados"
            else:
                screenshot_file = out_dir / f"{report.scenario_id}_options_step_{index}.png"
                if hasattr(driver, "page") and hasattr(driver.page, "screenshot"):
                    with contextlib.suppress(Exception):
                        await driver.page.screenshot(path=str(screenshot_file), full_page=True)
                cp = CheckpointResult(
                    name=f"options_step_{index}",
                    description=f"Validação de opções do seletor: {step.selector}",
                    expected_behavior=f"O elemento deve conter as opções: {expected_opts}",
                    screenshot_path=str(screenshot_file) if screenshot_file.is_file() else None,
                    status="problemas_encontrados",
                    issues=[issue],
                    viewport=current_viewport.label if current_viewport else None,
                )
                report.checkpoints.append(cp)
        else:
            ctx.console.print(
                f"    [bold green]✅ Opções validadas com sucesso:[/bold green] [{step.selector}] [dim]{expected_opts}[/dim]"
            )
