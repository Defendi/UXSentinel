import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.browser.dom_validator import DOMAnomalyType, DOMValidator
from uxsentinel.browser.drivers.generic_driver import GenericDriver
from uxsentinel.browser.som import InteractiveMark, SetOfMarksManager
from uxsentinel.core.config import GlobalConfig, VisionSettings
from uxsentinel.core.models import Issue, IssueCategory, IssueSeverity
from uxsentinel.vision.arbiter import DevilsAdvocateArbiter
from uxsentinel.vision.evaluators.base import EvaluatorContext
from uxsentinel.vision.evaluators.linguist import LinguistAgent, LinguistEvaluator
from uxsentinel.vision.inspector import ScreenInspector


@pytest.fixture
def mock_vision_client():
    client = MagicMock()
    client.analyze = AsyncMock()
    return client


@pytest.fixture
def sample_context():
    return EvaluatorContext(
        checkpoint_name="cp_dashboard_crm",
        expected_behavior="A página inicial do CRM deve exibir cards e gráficos em português.",
        image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        dom_text="<div><button>Submit</button><span class='title'>Status do Lead</span></div>",
        description="Auditoria do dashboard inicial",
        viewport="desktop (1440x900)",
    )


# ==============================================================================
# 1. Glossário Corporativo e Allowlist i18n
# ==============================================================================


def test_linguist_allowlist_identifies_permitted_terms():
    client = MagicMock()
    evaluator = LinguistEvaluator(client)

    # Termos permitidos devem ser identificados como falso positivo
    allowed_issue_1 = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.ALTA,
        descricao="Termo 'Status' não foi traduzido.",
        elemento_alvo="Status",
    )
    assert evaluator.is_allowlisted(allowed_issue_1) is True

    allowed_issue_2 = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.MEDIA,
        descricao="Substituir 'Dashboard' por 'Painel de Controle'.",
        elemento_alvo=".dashboard-title",
    )
    assert evaluator.is_allowlisted(allowed_issue_2) is True

    allowed_issue_3 = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.MEDIA,
        descricao="Campo 'Lead' em inglês.",
        elemento_alvo="input#lead",
    )
    assert evaluator.is_allowlisted(allowed_issue_3) is True

    allowed_issue_login = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.ALTA,
        descricao="Botão com rótulo 'Login' em inglês.",
        elemento_alvo="button#login",
    )
    assert evaluator.is_allowlisted(allowed_issue_login) is True


def test_linguist_allowlist_retains_untranslated_non_corporate_terms():
    client = MagicMock()
    evaluator = LinguistAgent(client)

    # Termos gerais de UI não estão no allowlist e devem ser mantidos como erros reais
    real_issue_1 = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.ALTA,
        descricao="Botão primário 'Submit' exibido em inglês.",
        elemento_alvo="button.btn-submit",
        sugestao_correcao="Substituir por 'Enviar'",
    )
    assert evaluator.is_allowlisted(real_issue_1) is False

    real_issue_2 = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.MEDIA,
        descricao="Ação 'Discard' em inglês.",
        elemento_alvo="button.btn-discard",
    )
    assert evaluator.is_allowlisted(real_issue_2) is False

    # Issue de outra categoria nunca deve ser filtrada por allowlist i18n
    layout_issue = Issue(
        categoria=IssueCategory.LAYOUT_MODAL,
        severidade=IssueSeverity.ALTA,
        descricao="Modal com overflow no card Status.",
        elemento_alvo="div.status-card",
    )
    assert evaluator.is_allowlisted(layout_issue) is False


def test_linguist_filter_allowlisted_issues():
    client = MagicMock()
    evaluator = LinguistAgent(client)

    raw_issues = [
        Issue(
            categoria=IssueCategory.TRADUCAO,
            severidade=IssueSeverity.ALTA,
            descricao="O termo 'Status' deve ser traduzido para 'Estado'.",
            elemento_alvo="Status",
        ),
        Issue(
            categoria=IssueCategory.TRADUCAO,
            severidade=IssueSeverity.ALTA,
            descricao="Botão de ação 'Cancel' em inglês.",
            elemento_alvo="button.btn-cancel",
            sugestao_correcao="Substituir por 'Cancelar'",
        ),
        Issue(
            categoria=IssueCategory.TRADUCAO,
            severidade=IssueSeverity.MEDIA,
            descricao="Rótulo 'Dashboard' não traduzido.",
            elemento_alvo="h1.dashboard",
        ),
    ]

    filtered = evaluator.filter_allowlisted_issues(raw_issues)
    assert len(filtered) == 1
    assert filtered[0].elemento_alvo == "button.btn-cancel"
    assert "Cancel" in filtered[0].descricao


@pytest.mark.asyncio
async def test_linguist_agent_evaluate_filters_allowlist_automatically(mock_vision_client, sample_context):
    mock_vision_client.analyze.return_value = json.dumps(
        {
            "issues": [
                {
                    "categoria": "traducao",
                    "severidade": "alta",
                    "descricao": "Palavra 'Status' não traduzida na UI.",
                    "elemento_alvo": "span.status",
                },
                {
                    "categoria": "traducao",
                    "severidade": "alta",
                    "descricao": "Botão 'Submit' não traduzido.",
                    "elemento_alvo": "button.submit",
                    "sugestao_correcao": "Alterar para 'Enviar'",
                },
            ]
        }
    )

    agent = LinguistAgent(mock_vision_client)
    results = await agent.evaluate(sample_context)

    # Apenas o botão Submit deve permanecer, Status foi descartado pelo allowlist
    assert len(results) == 1
    assert results[0].elemento_alvo == "button.submit"


def test_custom_i18n_allowlist():
    client = MagicMock()
    custom_allowlist = ["CustomTerm", "FeatureFlag"]
    evaluator = LinguistAgent(client, allowlist=custom_allowlist)

    assert "customterm" in evaluator._allowlist_set
    assert "featureflag" in evaluator._allowlist_set
    # Termo padrão 'Status' não deve constar se sobrescrevemos a lista
    assert "status" not in evaluator._allowlist_set


# ==============================================================================
# 2. Árbitro Reverso / Devil's Advocate
# ==============================================================================


@pytest.mark.asyncio
async def test_devils_advocate_discards_hallucination(mock_vision_client):
    arbiter = DevilsAdvocateArbiter(mock_vision_client)

    hallucinated_issue = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.BLOQUEANTE,
        descricao="Tela inteira está em inglês sem localização.",
        elemento_alvo="body",
    )

    valid_issue = Issue(
        categoria=IssueCategory.LAYOUT_MODAL,
        severidade=IssueSeverity.ALTA,
        descricao="Botão de confirmação sobreposto ao rodapé e ilegível.",
        elemento_alvo="button#confirm",
    )

    mock_vision_client.analyze.return_value = json.dumps(
        {
            "arbitration": [
                {
                    "id": 1,
                    "veredicto": "descartar",
                    "severidade_final": "baixa",
                    "justificativa": "Alucinação: todos os menus e botões visíveis na imagem estão em português correto.",
                },
                {
                    "id": 2,
                    "veredicto": "manter",
                    "severidade_final": "alta",
                    "justificativa": "Confirmado: botão #confirm está matematicamente sobreposto ao footer na coordenada Y=850.",
                },
            ]
        }
    )

    result = await arbiter.arbitrate(
        issues=[hallucinated_issue, valid_issue],
        image_base64="fake_b64",
        checkpoint_name="cp_test",
        expected_behavior="Comportamento esperado",
    )

    # Issue 1 foi descartada; apenas Issue 2 foi confirmada
    assert len(result) == 1
    assert result[0].descricao == valid_issue.descricao
    assert "DevilsAdvocate:confirmado" in result[0].evaluator


@pytest.mark.asyncio
async def test_devils_advocate_downgrades_cosmetic_issue(mock_vision_client):
    arbiter = DevilsAdvocateArbiter(mock_vision_client)

    cosmetic_issue = Issue(
        categoria=IssueCategory.LAYOUT_MODAL,
        severidade=IssueSeverity.BLOQUEANTE,
        descricao="Margem esquerda da tabela tem 14px em vez de 16px.",
        elemento_alvo="table.data-table",
    )

    mock_vision_client.analyze.return_value = json.dumps(
        {
            "arbitration": [
                {
                    "id": 1,
                    "veredicto": "rebaixar",
                    "severidade_final": "baixa",
                    "justificativa": "Pequena variação cosmética de 2px no padding sem impacto na usabilidade ou leitura.",
                }
            ]
        }
    )

    result = await arbiter.arbitrate(
        issues=[cosmetic_issue],
        image_base64="fake_b64",
        checkpoint_name="cp_test",
        expected_behavior="Comportamento esperado",
    )

    assert len(result) == 1
    assert result[0].severidade == IssueSeverity.BAIXA
    assert "DevilsAdvocate:rebaixado" in result[0].evaluator


@pytest.mark.asyncio
async def test_devils_advocate_skips_when_no_candidates(mock_vision_client):
    arbiter = DevilsAdvocateArbiter(mock_vision_client)

    medium_issue = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.MEDIA,
        descricao="Tooltip secundário em inglês.",
    )
    low_issue = Issue(
        categoria=IssueCategory.LAYOUT_MODAL,
        severidade=IssueSeverity.BAIXA,
        descricao="Alinhamento sutil de ícone.",
    )

    result = await arbiter.arbitrate(
        issues=[medium_issue, low_issue],
        image_base64="fake_b64",
        checkpoint_name="cp_test",
        expected_behavior="Comportamento esperado",
    )

    assert len(result) == 2
    # Não deve ter chamado o modelo de visão desnecessariamente
    mock_vision_client.analyze.assert_not_called()


@pytest.mark.asyncio
async def test_devils_advocate_disabled_passthrough(mock_vision_client):
    arbiter = DevilsAdvocateArbiter(mock_vision_client, enabled=False)

    critical_issue = Issue(
        categoria=IssueCategory.REGRA_NEGOCIO,
        severidade=IssueSeverity.BLOQUEANTE,
        descricao="Erro crítico",
    )

    result = await arbiter.arbitrate(
        issues=[critical_issue],
        image_base64="fake_b64",
        checkpoint_name="cp_test",
        expected_behavior="Comportamento esperado",
    )

    assert len(result) == 1
    mock_vision_client.analyze.assert_not_called()


@pytest.mark.asyncio
async def test_devils_advocate_fallback_on_network_failure(mock_vision_client):
    arbiter = DevilsAdvocateArbiter(mock_vision_client)
    mock_vision_client.analyze.side_effect = TimeoutError("Falha na chamada da API")

    critical_issue = Issue(
        categoria=IssueCategory.REGRA_NEGOCIO,
        severidade=IssueSeverity.BLOQUEANTE,
        descricao="Erro de negócio importante",
    )

    # Não deve propagar a exceção; mantém as issues originais
    result = await arbiter.arbitrate(
        issues=[critical_issue],
        image_base64="fake_b64",
        checkpoint_name="cp_test",
        expected_behavior="Comportamento esperado",
    )

    assert len(result) == 1
    assert result[0].descricao == critical_issue.descricao


# ==============================================================================
# 3. Pré-Validação Determinística no DOM
# ==============================================================================


@pytest.mark.asyncio
async def test_dom_validator_inspect_dom_and_anomalies_to_issues():
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(
        return_value=[
            {
                "anomaly_type": "text_truncation",
                "tag": "span",
                "class_name": "badge-status",
                "id": "status_label",
                "selector": "#status_label",
                "text_snippet": "Aguardando confirmação de entrega do...",
                "scroll_width": 240,
                "client_width": 180,
                "description": "Texto truncado no elemento <span>: scrollWidth (240px) > clientWidth (180px).",
                "severity": "alta",
                "suggested_fix": "Aumentar largura do badge",
            },
            {
                "anomaly_type": "modal_out_of_bounds",
                "tag": "dialog",
                "class_name": "modal-window",
                "id": "confirmation_modal",
                "selector": "#confirmation_modal",
                "bounding_box": {"left": 100, "top": -40, "right": 900, "bottom": 700},
                "description": "Modal ultrapassou o topo da viewport (T:-40).",
                "severity": "bloqueante",
                "suggested_fix": "Centralizar modal",
            },
        ]
    )

    validator = DOMValidator()
    anomalies = await validator.inspect_dom(mock_page)

    assert len(anomalies) == 2
    assert anomalies[0].anomaly_type == DOMAnomalyType.TEXT_TRUNCATION
    assert anomalies[0].scroll_width == 240
    assert anomalies[1].anomaly_type == DOMAnomalyType.MODAL_OUT_OF_BOUNDS
    assert anomalies[1].severity == IssueSeverity.BLOQUEANTE

    issues = validator.anomalies_to_issues(anomalies, viewport="desktop")
    assert len(issues) == 2
    assert issues[0].categoria == IssueCategory.LAYOUT_MODAL
    assert issues[0].severidade == IssueSeverity.ALTA
    assert "[DOM Determinístico]" in issues[0].descricao
    assert issues[0].evaluator == "DOMValidator (Determinístico)"

    assert issues[1].severidade == IssueSeverity.BLOQUEANTE

    # Testa sumário formatado
    summary = validator.format_anomalies_summary(anomalies)
    assert "[EVIDÊNCIAS DETERMINÍSTICAS DO DOM]:" in summary
    assert "Texto truncado" in summary


@pytest.mark.asyncio
async def test_base_driver_dom_validation_integration():
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(
        return_value=[
            {
                "anomaly_type": "container_overflow",
                "tag": "div",
                "class_name": "o_dialog",
                "selector": ".o_dialog",
                "scroll_width": 600,
                "client_width": 500,
                "scroll_height": 700,
                "client_height": 400,
                "description": "Container sofre overflow com conteúdo ocultado por overflow:hidden.",
                "severity": "alta",
            }
        ]
    )

    driver = GenericDriver(mock_page)
    anomalies = await driver.validate_dom()
    assert len(anomalies) == 1
    assert anomalies[0].anomaly_type == "container_overflow"

    issues = await driver.get_dom_issues(viewport="1440x900")
    assert len(issues) == 1
    assert issues[0].severidade == IssueSeverity.ALTA
    assert issues[0].viewport == "1440x900"


# ==============================================================================
# 4. Set-of-Marks (SoM) e Smart Cropping
# ==============================================================================


@pytest.mark.asyncio
async def test_set_of_marks_manager_inject_and_remove():
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock()

    # Injeção simulada
    mock_page.evaluate.return_value = [
        {
            "id": 1,
            "tag": "button",
            "text": "Salvar",
            "selector": "button#save",
            "role": "button",
            "box": {"x": 10, "y": 20, "width": 80, "height": 32},
        },
        {
            "id": 2,
            "tag": "a",
            "text": "Voltar",
            "selector": "a.nav-back",
            "role": "link",
            "box": {"x": 100, "y": 20, "width": 60, "height": 32},
        },
    ]

    som_mgr = SetOfMarksManager()
    marks = await som_mgr.inject_markers(mock_page)

    assert len(marks) == 2
    assert isinstance(marks[0], InteractiveMark)
    assert marks[0].id == 1
    assert marks[0].selector == "button#save"
    assert marks[1].id == 2

    # Remoção simulada
    mock_page.evaluate.return_value = True
    removed = await som_mgr.remove_markers(mock_page)
    assert removed is True


@pytest.mark.asyncio
async def test_set_of_marks_context_manager_guarantees_cleanup():
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(return_value=[])

    som_mgr = SetOfMarksManager()

    # Mesmo com exceção no bloco interno, remove_markers é chamado
    with pytest.raises(RuntimeError):
        async with som_mgr.apply_som(mock_page):
            raise RuntimeError("Erro simulado durante captura de tela")

    # Verifica que evaluate foi chamado duas vezes (injeção e remoção no finally)
    assert mock_page.evaluate.call_count == 2


@pytest.mark.asyncio
async def test_set_of_marks_smart_cropping_focal_elements(tmp_path):
    mock_page = MagicMock()
    mock_page.evaluate = AsyncMock(
        return_value=[
            {
                "type": "modal",
                "tag": "dialog",
                "selector": ".o_dialog",
                "box": {"x": 200, "y": 150, "width": 500, "height": 400},
            }
        ]
    )

    som_mgr = SetOfMarksManager()
    focal = await som_mgr.detect_focal_elements(mock_page)
    assert len(focal) == 1
    assert focal[0]["type"] == "modal"
    assert focal[0]["selector"] == ".o_dialog"

    # Simula recorte
    mock_locator = MagicMock()
    mock_locator.first = mock_locator
    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.screenshot = AsyncMock()
    mock_page.locator.return_value = mock_locator

    out_file = str(tmp_path / "crop_modal.png")
    cropped_path = await som_mgr.crop_focal_element(mock_page, ".o_dialog", out_file)

    assert cropped_path == out_file
    mock_locator.screenshot.assert_awaited_once_with(path=out_file)


# ==============================================================================
# 5. Integração no ScreenInspector com Arbitragem e DOM Issues
# ==============================================================================


@pytest.mark.asyncio
async def test_screen_inspector_with_arbiter_and_dom_issues(tmp_path):
    screenshot_file = tmp_path / "test_screenshot.png"
    screenshot_file.write_bytes(b"fake image data")

    config = GlobalConfig(
        vision=VisionSettings(
            use_mixture_of_evaluators=False,
            enable_devils_advocate=True,
            enable_dom_validation=True,
        )
    )

    # Mock do cliente LLM:
    # 1ª chamada: monólito gera 1 issue bloqueante e 1 média
    # 2ª chamada: árbitro desafia a issue bloqueante e rebaixa para média
    mock_client = MagicMock()
    mock_client.analyze = AsyncMock(
        side_effect=[
            json.dumps(
                {
                    "issues": [
                        {
                            "categoria": "layout_modal",
                            "severidade": "bloqueante",
                            "descricao": "Modal ligeiramente desalinhado à direita.",
                            "elemento_alvo": ".modal",
                        },
                        {
                            "categoria": "acessibilidade",
                            "severidade": "media",
                            "descricao": "Contraste baixo no texto secundário.",
                        },
                    ]
                }
            ),
            json.dumps(
                {
                    "arbitration": [
                        {
                            "id": 1,
                            "veredicto": "manter",
                            "severidade_final": "alta",
                            "justificativa": "Truncamento no DOM comprovado.",
                        },
                        {
                            "id": 2,
                            "veredicto": "rebaixar",
                            "severidade_final": "media",
                            "justificativa": "Desalinhamento de 4px não impede visualização de nenhum componente.",
                        },
                    ]
                }
            ),
        ]
    )

    inspector = ScreenInspector(config)
    inspector.client = mock_client
    inspector.arbiter.client = mock_client

    extra_dom_issue = Issue(
        categoria=IssueCategory.LAYOUT_MODAL,
        severidade=IssueSeverity.ALTA,
        descricao="[DOM Determinístico] Truncamento comprovado",
    )

    result = await inspector.inspect(
        checkpoint_name="cp_integracao",
        expected_behavior="Tudo normal",
        screenshot_path=str(screenshot_file),
        extra_issues=[extra_dom_issue],
    )

    # Issues esperadas: extra_dom_issue + as 2 do monólito (sendo que a bloqueante foi rebaixada)
    assert len(result.issues) == 3
    # Nenhuma deve ser bloqueante agora
    severities = [i.severidade for i in result.issues]
    assert IssueSeverity.BLOQUEANTE not in severities
    assert result.status == "problemas_encontrados"
