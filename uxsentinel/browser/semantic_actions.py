"""Motor de Ações Semânticas em Linguagem Natural (ai_action) para UXSentinel.

Permite execução de ações declarativas em linguagem natural (ai_click, ai_fill, ai_assert, ai_action)
utilizando resolução em cascata:
1. Árvore de acessibilidade (page.accessibility.snapshot()) com análise semântica de roles, labels e nomes acessíveis.
2. Fallback visual por IA multimodal (UnifiedVisionClient) prevendo coordenadas (x, y) e seletores semânticos.
"""

from __future__ import annotations

import base64
import contextlib
import inspect
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from playwright.async_api import Page
from pydantic import BaseModel

from uxsentinel.core.models import IssueSeverity, SemanticStepResult, SemanticStrategy

if TYPE_CHECKING:
    from uxsentinel.vision.client import UnifiedVisionClient

logger = logging.getLogger("uxsentinel.browser.semantic")

# Palavras sem valor semântico discriminante para busca em acessibilidade
STOPWORDS = {
    "o",
    "a",
    "os",
    "as",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "para",
    "pra",
    "pro",
    "com",
    "por",
    "e",
    "ou",
    "se",
    "the",
    "an",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
}

# Palavras indicativas de componentes UI
ROLE_HINTS = {
    "botao": "button",
    "botão": "button",
    "btn": "button",
    "button": "button",
    "link": "link",
    "aba": "tab",
    "tab": "tab",
    "menu": "menuitem",
    "item": "menuitem",
    "opcao": "option",
    "opção": "option",
    "campo": "textbox",
    "input": "textbox",
    "caixa": "textbox",
    "texto": "textbox",
    "email": "textbox",
    "e-mail": "textbox",
    "senha": "textbox",
    "busca": "searchbox",
    "pesquisa": "searchbox",
    "selecao": "combobox",
    "seleção": "combobox",
    "dropdown": "combobox",
    "checkbox": "checkbox",
    "marcador": "checkbox",
    "radio": "radio",
}


class SemanticActionError(Exception):
    """Exceção levantada quando uma ação semântica não pode ser resolvida ou executada."""

    pass


class SemanticAssertResult(BaseModel):
    """Resultado da avaliação cognitiva de uma asserção semântica em linguagem natural."""

    passed: bool
    confidence: float = 1.0
    reasoning: str = ""
    severity: IssueSeverity = IssueSeverity.ALTA
    suggestion: str | None = None
    evaluated_assertion: str = ""


class SemanticActionExecutor:
    """Motor de execução semântica orientada a linguagem natural com resolução em cascata."""

    def __init__(
        self,
        page: Page,
        vision_client: UnifiedVisionClient | None = None,
        highlight_clicks: bool = True,
    ):
        self.page = page
        self.vision_client = vision_client
        self.highlight_clicks = highlight_clicks

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para comparações semânticas ignorando maiúsculas e diacríticos comuns."""
        text = text.lower().strip()
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

    def _extract_terms(self, text: str) -> list[str]:
        """Extrai tokens semânticos relevantes do alvo em linguagem natural."""
        raw_tokens = re.split(r"[\s\,\.\;\:\!\?\"\'\(\)\[\]\-\_\/]+", text)
        terms: list[str] = []
        for tok in raw_tokens:
            tok_norm = self._normalize_text(tok)
            if len(tok_norm) >= 2 and tok_norm not in STOPWORDS and tok_norm not in terms:
                terms.append(tok_norm)
        return terms

    def _infer_expected_role(self, target: str, action: str) -> str | None:
        """Infere o papel (role) esperado do elemento a partir da ação e do texto descritivo."""
        target_norm = self._normalize_text(target)
        for hint, role in ROLE_HINTS.items():
            if hint in target_norm:
                return role
        if action == "click":
            return "button"
        if action == "fill":
            return "textbox"
        return None

    def _collect_accessibility_nodes(self, node: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Varre recursivamente a árvore de acessibilidade coletando nós com semântica relevante."""
        if not node or not isinstance(node, dict):
            return []

        nodes: list[dict[str, Any]] = []
        if node.get("role") or node.get("name") or node.get("description"):
            nodes.append(node)

        for child in node.get("children", []):
            nodes.extend(self._collect_accessibility_nodes(child))

        return nodes

    def _score_node(
        self,
        node: dict[str, Any],
        terms: list[str],
        action: str,
        expected_role: str | None,
        target_norm: str,
    ) -> float:
        """Calcula o score de correspondência semântica de um nó da árvore de acessibilidade."""
        role = str(node.get("role") or "").lower()
        raw_name = str(node.get("name") or "")
        name = self._normalize_text(raw_name)
        desc = self._normalize_text(str(node.get("description") or ""))

        if not name and not desc:
            return 0.0

        score = 0.0

        # Compatibilidade com a role esperada
        if expected_role and role == expected_role:
            score += 4.0
        elif action == "click" and role in (
            "button",
            "link",
            "menuitem",
            "tab",
            "checkbox",
            "radio",
            "switch",
        ):
            score += 2.5
        elif action == "fill" and role in ("textbox", "searchbox", "combobox", "spinbutton"):
            score += 3.0

        # Correspondência exata do nome acessível com a intenção
        if name == target_norm:
            score += 15.0
        elif name and name in target_norm:
            score += 8.0
        elif target_norm and target_norm in name:
            score += 7.0

        # Correspondência de termos individuais
        matched_terms = 0
        for term in terms:
            if term == role:
                continue
            if term in name:
                score += 3.5
                matched_terms += 1
            elif term in desc:
                score += 2.0
                matched_terms += 1

        # Penalidade se termos discriminantes essenciais não forem encontrados
        meaningful_terms = [t for t in terms if t not in ROLE_HINTS]
        if meaningful_terms and matched_terms == 0:
            score *= 0.3

        return score

    async def _safe_locator_check(self, sel: str) -> bool:
        """Testa com segurança se o seletor existe e está visível no DOM."""
        try:
            loc = self.page.locator(sel)
            if inspect.isawaitable(loc):
                loc = await loc
            count_val = loc.count()
            if inspect.isawaitable(count_val):
                count_val = await count_val
            if count_val > 0:
                first = loc.first
                if inspect.isawaitable(first):
                    first = await first
                is_vis = first.is_visible()
                if inspect.isawaitable(is_vis):
                    is_vis = await is_vis
                return bool(is_vis)
        except Exception as exc:
            logger.debug("Validação do seletor '%s' falhou: %s", sel, exc)
        return False

    async def resolve_via_accessibility(
        self,
        target: str,
        action: str = "click",
    ) -> tuple[str | None, float, dict[str, Any] | None]:
        """Tenta resolver o alvo semântico inspecionando a Árvore de Acessibilidade da página."""
        if not hasattr(self.page, "accessibility") or not hasattr(self.page.accessibility, "snapshot"):
            return None, 0.0, None

        try:
            snapshot = await self.page.accessibility.snapshot()
        except Exception as exc:
            logger.debug("Falha ao obter accessibility snapshot: %s", exc)
            return None, 0.0, None

        if not snapshot:
            return None, 0.0, None

        terms = self._extract_terms(target)
        target_norm = self._normalize_text(target)
        expected_role = self._infer_expected_role(target, action)
        all_nodes = self._collect_accessibility_nodes(snapshot)

        candidates: list[tuple[float, dict[str, Any]]] = []
        for node in all_nodes:
            s = self._score_node(node, terms, action, expected_role, target_norm)
            if s >= 4.0:
                candidates.append((s, node))

        if not candidates:
            return None, 0.0, None

        # Ordena candidatos por pontuação decrescente
        candidates.sort(key=lambda x: x[0], reverse=True)

        # Checa ambiguidade: se os dois melhores tiverem scores altos e idênticos com nomes diferentes
        if len(candidates) >= 2:
            top1_score, top1_node = candidates[0]
            top2_score, top2_node = candidates[1]
            if top1_score == top2_score and top1_node.get("name") != top2_node.get("name"):
                logger.debug(
                    "Ambiguidade semântica na árvore de acessibilidade entre '%s' e '%s'. Acionando fallback visual.",
                    top1_node.get("name"),
                    top2_node.get("name"),
                )
                return None, 0.0, None

        for score, node in candidates:
            role = str(node.get("role") or "").strip()
            name = str(node.get("name") or "").strip()

            if not name:
                continue

            possible_selectors: list[str] = []
            if role:
                possible_selectors.append(f'role={role}[name="{name}"]')
                possible_selectors.append(f'role={role}[name="{name}" i]')
            if role in ("button", "link", "tab") and len(name) < 60:
                possible_selectors.append(f'text="{name}"')
            if role in ("textbox", "searchbox"):
                possible_selectors.append(f'input[placeholder="{name}" i]')
                possible_selectors.append(f'input[aria-label="{name}" i]')

            for sel in possible_selectors:
                if await self._safe_locator_check(sel):
                    logger.info(
                        "Alvo semântico '%s' resolvido via Acessibilidade: '%s' (score: %.1f)",
                        target,
                        sel,
                        score,
                    )
                    return sel, score, node

        return None, 0.0, None

    def _extract_json(self, raw_response: str) -> str:
        """Extrai bloco JSON limpo de resposta gerada por modelos de linguagem."""
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_response, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        idx_open = raw_response.find("{")
        idx_close = raw_response.rfind("}")
        if idx_open != -1 and idx_close != -1 and idx_close > idx_open:
            return raw_response[idx_open : idx_close + 1].strip()
        return raw_response.strip()

    async def resolve_via_vision(
        self,
        target: str,
        action: str = "click",
        value: str | None = None,
    ) -> tuple[dict[str, float] | None, str | None, float, str]:
        """Localiza o elemento alvo visualmente via IA Multimodal (UnifiedVisionClient) sobre screenshot."""
        if not self.vision_client:
            logger.debug("UnifiedVisionClient não configurado para resolução visual semântica.")
            return None, None, 0.0, "Cliente de visão LMM não configurado"

        try:
            screenshot_bytes = await self.page.screenshot(type="png")
            image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as exc:
            logger.warning("Falha ao capturar screenshot para resolução visual semântica: %s", exc)
            return None, None, 0.0, f"Falha ao capturar screenshot: {exc}"

        raw_vp = getattr(self.page, "viewport_size", None)
        vp = raw_vp if isinstance(raw_vp, dict) else {"width": 1440, "height": 900}

        prompt = f"""Você é um motor especialista em automação visual e localização de elementos de interface web.
Analise a captura de tela e localize com precisão o elemento alvo descrito em linguagem natural.

INFORMAÇÕES DA AÇÃO SEMÂNTICA:
- Ação Solicitada: {action.upper()}
- Alvo em Linguagem Natural: "{target}"
- Valor a Preencher (se aplicável): {value or "Nenhum"}
- Resolução da Viewport: {vp.get("width")}x{vp.get("height")} pixels

SUA MISSÃO:
1. Examine a interface e identifique visualmente o botão, campo de entrada, ícone ou texto correspondente ao alvo.
2. Calcule o ponto central exato (x, y) em pixels do elemento para receber a interação (clique ou foco).
3. Se possível, sugira um seletor semântico CSS ou Playwright robusto.

Responda ESTRITAMENTE em formato JSON:
```json
{{
  "found": true,
  "confidence": 0.95,
  "coordinates": {{"x": 420.5, "y": 185.0}},
  "suggested_selector": "button[type='submit']",
  "reasoning": "Botão azul de confirmação identificado com destaque no canto superior direito"
}}
```
Caso o elemento não esteja presente ou visível na tela:
```json
{{
  "found": false,
  "confidence": 0.0,
  "reasoning": "Elemento não localizado na captura da tela atual"
}}
```
"""

        try:
            raw_res = await self.vision_client.analyze(image_b64, prompt)
            clean_json = self._extract_json(raw_res)
            parsed = json.loads(clean_json)

            if parsed.get("found") is True:
                coords = parsed.get("coordinates")
                conf = float(parsed.get("confidence", 0.85))
                suggested_sel = parsed.get("suggested_selector")
                reasoning = parsed.get("reasoning", "")

                if coords and "x" in coords and "y" in coords:
                    coords_dict = {"x": float(coords["x"]), "y": float(coords["y"])}
                    logger.info(
                        "Alvo semântico '%s' resolvido via Visão LMM nas coordenadas (%.1f, %.1f) [conf: %.2f]",
                        target,
                        coords_dict["x"],
                        coords_dict["y"],
                        conf,
                    )
                    return coords_dict, suggested_sel, conf, reasoning
                elif suggested_sel:
                    return None, suggested_sel, conf, reasoning

            return None, None, 0.0, parsed.get("reasoning", "Elemento não localizado pelo modelo visual")

        except Exception as exc:
            logger.warning("Erro na inferência visual de ação semântica via IA: %s", exc)
            return None, None, 0.0, f"Exceção na inferência visual: {exc}"

    async def _show_click_effect(self, x: float, y: float) -> None:
        """Gera efeito de feedback visual nas coordenadas especificadas."""
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

    async def execute_ai_click(
        self,
        target: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> SemanticStepResult:
        """Executa clique semântico com resolução em cascata (Acessibilidade -> Visão LMM)."""
        logger.info("Executando ai_click no alvo: '%s'", target)

        # 1. Tenta Acessibilidade
        sel, score, _node = await self.resolve_via_accessibility(target, action="click")
        if sel:
            try:
                loc = self.page.locator(sel)
                if inspect.isawaitable(loc):
                    loc = await loc
                first = loc.first
                if inspect.isawaitable(first):
                    first = await first

                await self._highlight_element(sel)
                with contextlib.suppress(Exception):
                    box = first.bounding_box()
                    if inspect.isawaitable(box):
                        box = await box
                    if box:
                        await self._show_click_effect(
                            box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                        )

                click_call = first.click(timeout=timeout)
                if inspect.isawaitable(click_call):
                    await click_call

                return SemanticStepResult(
                    step_index=step_index,
                    action="ai_click",
                    target=target,
                    strategy=SemanticStrategy.ACCESSIBILITY,
                    resolved_selector=sel,
                    confidence=min(round(score / 15.0, 2), 1.0),
                    passed=True,
                    reasoning=f"Elemento localizado e clicado via árvore de acessibilidade: '{sel}'",
                )
            except Exception as exc:
                logger.debug("Clique via seletor de acessibilidade '%s' falhou: %s", sel, exc)

        # 2. Fallback Visual via LMM
        coords, suggested_sel, conf, reasoning = await self.resolve_via_vision(target, action="click")

        # Se retornou seletor sugerido que existe no DOM, tenta utilizá-lo
        if suggested_sel and await self._safe_locator_check(suggested_sel):
            try:
                loc = self.page.locator(suggested_sel).first
                if inspect.isawaitable(loc):
                    loc = await loc
                await self._highlight_element(suggested_sel)
                click_call = loc.click(timeout=timeout)
                if inspect.isawaitable(click_call):
                    await click_call

                return SemanticStepResult(
                    step_index=step_index,
                    action="ai_click",
                    target=target,
                    strategy=SemanticStrategy.VISION_SELECTOR,
                    resolved_selector=suggested_sel,
                    coordinates=coords,
                    confidence=conf,
                    passed=True,
                    reasoning=reasoning or f"Elemento clicado via seletor semântico visual '{suggested_sel}'",
                )
            except Exception as exc:
                logger.debug("Clique via seletor sugerido pela visão falhou: %s", exc)

        # Se obteve coordenadas (x, y)
        if coords and "x" in coords and "y" in coords:
            await self._show_click_effect(coords["x"], coords["y"])
            click_call = self.page.mouse.click(coords["x"], coords["y"])
            if inspect.isawaitable(click_call):
                await click_call

            return SemanticStepResult(
                step_index=step_index,
                action="ai_click",
                target=target,
                strategy=SemanticStrategy.VISION_COORDINATES,
                coordinates=coords,
                resolved_selector=suggested_sel,
                confidence=conf,
                passed=True,
                reasoning=reasoning
                or f"Clique executado nas coordenadas ({coords['x']}, {coords['y']}) via Visão LMM",
            )

        raise SemanticActionError(
            f"Não foi possível localizar ou clicar no elemento alvo '{target}' nem por Acessibilidade nem por Visão LMM."
        )

    async def execute_ai_fill(
        self,
        target: str,
        value: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> SemanticStepResult:
        """Executa preenchimento semântico com resolução em cascata (Acessibilidade -> Visão LMM)."""
        logger.info("Executando ai_fill no alvo: '%s' com valor: '%s'", target, value)

        # 1. Tenta Acessibilidade
        sel, score, _node = await self.resolve_via_accessibility(target, action="fill")
        if sel:
            try:
                loc = self.page.locator(sel)
                if inspect.isawaitable(loc):
                    loc = await loc
                first = loc.first
                if inspect.isawaitable(first):
                    first = await first

                await self._highlight_element(sel)
                fill_call = first.fill(value, timeout=timeout)
                if inspect.isawaitable(fill_call):
                    await fill_call

                return SemanticStepResult(
                    step_index=step_index,
                    action="ai_fill",
                    target=target,
                    value=value,
                    strategy=SemanticStrategy.ACCESSIBILITY,
                    resolved_selector=sel,
                    confidence=min(round(score / 15.0, 2), 1.0),
                    passed=True,
                    reasoning=f"Campo localizado e preenchido via acessibilidade: '{sel}'",
                )
            except Exception as exc:
                logger.debug("Preenchimento via seletor de acessibilidade '%s' falhou: %s", sel, exc)

        # 2. Fallback Visual via LMM
        coords, suggested_sel, conf, reasoning = await self.resolve_via_vision(
            target, action="fill", value=value
        )

        if suggested_sel and await self._safe_locator_check(suggested_sel):
            try:
                loc = self.page.locator(suggested_sel).first
                if inspect.isawaitable(loc):
                    loc = await loc
                await self._highlight_element(suggested_sel)
                fill_call = loc.fill(value, timeout=timeout)
                if inspect.isawaitable(fill_call):
                    await fill_call

                return SemanticStepResult(
                    step_index=step_index,
                    action="ai_fill",
                    target=target,
                    value=value,
                    strategy=SemanticStrategy.VISION_SELECTOR,
                    resolved_selector=suggested_sel,
                    coordinates=coords,
                    confidence=conf,
                    passed=True,
                    reasoning=reasoning or f"Campo preenchido via seletor sugerido '{suggested_sel}'",
                )
            except Exception as exc:
                logger.debug("Preenchimento via seletor sugerido falhou: %s", exc)

        if coords and "x" in coords and "y" in coords:
            await self._show_click_effect(coords["x"], coords["y"])
            # Clica para dar foco ao campo
            click_call = self.page.mouse.click(coords["x"], coords["y"])
            if inspect.isawaitable(click_call):
                await click_call

            # Limpa qualquer conteúdo residual e digita o valor
            with contextlib.suppress(Exception):
                press_a = self.page.keyboard.press("Control+A")
                if inspect.isawaitable(press_a):
                    await press_a
                press_bs = self.page.keyboard.press("Backspace")
                if inspect.isawaitable(press_bs):
                    await press_bs

            type_call = self.page.keyboard.type(value)
            if inspect.isawaitable(type_call):
                await type_call

            return SemanticStepResult(
                step_index=step_index,
                action="ai_fill",
                target=target,
                value=value,
                strategy=SemanticStrategy.VISION_COORDINATES,
                coordinates=coords,
                resolved_selector=suggested_sel,
                confidence=conf,
                passed=True,
                reasoning=reasoning
                or f"Campo focado e preenchido nas coordenadas ({coords['x']}, {coords['y']})",
            )

        raise SemanticActionError(
            f"Não foi possível localizar ou preencher o campo alvo '{target}' nem por Acessibilidade nem por Visão LMM."
        )

    async def execute_ai_assert(
        self,
        assertion: str,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> SemanticAssertResult:
        """Avalia uma asserção declarativa cognitiva (ai_assert) sobre a captura de tela atual via LMM."""
        logger.info("Avaliando ai_assert declarativo: '%s'", assertion)

        if not self.vision_client:
            raise SemanticActionError(
                "UnifiedVisionClient é obrigatório para execução de asserções semânticas cognitivas (ai_assert)."
            )

        try:
            screenshot_bytes = await self.page.screenshot(type="png")
            image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as exc:
            raise SemanticActionError(f"Falha ao capturar screenshot para ai_assert: {exc}") from exc

        prompt = f"""Você é um auditor cognitivo e engenheiro de QA especialista em validação de interfaces web.
Avalie com rigor se a ASSERÇÃO DECLARATIVA abaixo é VERDADEIRA ou FALSA na captura de tela atual da aplicação.

ASSERÇÃO A SER VALIDADA:
"{assertion}"

CONTEXTO ADICIONAL DO PASSO:
{description or "Nenhum detalhe adicional informado."}

SUA TAREFA:
1. Examine cuidadosamente os textos, cabeçalhos, modais, botões, estados de componentes e ícones visíveis na tela.
2. Determine se a condição afirmada na asserção declarativa é atendida na íntegra.
3. Se a asserção for atendida, defina "passed": true.
4. Se a asserção NÃO for atendida ou contiver divergência visual/semântica, defina "passed": false, indique a severidade do impacto ("ALTA" ou "BLOQUEANTE") e forneça uma sugestão clara de correção.

Responda ESTRITAMENTE em formato JSON:
```json
{{
  "passed": true,
  "confidence": 0.98,
  "reasoning": "O modal com título 'Sucesso' está visível e centralizado na tela, contendo a mensagem de confirmação esperada.",
  "severity": "ALTA",
  "suggestion": null
}}
```
Ou caso a asserção falhe:
```json
{{
  "passed": false,
  "confidence": 0.95,
  "reasoning": "O modal de confirmação não foi exibido na tela; a interface continua na página de listagem.",
  "severity": "BLOQUEANTE",
  "suggestion": "Verificar se o clique no botão anterior acionou a requisição e abriu o modal de confirmação corretamente."
}}
```
"""

        try:
            raw_res = await self.vision_client.analyze(image_b64, prompt)
            clean_json = self._extract_json(raw_res)
            parsed = json.loads(clean_json)

            passed = bool(parsed.get("passed", False))
            confidence = float(parsed.get("confidence", 0.9))
            reasoning = parsed.get("reasoning", "Asserção avaliada pelo modelo visual LMM.")
            raw_sev = str(parsed.get("severity", "ALTA")).strip().upper()
            severity = (
                IssueSeverity.BLOQUEANTE if raw_sev in ("BLOQUEANTE", "CRITICAL") else IssueSeverity.ALTA
            )
            suggestion = parsed.get("suggestion")

            return SemanticAssertResult(
                passed=passed,
                confidence=confidence,
                reasoning=reasoning,
                severity=severity,
                suggestion=suggestion,
                evaluated_assertion=assertion,
            )

        except Exception as exc:
            logger.error("Erro ao avaliar ai_assert via LMM: %s", exc)
            return SemanticAssertResult(
                passed=False,
                confidence=0.5,
                reasoning=f"Falha técnica ao processar a asserção com o modelo de visão: {exc}",
                severity=IssueSeverity.ALTA,
                suggestion="Reexecutar a validação e verificar a conectividade com o provedor de IA multimodal.",
                evaluated_assertion=assertion,
            )

    async def execute_ai_action(
        self,
        instruction: str,
        value: str | None = None,
        timeout: int = 10000,
        description: str | None = None,
        step_index: int | None = None,
    ) -> SemanticStepResult:
        """Executa ação semântica genérica (ai_action) inferindo se a intenção é clique, preenchimento ou validação."""
        logger.info("Executando ai_action genérica: '%s'", instruction)
        norm_inst = self._normalize_text(instruction)

        # Padrões de preenchimento
        fill_keywords = ("preencher", "digitar", "escrever", "inserir", "informar", "fill", "type", "enter")
        if any(k in norm_inst for k in fill_keywords) and value is not None:
            return await self.execute_ai_fill(
                target=instruction,
                value=value,
                timeout=timeout,
                description=description,
                step_index=step_index,
            )

        # Padrões de asserção
        assert_keywords = (
            "verificar",
            "garantir",
            "assegurar",
            "deve estar",
            "deve conter",
            "assert",
            "check",
        )
        if any(k in norm_inst for k in assert_keywords) and not value:
            assert_res = await self.execute_ai_assert(
                assertion=instruction,
                timeout=timeout,
                description=description,
                step_index=step_index,
            )
            return SemanticStepResult(
                step_index=step_index,
                action="ai_action",
                target=instruction,
                strategy=SemanticStrategy.LMM_ASSERTION,
                confidence=assert_res.confidence,
                passed=assert_res.passed,
                reasoning=assert_res.reasoning,
            )

        # Fallback padrão: clique semântico
        return await self.execute_ai_click(
            target=instruction,
            timeout=timeout,
            description=description,
            step_index=step_index,
        )
