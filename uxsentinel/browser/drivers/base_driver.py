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

    async def clear(
        self,
        selector: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> None:
        """Limpa o conteúdo de um campo de formulário (input ou textarea)."""
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._highlight_element(selector)
            await self.page.fill(selector, "", timeout=timeout)
        except Exception as exc:
            if self.healer and self.healer.enabled:
                event = await self.healer.heal_action(
                    page=self.page,
                    action="fill",
                    selector=selector,
                    value="",
                    timeout=timeout,
                    description=description,
                    step_index=step_index,
                    highlight_callback=self._show_click_effect,
                )
                if event:
                    self.healing_events.append(event)
                    return
            raise exc

    async def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 40,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> None:
        """Digita texto caractere por caractere (com ritmo humano), ideal para campos com máscara e autocompletes."""
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._highlight_element(selector)
            loc = self.page.locator(selector).first
            await loc.focus(timeout=timeout)
            if hasattr(loc, "press_sequentially"):
                await loc.press_sequentially(text, delay=delay_ms, timeout=timeout)
            else:
                await self.page.type(selector, text, delay=delay_ms, timeout=timeout)
            await self.wait_until_ready()
        except Exception as exc:
            if self.healer and self.healer.enabled:
                event = await self.healer.heal_action(
                    page=self.page,
                    action="fill",
                    selector=selector,
                    value=text,
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
        """Seleciona uma opção em um elemento <select> nativo ou em dropdowns customizados de frameworks."""
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            await self._highlight_element(selector)

            # Detecta a tag do elemento para escolher a melhor estratégia
            tag_name = await self.page.evaluate(
                """(sel) => {
                    const el = document.querySelector(sel);
                    return el ? el.tagName.toLowerCase() : '';
                }""",
                selector,
            )

            if tag_name == "select":
                # Tenta selecionar primeiro por label visível e depois por valor/value
                try:
                    await self.page.select_option(selector, label=value, timeout=timeout)
                except Exception:
                    await self.page.select_option(selector, value=value, timeout=timeout)
            else:
                # Dropdown customizado (Bootstrap, Material UI, Odoo OWL, React, Tailwind, Shadcn)
                await self.page.click(selector, timeout=timeout)
                await self.page.wait_for_timeout(250)

                # Procura o item correspondente entre as opções abertas
                option_locators = [
                    f"[role='option']:has-text('{value}')",
                    f".dropdown-item:has-text('{value}')",
                    f".o_dropdown_item:has-text('{value}')",
                    f".o-autocomplete--dropdown-item:has-text('{value}')",
                    f"li:has-text('{value}')",
                    f"text='{value}'",
                ]
                selected = False
                for opt_sel in option_locators:
                    loc = self.page.locator(opt_sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        await loc.first.click(timeout=timeout)
                        selected = True
                        break

                if not selected:
                    # Se for um input de busca (autocomplete), preenche e pressiona Enter
                    if tag_name == "input":
                        await self.page.fill(selector, value, timeout=timeout)
                        await self.page.keyboard.press("Enter")
                    else:
                        raise ValueError(f"Opção '{value}' não encontrada no dropdown '{selector}'")

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

    async def check_field_required(self, selector: str, timeout: int = 5000) -> tuple[bool, str]:
        """Avalia no DOM se o campo é identificado como obrigatório (HTML5, ARIA, classes ou label)."""
        await self.page.wait_for_selector(selector, timeout=timeout)
        result = await self.page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return { required: false, reason: "Elemento não localizado" };

                // 1. Atributo nativo HTML5
                if (el.required) return { required: true, reason: "Atributo HTML5 'required' presente" };

                // 2. Atributo de Acessibilidade W3C ARIA
                if (el.getAttribute("aria-required") === "true") {
                    return { required: true, reason: "Atributo 'aria-required=\"true\"' presente" };
                }

                // 3. Classes de frameworks (Bootstrap, Odoo, custom)
                const classList = Array.from(el.classList || []);
                const requiredClasses = ["required", "is-required", "o_required_modifier", "o_required"];
                const matchedClass = requiredClasses.find(c => classList.includes(c));
                if (matchedClass) {
                    return { required: true, reason: `Classe CSS de obrigatoriedade '.${matchedClass}' presente` };
                }

                // 4. Label associado com indicador de asterisco (*)
                const id = el.id;
                let label = null;
                if (id) {
                    label = document.querySelector(`label[for="${id}"]`);
                }
                if (!label) {
                    label = el.closest("label") || el.closest(".form-group, .o_field_widget, .mb-3")?.querySelector("label");
                }
                if (label) {
                    const labelText = label.innerText || "";
                    if (labelText.includes("*") || label.classList.contains("required") || label.querySelector(".text-danger, .required")) {
                        return { required: true, reason: "Rótulo (<label>) associado possui indicador visual de asterisco (*)" };
                    }
                }

                return { required: false, reason: "Nenhum indicativo de campo obrigatório encontrado (sem 'required', 'aria-required' ou asterisco)" };
            }""",
            selector,
        )
        return bool(result.get("required")), str(result.get("reason"))

    async def check_field_invalid(self, selector: str, timeout: int = 5000) -> tuple[bool, str]:
        """Verifica se o campo está visualmente ou funcionalmente em estado de validação inválida/erro."""
        await self.page.wait_for_selector(selector, timeout=timeout)
        result = await self.page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return { invalid: false, reason: "Elemento não localizado" };

                // 1. Validação nativa HTML5
                if (el.validity && !el.validity.valid) {
                    return { invalid: true, reason: `Validação HTML5 inválida: ${el.validationMessage || 'campo inválido'}` };
                }

                // 2. ARIA invalid
                if (el.getAttribute("aria-invalid") === "true") {
                    return { invalid: true, reason: "Atributo 'aria-invalid=\"true\"' ativo" };
                }

                // 3. Classes de erro
                const classList = Array.from(el.classList || []);
                const invalidClasses = ["is-invalid", "has-error", "border-danger", "o_field_invalid"];
                const matched = invalidClasses.find(c => classList.includes(c));
                if (matched) {
                    return { invalid: true, reason: `Classe CSS de erro '.${matched}' detectada` };
                }

                // 4. Mensagem de erro adjacente
                const parent = el.closest(".form-group, .mb-3, .o_field_widget, div");
                if (parent) {
                    const errorEl = parent.querySelector(".invalid-feedback, .error-message, .text-danger, .o_field_invalid");
                    if (errorEl && errorEl.innerText.trim()) {
                        return { invalid: true, reason: `Mensagem de erro visível: '${errorEl.innerText.trim()}'` };
                    }
                }

                return { invalid: false, reason: "Campo não apresenta estado de erro visível" };
            }""",
            selector,
        )
        return bool(result.get("invalid")), str(result.get("reason"))

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
