from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from playwright.async_api import Page

from uxsentinel.browser.dom_validator import DOMAnomaly, DOMValidator
from uxsentinel.core.models import HealingEvent, Issue

if TYPE_CHECKING:
    from uxsentinel.browser.healing import SelectorHealer
    from uxsentinel.browser.semantic_actions import (
        SemanticActionExecutor,
        SemanticAssertResult,
    )


class BaseDriver(ABC):
    """Interface base para drivers de interação com o navegador e frameworks."""

    def __init__(self, page: Page, highlight_clicks: bool = True):
        self.page = page
        self.highlight_clicks = highlight_clicks
        self.healer: SelectorHealer | None = None
        self.healing_events: list[HealingEvent] = []
        self.semantic_executor: SemanticActionExecutor | None = None
        self.video_path: str | None = None
        self.session: Any | None = None
        self.dom_validator: DOMValidator = DOMValidator()
        self.telemetry: Any | None = None

    async def _highlight_element(self, selector: str) -> None:
        """Aplica halo visual no elemento antes da ação."""
        if not self.highlight_clicks:
            return
        with contextlib.suppress(Exception):
            await self.page.evaluate(
                """
                (sel) => {
                    const el = document.querySelector(sel);
                    if (el && window.__uxsentinel_highlight_elem) {
                        window.__uxsentinel_highlight_elem(el);
                    }
                }
            """,
                selector,
            )

    async def _show_click_effect(self, x: float, y: float) -> None:
        """Gera efeito de onda no ponto do clique."""
        if not self.highlight_clicks:
            return
        with contextlib.suppress(Exception):
            await self.page.evaluate(
                """
                ({x, y}) => {
                    if (window.__uxsentinel_show_click) {
                        window.__uxsentinel_show_click(x, y);
                    }
                }
            """,
                {"x": x, "y": y},
            )

    async def set_viewport(self, width: int, height: int) -> None:
        """Ajusta dinamicamente as dimensões da viewport da página atual."""
        if hasattr(self.page, "set_viewport_size"):
            await self.page.set_viewport_size({"width": width, "height": height})

    async def goto(self, url: str, timeout: int = 30000) -> None:
        await self.page.goto(url, timeout=timeout)
        await self.wait_until_ready()
        if self.telemetry:
            with contextlib.suppress(Exception):
                await self.telemetry.capture_performance_metrics(self.page)

    async def click(
        self,
        selector: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> None:
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._highlight_element(selector)

            # Pega a posição do elemento para o efeito de ripple
            try:
                box = await self.page.locator(selector).first.bounding_box()
                if box:
                    await self._show_click_effect(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            except Exception:
                pass

            await self.page.click(selector, timeout=timeout)
            await self.wait_until_ready()
        except Exception as exc:
            if self.healer and self.healer.enabled:
                event = await self.healer.heal_action(
                    page=self.page,
                    action="click",
                    selector=selector,
                    timeout=timeout,
                    description=description,
                    step_index=step_index,
                    highlight_callback=self._show_click_effect,
                )
                if event:
                    self.healing_events.append(event)
                    await self.wait_until_ready()
                    return
            raise exc

    async def fill(
        self,
        selector: str,
        value: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> None:
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._highlight_element(selector)
            await self.page.fill(selector, value, timeout=timeout)
        except Exception as exc:
            if self.healer and self.healer.enabled:
                event = await self.healer.heal_action(
                    page=self.page,
                    action="fill",
                    selector=selector,
                    value=value,
                    timeout=timeout,
                    description=description,
                    step_index=step_index,
                    highlight_callback=self._show_click_effect,
                )
                if event:
                    self.healing_events.append(event)
                    return
            raise exc

    async def select_option(
        self,
        selector: str,
        value: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> None:
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._highlight_element(selector)
            await self.page.select_option(selector, value, timeout=timeout)
            await self.wait_until_ready()
        except Exception as exc:
            if self.healer and self.healer.enabled:
                event = await self.healer.heal_action(
                    page=self.page,
                    action="select",
                    selector=selector,
                    value=value,
                    timeout=timeout,
                    description=description,
                    step_index=step_index,
                )
                if event:
                    self.healing_events.append(event)
                    await self.wait_until_ready()
                    return
            raise exc

    async def press(self, key: str) -> None:
        await self.page.keyboard.press(key)
        await self.wait_until_ready()

    async def hover(
        self,
        selector: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> None:
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._highlight_element(selector)
            await self.page.hover(selector, timeout=timeout)
        except Exception as exc:
            if self.healer and self.healer.enabled:
                event = await self.healer.heal_action(
                    page=self.page,
                    action="hover",
                    selector=selector,
                    timeout=timeout,
                    description=description,
                    step_index=step_index,
                )
                if event:
                    self.healing_events.append(event)
                    return
            raise exc

    async def scroll(self, direction: str = "down", amount: int = 400) -> None:
        delta = amount if direction == "down" else -amount
        await self.page.mouse.wheel(0, delta)
        await self.page.wait_for_timeout(300)

    async def get_clean_dom_text(self) -> str:
        """Extrai o texto visível da página, descartando ruído de scripts/estilos."""
        try:
            return await self.page.evaluate("""
                () => {
                    const clone = document.body.cloneNode(true);
                    const removeSelectors = ['script', 'style', 'noscript', 'svg', 'iframe'];
                    removeSelectors.forEach(s => clone.querySelectorAll(s).forEach(e => e.remove()));
                    return clone.innerText || '';
                }
            """)
        except Exception:
            return ""

    async def validate_dom(self) -> list[DOMAnomaly]:
        """Executa a rotina determinística de validação do DOM para detecção de anomalias geométricas."""
        return await self.dom_validator.inspect_dom(self.page)

    async def get_dom_issues(self, viewport: str | None = None) -> list[Issue]:
        """Executa a validação determinística do DOM e converte em inconsistências estruturadas."""
        anomalies = await self.validate_dom()
        return self.dom_validator.anomalies_to_issues(anomalies, viewport=viewport)

    @abstractmethod
    async def wait_until_ready(self, timeout: int = 10000) -> None:
        """Aguarda a aplicação e componentes terminarem carregamentos assíncronos."""
        pass

    @abstractmethod
    async def wait_for_modal(self, timeout: int = 10000) -> bool:
        """Aguarda abertura e estabilização de janela modal."""
        pass

    @abstractmethod
    async def wait_modal_close(self, timeout: int = 10000) -> bool:
        """Aguarda fechamento e desaparecimento do modal."""
        pass

    def _get_semantic_executor(self) -> SemanticActionExecutor:
        """Obtém ou instancia o executor de ações semânticas."""
        if self.semantic_executor is None:
            from uxsentinel.browser.semantic_actions import SemanticActionExecutor

            vision_client = self.healer.vision_client if self.healer else None
            self.semantic_executor = SemanticActionExecutor(
                page=self.page,
                vision_client=vision_client,
                highlight_clicks=self.highlight_clicks,
            )
        return self.semantic_executor

    async def ai_click(
        self,
        target: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> Any:
        """Executa clique semântico guiado por linguagem natural."""
        executor = self._get_semantic_executor()
        res = await executor.execute_ai_click(
            target=target,
            timeout=timeout,
            description=description,
            step_index=step_index,
        )
        await self.wait_until_ready()
        return res

    async def ai_fill(
        self,
        target: str,
        value: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> Any:
        """Executa preenchimento semântico guiado por linguagem natural."""
        executor = self._get_semantic_executor()
        res = await executor.execute_ai_fill(
            target=target,
            value=value,
            timeout=timeout,
            description=description,
            step_index=step_index,
        )
        await self.wait_until_ready()
        return res

    async def ai_assert(
        self,
        assertion: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> SemanticAssertResult:
        """Executa asserção declarativa cognitiva visual via LMM."""
        executor = self._get_semantic_executor()
        return await executor.execute_ai_assert(
            assertion=assertion,
            timeout=timeout,
            description=description,
            step_index=step_index,
        )

    async def ai_action(
        self,
        instruction: str,
        value: str | None = None,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> Any:
        """Executa ação semântica genérica em linguagem natural."""
        executor = self._get_semantic_executor()
        res = await executor.execute_ai_action(
            instruction=instruction,
            value=value,
            timeout=timeout,
            description=description,
            step_index=step_index,
        )
        await self.wait_until_ready()
        return res
