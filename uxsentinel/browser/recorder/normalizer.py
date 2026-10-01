"""Normalizador de eventos brutos de DOM e navegador do Recorder (UXS-96).

Ingere eventos brutos recebidos da RecorderSession, filtra ruídos técnicos,
deduplica rajadas temporais de cliques (< 300ms), agrega sequências de digitação
em passos de alto nível ('fill') e consulta o RecorderAdvisor para ações ambíguas.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from uxsentinel.browser.recorder.models import (
    RecordedStep,
    RecordedTarget,
    StepStatus,
)
from uxsentinel.browser.recorder.resolver import ElementResolver

logger = logging.getLogger("uxsentinel.browser.recorder.normalizer")

# Eventos técnicos que devem ser descartados sumariamente
NOISE_EVENT_ACTIONS: frozenset[str] = frozenset(
    {
        "mousemove",
        "pointermove",
        "pointerover",
        "pointerout",
        "wheel",
        "scroll",
        "resize",
    }
)


class EventNormalizer:
    """Normaliza eventos brutos do DOM e do navegador em RecordedSteps semânticos.

    Responsável por:
    - Descarte de ruído técnico (mousemove, scroll, wheel, resize).
    - Deduplicação de rajadas de cliques (< 300ms) no mesmo elemento (CA02b).
    - Agrupamento de eventos de digitação (focus, input, change, blur) em passos 'fill'.
    - Resolução de targets via ElementResolver com hierarquia robusta.
    - Encaminhamento de ações ambíguas para consulta com RecorderAdvisor (CA15).
    - Consolidação de passos pendentes via flush().
    """

    def __init__(
        self,
        resolver: ElementResolver | None = None,
        advisor: Any | None = None,
    ) -> None:
        """Inicializa o normalizador com resolver e advisor opcionais.

        Args:
            resolver: Instância de ElementResolver para inferência de seletores.
            advisor: Instância opcional de RecorderAdvisor para auxílio em ações ambíguas.
        """
        self.resolver = resolver or ElementResolver()
        self.advisor = advisor

        self._step_counter: int = 0
        self._last_click_target_key: str | None = None
        self._last_click_time_ms: float = 0.0

        self._input_buffer: dict[str, Any] | None = None
        self._emitted_fills: dict[str, str] = {}
        self._pending_steps: list[RecordedStep] = []

    def _next_step_index(self) -> int:
        """Retorna e incrementa o próximo índice sequencial de passo."""
        idx = self._step_counter
        self._step_counter += 1
        return idx

    @staticmethod
    def _extract_target_key(target_raw: Any) -> str:
        """Gera uma chave única e estável para identificar o elemento alvo."""
        if not target_raw:
            return ""
        if isinstance(target_raw, dict):
            test_id = target_raw.get("testId") or target_raw.get("data-testid")
            if test_id:
                return f"testid:{test_id}"
            elem_id = target_raw.get("id")
            if elem_id:
                return f"id:{elem_id}"
            name = target_raw.get("name")
            if name:
                return f"name:{name}"
            outer_html = target_raw.get("outerHtml")
            if outer_html:
                return f"html:{outer_html.strip()}"
            selector = target_raw.get("selector") or target_raw.get("cssSelector")
            if selector:
                return f"sel:{selector}"
            tag = target_raw.get("tagName") or ""
            text = target_raw.get("innerText") or target_raw.get("ariaLabel") or ""
            return f"{tag}:{text}"
        if isinstance(target_raw, RecordedTarget) and target_raw.primary:
            return f"{target_raw.primary.strategy}:{target_raw.primary.value}"
        return str(target_raw)

    async def _resolve_target(self, target_raw: Any) -> RecordedTarget | None:
        """Resolve o alvo em um RecordedTarget estruturado."""
        if target_raw is None:
            return None
        if isinstance(target_raw, RecordedTarget):
            return target_raw

        if self.resolver is not None:
            # Suporte a mock assíncrono (AsyncMock) ou chamada regular
            if hasattr(self.resolver, "resolve"):
                try:
                    res = self.resolver.resolve(target_raw)
                    if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                        resolved = await res
                    else:
                        resolved = res
                    if isinstance(resolved, RecordedTarget):
                        return resolved
                except Exception as exc:
                    logger.debug("Falha na chamada a resolver.resolve(): %s", exc)

            if hasattr(self.resolver, "resolve_target_data") and isinstance(target_raw, dict):
                return self.resolver.resolve_target_data(target_raw)
            if hasattr(self.resolver, "_build_target") and isinstance(target_raw, dict):
                return self.resolver._build_target(target_raw)

        return None

    async def _create_fill_step(self, buffer_data: dict[str, Any]) -> RecordedStep | None:
        """Constrói um RecordedStep de ação 'fill' a partir dos dados do buffer."""
        target_raw = buffer_data.get("target")
        target = await self._resolve_target(target_raw)
        val = buffer_data.get("value")
        step = RecordedStep(
            index=self._next_step_index(),
            action="fill",
            target=target,
            value=str(val) if val is not None else "",
            url=buffer_data.get("url"),
            status=StepStatus.CONFIRMED,
        )
        return step

    async def _consolidate_input_buffer(self) -> RecordedStep | None:
        """Consolida e emite o buffer de digitação pendente se ainda não foi emitido."""
        if not self._input_buffer:
            return None

        key = self._input_buffer.get("target_key", "")
        val = str(self._input_buffer.get("value", ""))
        already_emitted = self._input_buffer.get("emitted", False)

        step: RecordedStep | None = None
        if not already_emitted and self._emitted_fills.get(key) != val:
            self._emitted_fills[key] = val
            step = await self._create_fill_step(self._input_buffer)

        self._input_buffer = None
        return step

    async def ingest_event(self, raw_event: dict[str, Any]) -> RecordedStep | None:
        """Ingere um evento bruto emitido pelo navegador e o normaliza em RecordedStep.

        Args:
            raw_event: Dicionário contendo os dados do evento bruto.

        Returns:
            RecordedStep normalizado se a ação for consolidada, ou None se for ruído
            ou evento intermediário acumulado no buffer.
        """
        if not isinstance(raw_event, dict):
            return None

        action = str(raw_event.get("action") or raw_event.get("type") or "").strip().lower()

        # 1. Filtro de Ruído Técnico
        if action in NOISE_EVENT_ACTIONS:
            return None

        # 2. Tratamento de Ações Ambíguas (CA15)
        is_ambiguous = (
            raw_event.get("is_ambiguous") is True
            or raw_event.get("ambiguous") is True
            or action in ("ambiguous", "hover", "hover_long")
        )
        if is_ambiguous:
            # Consolida buffer anterior se houver
            pending_fill = await self._consolidate_input_buffer()
            if pending_fill:
                self._pending_steps.append(pending_fill)

            step = await self._handle_ambiguous_event(raw_event)
            if self._pending_steps:
                self._pending_steps.append(step)
                return self._pending_steps.pop(0)
            return step

        # 3. Navegação (framenavigated / navigate / goto)
        if action in ("navigate", "goto", "framenavigated"):
            pending_fill = await self._consolidate_input_buffer()
            if pending_fill:
                self._pending_steps.append(pending_fill)

            url = raw_event.get("url")
            if not url or url.startswith("about:blank") or url.startswith("chrome-error://"):
                if self._pending_steps:
                    return self._pending_steps.pop(0)
                return None

            nav_step = RecordedStep(
                index=self._next_step_index(),
                action="navigate",
                url=url,
                status=StepStatus.CONFIRMED,
            )
            if self._pending_steps:
                self._pending_steps.append(nav_step)
                return self._pending_steps.pop(0)
            return nav_step

        target_raw = raw_event.get("target") or {}
        target_key = self._extract_target_key(target_raw)
        tag_name = str(target_raw.get("tagName") or "").lower() if isinstance(target_raw, dict) else ""

        # 4. Dropdowns / <select>
        if action in ("select", "select_option") or (tag_name == "select" and action in ("change", "select")):
            pending_fill = await self._consolidate_input_buffer()
            if pending_fill:
                self._pending_steps.append(pending_fill)

            target = await self._resolve_target(target_raw)
            select_step = RecordedStep(
                index=self._next_step_index(),
                action="select",
                target=target,
                value=raw_event.get("value") or raw_event.get("selected"),
                url=raw_event.get("url"),
                status=StepStatus.CONFIRMED,
            )
            if self._pending_steps:
                self._pending_steps.append(select_step)
                return self._pending_steps.pop(0)
            return select_step

        # 5. Agrupamento de Digitação (focus, input, keydown, keyup, change, blur)
        if action in ("focus", "input", "keydown", "keyup"):
            # Se for um elemento diferente do buffer ativo, consolida o anterior
            if self._input_buffer and self._input_buffer.get("target_key") != target_key:
                flushed = await self._consolidate_input_buffer()
                if flushed:
                    self._pending_steps.append(flushed)

            if not self._input_buffer:
                self._input_buffer = {
                    "target_key": target_key,
                    "target": target_raw,
                    "value": raw_event.get("value", ""),
                    "url": raw_event.get("url"),
                    "events": [raw_event],
                    "emitted": False,
                }
            else:
                if raw_event.get("value") is not None:
                    self._input_buffer["value"] = raw_event.get("value")
                self._input_buffer["events"].append(raw_event)
                if raw_event.get("url"):
                    self._input_buffer["url"] = raw_event.get("url")

            if self._pending_steps:
                return self._pending_steps.pop(0)
            return None

        if action == "change":
            # Evento de commit do valor do campo
            if self._input_buffer and self._input_buffer.get("target_key") != target_key:
                flushed = await self._consolidate_input_buffer()
                if flushed:
                    self._pending_steps.append(flushed)

            new_val = str(raw_event.get("value", ""))
            if not self._input_buffer:
                self._input_buffer = {
                    "target_key": target_key,
                    "target": target_raw,
                    "value": new_val,
                    "url": raw_event.get("url"),
                    "events": [raw_event],
                    "emitted": False,
                }
            else:
                self._input_buffer["value"] = new_val
                self._input_buffer["events"].append(raw_event)

            # Se já emitimos para esse target com o mesmo valor, evita duplicata
            if self._emitted_fills.get(target_key) == new_val:
                if self._pending_steps:
                    return self._pending_steps.pop(0)
                return None

            self._emitted_fills[target_key] = new_val
            self._input_buffer["emitted"] = True
            step = await self._create_fill_step(self._input_buffer)

            if self._pending_steps:
                self._pending_steps.append(step)
                return self._pending_steps.pop(0)
            return step

        if action == "blur":
            step = None
            if self._input_buffer and self._input_buffer.get("target_key") == target_key:
                val = str(self._input_buffer.get("value", ""))
                if not self._input_buffer.get("emitted") and self._emitted_fills.get(target_key) != val:
                    self._emitted_fills[target_key] = val
                    step = await self._create_fill_step(self._input_buffer)
                self._input_buffer = None

            if self._pending_steps:
                if step:
                    self._pending_steps.append(step)
                return self._pending_steps.pop(0)
            return step

        # 6. Cliques e Deduplicação de Rajadas (CA02b)
        if action == "click":
            # Consolida digitação pendente se houver
            pending_fill = await self._consolidate_input_buffer()
            if pending_fill:
                self._pending_steps.append(pending_fill)

            event_ts = raw_event.get("timestamp")
            current_ms = float(event_ts) if isinstance(event_ts, (int, float)) else time.monotonic() * 1000

            # Deduplicação de burst (< 300ms no mesmo target)
            diff_ms = current_ms - self._last_click_time_ms
            if self._last_click_target_key == target_key and 0 <= diff_ms < 300:
                logger.debug(
                    "Clique deduplicado (burst diff: %.1fms < 300ms) para target: %s",
                    diff_ms,
                    target_key,
                )
                if self._pending_steps:
                    return self._pending_steps.pop(0)
                return None

            self._last_click_target_key = target_key
            self._last_click_time_ms = current_ms

            target = await self._resolve_target(target_raw)
            click_step = RecordedStep(
                index=self._next_step_index(),
                action="click",
                target=target,
                value=raw_event.get("value"),
                url=raw_event.get("url"),
                status=StepStatus.CONFIRMED,
            )

            if self._pending_steps:
                self._pending_steps.append(click_step)
                return self._pending_steps.pop(0)
            return click_step

        # 7. Demais Ações (assert, submit, etc.)
        pending_fill = await self._consolidate_input_buffer()
        if pending_fill:
            self._pending_steps.append(pending_fill)

        target = await self._resolve_target(target_raw)
        step = RecordedStep(
            index=self._next_step_index(),
            action=action,
            target=target,
            value=raw_event.get("value"),
            url=raw_event.get("url"),
            status=StepStatus.CONFIRMED,
        )
        if self._pending_steps:
            self._pending_steps.append(step)
            return self._pending_steps.pop(0)
        return step

    async def _handle_ambiguous_event(self, raw_event: dict[str, Any]) -> RecordedStep:
        """Processa eventos ambíguos consultando o Advisor ou marcando revisão manual."""
        events = raw_event.get("events") or [raw_event]
        context = str(raw_event.get("context") or raw_event.get("url") or "")

        confidence: float | None = None
        justification: str | None = None
        suggested_step: RecordedStep | None = None

        if self.advisor and hasattr(self.advisor, "consult"):
            try:
                res = self.advisor.consult(events, context, "ambiguous_action")
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    response = await res
                else:
                    response = res

                if response is not None:
                    confidence = getattr(response, "confidence", None)
                    if confidence is None and isinstance(response, dict):
                        confidence = response.get("confidence")

                    justification = getattr(response, "justification", None)
                    if justification is None and isinstance(response, dict):
                        justification = response.get("justification")

                    step_candidate = getattr(response, "suggested_step", None)
                    if step_candidate is None and isinstance(response, dict):
                        step_candidate = response.get("suggested_step")
                    if isinstance(step_candidate, RecordedStep):
                        suggested_step = step_candidate
            except Exception as exc:
                logger.warning("Falha ao consultar RecorderAdvisor para evento ambíguo: %s", exc)

        # Regra CA15: Confiança >= 0.85 -> SUGGESTED; Confiança < 0.85 ou ausente -> PENDING_REVIEW
        if confidence is not None and confidence >= 0.85:
            status = StepStatus.SUGGESTED
        else:
            status = StepStatus.PENDING_REVIEW

        if suggested_step:
            return suggested_step.model_copy(
                update={
                    "index": self._next_step_index(),
                    "status": status,
                    "advisor_justification": justification or suggested_step.advisor_justification,
                    "advisor_confidence": confidence
                    if confidence is not None
                    else suggested_step.advisor_confidence,
                }
            )

        target = await self._resolve_target(raw_event.get("target"))
        action_name = str(raw_event.get("suggested_action") or raw_event.get("action") or "hover")
        return RecordedStep(
            index=self._next_step_index(),
            action=action_name,
            target=target,
            value=raw_event.get("value"),
            url=raw_event.get("url"),
            status=status,
            advisor_justification=justification,
            advisor_confidence=confidence,
        )

    async def flush(self) -> list[RecordedStep]:
        """Esvazia e consolida buffers pendentes (ex: digitação sem blur antes do stop).

        Returns:
            Lista de passos consolidados durante o esvaziamento.
        """
        flushed: list[RecordedStep] = []

        if self._pending_steps:
            flushed.extend(self._pending_steps)
            self._pending_steps.clear()

        if self._input_buffer:
            fill_step = await self._consolidate_input_buffer()
            if fill_step:
                flushed.append(fill_step)

        return flushed

    def pop_pending_steps(self) -> list[RecordedStep]:
        """Retorna e esvazia passos pendentes gerados por transições de eventos."""
        steps = list(self._pending_steps)
        self._pending_steps.clear()
        return steps

    async def process_event(self, source: Any, event_data: dict[str, Any]) -> RecordedStep | None:
        """Alias de compatibilidade com chamadas de binding de sessão."""
        return await self.ingest_event(event_data)
