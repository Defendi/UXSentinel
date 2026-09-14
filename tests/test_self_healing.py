"""Testes unitários e de integração herméticos para o motor de Self-Healing (Autocura).

Cobre recuperação via Árvore de Acessibilidade, Visão Multimodal LMM (mock),
propagação de eventos para TestReport, ExecutionResult, CheckpointResult e relatórios.
"""

from __future__ import annotations

import json
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uxsentinel.browser.drivers.generic_driver import GenericDriver
from uxsentinel.browser.healing import SelectorHealer
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig, load_config
from uxsentinel.core.models import (
    CheckpointResult,
    ExecutionResult,
    HealingEvent,
    HealingStrategy,
    Scenario,
    StepAction,
    TestReport,
)
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.reporter.json_builder import save_json_report
from uxsentinel.reporter.prompt_builder import build_fix_prompt
from uxsentinel.vision.client import UnifiedVisionClient


def test_search_terms_extraction():
    """Valida a extração inteligente de termos semânticos a partir de seletores e descrições."""
    healer = SelectorHealer(enabled=True)

    terms = healer._extract_search_terms("button.btn-primary.o_sale_confirm")
    assert "sale" in terms
    assert "confirm" in terms
    assert "btn" not in terms  # Stopword descartada

    terms_with_desc = healer._extract_search_terms(
        "button#salvar-pedido-btn",
        description="Clicar no botão Salvar Alterações",
    )
    assert "salvar" in terms_with_desc
    assert "pedido" in terms_with_desc
    assert "alteracoes" in terms_with_desc


def test_accessibility_scoring():
    """Valida o cálculo de pontuação de relevância de nós da árvore de acessibilidade."""
    healer = SelectorHealer(enabled=True)

    terms = ["confirmar", "pedido"]
    matching_node = {"role": "button", "name": "Confirmar Pedido"}
    score_match = healer._score_accessibility_node(matching_node, terms, action="click")

    unrelated_node = {"role": "link", "name": "Ajuda e Suporte"}
    score_unrelated = healer._score_accessibility_node(unrelated_node, terms, action="click")

    assert score_match > score_unrelated
    assert score_match >= 10.0


@pytest.mark.asyncio
async def test_healing_via_accessibility():
    """Valida a recuperação de clique através da Árvore de Acessibilidade quando o seletor original falha."""
    mock_page = AsyncMock()

    # Árvore de acessibilidade com nó compatível
    mock_page.accessibility.snapshot.return_value = {
        "role": "WebArea",
        "name": "Página de Vendas",
        "children": [
            {"role": "heading", "name": "Pedido #1024"},
            {"role": "button", "name": "Confirmar Pedido"},
        ],
    }

    # Mock do locator do Playwright
    mock_locator = AsyncMock()
    mock_locator.count.return_value = 1
    mock_locator.first.is_visible.return_value = True
    mock_locator.first.bounding_box.return_value = {"x": 100, "y": 200, "width": 80, "height": 30}

    mock_page.locator.return_value = mock_locator

    healer = SelectorHealer(enabled=True)

    event = await healer.heal_action(
        page=mock_page,
        action="click",
        selector="button.btn-primary.o_sale_confirm",
        description="Confirmar o pedido atual",
        step_index=2,
    )

    assert event is not None
    assert event.strategy == HealingStrategy.ACCESSIBILITY
    assert 'role=button[name="Confirmar Pedido"]' in (event.recovered_selector or "")
    assert "role=button" in (event.yaml_fix_suggestion or "")
    assert event.step_index == 2

    # Verifica que o locator correspondente foi clicado
    mock_locator.first.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_healing_via_vision():
    """Valida a recuperação através de visão LMM quando a árvore de acessibilidade não encontra correspondência."""
    mock_page = AsyncMock()
    mock_page.viewport_size = {"width": 1440, "height": 900}
    # Árvore sem nós compatíveis
    mock_page.accessibility.snapshot.return_value = {"role": "WebArea", "children": []}
    mock_page.screenshot.return_value = b"fake_screenshot_bytes"

    # Mock do cliente de visão IA
    mock_vision = AsyncMock(spec=UnifiedVisionClient)
    mock_vision.analyze.return_value = json.dumps(
        {
            "found": True,
            "confidence": 0.94,
            "coordinates": {"x": 480, "y": 310},
            "suggested_selector": "button.btn-confirm-action",
            "reasoning": "Botão azul centralizado com texto Confirmar",
        }
    )

    healer = SelectorHealer(vision_client=mock_vision, enabled=True)

    event = await healer.heal_action(
        page=mock_page,
        action="click",
        selector="#invalid_btn_id",
        description="Clicar em Confirmar",
        step_index=3,
    )

    assert event is not None
    assert event.strategy == HealingStrategy.VISION_COORDINATES
    assert event.coordinates == {"x": 480.0, "y": 310.0}
    assert event.recovered_selector == "button.btn-confirm-action"
    assert "button.btn-confirm-action" in (event.yaml_fix_suggestion or "")
    assert event.confidence == 0.94

    # Verifica que o clique foi realizado nas coordenadas
    mock_page.mouse.click.assert_awaited_once_with(480.0, 310.0)


@pytest.mark.asyncio
async def test_healing_fill_via_vision():
    """Valida preenchimento de campo (fill) recuperado por visão computacional."""
    mock_page = AsyncMock()
    mock_page.viewport_size = {"width": 1440, "height": 900}
    mock_page.accessibility.snapshot.return_value = None
    mock_page.screenshot.return_value = b"fake_png"

    mock_vision = AsyncMock(spec=UnifiedVisionClient)
    mock_vision.analyze.return_value = json.dumps(
        {
            "found": True,
            "confidence": 0.9,
            "coordinates": {"x": 200, "y": 150},
            "suggested_selector": "input[name='email']",
        }
    )

    healer = SelectorHealer(vision_client=mock_vision, enabled=True)

    event = await healer.heal_action(
        page=mock_page,
        action="fill",
        selector="input#missing_email",
        value="alexandre@example.com",
        description="Preencher email",
    )

    assert event is not None
    assert event.strategy == HealingStrategy.VISION_COORDINATES
    mock_page.mouse.click.assert_awaited_once_with(200.0, 150.0)
    mock_page.keyboard.type.assert_awaited_once_with("alexandre@example.com")


@pytest.mark.asyncio
async def test_driver_self_healing_integration():
    """Valida a integração transparente do Self-Healing no GenericDriver."""
    mock_page = AsyncMock()

    # O seletor original falha com TimeoutError
    mock_page.wait_for_selector.side_effect = TimeoutError("Elemento não encontrado após 1000ms")

    # Acessibilidade consegue resolver
    mock_page.accessibility.snapshot.return_value = {
        "role": "WebArea",
        "children": [{"role": "button", "name": "Salvar Dados"}],
    }
    mock_locator = AsyncMock()
    mock_locator.count.return_value = 1
    mock_locator.first.is_visible.return_value = True
    mock_locator.first.bounding_box.return_value = None
    mock_page.locator.return_value = mock_locator

    driver = GenericDriver(mock_page, highlight_clicks=False)
    driver.healer = SelectorHealer(enabled=True)

    # Não deve levantar exceção, pois o self-healing recuperará
    await driver.click("#btn_inexistente", timeout=1000, description="Salvar os dados")

    assert len(driver.healing_events) == 1
    event = driver.healing_events[0]
    assert event.strategy == HealingStrategy.ACCESSIBILITY
    assert event.original_selector == "#btn_inexistente"


@pytest.mark.asyncio
async def test_healing_disabled_raises_original_error():
    """Valida que se o self-healing estiver desabilitado, a exceção original é relançada."""
    mock_page = AsyncMock()
    mock_page.wait_for_selector.side_effect = TimeoutError("Timeout proposital")

    driver = GenericDriver(mock_page, highlight_clicks=False)
    driver.healer = SelectorHealer(enabled=False)

    with pytest.raises(TimeoutError, match="Timeout proposital"):
        await driver.click("#inexistente", timeout=1000)

    assert len(driver.healing_events) == 0


@pytest.mark.asyncio
async def test_healing_failure_raises_original_error():
    """Valida que se nem acessibilidade nem visão conseguirem recuperar, o erro é relançado."""
    mock_page = AsyncMock()
    mock_page.wait_for_selector.side_effect = TimeoutError("Falha irrecuperável")
    mock_page.accessibility.snapshot.return_value = None
    mock_page.screenshot.return_value = b"bytes"

    mock_vision = AsyncMock(spec=UnifiedVisionClient)
    mock_vision.analyze.return_value = json.dumps({"found": False})

    driver = GenericDriver(mock_page, highlight_clicks=False)
    driver.healer = SelectorHealer(vision_client=mock_vision, enabled=True)

    with pytest.raises(TimeoutError, match="Falha irrecuperável"):
        await driver.click("#inexistente", timeout=1000)

    assert len(driver.healing_events) == 0


@pytest.mark.asyncio
async def test_agent_scenario_execution_with_healing():
    """Valida a execução de ponta a ponta com o UXSentinelAgent registrando os eventos no TestReport e ExecutionResult."""
    cfg: GlobalConfig = load_config("config/config.yaml")
    cfg.browser.headless = True
    cfg.browser.self_healing = True

    agent = UXSentinelAgent(cfg)

    scenario = Scenario(
        id="cenario_healing",
        title="Cenário com Seletor Quebrado Auto-Curado",
        steps=[
            StepAction(
                action="click",
                selector="button.obsoleto",
                description="Clicar em Avançar",
            ),
            StepAction(
                action="checkpoint",
                name="cp_pos_healing",
                expected_behavior="Deve avançar com sucesso",
            ),
        ],
    )

    mock_driver = MagicMock(spec=GenericDriver)
    mock_driver.page = AsyncMock()
    mock_driver.healing_events = []

    # Simula ação click que dispara healing no driver
    async def fake_click(*args, **kwargs):
        ev = HealingEvent(
            step_index=1,
            action="click",
            original_selector="button.obsoleto",
            strategy=HealingStrategy.ACCESSIBILITY,
            recovered_selector='role=button[name="Avançar"]',
            yaml_fix_suggestion="selector: 'role=button[name=\"Avançar\"]'",
        )
        mock_driver.healing_events.append(ev)

    mock_driver.click = AsyncMock(side_effect=fake_click)
    mock_driver.get_clean_dom_text = AsyncMock(return_value="Conteúdo da página pós clique")

    with (
        patch.object(
            agent.inspector.client, "test_connection", new=AsyncMock(return_value=(True, "IA Conectada"))
        ),
        patch("uxsentinel.core.agent.open_browser_session") as mock_session_ctx,
        patch.object(
            agent.inspector,
            "inspect",
            new=AsyncMock(
                return_value=CheckpointResult(
                    name="cp_pos_healing",
                    expected_behavior="Deve avançar com sucesso",
                    status="ok",
                )
            ),
        ),
    ):
        mock_session_ctx.return_value.__aenter__.return_value = mock_driver

        report = await agent.run_scenario(scenario)

        # Valida TestReport
        assert len(report.healed_steps) == 1
        assert report.healed_steps[0].original_selector == "button.obsoleto"
        assert report.healed_steps[0].recovered_selector == 'role=button[name="Avançar"]'

        # Valida CheckpointResult
        assert len(report.checkpoints) == 1
        assert len(report.checkpoints[0].healed_events) == 1

        # Valida ExecutionResult
        assert agent.last_execution_result is not None
        assert isinstance(agent.last_execution_result, ExecutionResult)
        assert len(agent.last_execution_result.healed_events) == 1
        assert agent.last_execution_result.success is True


def test_reports_with_healing_events():
    """Valida a inclusão correta dos dados de self-healing no JSON, HTML e Fix Prompt."""
    report = TestReport(
        scenario_id="healing_report_test",
        scenario_title="Teste de Relatório com Self-Healing",
        profile="generic",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp1",
                expected_behavior="Tela sem erros",
                status="ok",
            )
        ],
        healed_steps=[
            HealingEvent(
                step_index=1,
                action="click",
                original_selector="button#velho",
                strategy=HealingStrategy.ACCESSIBILITY,
                recovered_selector='role=button[name="Novo"]',
                yaml_fix_suggestion="selector: 'role=button[name=\"Novo\"]'",
            )
        ],
    )
    report.compute_totals()

    # 1. Prompt de Correção
    prompt_text = build_fix_prompt(report)
    assert "## ⚡ Sugestões de Correção de Seletores YAML (Self-Healing)" in prompt_text
    assert "button#velho" in prompt_text
    assert "selector: 'role=button[name=\"Novo\"]'" in prompt_text

    # 2. Relatórios em disco
    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = save_json_report(report, tmpdir)
        html_file = save_html_report(report, tmpdir)

        # JSON
        json_content = json.loads(json_file.read_text(encoding="utf-8"))
        assert len(json_content.get("healed_steps", [])) == 1
        assert json_content["healed_steps"][0]["original_selector"] == "button#velho"

        # HTML
        html_content = html_file.read_text(encoding="utf-8")
        assert "Auto-Curados (Self-Healing)" in html_content
        assert "button#velho" in html_content
        assert 'role=button[name="Novo"]' in html_content
