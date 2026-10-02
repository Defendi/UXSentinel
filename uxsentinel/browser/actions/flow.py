from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from uxsentinel.browser.actions.context import ActionContext, BaseActionHandler

if TYPE_CHECKING:
    from uxsentinel.browser.drivers.base_driver import BaseDriver
    from uxsentinel.core.models import StepAction


async def _awaitable_or_val(val: Any) -> Any:
    if inspect.isawaitable(val):
        return await val
    return val


async def _is_element_present(page: Any, selector: str) -> bool:
    try:
        loc = await _awaitable_or_val(page.locator(selector))
        count = await _awaitable_or_val(loc.count())
        return int(count) > 0
    except Exception:
        return False


async def _is_element_visible(page: Any, selector: str) -> bool:
    try:
        loc = await _awaitable_or_val(page.locator(selector))
        count = await _awaitable_or_val(loc.count())
        if int(count) == 0:
            return False
        first_el = loc.first if hasattr(loc, "first") else loc
        first_el = await _awaitable_or_val(first_el)
        return bool(await _awaitable_or_val(first_el.is_visible()))
    except Exception:
        return False


async def _is_text_visible(page: Any, text: str, selector: str | None = None) -> bool:
    try:
        if selector and hasattr(page, "locator"):
            loc = await _awaitable_or_val(page.locator(selector))
            if hasattr(loc, "get_by_text"):
                text_loc = await _awaitable_or_val(loc.get_by_text(text))
                count = await _awaitable_or_val(text_loc.count())
                if int(count) > 0:
                    first = text_loc.first if hasattr(text_loc, "first") else text_loc
                    first = await _awaitable_or_val(first)
                    if bool(await _awaitable_or_val(first.is_visible())):
                        return True
            if hasattr(loc, "first") and hasattr(loc.first, "inner_text"):
                inner = await _awaitable_or_val(loc.first.inner_text())
                if text in str(inner):
                    return True

        if hasattr(page, "get_by_text"):
            text_loc = await _awaitable_or_val(page.get_by_text(text))
            count = await _awaitable_or_val(text_loc.count())
            if int(count) > 0:
                first = text_loc.first if hasattr(text_loc, "first") else text_loc
                first = await _awaitable_or_val(first)
                return bool(await _awaitable_or_val(first.is_visible()))

        if hasattr(page, "content"):
            content = await _awaitable_or_val(page.content())
            return text in str(content)
        return False
    except Exception:
        return False


def _check_url_contains(page: Any, expected: str) -> bool:
    current_url = getattr(page, "url", "")
    if callable(current_url):
        current_url = current_url()
    return str(expected) in str(current_url or "")


def _check_url_equals(page: Any, expected: str) -> bool:
    current_url = getattr(page, "url", "")
    if callable(current_url):
        current_url = current_url()
    return str(current_url or "").strip() == str(expected).strip()


async def _eval_js(page: Any, expr: str) -> bool:
    try:
        if hasattr(page, "evaluate"):
            res = await _awaitable_or_val(page.evaluate(expr))
            return bool(res)
        return False
    except Exception:
        return False


async def _eval_single_condition(
    cond_type: str,
    arg: Any,
    driver: BaseDriver,
    step: StepAction | None = None,
) -> bool:
    page = getattr(driver, "page", None)
    if page is None:
        return False

    c_norm = cond_type.lower().strip()

    # Presença do elemento no DOM
    if c_norm in ("element_present", "element_exists", "seletor_presente", "presente"):
        selector = arg or (step.selector if step else None) or (step.target if step else None)
        if not selector:
            return False
        return await _is_element_present(page, str(selector))

    # Elemento visível
    if c_norm in ("element_visible", "is_visible", "elemento_visivel", "visivel"):
        selector = arg or (step.selector if step else None) or (step.target if step else None)
        if not selector:
            return False
        return await _is_element_visible(page, str(selector))

    # Elemento ausente do DOM
    if c_norm in ("element_not_present", "element_absent", "seletor_ausente", "ausente"):
        selector = arg or (step.selector if step else None) or (step.target if step else None)
        if not selector:
            return True
        return not (await _is_element_present(page, str(selector)))

    # Elemento oculto
    if c_norm in ("element_not_visible", "element_hidden", "elemento_oculto", "oculto"):
        selector = arg or (step.selector if step else None) or (step.target if step else None)
        if not selector:
            return True
        return not (await _is_element_visible(page, str(selector)))

    # Texto visível
    if c_norm in ("text_visible", "has_text", "texto_visivel", "contem_texto"):
        text = arg or (step.value if step else None) or (step.target if step else None)
        if not text:
            return False
        sel = step.selector if step else None
        return await _is_text_visible(page, str(text), selector=sel)

    # Texto não visível
    if c_norm in ("text_not_visible", "texto_nao_visivel"):
        text = arg or (step.value if step else None) or (step.target if step else None)
        if not text:
            return True
        sel = step.selector if step else None
        return not (await _is_text_visible(page, str(text), selector=sel))

    # URL contém
    if c_norm in ("url_contains", "url_contem", "url_matches"):
        url_part = (
            arg
            or (step.url if step else None)
            or (step.value if step else None)
            or (step.target if step else None)
        )
        if not url_part:
            return False
        return _check_url_contains(page, str(url_part))

    # URL exata
    if c_norm in ("url_equals", "url_exata"):
        target_url = (
            arg
            or (step.url if step else None)
            or (step.value if step else None)
            or (step.target if step else None)
        )
        if not target_url:
            return False
        return _check_url_equals(page, str(target_url))

    # Expressão JavaScript
    if c_norm in ("js_expression", "javascript", "eval", "js"):
        expr = arg or (step.value if step else None)
        if not expr:
            return False
        return await _eval_js(page, str(expr))

    return False


async def evaluate_condition(
    condition: Any,
    driver: BaseDriver,
    step: StepAction | None = None,
) -> bool:
    """Avalia uma especificação de condição contra o navegador/driver."""
    if condition is None:
        return True

    if isinstance(condition, bool):
        return condition

    if isinstance(condition, str):
        c_str = condition.strip()
        c_low = c_str.lower()
        if c_low in ("true", "1", "yes", "sim"):
            return True
        if c_low in ("false", "0", "no", "nao", "não"):
            return False

        # Verifica se começa com um tipo de condição conhecido seguido por argumento
        parts = c_str.split(None, 1)
        first_token = parts[0].lower()
        known = {
            "element_present",
            "element_visible",
            "element_not_present",
            "element_not_visible",
            "text_visible",
            "text_not_visible",
            "url_contains",
            "url_equals",
            "javascript",
            "js",
        }
        if first_token in known:
            arg = parts[1] if len(parts) > 1 else None
            return await _eval_single_condition(first_token, arg, driver, step)

        if c_low in known:
            return await _eval_single_condition(c_low, None, driver, step)

        # Caso contrário, avalia como expressão JavaScript
        return await _eval_single_condition("javascript", c_str, driver, step)

    if isinstance(condition, dict):
        if "not" in condition:
            return not await evaluate_condition(condition["not"], driver, step)

        cond_type = condition.get("type") or condition.get("condition") or condition.get("condicao")
        if cond_type:
            arg = (
                condition.get("selector")
                or condition.get("value")
                or condition.get("url")
                or condition.get("text")
                or condition.get("target")
                or condition.get("arg")
            )
            return await _eval_single_condition(str(cond_type), arg, driver, step)

        for k, v in condition.items():
            return await _eval_single_condition(k, v, driver, step)

    return False


async def evaluate_step_condition(step: StepAction, driver: BaseDriver) -> bool:
    """Verifica todas as possíveis condições declaradas no passo."""
    if step.condition is not None:
        return await evaluate_condition(step.condition, driver, step)

    for attr in ("element_present", "element_visible", "text_visible", "url_contains", "js_expression"):
        val = getattr(step, attr, None)
        if val is not None:
            return await _eval_single_condition(attr, val, driver, step)

    return True


class JumpToActionHandler(BaseActionHandler):
    """Handler para a ação 'jump_to' que redireciona incondicionalmente o ponteiro de passos."""

    async def execute(self, ctx: ActionContext) -> None:
        target = ctx.step.target or ctx.step.then_jump_to
        if not target:
            raise ValueError(
                f"Passo {ctx.step_index} ('jump_to') requer a especificação do atributo 'target'."
            )
        ctx.next_step_id = str(target).strip()
        ctx.console.print(
            f"    [bold cyan]↪️ Desvio incondicional (jump_to):[/bold cyan] redirecionando execução para o passo '[bold]{ctx.next_step_id}[/bold]'"
        )


class BranchActionHandler(BaseActionHandler):
    """Handler para a ação 'branch' que avalia condições em runtime e decide o próximo passo."""

    async def execute(self, ctx: ActionContext) -> None:
        condition_result = await evaluate_step_condition(ctx.step, ctx.driver)
        then_target = ctx.step.then_jump_to or ctx.step.target
        else_target = ctx.step.else_jump_to

        if condition_result:
            if then_target:
                ctx.next_step_id = str(then_target).strip()
                ctx.console.print(
                    f"    [bold green]↪️ Desvio condicional (branch - VERDADEIRO):[/bold green] saltando para '[bold]{ctx.next_step_id}[/bold]'"
                )
            else:
                ctx.console.print(
                    "    [dim]↪️ Desvio condicional (branch - VERDADEIRO): nenhum then_jump_to informado, seguindo fluxo sequencial.[/dim]"
                )
        else:
            if else_target:
                ctx.next_step_id = str(else_target).strip()
                ctx.console.print(
                    f"    [bold yellow]↪️ Desvio condicional (branch - FALSO):[/bold yellow] saltando para '[bold]{ctx.next_step_id}[/bold]'"
                )
            else:
                ctx.console.print(
                    "    [dim]↪️ Desvio condicional (branch - FALSO): nenhum else_jump_to informado, seguindo fluxo sequencial.[/dim]"
                )
