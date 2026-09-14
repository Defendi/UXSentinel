"""Testes unitários e de integração herméticos para o Motor de Ações Semânticas (ai_action).

Cobre:
- Parsing YAML de ai_click, ai_fill, ai_assert, ai_action (chaves diretas e explícitas)
- Resolução em cascata por Árvore de Acessibilidade
- Resolução em cascata por Visão Multimodal LMM (mock)
- Execução de ai_click e ai_fill (acessibilidade e visão)
- Execução de ai_assert declarativo cognitivo (aprovado e reprovado gerando Issue)
- Execução de ai_action genérica com inferência de intenção
- Integração de ponta a ponta no UXSentinelAgent
- Renderização visual no relatório HTML
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uxsentinel.browser.drivers.generic_driver import GenericDriver
from uxsentinel.browser.semantic_actions import (
    SemanticActionError,
    SemanticActionExecutor,
    SemanticAssertResult,
)
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig, load_config
from uxsentinel.core.models import (
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    SemanticStepResult,
    SemanticStrategy,
    StepAction,
    TestReport,
)
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.scenarios.parser import load_scenario
from uxsentinel.vision.client import UnifiedVisionClient

# ==============================================================================
# 1. TESTES DE PARSING YAML
# ==============================================================================


def test_parse_semantic_scenario_yaml_direct_keys():
    """Valida o carregamento e parsing de cenários YAML com chaves semânticas diretas."""
    yaml_content = """
id: cenario_semantico_direto
title: Teste de Ações Semânticas Diretas
steps:
  - ai_click: "o botão azul de confirmar pedido"
    timeout: 5000
  - ai_fill: "campo de e-mail do cliente"
    value: "admin@gotryx.com"
  - ai_assert: "o modal de confirmação deve estar aberto com título Sucesso"
  - ai_action: "fechar o modal de confirmação"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        scenario = load_scenario(temp_path)
        assert len(scenario.steps) == 4

        # Passo 1: ai_click
        s1 = scenario.steps[0]
        assert s1.action == "ai_click"
        assert s1.ai_click == "o botão azul de confirmar pedido"
        assert s1.target == "o botão azul de confirmar pedido"
        assert s1.timeout == 5000

        # Passo 2: ai_fill
        s2 = scenario.steps[1]
        assert s2.action == "ai_fill"
        assert s2.ai_fill == "campo de e-mail do cliente"
        assert s2.target == "campo de e-mail do cliente"
        assert s2.value == "admin@gotryx.com"

        # Passo 3: ai_assert
        s3 = scenario.steps[2]
        assert s3.action == "ai_assert"
        assert s3.ai_assert == "o modal de confirmação deve estar aberto com título Sucesso"
        assert s3.target == "o modal de confirmação deve estar aberto com título Sucesso"

        # Passo 4: ai_action
        s4 = scenario.steps[3]
        assert s4.action == "ai_action"
        assert s4.ai_action == "fechar o modal de confirmação"
        assert s4.target == "fechar o modal de confirmação"

    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_parse_semantic_scenario_yaml_explicit_action():
    """Valida o parsing com a sintaxe explícita de action: ai_*."""
    yaml_content = """
id: cenario_semantico_explicito
title: Teste com action explícita
steps:
  - action: ai_click
    target: "botão salvar alterações"
  - action: ai_fill
    target: "campo de busca rápida"
    value: "laptop dell"
  - action: ai_assert
    target: "o grid de resultados deve exibir pelo menos 1 item"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        scenario = load_scenario(temp_path)
        assert len(scenario.steps) == 3
        assert scenario.steps[0].action == "ai_click"
        assert scenario.steps[0].target == "botão salvar alterações"
        assert scenario.steps[0].ai_click == "botão salvar alterações"

        assert scenario.steps[1].action == "ai_fill"
        assert scenario.steps[1].target == "campo de busca rápida"
        assert scenario.steps[1].value == "laptop dell"

        assert scenario.steps[2].action == "ai_assert"
        assert scenario.steps[2].target == "o grid de resultados deve exibir pelo menos 1 item"
        assert scenario.steps[2].ai_assert == "o grid de resultados deve exibir pelo menos 1 item"
    finally:
        Path(temp_path).unlink(missing_ok=True)


# ==============================================================================
# 2. TESTES DO MOTOR SEMÂNTICO (ACSIBILIDADE E VISÃO)
# ==============================================================================


def test_semantic_terms_and_role_inference():
    """Valida normalização, extração de termos e inferência de role para ações semânticas."""
    executor = SemanticActionExecutor(page=MagicMock())

    assert executor._normalize_text("Botão de Confirmação!") == "botao de confirmacao!"
    terms = executor._extract_terms("o botão azul de confirmar pedido")
    assert "confirmar" in terms
    assert "pedido" in terms
    assert "azul" in terms
    assert "o" not in terms  # Stopword
    assert "de" not in terms  # Stopword

    assert executor._infer_expected_role("o botão de salvar", "click") == "button"
    assert executor._infer_expected_role("o link para termos de uso", "click") == "link"
    assert executor._infer_expected_role("o campo de e-mail", "fill") == "textbox"
    assert executor._infer_expected_role("caixa de pesquisa", "fill") == "textbox"


@pytest.mark.asyncio
async def test_resolve_via_accessibility_success():
    """Valida a localização inequívoca de elemento na árvore de acessibilidade."""
    mock_page = MagicMock()
    mock_page.accessibility = MagicMock()

    fake_tree = {
        "role": "WebArea",
        "name": "Página Principal",
        "children": [
            {
                "role": "heading",
                "name": "Bem-vindo",
            },
            {
                "role": "button",
                "name": "Confirmar Pedido",
                "description": "Submete o pedido do cliente",
            },
            {
                "role": "button",
                "name": "Cancelar",
            },
        ],
    }
    mock_page.accessibility.snapshot = AsyncMock(return_value=fake_tree)

    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_first = MagicMock()
    mock_first.is_visible = AsyncMock(return_value=True)
    mock_locator.first = mock_first
    mock_page.locator.return_value = mock_locator

    executor = SemanticActionExecutor(page=mock_page)
    sel, score, node = await executor.resolve_via_accessibility("botão de confirmar pedido", action="click")

    assert sel is not None
    assert "Confirmar Pedido" in sel
    assert score > 5.0
    assert node["name"] == "Confirmar Pedido"


@pytest.mark.asyncio
async def test_resolve_via_accessibility_ambiguous_returns_none():
    """Valida que alvos ambíguos na árvore de acessibilidade retornam None para acionar a visão."""
    mock_page = MagicMock()
    mock_page.accessibility = MagicMock()

    # Dois nós com a mesma pontuação exata
    fake_tree = {
        "role": "WebArea",
        "name": "Página",
        "children": [
            {"role": "button", "name": "Excluir Registro"},
            {"role": "button", "name": "Excluir Item"},
        ],
    }
    mock_page.accessibility.snapshot = AsyncMock(return_value=fake_tree)

    executor = SemanticActionExecutor(page=mock_page)
    # Busca por "excluir" pontuará ambos com igual score
    sel, score, node = await executor.resolve_via_accessibility("botão de excluir", action="click")
    assert sel is None


@pytest.mark.asyncio
async def test_resolve_via_vision_coordinates_and_selector():
    """Valida a resolução visual via LMM quando a acessibilidade falha."""
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_png_bytes")
    mock_page.viewport_size = {"width": 1280, "height": 800}

    mock_vision_client = MagicMock(spec=UnifiedVisionClient)
    lmm_response = """
    ```json
    {
      "found": true,
      "confidence": 0.96,
      "coordinates": {"x": 640.0, "y": 420.0},
      "suggested_selector": "button.btn-primary-confirm",
      "reasoning": "Botão azul centralizado com ícone de check"
    }
    ```
    """
    mock_vision_client.analyze = AsyncMock(return_value=lmm_response)

    executor = SemanticActionExecutor(page=mock_page, vision_client=mock_vision_client)
    coords, sel, conf, reasoning = await executor.resolve_via_vision("botão de confirmar", action="click")

    assert coords == {"x": 640.0, "y": 420.0}
    assert sel == "button.btn-primary-confirm"
    assert conf == 0.96
    assert "Botão azul" in reasoning


# ==============================================================================
# 3. TESTES DE EXECUÇÃO DE AI_CLICK E AI_FILL
# ==============================================================================


@pytest.mark.asyncio
async def test_execute_ai_click_via_accessibility():
    """Valida a execução de clique quando o elemento é resolvido via acessibilidade."""
    mock_page = MagicMock()
    mock_page.accessibility.snapshot = AsyncMock(
        return_value={
            "role": "button",
            "name": "Salvar Dados",
        }
    )

    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_first = MagicMock()
    mock_first.is_visible = AsyncMock(return_value=True)
    mock_first.bounding_box = AsyncMock(return_value={"x": 100, "y": 50, "width": 80, "height": 30})
    mock_first.click = AsyncMock()
    mock_locator.first = mock_first
    mock_page.locator.return_value = mock_locator
    mock_page.evaluate = AsyncMock()

    executor = SemanticActionExecutor(page=mock_page)
    result = await executor.execute_ai_click("botão de salvar dados", step_index=1)

    assert result.action == "ai_click"
    assert result.strategy == SemanticStrategy.ACCESSIBILITY
    assert result.passed is True
    assert "Salvar Dados" in result.resolved_selector
    mock_first.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_ai_click_via_vision_coordinates():
    """Valida o clique em coordenadas físicas quando a acessibilidade não encontra o alvo."""
    mock_page = MagicMock()
    # Acessibilidade não encontra nada
    mock_page.accessibility.snapshot = AsyncMock(return_value={})
    mock_page.screenshot = AsyncMock(return_value=b"fake_bytes")
    mock_page.viewport_size = {"width": 1440, "height": 900}
    mock_page.evaluate = AsyncMock()
    mock_page.mouse.click = AsyncMock()

    # O seletor sugerido pela IA não existe no DOM
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=0)
    mock_page.locator.return_value = mock_locator

    mock_vision = MagicMock(spec=UnifiedVisionClient)
    mock_vision.analyze = AsyncMock(
        return_value=json.dumps(
            {
                "found": True,
                "confidence": 0.92,
                "coordinates": {"x": 300.0, "y": 150.0},
                "suggested_selector": ".inexistente",
                "reasoning": "Elemento visual localizado no cabeçalho",
            }
        )
    )

    executor = SemanticActionExecutor(page=mock_page, vision_client=mock_vision)
    result = await executor.execute_ai_click("ícone de ajuda no topo", step_index=2)

    assert result.action == "ai_click"
    assert result.strategy == SemanticStrategy.VISION_COORDINATES
    assert result.coordinates == {"x": 300.0, "y": 150.0}
    assert result.passed is True
    mock_page.mouse.click.assert_awaited_once_with(300.0, 150.0)


@pytest.mark.asyncio
async def test_execute_ai_click_fails_raises_semantic_error():
    """Valida que SemanticActionError é lançado quando nem acessibilidade nem visão encontram o elemento."""
    mock_page = MagicMock()
    mock_page.accessibility.snapshot = AsyncMock(return_value={})
    mock_page.screenshot = AsyncMock(return_value=b"fake_bytes")
    mock_vision = MagicMock(spec=UnifiedVisionClient)
    mock_vision.analyze = AsyncMock(return_value=json.dumps({"found": False}))

    executor = SemanticActionExecutor(page=mock_page, vision_client=mock_vision)
    with pytest.raises(SemanticActionError, match="Não foi possível localizar ou clicar"):
        await executor.execute_ai_click("botão fantasma inexistente")


@pytest.mark.asyncio
async def test_execute_ai_fill_via_accessibility():
    """Valida preenchimento semântico por acessibilidade."""
    mock_page = MagicMock()
    mock_page.accessibility.snapshot = AsyncMock(
        return_value={
            "role": "textbox",
            "name": "E-mail Corporativo",
        }
    )
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_first = MagicMock()
    mock_first.is_visible = AsyncMock(return_value=True)
    mock_first.fill = AsyncMock()
    mock_locator.first = mock_first
    mock_page.locator.return_value = mock_locator
    mock_page.evaluate = AsyncMock()

    executor = SemanticActionExecutor(page=mock_page)
    result = await executor.execute_ai_fill("campo de e-mail corporativo", "admin@empresa.com", step_index=1)

    assert result.action == "ai_fill"
    assert result.strategy == SemanticStrategy.ACCESSIBILITY
    assert result.value == "admin@empresa.com"
    mock_first.fill.assert_awaited_once_with("admin@empresa.com", timeout=10000)


@pytest.mark.asyncio
async def test_execute_ai_fill_via_vision_coordinates():
    """Valida preenchimento por coordenadas clicando para focar e digitando no teclado."""
    mock_page = MagicMock()
    mock_page.accessibility.snapshot = AsyncMock(return_value={})
    mock_page.screenshot = AsyncMock(return_value=b"fake_bytes")
    mock_page.evaluate = AsyncMock()
    mock_page.mouse.click = AsyncMock()
    mock_page.keyboard.press = AsyncMock()
    mock_page.keyboard.type = AsyncMock()

    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=0)
    mock_page.locator.return_value = mock_locator

    mock_vision = MagicMock(spec=UnifiedVisionClient)
    mock_vision.analyze = AsyncMock(
        return_value=json.dumps(
            {
                "found": True,
                "confidence": 0.88,
                "coordinates": {"x": 500.0, "y": 300.0},
                "reasoning": "Campo de texto sem label acessível",
            }
        )
    )

    executor = SemanticActionExecutor(page=mock_page, vision_client=mock_vision)
    result = await executor.execute_ai_fill("caixa de pesquisa sem rótulo", "termo_de_busca")

    assert result.strategy == SemanticStrategy.VISION_COORDINATES
    assert result.coordinates == {"x": 500.0, "y": 300.0}
    mock_page.mouse.click.assert_awaited_once_with(500.0, 300.0)
    mock_page.keyboard.type.assert_awaited_once_with("termo_de_busca")


# ==============================================================================
# 4. TESTES DE AI_ASSERT DECLARATIVO COGNITIVO
# ==============================================================================


@pytest.mark.asyncio
async def test_execute_ai_assert_passed():
    """Valida avaliação cognitiva de asserção verdadeira."""
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_bytes")

    mock_vision = MagicMock(spec=UnifiedVisionClient)
    mock_vision.analyze = AsyncMock(
        return_value=json.dumps(
            {
                "passed": True,
                "confidence": 0.99,
                "reasoning": "O modal com mensagem de sucesso está visível e ativo.",
                "severity": "ALTA",
            }
        )
    )

    executor = SemanticActionExecutor(page=mock_page, vision_client=mock_vision)
    res: SemanticAssertResult = await executor.execute_ai_assert(
        "o modal de confirmação deve estar aberto com título Sucesso"
    )

    assert res.passed is True
    assert res.confidence == 0.99
    assert "sucesso está visível" in res.reasoning


@pytest.mark.asyncio
async def test_execute_ai_assert_failed():
    """Valida avaliação cognitiva de asserção falsa retornando severidade e justificativa."""
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_bytes")

    mock_vision = MagicMock(spec=UnifiedVisionClient)
    mock_vision.analyze = AsyncMock(
        return_value=json.dumps(
            {
                "passed": False,
                "confidence": 0.95,
                "reasoning": "A tela continua na listagem e nenhum modal foi aberto.",
                "severity": "BLOQUEANTE",
                "suggestion": "Verificar se o clique no botão disparou a chamada correta.",
            }
        )
    )

    executor = SemanticActionExecutor(page=mock_page, vision_client=mock_vision)
    res: SemanticAssertResult = await executor.execute_ai_assert("o modal de confirmação deve estar aberto")

    assert res.passed is False
    assert res.severity == IssueSeverity.BLOQUEANTE
    assert "nenhum modal foi aberto" in res.reasoning
    assert res.suggestion is not None


@pytest.mark.asyncio
async def test_execute_ai_action_routing():
    """Valida o roteamento inteligente de ai_action para clique, preenchimento ou asserção."""
    mock_page = MagicMock()
    mock_page.accessibility.snapshot = AsyncMock(return_value={})
    mock_page.screenshot = AsyncMock(return_value=b"fake_bytes")
    mock_page.mouse.click = AsyncMock()
    mock_page.keyboard.type = AsyncMock()

    mock_vision = MagicMock(spec=UnifiedVisionClient)
    mock_vision.analyze = AsyncMock(
        return_value=json.dumps(
            {
                "found": True,
                "passed": True,
                "coordinates": {"x": 100, "y": 100},
                "reasoning": "OK",
            }
        )
    )

    executor = SemanticActionExecutor(page=mock_page, vision_client=mock_vision)

    # 1. Roteamento de preenchimento
    res_fill = await executor.execute_ai_action("preencher o campo de usuário", value="admin")
    assert res_fill.action == "ai_fill"
    assert res_fill.value == "admin"

    # 2. Roteamento de asserção
    res_assert = await executor.execute_ai_action("garantir que a tela exibe o título Painel")
    assert res_assert.action == "ai_action"
    assert res_assert.passed is True

    # 3. Roteamento de clique
    res_click = await executor.execute_ai_action("clicar no botão sair")
    assert res_click.action == "ai_click"


# ==============================================================================
# 5. TESTES DE INTEGRAÇÃO NO BASEDRIVER
# ==============================================================================


@pytest.mark.asyncio
async def test_driver_semantic_methods_integration():
    """Valida que GenericDriver expõe e executa os métodos ai_click, ai_fill, ai_assert e ai_action."""
    mock_page = MagicMock()
    driver = GenericDriver(mock_page)

    mock_executor = MagicMock(spec=SemanticActionExecutor)
    mock_executor.execute_ai_click = AsyncMock(
        return_value=SemanticStepResult(
            action="ai_click",
            target="alvo",
            passed=True,
            strategy=SemanticStrategy.ACCESSIBILITY,
        )
    )
    mock_executor.execute_ai_fill = AsyncMock(
        return_value=SemanticStepResult(
            action="ai_fill",
            target="campo",
            value="valor",
            passed=True,
            strategy=SemanticStrategy.ACCESSIBILITY,
        )
    )
    mock_executor.execute_ai_assert = AsyncMock(
        return_value=SemanticAssertResult(
            passed=True,
            reasoning="Validado com sucesso",
        )
    )
    mock_executor.execute_ai_action = AsyncMock(
        return_value=SemanticStepResult(
            action="ai_action",
            target="instrução",
            passed=True,
        )
    )

    driver.semantic_executor = mock_executor
    driver.wait_until_ready = AsyncMock()

    # Testa chamadas
    r_click = await driver.ai_click("alvo")
    assert r_click.action == "ai_click"
    driver.wait_until_ready.assert_awaited()

    r_fill = await driver.ai_fill("campo", "valor")
    assert r_fill.action == "ai_fill"

    r_assert = await driver.ai_assert("asserção")
    assert r_assert.passed is True

    r_action = await driver.ai_action("instrução")
    assert r_action.action == "ai_action"


# ==============================================================================
# 6. TESTE DE EXECUÇÃO DE PONTA A PONTA NO AGENTE (UXSENTINELAGENT)
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_scenario_execution_with_semantic_actions():
    """Valida a execução de cenário com ai_click, ai_fill e ai_assert com falha gerando Issue no agente."""
    cfg: GlobalConfig = load_config("config/config.yaml")
    cfg.browser.headless = True
    cfg.browser.self_healing = False

    agent = UXSentinelAgent(cfg)

    scenario = Scenario(
        id="cenario_ia_action",
        title="Cenário com Ações Semânticas em Linguagem Natural",
        steps=[
            StepAction(
                action="ai_click",
                ai_click="o botão de login principal",
                description="Clicar no botão de login",
            ),
            StepAction(
                action="ai_fill",
                ai_fill="campo de usuário",
                value="tester@gotryx.com",
            ),
            StepAction(
                action="ai_assert",
                ai_assert="o modal com título Sucesso deve estar visível",
            ),
        ],
    )

    mock_driver = MagicMock(spec=GenericDriver)
    mock_driver.page = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.highlight_clicks = True

    # Simula ai_click com sucesso
    mock_driver.ai_click = AsyncMock(
        return_value=SemanticStepResult(
            step_index=1,
            action="ai_click",
            target="o botão de login principal",
            strategy=SemanticStrategy.ACCESSIBILITY,
            resolved_selector='role=button[name="Login"]',
            passed=True,
        )
    )

    # Simula ai_fill com sucesso
    mock_driver.ai_fill = AsyncMock(
        return_value=SemanticStepResult(
            step_index=2,
            action="ai_fill",
            target="campo de usuário",
            value="tester@gotryx.com",
            strategy=SemanticStrategy.VISION_COORDINATES,
            coordinates={"x": 200, "y": 150},
            passed=True,
        )
    )

    # Simula ai_assert reprovado pelo modelo LMM
    mock_driver.ai_assert = AsyncMock(
        return_value=SemanticAssertResult(
            passed=False,
            confidence=0.97,
            reasoning="Modal com título Sucesso não foi encontrado após o login.",
            severity=IssueSeverity.BLOQUEANTE,
            suggestion="Verificar autenticação da API.",
        )
    )

    with (
        patch.object(agent.inspector.client, "test_connection", new=AsyncMock(return_value=(True, "OK"))),
        patch("uxsentinel.core.agent.open_browser_session") as mock_session_ctx,
    ):
        mock_session_ctx.return_value.__aenter__.return_value = mock_driver

        report: TestReport = await agent.run_scenario(scenario)

        # Valida que todos os 3 passos semânticos foram registrados
        assert len(report.semantic_steps) == 3
        assert report.semantic_steps[0].action == "ai_click"
        assert report.semantic_steps[1].action == "ai_fill"
        assert report.semantic_steps[2].action == "ai_assert"
        assert report.semantic_steps[2].passed is False

        # Valida que a falha na asserção cognitiva gerou uma Issue de severidade BLOQUEANTE
        assert len(report.checkpoints) >= 1
        cp = report.checkpoints[-1]
        assert cp.status == "problemas_encontrados"
        assert len(cp.issues) >= 1
        issue = cp.issues[0]
        assert issue.severidade == IssueSeverity.BLOQUEANTE
        assert issue.evaluator == "ai_assert"
        assert "Modal com título Sucesso não foi encontrado" in issue.descricao

        # O relatório geral deve estar reprovado devido à severidade BLOQUEANTE
        assert report.success is False
        assert report.total_bloqueantes >= 1


# ==============================================================================
# 7. TESTE DE RENDERIZAÇÃO NO RELATÓRIO HTML
# ==============================================================================


def test_html_report_rendering_with_semantic_steps():
    """Valida que o relatório HTML exibe a métrica e a seção visual de ações semânticas."""
    report = TestReport(
        scenario_id="cenario_html_semantic",
        scenario_title="Cenário Semântico HTML",
        profile="generic",
        provider_used="anthropic_cloud",
        semantic_steps=[
            SemanticStepResult(
                step_index=1,
                action="ai_click",
                target="botão azul de prosseguir",
                strategy=SemanticStrategy.ACCESSIBILITY,
                resolved_selector='role=button[name="Prosseguir"]',
                confidence=0.95,
                passed=True,
                reasoning="Elemento localizado na árvore de acessibilidade",
            ),
            SemanticStepResult(
                step_index=2,
                action="ai_fill",
                target="campo de cupom promocional",
                value="DESCONTO10",
                strategy=SemanticStrategy.VISION_COORDINATES,
                coordinates={"x": 420.0, "y": 180.0},
                confidence=0.88,
                passed=True,
                reasoning="Foco via coordenadas visuais e preenchimento",
            ),
            SemanticStepResult(
                step_index=3,
                action="ai_assert",
                target="mensagem de desconto aplicado deve ser exibida",
                strategy=SemanticStrategy.LMM_ASSERTION,
                confidence=0.92,
                passed=False,
                reasoning="Mensagem de desconto não encontrada na tela.",
            ),
        ],
        checkpoints=[
            CheckpointResult(
                name="cp_final",
                expected_behavior="Finalizado",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.REGRA_NEGOCIO,
                        severidade=IssueSeverity.BLOQUEANTE,
                        descricao="Falha na asserção semântica de desconto",
                        evaluator="ai_assert",
                    )
                ],
            )
        ],
    )
    report.compute_totals()

    with tempfile.TemporaryDirectory() as tmp_dir:
        report_file = save_html_report(report, tmp_dir)

        assert report_file.is_file()
        content = report_file.read_text(encoding="utf-8")

        # Verifica o card de métrica
        assert "Ações Semânticas (IA)" in content
        assert "3" in content

        # Verifica a seção dedicada de Ações Semânticas
        assert "Ações Semânticas em Linguagem Natural (ai_action)" in content
        assert "botão azul de prosseguir" in content
        assert "campo de cupom promocional" in content
        assert "DESCONTO10" in content
        assert "mensagem de desconto aplicado deve ser exibida" in content
        assert "Aprovado" in content
        assert "Reprovado" in content
        assert "Mensagem de desconto não encontrada na tela." in content
