from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from playwright.async_api import Page

from uxsentinel.core.models import HealingEvent

if TYPE_CHECKING:
    from uxsentinel.browser.healing import SelectorHealer


class BaseDriver(ABC):
    """Interface base para drivers de interação com o navegador e frameworks."""

    def __init__(self, page: Page, highlight_clicks: bool = True):
        self.page = page
        self.highlight_clicks = highlight_clicks
        self.healer: SelectorHealer | None = None
        self.healing_events: list[HealingEvent] = []

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

    async def goto(self, url: str, timeout: int = 30000) -> None:
        await self.page.goto(url, timeout=timeout)
        await self.wait_until_ready()

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
