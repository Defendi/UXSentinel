from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from uxsentinel.browser.actions.context import ActionContext, BaseActionHandler

if TYPE_CHECKING:
    pass


class ClickActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.selector:
            raise ValueError(f"Passo {index}: 'click' requer 'selector'")
        desc = step.description or f"click {step.selector}"
        await driver.click(
            step.selector,
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )


class FillActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.selector:
            raise ValueError(f"Passo {index}: 'fill' requer 'selector'")
        desc = step.description or f"fill {step.selector}"
        await driver.fill(
            step.selector,
            step.value or "",
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )


class TypeActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.selector:
            raise ValueError(f"Passo {index}: 'type' requer 'selector'")
        desc = step.description or f"type {step.selector}"
        await driver.type_text(
            step.selector,
            step.value or "",
            delay_ms=40,
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )


class ClearActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.selector:
            raise ValueError(f"Passo {index}: 'clear' requer 'selector'")
        desc = step.description or f"clear {step.selector}"
        await driver.clear(
            step.selector,
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )


class SelectActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        action = step.action.lower().strip()
        if not step.selector:
            raise ValueError(f"Passo {index}: '{action}' requer 'selector'")
        desc = step.description or f"{action} {step.selector}"
        await driver.select_option(
            step.selector,
            step.value or "",
            timeout=step.timeout or 10000,
            description=desc,
            step_index=index,
        )


class UploadFileActionHandler(BaseActionHandler):
    async def execute(self, ctx: ActionContext) -> None:
        step = ctx.step
        index = ctx.step_index
        driver = ctx.driver
        if not step.selector:
            raise ValueError(f"Passo {index}: 'upload_file' requer 'selector'")
        file_path_str = step.value or step.target
        if not file_path_str:
            raise ValueError(f"Passo {index}: 'upload_file' requer caminho do arquivo em 'value' ou 'target'")
        file_path = Path(file_path_str)
        timeout = step.timeout or 10000
        if hasattr(driver, "set_input_files"):
            await driver.set_input_files(step.selector, str(file_path), timeout=timeout)
        elif hasattr(driver, "page") and hasattr(driver.page, "set_input_files"):
            await driver.page.set_input_files(step.selector, str(file_path), timeout=timeout)
        else:
            raise NotImplementedError("Driver não suporta upload de arquivos")
        if hasattr(driver, "wait_until_ready"):
            await driver.wait_until_ready()
