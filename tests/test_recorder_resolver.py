"""Testes unitários herméticos para o ElementResolver (UXS-94).

Valida a inferência e a hierarquia estrita de seletores sem abrir
navegadores reais, utilizando mocks assíncronos de ElementHandle.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.browser.recorder import (
    ElementResolver,
    RecordedTarget,
    SelectorStrategy,
)


@pytest.fixture
def resolver() -> ElementResolver:
    """Fixture que fornece uma instância padrão de ElementResolver."""
    return ElementResolver()


class TestElementResolverHierarchy:
    """Valida a hierarquia estrita de resolução de seletores."""

    @pytest.mark.asyncio
    async def test_resolve_testid_primary(self, resolver: ElementResolver) -> None:
        """Nível 1: Elemento com data-testid deve gerar primary TESTID."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": "login-submit-button",
            "role": "button",
            "accessibleName": "Entrar",
            "visibleText": "Entrar",
            "cssSelector": "button.btn-primary",
            "xpath": "/html/body/form/button",
            "outerHtml": '<button data-testid="login-submit-button">Entrar</button>',
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.TESTID
        assert target.primary.value == "login-submit-button"
        assert target.primary.name is None

        # Fallbacks devem conter as estratégias subsequentes e finalizar com XPATH
        fallback_strategies = [fb.strategy for fb in target.fallbacks]
        assert SelectorStrategy.ROLE in fallback_strategies
        assert SelectorStrategy.TEXT in fallback_strategies
        assert SelectorStrategy.CSS in fallback_strategies
        assert SelectorStrategy.XPATH in fallback_strategies
        assert target.fallbacks[-1].strategy == SelectorStrategy.XPATH
        assert target.raw_html_snippet == '<button data-testid="login-submit-button">Entrar</button>'

    @pytest.mark.asyncio
    async def test_resolve_role_with_accessible_name(self, resolver: ElementResolver) -> None:
        """Nível 2: Elemento <button aria-label="Confirmar">OK</button> sem testid gera primary ROLE."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": None,
            "role": "button",
            "accessibleName": "Confirmar",
            "visibleText": "OK",
            "cssSelector": "button.btn-ok",
            "xpath": "/html/body/div/button[1]",
            "outerHtml": '<button aria-label="Confirmar" class="btn-ok">OK</button>',
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.ROLE
        assert target.primary.value == "button"
        assert target.primary.name == "Confirmar"

        # Fallbacks devem incluir o XPath canônico
        assert any(fb.strategy == SelectorStrategy.XPATH for fb in target.fallbacks)

    @pytest.mark.asyncio
    async def test_resolve_label_primary(self, resolver: ElementResolver) -> None:
        """Nível 3: Input associado a <label> gera primary LABEL."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": None,
            "role": None,  # sem role+name inequívoco
            "accessibleName": None,
            "labelText": "E-mail corporativo",
            "visibleText": None,
            "cssSelector": "input#user-email",
            "xpath": "/html/body/form/input[1]",
            "outerHtml": '<input id="user-email" type="email" />',
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.LABEL
        assert target.primary.value == "E-mail corporativo"
        assert target.primary.name is None

        # CSS e XPATH como fallbacks
        fallback_strategies = [fb.strategy for fb in target.fallbacks]
        assert SelectorStrategy.CSS in fallback_strategies
        assert SelectorStrategy.XPATH in fallback_strategies

    @pytest.mark.asyncio
    async def test_resolve_text_primary(self, resolver: ElementResolver) -> None:
        """Nível 4: Elemento com texto visível estável gera primary TEXT."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": None,
            "role": None,
            "accessibleName": None,
            "labelText": None,
            "visibleText": "Clique aqui para saber mais",
            "cssSelector": "span.info-link",
            "xpath": "/html/body/div/span",
            "outerHtml": '<span class="info-link">Clique aqui para saber mais</span>',
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.TEXT
        assert target.primary.value == "Clique aqui para saber mais"
        assert target.primary.name is None

    @pytest.mark.asyncio
    async def test_resolve_css_primary_and_xpath_fallback(self, resolver: ElementResolver) -> None:
        """Nível 5: Elemento genérico sem acessibilidade gera CSS e fallback XPATH."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": None,
            "role": None,
            "accessibleName": None,
            "labelText": None,
            "visibleText": None,
            "cssSelector": "div.card-container.active",
            "xpath": "/html/body/main/div[2]",
            "outerHtml": '<div class="card-container active"></div>',
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.CSS
        assert target.primary.value == "div.card-container.active"

        assert len(target.fallbacks) == 1
        assert target.fallbacks[0].strategy == SelectorStrategy.XPATH
        assert target.fallbacks[0].value == "/html/body/main/div[2]"

    @pytest.mark.asyncio
    async def test_resolve_xpath_only(self, resolver: ElementResolver) -> None:
        """Nível 6: Elemento sem nenhum seletor superior gera primary XPATH e zero fallbacks."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": None,
            "role": None,
            "accessibleName": None,
            "labelText": None,
            "visibleText": None,
            "cssSelector": None,
            "xpath": "/html/body/section[1]/div[3]",
            "outerHtml": "<div></div>",
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.XPATH
        assert target.primary.value == "/html/body/section[1]/div[3]"
        assert target.fallbacks == []


class TestElementResolverSpecialCases:
    """Casos especiais: alternativas de atributos de teste, role sem name e fallbacks."""

    @pytest.mark.asyncio
    async def test_resolve_alternative_testid_attributes(self, resolver: ElementResolver) -> None:
        """Atributos alternativos como data-test e data-cy devem ser reconhecidos."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "data-cy": "cypress-action-btn",
            "xpath": "/html/body/button",
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.TESTID
        assert target.primary.value == "cypress-action-btn"

    @pytest.mark.asyncio
    async def test_custom_test_id_attributes_configuration(self) -> None:
        """ElementResolver inicializado com atributos de teste customizados."""
        custom_resolver = ElementResolver(test_id_attributes=["data-qa", "qa-id"])
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "data-qa": "qa-target-123",
            "xpath": "//div",
        }

        target = await custom_resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.TESTID
        assert target.primary.value == "qa-target-123"

    @pytest.mark.asyncio
    async def test_role_without_name_falls_back_to_next_strategy(
        self,
        resolver: ElementResolver,
    ) -> None:
        """Role sem accessible name inequívoco não deve ser aceito como ROLE."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": None,
            "role": "button",
            "accessibleName": None,  # sem name
            "visibleText": "Apenas texto",
            "cssSelector": "button.ghost",
            "xpath": "/html/body/button",
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.TEXT
        assert target.primary.value == "Apenas texto"

    @pytest.mark.asyncio
    async def test_deduplication_of_fallbacks(self, resolver: ElementResolver) -> None:
        """Fallbacks idênticos não devem ser duplicados."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": "my-btn",
            "cssSelector": "button.btn",
            "xpath": "/html/body/button",
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is not None
        assert target.primary.strategy == SelectorStrategy.TESTID
        strategies = [fb.strategy for fb in target.fallbacks]
        assert len(strategies) == len(set(strategies))


class TestElementResolverErrorHandling:
    """Valida o tratamento gracioso de exceções e nós corrompidos."""

    @pytest.mark.asyncio
    async def test_resolve_evaluate_exception_with_raw_html_snippet(
        self,
        resolver: ElementResolver,
    ) -> None:
        """Elemento que lança erro no evaluate retorna primary=None e preserva raw_html_snippet."""
        mock_element = AsyncMock()
        mock_element.evaluate.side_effect = Exception("Element is detached from DOM")

        target = await resolver.resolve(
            mock_element,
            raw_html_snippet='<div class="stale-node">Erro</div>',
        )

        assert isinstance(target, RecordedTarget)
        assert target.primary is None
        assert target.fallbacks == []
        assert target.raw_html_snippet == '<div class="stale-node">Erro</div>'

    @pytest.mark.asyncio
    async def test_resolve_evaluate_exception_with_element_attribute_snippet(
        self,
        resolver: ElementResolver,
    ) -> None:
        """Snippet associado ao elemento mock é preservado quando evaluate falha."""
        mock_element = MagicMock()
        mock_element.evaluate = AsyncMock(
            side_effect=RuntimeError("Target page, context or browser has been closed")
        )
        mock_element.raw_html_snippet = "<span id='closed'>Inacessível</span>"

        target = await resolver.resolve(mock_element)

        assert target.primary is None
        assert target.fallbacks == []
        assert target.raw_html_snippet == "<span id='closed'>Inacessível</span>"

    @pytest.mark.asyncio
    async def test_resolve_evaluate_returns_non_dict(self, resolver: ElementResolver) -> None:
        """Retorno não estruturado do evaluate resulta em primary=None sem lançar exceção."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = None

        target = await resolver.resolve(mock_element)

        assert target.primary is None
        assert target.fallbacks == []
        assert target.raw_html_snippet is None

    @pytest.mark.asyncio
    async def test_resolve_empty_element_data(self, resolver: ElementResolver) -> None:
        """Elemento com dados todos vazios retorna primary=None."""
        mock_element = AsyncMock()
        mock_element.evaluate.return_value = {
            "testId": "",
            "role": "",
            "accessibleName": "",
            "labelText": "",
            "visibleText": "",
            "cssSelector": "",
            "xpath": "",
        }

        target = await resolver.resolve(mock_element)

        assert target.primary is None
        assert target.fallbacks == []
