"""Testes unitários herméticos para o EventNormalizer (UXS-96).

Valida a normalização de eventos brutos de DOM e navegador:
- Filtragem de ruídos técnicos (mousemove, scroll, wheel, resize)
- Deduplicação de rajadas de cliques (< 300ms) (CA02b)
- Agrupamento de sequências de digitação em passos 'fill'
- Resolução de navegações ('framenavigated' -> 'navigate')
- Seleção de opções em dropdowns (<select> -> 'select')
- Flush de buffers pendentes no encerramento da gravação
- Classificação de eventos ambíguos via Advisor (SUGGESTED vs PENDING_REVIEW) (CA15)
- Integração hermética entre RecorderSession e EventNormalizer
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.browser.recorder import (
    ElementResolver,
    EventNormalizer,
    RecordedTarget,
    RecorderSession,
    SelectorCandidate,
    SelectorStrategy,
    StepStatus,
)


@pytest.fixture
def mock_resolver() -> AsyncMock:
    """Fixture de mock assíncrono para ElementResolver."""
    resolver = AsyncMock(spec=ElementResolver)
    target = RecordedTarget(
        primary=SelectorCandidate(
            strategy=SelectorStrategy.TESTID,
            value="input-nome",
        ),
        fallbacks=[],
        raw_html_snippet="<input data-testid='input-nome' />",
    )
    resolver.resolve = AsyncMock(return_value=target)
    resolver.resolve_target_data = MagicMock(return_value=target)
    resolver._build_target = MagicMock(return_value=target)
    return resolver


@pytest.fixture
def mock_advisor() -> AsyncMock:
    """Fixture de mock assíncrono para RecorderAdvisor."""
    advisor = AsyncMock()
    advisor.consult = AsyncMock()
    return advisor


class TestEventNormalizerNoiseFiltering:
    """Valida o descarte sumário de ruídos técnicos do navegador."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "noise_action",
        [
            "mousemove",
            "pointermove",
            "pointerover",
            "pointerout",
            "wheel",
            "scroll",
            "resize",
        ],
    )
    async def test_noise_events_return_none(self, noise_action: str, mock_resolver: AsyncMock) -> None:
        """Eventos técnicos de movimentação e scroll devem ser descartados sem gerar passos."""
        normalizer = EventNormalizer(resolver=mock_resolver)
        event = {
            "action": noise_action,
            "target": {"tagName": "div"},
            "timestamp": 1000.0,
        }
        step = await normalizer.ingest_event(event)
        assert step is None
        assert normalizer._step_counter == 0


class TestEventNormalizerClickBurstDeduplication:
    """Valida a deduplicação de rajadas temporais de cliques (< 300ms) (CA02b)."""

    @pytest.mark.asyncio
    async def test_click_burst_within_300ms_is_deduplicated(self, mock_resolver: AsyncMock) -> None:
        """Cliques rápidos no mesmo alvo em menos de 300ms processam apenas o primeiro."""
        normalizer = EventNormalizer(resolver=mock_resolver)
        target_dict = {
            "tagName": "button",
            "testId": "btn-enviar",
            "outerHtml": "<button data-testid='btn-enviar'>Enviar</button>",
        }

        # Primeiro clique em t = 1000ms
        step1 = await normalizer.ingest_event(
            {
                "action": "click",
                "target": target_dict,
                "url": "https://example.com/checkout",
                "timestamp": 1000.0,
            }
        )
        assert step1 is not None
        assert step1.action == "click"
        assert step1.index == 0
        assert step1.status == StepStatus.CONFIRMED

        # Segundo clique no mesmo alvo em t = 1150ms (diff: 150ms < 300ms)
        step2 = await normalizer.ingest_event(
            {
                "action": "click",
                "target": target_dict,
                "url": "https://example.com/checkout",
                "timestamp": 1150.0,
            }
        )
        assert step2 is None

        # Terceiro clique no mesmo alvo em t = 1250ms (diff: 250ms < 300ms)
        step3 = await normalizer.ingest_event(
            {
                "action": "click",
                "target": target_dict,
                "url": "https://example.com/checkout",
                "timestamp": 1250.0,
            }
        )
        assert step3 is None

        # Quarto clique após 350ms em t = 1350ms (diff: 350ms >= 300ms em relação a 1000ms)
        step4 = await normalizer.ingest_event(
            {
                "action": "click",
                "target": target_dict,
                "url": "https://example.com/checkout",
                "timestamp": 1350.0,
            }
        )
        assert step4 is not None
        assert step4.action == "click"
        assert step4.index == 1

    @pytest.mark.asyncio
    async def test_clicks_on_different_targets_are_not_deduplicated(self, mock_resolver: AsyncMock) -> None:
        """Cliques em elementos distintos não sofrem deduplicação de burst."""
        normalizer = EventNormalizer(resolver=mock_resolver)

        step1 = await normalizer.ingest_event(
            {
                "action": "click",
                "target": {"testId": "btn-item-1"},
                "timestamp": 1000.0,
            }
        )
        assert step1 is not None

        step2 = await normalizer.ingest_event(
            {
                "action": "click",
                "target": {"testId": "btn-item-2"},
                "timestamp": 1050.0,  # 50ms depois, mas elemento diferente
            }
        )
        assert step2 is not None
        assert step1.index == 0
        assert step2.index == 1


class TestEventNormalizerTypingSequence:
    """Valida o agrupamento de digitação em passos 'fill'."""

    @pytest.mark.asyncio
    async def test_full_typing_sequence_emits_single_confirmed_fill(self, mock_resolver: AsyncMock) -> None:
        """Cenário 1: focus -> input -> input -> change -> blur gera um único fill confirmado."""
        normalizer = EventNormalizer(resolver=mock_resolver)
        target = {
            "tagName": "input",
            "testId": "campo-email",
            "outerHtml": "<input data-testid='campo-email' />",
        }
        url = "https://example.com/cadastro"

        # 1. focus
        s1 = await normalizer.ingest_event({"action": "focus", "target": target, "url": url})
        assert s1 is None

        # 2. input ("a")
        s2 = await normalizer.ingest_event({"action": "input", "target": target, "value": "a", "url": url})
        assert s2 is None

        # 3. input ("alexandre@example.com")
        s3 = await normalizer.ingest_event(
            {
                "action": "input",
                "target": target,
                "value": "alexandre@example.com",
                "url": url,
            }
        )
        assert s3 is None

        # 4. change ("alexandre@example.com")
        s4 = await normalizer.ingest_event(
            {
                "action": "change",
                "target": target,
                "value": "alexandre@example.com",
                "url": url,
            }
        )
        assert s4 is not None
        assert s4.action == "fill"
        assert s4.value == "alexandre@example.com"
        assert s4.status == StepStatus.CONFIRMED
        assert s4.index == 0

        # 5. blur (com o mesmo elemento/valor) não duplica
        s5 = await normalizer.ingest_event({"action": "blur", "target": target, "url": url})
        assert s5 is None

    @pytest.mark.asyncio
    async def test_blur_emits_fill_if_no_change_occurred(self, mock_resolver: AsyncMock) -> None:
        """Digitação seguida diretamente de blur sem evento de change emite o fill."""
        normalizer = EventNormalizer(resolver=mock_resolver)
        target = {"testId": "campo-sobrenome"}

        await normalizer.ingest_event({"action": "focus", "target": target})
        await normalizer.ingest_event({"action": "input", "target": target, "value": "Defendi"})

        step = await normalizer.ingest_event({"action": "blur", "target": target})
        assert step is not None
        assert step.action == "fill"
        assert step.value == "Defendi"
        assert step.status == StepStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_flush_emits_uncommitted_input_step(self, mock_resolver: AsyncMock) -> None:
        """Cenário 5: flush() emite passo acumulado que não recebeu blur."""
        normalizer = EventNormalizer(resolver=mock_resolver)
        target = {"testId": "campo-mensagem"}

        await normalizer.ingest_event({"action": "focus", "target": target})
        await normalizer.ingest_event(
            {
                "action": "input",
                "target": target,
                "value": "Texto em digitação antes do stop",
            }
        )

        # Encerramento antes do blur
        flushed_steps = await normalizer.flush()
        assert len(flushed_steps) == 1
        step = flushed_steps[0]
        assert step.action == "fill"
        assert step.value == "Texto em digitação antes do stop"
        assert step.status == StepStatus.CONFIRMED

        # Chamada subsequente de flush com buffer vazio retorna lista vazia
        second_flush = await normalizer.flush()
        assert second_flush == []


class TestEventNormalizerNavigationAndSelect:
    """Valida normalização de navegações de página e seleção em dropdowns."""

    @pytest.mark.asyncio
    async def test_framenavigated_emits_navigate_step(self, mock_resolver: AsyncMock) -> None:
        """Cenário 4: Mudança de URL (framenavigated) gerando passo navigate."""
        normalizer = EventNormalizer(resolver=mock_resolver)

        step = await normalizer.ingest_event(
            {
                "action": "framenavigated",
                "url": "https://example.com/dashboard",
            }
        )
        assert step is not None
        assert step.action == "navigate"
        assert step.url == "https://example.com/dashboard"
        assert step.status == StepStatus.CONFIRMED
        assert step.index == 0

    @pytest.mark.asyncio
    async def test_select_dropdown_emits_select_step(self, mock_resolver: AsyncMock) -> None:
        """Seleção em elemento <select> emite passo select com opção correspondente."""
        normalizer = EventNormalizer(resolver=mock_resolver)
        target = {
            "tagName": "select",
            "name": "estado",
            "id": "uf-select",
        }

        step = await normalizer.ingest_event(
            {
                "action": "change",
                "target": target,
                "value": "SP",
                "url": "https://example.com/perfil",
            }
        )
        assert step is not None
        assert step.action == "select"
        assert step.value == "SP"
        assert step.status == StepStatus.CONFIRMED


class TestEventNormalizerAmbiguousEventsAndAdvisor:
    """Valida o tratamento de ambiguidades e integração com o Advisor (CA15)."""

    @pytest.mark.asyncio
    async def test_ambiguous_event_with_high_confidence_advisor(
        self, mock_resolver: AsyncMock, mock_advisor: AsyncMock
    ) -> None:
        """Cenário 6a: Caso ambíguo aciona Advisor retornando confiança 0.90 -> SUGGESTED."""
        advisor_response = MagicMock()
        advisor_response.confidence = 0.90
        advisor_response.justification = "Interação consistente com expansão intencional de menu dropdown"
        advisor_response.suggested_step = None
        mock_advisor.consult.return_value = advisor_response

        normalizer = EventNormalizer(resolver=mock_resolver, advisor=mock_advisor)

        raw_event = {
            "action": "hover",
            "is_ambiguous": True,
            "target": {"testId": "menu-dropdown"},
            "url": "https://example.com/nav",
        }

        step = await normalizer.ingest_event(raw_event)
        assert step is not None
        assert step.status == StepStatus.SUGGESTED
        assert step.advisor_confidence == 0.90
        assert step.advisor_justification == "Interação consistente com expansão intencional de menu dropdown"
        mock_advisor.consult.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ambiguous_event_with_low_confidence_advisor(
        self, mock_resolver: AsyncMock, mock_advisor: AsyncMock
    ) -> None:
        """Cenário 6b: Caso ambíguo aciona Advisor retornando confiança 0.60 -> PENDING_REVIEW."""
        advisor_response = MagicMock()
        advisor_response.confidence = 0.60
        advisor_response.justification = "Incerteza entre foco acidental de mouse e clique abortado"
        advisor_response.suggested_step = None
        mock_advisor.consult.return_value = advisor_response

        normalizer = EventNormalizer(resolver=mock_resolver, advisor=mock_advisor)

        raw_event = {
            "action": "ambiguous",
            "target": {"testId": "banner-promo"},
            "url": "https://example.com/home",
        }

        step = await normalizer.ingest_event(raw_event)
        assert step is not None
        assert step.status == StepStatus.PENDING_REVIEW
        assert step.advisor_confidence == 0.60
        assert step.advisor_justification == "Incerteza entre foco acidental de mouse e clique abortado"
        mock_advisor.consult.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ambiguous_event_without_advisor_marks_pending_review(
        self, mock_resolver: AsyncMock
    ) -> None:
        """Cenário 7: Caso ambíguo com advisor=None marca diretamente como PENDING_REVIEW."""
        normalizer = EventNormalizer(resolver=mock_resolver, advisor=None)

        raw_event = {
            "action": "hover_long",
            "is_ambiguous": True,
            "target": {"testId": "tooltip-ajuda"},
            "url": "https://example.com/ajuda",
        }

        step = await normalizer.ingest_event(raw_event)
        assert step is not None
        assert step.status == StepStatus.PENDING_REVIEW
        assert step.advisor_confidence is None
        assert step.advisor_justification is None


class TestEventNormalizerIntegrationWithSession:
    """Valida a integração hermética do EventNormalizer na RecorderSession."""

    @pytest.mark.asyncio
    async def test_session_uses_normalizer_and_flushes_on_stop(self, tmp_path: Any) -> None:
        """RecorderSession ingere eventos via normalizer e esvazia buffer no stop()."""
        normalizer = EventNormalizer()
        session = RecorderSession(
            session_id="test-sess-normalizer",
            name="Normalizer Integrado",
            url="https://example.com",
            scenario_output_dir=tmp_path,
            normalizer=normalizer,
        )

        # 1. Simula digitação em campo sem blur prévio
        await session._handle_dom_event(
            source=None,
            event_data={
                "action": "input",
                "value": "alexandre@defendi.org",
                "target": {
                    "tagName": "input",
                    "testId": "user-email",
                },
                "url": "https://example.com/login",
            },
        )
        # Nenhuma ação emitida ainda porque está no buffer do normalizer
        assert len(session.workflow.steps) == 0

        # 2. Chama stop() que aciona normalizer.flush()
        res = await session.stop()
        assert res["saved"] is True

        # O passo fill foi descarregado e salvo no workflow
        assert len(session.workflow.steps) == 1
        saved_step = session.workflow.steps[0]
        assert saved_step.action == "fill"
        assert saved_step.value == "alexandre@defendi.org"
        assert saved_step.status == StepStatus.CONFIRMED
