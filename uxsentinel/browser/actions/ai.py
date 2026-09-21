from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from uxsentinel.browser.actions.context import ActionContext, BaseActionHandler
from uxsentinel.core.models import (
    CheckpointResult,
    Issue,
    IssueCategory,
    SemanticStepResult,
    SemanticStrategy,
)

if TYPE_CHECKING:
    pass


class AiClickActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        report = ctx.report

        target = step.ai_click or step.target or step.selector or ""
        if not target:
            raise ValueError(f"Passo {index}: 'ai_click' requer alvo descritivo em linguagem natural")
        desc = step.description or f"ai_click {target}"
        sem_res = await driver.ai_click(
            target=target,
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )
        report.semantic_steps.append(sem_res)
        strat_label = "Acessibilidade" if sem_res.strategy == SemanticStrategy.ACCESSIBILITY else "Visão LMM"
        loc_label = sem_res.resolved_selector or (
            f"coords {sem_res.coordinates}" if sem_res.coordinates else "ok"
        )
        ctx.console.print(f"    [green]✔ Alvo clicado via {strat_label}:[/green] [dim]{loc_label}[/dim]")


class AiFillActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        report = ctx.report

        target = step.ai_fill or step.target or step.selector or ""
        if not target:
            raise ValueError(f"Passo {index}: 'ai_fill' requer alvo descritivo em linguagem natural")
        val = step.value or ""
        desc = step.description or f"ai_fill {target}"
        sem_res = await driver.ai_fill(
            target=target,
            value=val,
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )
        report.semantic_steps.append(sem_res)
        strat_label = "Acessibilidade" if sem_res.strategy == SemanticStrategy.ACCESSIBILITY else "Visão LMM"
        loc_label = sem_res.resolved_selector or (
            f"coords {sem_res.coordinates}" if sem_res.coordinates else "ok"
        )
        ctx.console.print(f"    [green]✔ Campo preenchido via {strat_label}:[/green] [dim]{loc_label}[/dim]")


class AiAssertActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        report = ctx.report
        out_dir = ctx.out_dir
        current_viewport = ctx.current_viewport

        assertion = step.ai_assert or step.target or step.expected_behavior or ""
        if not assertion:
            raise ValueError(f"Passo {index}: 'ai_assert' requer texto da asserção declarativa")
        desc = step.description or f"ai_assert {assertion}"
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
            ctx.console.print(
                f"    [bold green]✅ Asserção Cognitiva Aprovada:[/bold green] [dim]{assert_res.reasoning}[/dim]"
            )
        else:
            ctx.console.print(
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


class AiActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        report = ctx.report

        instruction = step.ai_action or step.target or step.description or ""
        if not instruction:
            raise ValueError(f"Passo {index}: 'ai_action' requer instrução em linguagem natural")
        desc = step.description or f"ai_action {instruction}"
        sem_res = await driver.ai_action(
            instruction=instruction,
            value=step.value,
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )
        report.semantic_steps.append(sem_res)
        ctx.console.print(
            f"    [green]✔ Ação semântica executada:[/green] [dim]{sem_res.reasoning or 'sucesso'}[/dim]"
        )
