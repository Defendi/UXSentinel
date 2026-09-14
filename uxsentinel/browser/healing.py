"""Módulo de Self-Healing (Autocura) de seletores para automação Playwright.

Combina inspeção semântica na Árvore de Acessibilidade (Playwright Accessibility Snapshot)
e inferência visual por IA Multimodal (UnifiedVisionClient) para recuperar ações quebradas.
"""

from __future__ import annotations

import base64
import inspect
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from playwright.async_api import Page

from uxsentinel.core.models import HealingEvent, HealingStrategy
from uxsentinel.vision.client import UnifiedVisionClient

logger = logging.getLogger("uxsentinel.browser.healing")

# Palavras sem valor semântico para descarte na tokenização de seletores
STOPWORDS = {
    "btn",
    "button",
    "input",
    "div",
    "span",
    "class",
    "id",
    "name",
    "type",
    "submit",
    "form",
    "primary",
    "secondary",
    "action",
    "o",
    "de",
    "do",
    "da",
    "em",
    "para",
    "com",
    "no",
    "na",
    "e",
    "the",
    "a",
    "an",
    "in",
    "on",
    "at",
    "to",
    "for",
}


class SelectorHealer:
    """Motor de recuperação e autocura de seletores com fallback duplo: Acessibilidade + Visão."""

    def __init__(
        self,
        vision_client: UnifiedVisionClient | None = None,
        enabled: bool = True,
    ):
        self.vision_client = vision_client
        self.enabled = enabled

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para comparações semânticas ignorando acentos e maiúsculas."""
        text = text.lower().strip()
        # Normalização simples de caracteres acentuados comuns em pt-BR
        replacements = {
            "á": "a",
            "à": "a",
            "ã": "a",
            "â": "a",
            "é": "e",
            "ê": "e",
            "í": "i",
            "ó": "o",
            "ô": "o",
            "õ": "o",
            "ú": "u",
            "ç": "c",
        }
        for orig, sub in replacements.items():
            text = text.replace(orig, sub)
        return text

    def _extract_search_terms(self, selector: str, description: str | None = None) -> list[str]:
        """Extrai termos semânticos relevantes do seletor que falhou e da descrição da ação."""
        terms: list[str] = []

        # Extrai do seletor quebrando em separadores comuns
        raw_tokens = re.split(r"[\s\.\#\[\]\=\'\"_\-\:\>\<\(\)\@\*\^\$\,\/]+", selector)
        for tok in raw_tokens:
            tok_norm = self._normalize_text(tok)
            if (
                len(tok_norm) >= 3
                and tok_norm not in STOPWORDS
                and not tok_norm.isdigit()
                and tok_norm not in terms
            ):
                terms.append(tok_norm)

        # Se houver descrição do passo no YAML (ex: 'Clicar no botão Confirmar Pedido')
        if description:
            desc_tokens = re.split(r"[\s\,\.\;\:\!\?\"\'\(\)]+", description)
            for tok in desc_tokens:
                tok_norm = self._normalize_text(tok)
                if len(tok_norm) >= 3 and tok_norm not in STOPWORDS and tok_norm not in terms:
                    terms.append(tok_norm)

        return terms

    def _collect_accessibility_nodes(self, node: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Varre recursivamente a árvore de acessibilidade coletando todos os nós com role ou name."""
        if not node or not isinstance(node, dict):
            return []

        nodes: list[dict[str, Any]] = []
        if node.get("role") or node.get("name"):
            nodes.append(node)

        for child in node.get("children", []):
            nodes.extend(self._collect_accessibility_nodes(child))

        return nodes

    def _score_accessibility_node(
        self,
        node: dict[str, Any],
        terms: list[str],
        action: str,
        description: str | None = None,
    ) -> float:
        """Calcula score de relevância semântica do nó da árvore de acessibilidade."""
        role = str(node.get("role") or "").lower()
        raw_name = str(node.get("name") or "")
        name = self._normalize_text(raw_name)
        desc = self._normalize_text(str(node.get("description") or ""))

        score = 0.0

        # Compatibilidade de role com a ação
        click_roles = {
            "button": 3.0,
            "link": 2.5,
            "menuitem": 2.5,
            "tab": 2.0,
            "checkbox": 2.0,
            "radio": 2.0,
            "switch": 2.0,
            "option": 1.5,
        }
        fill_roles = {
            "textbox": 3.5,
            "searchbox": 3.5,
            "combobox": 3.0,
            "spinbutton": 2.5,
        }

        if action == "click":
            score += click_roles.get(role, 0.0)
        elif action == "fill":
            score += fill_roles.get(role, 0.0)

        # Se o nó não tiver nem nome nem descrição, score é baixo
        if not name and not desc:
            return 0.0

        # Comparação com termos extraídos
        for term in terms:
            if term in name:
                # Se for igualdade exata
                if term == name:
                    score += 10.0
                else:
                    score += 5.0
            elif term in desc:
                score += 3.0

        # Comparação direta com a descrição da ação
        if description:
            desc_norm = self._normalize_text(description)
            if name and name in desc_norm:
                score += 8.0
            if desc_norm and desc_norm in name:
                score += 8.0

        return score

    async def find_in_accessibility_tree(
        self,
        page: Page,
        selector: str,
        action: str = "click",
        description: str | None = None,
    ) -> tuple[str | None, float, dict[str, Any] | None]:
        """Busca candidato semântico na árvore de acessibilidade e valida a existência no DOM."""
        try:
            snapshot = await page.accessibility.snapshot()
        except Exception as exc:
            logger.debug("Falha ao capturar accessibility snapshot: %s", exc)
            return None, 0.0, None

        if not snapshot:
            return None, 0.0, None

        terms = self._extract_search_terms(selector, description)
        all_nodes = self._collect_accessibility_nodes(snapshot)

        candidates: list[tuple[float, dict[str, Any]]] = []
        for node in all_nodes:
            s = self._score_accessibility_node(node, terms, action, description)
            if s >= 2.0:
                candidates.append((s, node))

        # Ordena candidatos pelo maior score
        candidates.sort(key=lambda x: x[0], reverse=True)

        for score, node in candidates:
            role = str(node.get("role") or "").strip()
            name = str(node.get("name") or "").strip()

            if not name:
                continue

            # Constrói possíveis seletores Playwright suportados
            candidate_selectors: list[str] = []
            if role:
                candidate_selectors.append(f'role={role}[name="{name}"]')
                candidate_selectors.append(f'role={role}[name="{name}" i]')

            # Se for botão ou link com texto simples
            if role in ("button", "link") and len(name) < 50:
                candidate_selectors.append(f'text="{name}"')

            for sel in candidate_selectors:
                try:
                    loc = page.locator(sel)
                    if inspect.isawaitable(loc):
                        loc = await loc
                    first = loc.first
                    if inspect.isawaitable(first):
                        first = await first
                    count_val = loc.count()
                    if inspect.isawaitable(count_val):
                        count_val = await count_val
                    if count_val > 0:
                        is_visible_val = first.is_visible()
                        if inspect.isawaitable(is_visible_val):
                            is_visible_val = await is_visible_val
                        if is_visible_val:
                            logger.info(
                                "Autocura por Acessibilidade encontrou elemento válido: '%s' (score: %.1f)",
                                sel,
                                score,
                            )
                            return sel, score, node
                except Exception as ex:
                    logger.debug("Tentativa com seletor candidato '%s' falhou: %s", sel, ex)
                    continue

        return None, 0.0, None

    async def find_via_vision(
        self,
        page: Page,
        selector: str,
        action: str = "click",
        description: str | None = None,
        value: str | None = None,
    ) -> tuple[dict[str, float] | None, str | None, float]:
        """Localiza o elemento visualmente via LMM multimodal a partir de screenshot da viewport."""
        if not self.vision_client:
            logger.debug("Cliente de visão LMM não configurado para Self-Healing.")
            return None, None, 0.0

        try:
            screenshot_bytes = await page.screenshot(type="png")
            image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as exc:
            logger.warning("Falha ao capturar screenshot para visão de Self-Healing: %s", exc)
            return None, None, 0.0

        raw_viewport = getattr(page, "viewport_size", None)
        viewport = raw_viewport if isinstance(raw_viewport, dict) else {"width": 1440, "height": 900}

        prompt = f"""Você é um motor inteligente de autocura (Self-Healing) de testes visuais automatizados.
Um seletor CSS falhou com TimeoutError na página web. Analise a captura de tela e localize o elemento visual alvo pretendido.

DADOS DA AÇÃO QUE FALHOU:
- Ação: {action.upper()}
- Seletor original quebrado: {selector}
- Descrição da intenção do passo: {description or "Não informada"}
- Valor a preencher (se aplicável): {value or "Nenhum"}
- Dimensões da tela: {viewport.get("width")}x{viewport.get("height")}

Sua tarefa:
1. Localize visualmente o botão, campo de entrada, link ou componente correspondente à intenção da ação.
2. Calcule o ponto central exato (x, y) do elemento na imagem para receber o clique/foco.
3. Formule um novo seletor semântico sugerido para substituir o seletor quebrado.

Responda ESTRITAMENTE em formato JSON com a seguinte estrutura:
```json
{{
  "found": true,
  "confidence": 0.95,
  "coordinates": {{"x": 350, "y": 180}},
  "suggested_selector": "button.btn-confirm",
  "reasoning": "Botão de confirmação azul localizado no topo direito do modal"
}}
```
Se não for possível identificar o elemento de forma inequívoca, retorne:
```json
{{
  "found": false,
  "reasoning": "Elemento não visível na tela"
}}
```
"""

        try:
            raw_text = await self.vision_client.analyze(image_b64, prompt)
            clean_json = self._extract_json(raw_text)
            parsed = json.loads(clean_json)

            if parsed.get("found") is True:
                coords = parsed.get("coordinates")
                if coords and "x" in coords and "y" in coords:
                    confidence = float(parsed.get("confidence", 0.8))
                    suggested_sel = parsed.get("suggested_selector")
                    logger.info(
                        "Autocura por Visão identificou coordenadas: (%s, %s) com confiança %.2f",
                        coords["x"],
                        coords["y"],
                        confidence,
                    )
                    return {"x": float(coords["x"]), "y": float(coords["y"])}, suggested_sel, confidence

        except Exception as exc:
            logger.warning("Falha na inferência visual de Self-Healing via IA: %s", exc)

        return None, None, 0.0

    async def heal_action(
        self,
        page: Page,
        action: str,
        selector: str,
        value: str | None = None,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
        highlight_callback: Callable[[float, float], Any] | None = None,
    ) -> HealingEvent | None:
        """Tenta recuperar a ação executando as estratégias de Acessibilidade e Visão em cascata."""
        if not self.enabled:
            return None

        logger.info(
            "Iniciando Self-Healing para ação '%s' com seletor original quebrado: '%s'",
            action,
            selector,
        )

        # 1. Estratégia A: Árvore de Acessibilidade
        recov_sel, a11y_score, _node = await self.find_in_accessibility_tree(
            page=page,
            selector=selector,
            action=action,
            description=description,
        )

        if recov_sel:
            try:
                loc = page.locator(recov_sel)
                if inspect.isawaitable(loc):
                    loc = await loc
                first = loc.first
                if inspect.isawaitable(first):
                    first = await first

                if action == "click":
                    box = first.bounding_box()
                    if inspect.isawaitable(box):
                        box = await box
                    if box and highlight_callback:
                        cb_res = highlight_callback(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        if inspect.isawaitable(cb_res):
                            await cb_res
                    click_res = first.click(timeout=timeout)
                    if inspect.isawaitable(click_res):
                        await click_res
                elif action == "fill":
                    fill_res = first.fill(value or "", timeout=timeout)
                    if inspect.isawaitable(fill_res):
                        await fill_res
                elif action == "hover":
                    hover_res = first.hover(timeout=timeout)
                    if inspect.isawaitable(hover_res):
                        await hover_res
                elif action == "select":
                    select_res = first.select_option(value or "", timeout=timeout)
                    if inspect.isawaitable(select_res):
                        await select_res

                event = HealingEvent(
                    step_index=step_index,
                    action=action,
                    original_selector=selector,
                    strategy=HealingStrategy.ACCESSIBILITY,
                    recovered_selector=recov_sel,
                    yaml_fix_suggestion=f"selector: '{recov_sel}'",
                    confidence=min(1.0, a11y_score / 10.0),
                    description=description,
                )
                logger.info(
                    "Self-Healing concluído via Acessibilidade: '%s' -> '%s'",
                    selector,
                    recov_sel,
                )
                return event
            except Exception as exc:
                logger.warning(
                    "Falha ao executar ação no seletor recuperado por acessibilidade '%s': %s",
                    recov_sel,
                    exc,
                )

        # 2. Estratégia B: Visão Computacional Multimodal (LMM)
        coords, suggested_sel, confidence = await self.find_via_vision(
            page=page,
            selector=selector,
            action=action,
            description=description,
            value=value,
        )

        if coords:
            try:
                x = coords["x"]
                y = coords["y"]

                if highlight_callback:
                    await highlight_callback(x, y)

                if action == "click":
                    await page.mouse.click(x, y)
                elif action == "fill":
                    await page.mouse.click(x, y)
                    # Seleciona todo o conteúdo anterior do campo antes de digitar
                    await page.keyboard.press("Control+A")
                    await page.keyboard.type(value or "")
                elif action == "hover":
                    await page.mouse.move(x, y)

                fix_suggestion = (
                    f"selector: '{suggested_sel}'"
                    if suggested_sel
                    else f"# Seletor quebrado. Coordenadas visuais detectadas: x={x:.0f}, y={y:.0f}"
                )

                event = HealingEvent(
                    step_index=step_index,
                    action=action,
                    original_selector=selector,
                    strategy=HealingStrategy.VISION_COORDINATES,
                    recovered_selector=suggested_sel,
                    coordinates=coords,
                    yaml_fix_suggestion=fix_suggestion,
                    confidence=confidence,
                    description=description,
                )
                logger.info(
                    "Self-Healing concluído via Visão Multimodal: '%s' -> coords (%s, %s)",
                    selector,
                    x,
                    y,
                )
                return event
            except Exception as exc:
                logger.warning("Falha ao executar ação via coordenadas de visão (%s, %s): %s", coords, exc)

        return None

    def _extract_json(self, text: str) -> str:
        """Extrai bloco JSON de resposta em markdown se presente."""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1).strip()
        return text
