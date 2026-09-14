from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.core.config import GlobalConfig, VisionSettings
from uxsentinel.core.models import Issue, IssueCategory, IssueSeverity
from uxsentinel.vision.evaluators.base import BaseEvaluator, EvaluatorContext
from uxsentinel.vision.evaluators.domain import DomainQAAgent
from uxsentinel.vision.evaluators.layout import LayoutAgent
from uxsentinel.vision.evaluators.leakage import LeakageSentinel
from uxsentinel.vision.evaluators.linguist import LinguistAgent
from uxsentinel.vision.evaluators.orchestrator import MixtureOfEvaluators
from uxsentinel.vision.inspector import ScreenInspector


@pytest.fixture
def mock_vision_client():
    client = MagicMock()
    client.analyze = AsyncMock()
    return client


@pytest.fixture
def sample_context():
    return EvaluatorContext(
        checkpoint_name="cp_pedido_venda",
        expected_behavior="O pedido de venda deve estar confirmado com status 'Pedido de Venda'.",
        image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        dom_text="<div><button>Discard</button><span class='badge'>user_id</span></div>",
        description="Verifica status e botões de ação",
        viewport="desktop (1440x900)",
    )


# ==============================================================================
# Testes Unitários de Avaliadores Isolados
# ==============================================================================


@pytest.mark.asyncio
async def test_linguist_agent_detects_untranslated_terms(mock_vision_client, sample_context):
    mock_vision_client.analyze.return_value = """
    ```json
    {
      "issues": [
        {
          "categoria": "traducao",
          "severidade": "media",
          "descricao": "Botão 'Discard' exibido em inglês.",
          "sugestao_correcao": "Alterar para 'Descartar'.",
          "elemento_alvo": "button.btn-discard"
        }
      ]
    }
    ```
    """

    agent = LinguistAgent(mock_vision_client)
    issues = await agent.evaluate(sample_context)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.evaluator == "Linguist Agent"
    assert issue.categoria == IssueCategory.TRADUCAO
    assert issue.severidade == IssueSeverity.MEDIA
    assert "Discard" in issue.descricao
    assert issue.elemento_alvo == "button.btn-discard"
    assert issue.viewport == "desktop (1440x900)"

    # Verifica se chamou analyze com o system_prompt específico do Linguist
    mock_vision_client.analyze.assert_called_once()
    _, kwargs = mock_vision_client.analyze.call_args
    assert "Linguist Agent" in kwargs["system_prompt"]
    assert "Português do Brasil" in kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_linguist_agent_empty_when_no_issues(mock_vision_client, sample_context):
    mock_vision_client.analyze.return_value = '{"issues": []}'

    agent = LinguistAgent(mock_vision_client)
    issues = await agent.evaluate(sample_context)

    assert issues == []


@pytest.mark.asyncio
async def test_leakage_sentinel_detects_snake_case_and_technical_id(mock_vision_client, sample_context):
    mock_vision_client.analyze.return_value = """
    {
      "issues": [
        {
          "categoria": "texto_tecnico",
          "severidade": "alta",
          "descricao": "Coluna com identificador técnico 'partner_id' visível na tabela.",
          "sugestao_correcao": "Substituir por 'Cliente / Parceiro'.",
          "elemento_alvo": "th[data-name='partner_id']"
        },
        {
          "categoria": "texto_tecnico",
          "severidade": "media",
          "descricao": "Prefixo de ERP 'x_studio_campo' exposto no formulário.",
          "sugestao_correcao": "Configurar rótulo amigável na visão.",
          "elemento_alvo": "label[for='x_studio_campo']"
        }
      ]
    }
    """

    sentinel = LeakageSentinel(mock_vision_client)
    issues = await sentinel.evaluate(sample_context)

    assert len(issues) == 2
    assert all(i.evaluator == "Leakage Sentinel" for i in issues)
    assert issues[0].categoria == IssueCategory.TEXTO_TECNICO
    assert issues[0].severidade == IssueSeverity.ALTA
    assert "partner_id" in issues[0].descricao
    assert issues[1].severidade == IssueSeverity.MEDIA
    assert "x_studio_campo" in issues[1].descricao

    _, kwargs = mock_vision_client.analyze.call_args
    assert "Leakage Sentinel" in kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_layout_agent_detects_modal_cut_off(mock_vision_client, sample_context):
    mock_vision_client.analyze.return_value = """
    {
      "issues": [
        {
          "categoria": "layout_modal",
          "severidade": "bloqueante",
          "descricao": "Botão 'Confirmar' do rodapé do modal cortado pela borda inferior da viewport.",
          "sugestao_correcao": "Adicionar max-height e overflow-y: auto ao container do modal.",
          "elemento_alvo": "div.modal-footer button.btn-primary"
        }
      ]
    }
    """

    layout = LayoutAgent(mock_vision_client)
    issues = await layout.evaluate(sample_context)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.evaluator == "Layout & Modal Agent"
    assert issue.categoria == IssueCategory.LAYOUT_MODAL
    assert issue.severidade == IssueSeverity.BLOQUEANTE
    assert "cortado" in issue.descricao

    _, kwargs = mock_vision_client.analyze.call_args
    assert "Layout & Modal Agent" in kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_domain_qa_agent_detects_business_rule_divergence(mock_vision_client, sample_context):
    mock_vision_client.analyze.return_value = """
    {
      "issues": [
        {
          "categoria": "regra_negocio",
          "severidade": "alta",
          "descricao": "O documento permaneceu em 'Cotação' ao invés de transicionar para 'Pedido de Venda'.",
          "sugestao_correcao": "Verificar se o clique no botão de confirmação disparou a ação de backend.",
          "elemento_alvo": "div.o_statusbar_status"
        }
      ]
    }
    """

    domain = DomainQAAgent(mock_vision_client)
    issues = await domain.evaluate(sample_context)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.evaluator == "Domain QA Agent"
    assert issue.categoria == IssueCategory.REGRA_NEGOCIO
    assert issue.severidade == IssueSeverity.ALTA
    assert "Cotação" in issue.descricao

    _, kwargs = mock_vision_client.analyze.call_args
    assert "Domain QA Agent" in kwargs["system_prompt"]


# ==============================================================================
# Testes do Orquestrador (MixtureOfEvaluators)
# ==============================================================================


@pytest.mark.asyncio
async def test_orchestrator_runs_all_evaluators_in_parallel(sample_context):
    cfg = GlobalConfig()

    evaluator1 = MagicMock(spec=BaseEvaluator)
    evaluator1.name = "Evaluator 1"
    evaluator1.evaluate = AsyncMock(
        return_value=[
            Issue(
                categoria=IssueCategory.TRADUCAO,
                severidade=IssueSeverity.MEDIA,
                descricao="Texto em inglês",
                evaluator="Evaluator 1",
            )
        ]
    )

    evaluator2 = MagicMock(spec=BaseEvaluator)
    evaluator2.name = "Evaluator 2"
    evaluator2.evaluate = AsyncMock(
        return_value=[
            Issue(
                categoria=IssueCategory.TEXTO_TECNICO,
                severidade=IssueSeverity.ALTA,
                descricao="ID de banco cru",
                evaluator="Evaluator 2",
            )
        ]
    )

    orchestrator = MixtureOfEvaluators(cfg, evaluators=[evaluator1, evaluator2])
    results = await orchestrator.evaluate(sample_context)

    evaluator1.evaluate.assert_awaited_once_with(sample_context)
    evaluator2.evaluate.assert_awaited_once_with(sample_context)
    assert len(results) == 2
    # Ordenado por severidade: ALTA primeiro, depois MEDIA
    assert results[0].severidade == IssueSeverity.ALTA
    assert results[1].severidade == IssueSeverity.MEDIA


@pytest.mark.asyncio
async def test_orchestrator_deduplication_and_merging():
    cfg = GlobalConfig()
    orchestrator = MixtureOfEvaluators(cfg, evaluators=[])

    # Dois avaliadores detectam o mesmo problema com severidades e nomes diferentes
    issue_linguist = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.MEDIA,
        descricao="Termo técnico em inglês 'partner_id' exibido no cabeçalho",
        sugestao_correcao="Traduzir para 'Cliente'",
        elemento_alvo="th.partner_col",
        evaluator="Linguist Agent",
    )

    issue_leakage = Issue(
        categoria=IssueCategory.TEXTO_TECNICO,
        severidade=IssueSeverity.ALTA,
        descricao="Termo técnico em inglês 'partner_id' exibido no cabeçalho (snake_case)",
        sugestao_correcao="Substituir nome de coluna cru por rótulo amigável de negócio",
        elemento_alvo="th.partner_col",
        evaluator="Leakage Sentinel",
    )

    issue_layout = Issue(
        categoria=IssueCategory.LAYOUT_MODAL,
        severidade=IssueSeverity.BAIXA,
        descricao="Pequeno desalinhamento de 2px no cabeçalho",
        elemento_alvo="header.top-bar",
        evaluator="Layout & Modal Agent",
    )

    consolidated = orchestrator.consolidate_and_deduplicate([issue_linguist, issue_leakage, issue_layout])

    assert len(consolidated) == 2
    merged = consolidated[0]
    # Severidade mais alta preservada (ALTA > MEDIA)
    assert merged.severidade == IssueSeverity.ALTA
    # Rastreamento de ambos os agentes que detectaram
    assert "Leakage Sentinel" in merged.evaluator
    assert "Linguist Agent" in merged.evaluator
    assert merged.elemento_alvo == "th.partner_col"

    # Segunda issue (não duplicada) permaneceu intacta
    assert consolidated[1].elemento_alvo == "header.top-bar"
    assert consolidated[1].severidade == IssueSeverity.BAIXA


@pytest.mark.asyncio
async def test_orchestrator_partial_failure_tolerance(sample_context):
    cfg = GlobalConfig()

    failing_evaluator = MagicMock(spec=BaseEvaluator)
    failing_evaluator.name = "Failing Agent"
    failing_evaluator.evaluate = AsyncMock(side_effect=RuntimeError("Timeout de rede com o provedor"))

    working_evaluator = MagicMock(spec=BaseEvaluator)
    working_evaluator.name = "Working Agent"
    working_evaluator.evaluate = AsyncMock(
        return_value=[
            Issue(
                categoria=IssueCategory.REGRA_NEGOCIO,
                severidade=IssueSeverity.ALTA,
                descricao="Total diverge do esperado",
                evaluator="Working Agent",
            )
        ]
    )

    orchestrator = MixtureOfEvaluators(cfg, evaluators=[failing_evaluator, working_evaluator])
    results = await orchestrator.evaluate(sample_context)

    # Não deve lançar exceção! O avaliador que funcionou deve entregar o resultado normalmente
    assert len(results) == 1
    assert results[0].descricao == "Total diverge do esperado"
    assert results[0].evaluator == "Working Agent"


# ==============================================================================
# Testes de Integração com ScreenInspector
# ==============================================================================


@pytest.mark.asyncio
async def test_screen_inspector_uses_mixture_when_enabled(tmp_path):
    img_file = tmp_path / "screen.png"
    img_file.write_bytes(b"dummy_png_bytes")

    cfg = GlobalConfig(vision=VisionSettings(use_mixture_of_evaluators=True))

    mock_mixture = MagicMock(spec=MixtureOfEvaluators)
    mock_mixture.evaluate = AsyncMock(
        return_value=[
            Issue(
                categoria=IssueCategory.TRADUCAO,
                severidade=IssueSeverity.MEDIA,
                descricao="Botão não traduzido",
                evaluator="Linguist Agent",
            )
        ]
    )

    inspector = ScreenInspector(cfg, mixture=mock_mixture)
    result = await inspector.inspect(
        checkpoint_name="cp_teste",
        expected_behavior="Tudo em português",
        screenshot_path=str(img_file),
    )

    mock_mixture.evaluate.assert_awaited_once()
    assert result.status == "problemas_encontrados"
    assert len(result.issues) == 1
    assert result.issues[0].evaluator == "Linguist Agent"


@pytest.mark.asyncio
async def test_screen_inspector_falls_back_to_monolith_when_disabled(tmp_path):
    img_file = tmp_path / "screen.png"
    img_file.write_bytes(b"dummy_png_bytes")

    cfg = GlobalConfig(vision=VisionSettings(use_mixture_of_evaluators=False))

    mock_mixture = MagicMock(spec=MixtureOfEvaluators)
    mock_mixture.evaluate = AsyncMock()

    inspector = ScreenInspector(cfg, mixture=mock_mixture)
    inspector.client = MagicMock()
    inspector.client.analyze = AsyncMock(return_value='{"status": "ok", "issues": []}')

    result = await inspector.inspect(
        checkpoint_name="cp_teste",
        expected_behavior="Tela sem problemas",
        screenshot_path=str(img_file),
    )

    # Não deve ter chamado a mistura multiagente
    mock_mixture.evaluate.assert_not_called()
    inspector.client.analyze.assert_awaited_once()
    assert result.status == "ok"
    assert result.issues == []


@pytest.mark.asyncio
async def test_screen_inspector_mixture_critical_fallback(tmp_path):
    img_file = tmp_path / "screen.png"
    img_file.write_bytes(b"dummy_png_bytes")

    cfg = GlobalConfig(vision=VisionSettings(use_mixture_of_evaluators=True))

    mock_mixture = MagicMock(spec=MixtureOfEvaluators)
    # Simula falha crítica inesperada no orquestrador
    mock_mixture.evaluate = AsyncMock(side_effect=Exception("Falha crítica inexperada"))

    inspector = ScreenInspector(cfg, mixture=mock_mixture)
    inspector.client = MagicMock()
    inspector.client.analyze = AsyncMock(return_value='{"status": "ok", "issues": []}')

    result = await inspector.inspect(
        checkpoint_name="cp_teste",
        expected_behavior="Tela sem problemas",
        screenshot_path=str(img_file),
    )

    # Deve ter tentado a mistura, falhado e feito fallback com sucesso para o monólito clássico
    mock_mixture.evaluate.assert_awaited_once()
    inspector.client.analyze.assert_awaited_once()
    assert result.status == "ok"
