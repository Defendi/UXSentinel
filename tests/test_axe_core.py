from unittest.mock import AsyncMock

import pytest

from uxsentinel.browser.axe_runner import (
    DEFAULT_WCAG_TAGS,
    AxeRunner,
    calculate_a11y_score,
    convert_violations_to_issues,
    get_axe_script,
    parse_axe_results,
)
from uxsentinel.core.config import BrowserSettings, resolve_axe_mode
from uxsentinel.core.models import (
    AxeNodeResult,
    AxeViolation,
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    TestReport,
)
from uxsentinel.integrations.jira import JiraClient
from uxsentinel.reporter.html_builder import build_html_report


def test_get_axe_script_loads_offline() -> None:
    """Garante que o script minificado do axe-core é carregado localmente sem internet."""
    script = get_axe_script()
    assert isinstance(script, str)
    assert len(script) > 10000
    assert "axe" in script


def test_calculate_a11y_score_deterministic() -> None:
    """Testa o cálculo determinístico de pontuação A11y Score de 0 a 100%."""
    # 1. Sem violações -> 100.0%
    assert calculate_a11y_score([]) == 100.0

    # 2. Uma violação critical (peso 10, 1 nó) -> 100 - 10 = 90.0%
    v_crit = AxeViolation(
        id="color-contrast",
        impact="critical",
        description="Contraste de cores insuficiente",
        nodes=[AxeNodeResult(target=["button.primary"], html="<button>Enviar</button>")],
    )
    score_one = calculate_a11y_score([v_crit])
    assert score_one == 90.0

    # 3. Violação com múltiplos nós -> amortecimento proporcional
    v_crit_multi = AxeViolation(
        id="color-contrast",
        impact="critical",
        description="Contraste de cores insuficiente",
        nodes=[AxeNodeResult(target=[f"button.{i}"], html=f"<button>{i}</button>") for i in range(5)],
    )
    score_multi = calculate_a11y_score([v_crit_multi])
    assert 75.0 <= score_multi < 90.0

    # 4. Violações severas acumuladas não descem abaixo de 0.0
    heavy_violations = [
        AxeViolation(
            id=f"heavy-rule-{i}",
            impact="critical",
            description="Falha grave",
            nodes=[AxeNodeResult(target=[".el"]) for _ in range(5)],
        )
        for i in range(15)
    ]
    assert calculate_a11y_score(heavy_violations) == 0.0


def test_parse_axe_results() -> None:
    """Testa o parser do payload JSON do axe-core em modelos Pydantic v2."""
    raw = [
        {
            "id": "image-alt",
            "impact": "critical",
            "description": "Imagens devem possuir texto alternativo",
            "help": "Imagens precisam de atributo alt",
            "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/image-alt",
            "tags": ["wcag2a", "wcag111", "section508"],
            "nodes": [
                {
                    "target": ["img.hero", "#banner-logo"],
                    "html": '<img src="logo.png">',
                    "failureSummary": "Corrija: falta o atributo alt",
                    "impact": "critical",
                }
            ],
        }
    ]

    violations = parse_axe_results(raw)
    assert len(violations) == 1
    v = violations[0]
    assert v.id == "image-alt"
    assert v.impact == "critical"
    assert v.help_url == "https://dequeuniversity.com/rules/axe/4.10/image-alt"
    assert "wcag2a" in v.tags
    assert len(v.nodes) == 1
    assert v.nodes[0].target == ["img.hero", "#banner-logo"]
    assert v.nodes[0].failure_summary == "Corrija: falta o atributo alt"


def test_convert_violations_to_issues() -> None:
    """Testa a conversão de violações graves do axe em Issues unificadas do UXSentinel."""
    v1 = AxeViolation(
        id="color-contrast",
        impact="critical",
        description="Texto sem contraste suficiente",
        help_url="https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        nodes=[
            AxeNodeResult(
                target=["p.text-muted"],
                html="<p class='text-muted'>Texto claro</p>",
                failure_summary="Element has insufficient color contrast of 2.1:1",
            )
        ],
    )
    v2 = AxeViolation(
        id="button-name",
        impact="serious",
        description="Botão sem nome acessível",
        help_url="https://dequeuniversity.com/rules/axe/4.10/button-name",
        nodes=[
            AxeNodeResult(
                target=["button.icon-only"],
                html="<button class='icon-only'><i class='fa'></i></button>",
                failure_summary="Element does not have an accessible name",
            )
        ],
    )
    v3 = AxeViolation(
        id="minor-rule",
        impact="minor",
        description="Regra de impacto leve",
        nodes=[AxeNodeResult(target=["div"])],
    )

    # Por padrão (min_severity="serious"), apenas critical e serious são convertidos
    issues = convert_violations_to_issues([v1, v2, v3], viewport="desktop (1440x900)")
    assert len(issues) == 2

    # Issue 1: critical -> BLOQUEANTE
    assert issues[0].categoria == IssueCategory.ACESSIBILIDADE
    assert issues[0].severidade == IssueSeverity.BLOQUEANTE
    assert "color-contrast" in issues[0].descricao
    assert issues[0].elemento_alvo == "p.text-muted"
    assert issues[0].evaluator == "axe-core"
    assert issues[0].viewport == "desktop (1440x900)"

    # Issue 2: serious -> ALTA
    assert issues[1].categoria == IssueCategory.ACESSIBILIDADE
    assert issues[1].severidade == IssueSeverity.ALTA
    assert "button-name" in issues[1].descricao

    # Conversão de todas as violações
    all_issues = convert_violations_to_issues([v1, v2, v3], min_severity="all")
    assert len(all_issues) == 3
    assert all_issues[2].severidade == IssueSeverity.BAIXA


@pytest.mark.asyncio
async def test_axe_runner_inject_and_run_with_mock() -> None:
    """Testa a injeção e execução do axe.run() utilizando mock assíncrono do Playwright."""
    runner = AxeRunner()

    mock_page = AsyncMock()
    # 1ª chamada de evaluate: is_present -> False
    # 2ª chamada: inject script
    # 3ª chamada: window.axe.run(payload)
    mock_page.evaluate.side_effect = [
        False,  # is_present
        None,  # inject script
        {  # eval_js results
            "violations": [
                {
                    "id": "document-title",
                    "impact": "serious",
                    "description": "Documentos devem possuir elemento <title>",
                    "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/document-title",
                    "tags": ["wcag2a", "wcag242"],
                    "nodes": [
                        {
                            "target": ["html"],
                            "html": "<html>",
                            "failureSummary": "O documento não tem título",
                            "impact": "serious",
                        }
                    ],
                }
            ],
            "passes_count": 25,
            "incomplete_count": 0,
        },
    ]

    violations = await runner.run(mock_page, tags=["wcag2a", "wcag2aa"])
    assert len(violations) == 1
    assert violations[0].id == "document-title"
    assert violations[0].impact == "serious"
    assert mock_page.evaluate.call_count == 3


@pytest.mark.asyncio
async def test_axe_runner_resilience_on_page_failure() -> None:
    """Testa a resiliência do AxeRunner contra exceções ou falhas na página."""
    runner = AxeRunner()
    mock_page = AsyncMock()
    # Simula erro de navegação ou crash de página
    mock_page.evaluate.side_effect = RuntimeError("Execution context was destroyed")

    violations = await runner.run(mock_page)
    # Não deve propagar exceção, deve retornar lista vazia
    assert violations == []


def test_checkpoint_and_test_report_a11y_totals() -> None:
    """Testa a consolidação de métricas e violações de acessibilidade no TestReport."""
    v1 = AxeViolation(
        id="color-contrast",
        impact="critical",
        description="Falta contraste",
        nodes=[AxeNodeResult(target=["#btn"])],
    )
    v2 = AxeViolation(
        id="aria-label",
        impact="serious",
        description="Falta aria-label",
        nodes=[AxeNodeResult(target=["#input"])],
    )

    cp1 = CheckpointResult(
        name="CP1",
        expected_behavior="Tela inicial",
        a11y_score=90.0,
        a11y_violations=[v1],
    )
    cp2 = CheckpointResult(
        name="CP2",
        expected_behavior="Formulário",
        a11y_score=80.0,
        a11y_violations=[v2],
    )

    report = TestReport(
        scenario_id="sc-a11y",
        scenario_title="Teste A11y",
        profile="generic",
        provider_used="mock",
        checkpoints=[cp1, cp2],
    )
    report.compute_totals()

    assert report.a11y_score == 85.0  # Média (90 + 80) / 2
    assert len(report.a11y_violations) == 2


def test_html_report_renders_a11y_score_and_violations() -> None:
    """Testa se o template HTML exibe o gauge de A11y Score e o detalhamento de violações WCAG."""
    v = AxeViolation(
        id="image-alt",
        impact="critical",
        description="A tag <img> precisa de atributo alt",
        help_url="https://dequeuniversity.com/rules/axe/4.10/image-alt",
        tags=["wcag2a", "wcag22aa"],
        nodes=[
            AxeNodeResult(
                target=["img.avatar"],
                html="<img class='avatar' src='usr.jpg'>",
                failure_summary="Atributo alt não encontrado",
            )
        ],
    )

    issue = Issue(
        categoria=IssueCategory.ACESSIBILIDADE,
        severidade=IssueSeverity.BLOQUEANTE,
        descricao="Acessibilidade [image-alt]: A tag <img> precisa de atributo alt",
        elemento_alvo="img.avatar",
        evaluator="axe-core",
    )

    cp = CheckpointResult(
        name="checkpoint_home",
        expected_behavior="Banner acessível",
        status="problemas_encontrados",
        issues=[issue],
        a11y_score=88.5,
        a11y_violations=[v],
    )

    report = TestReport(
        scenario_id="scenario_wcag",
        scenario_title="Cenário de Auditoria Acessibilidade",
        profile="generic",
        provider_used="mock",
        checkpoints=[cp],
    )
    report.compute_totals()

    html = build_html_report(report)

    # Verifica se os elementos do dashboard estão presentes
    assert "A11y Score (WCAG 2.2)" in html
    assert "88.5%" in html
    assert "Auditoria Axe-Core (WCAG 2.2 AA)" in html
    assert "image-alt" in html
    assert "https://dequeuniversity.com/rules/axe/4.10/image-alt" in html
    assert "img.avatar" in html


def test_jira_integration_formats_wcag_section() -> None:
    """Testa se a integração com o Jira formata a seção WCAG e adiciona labels correspondentes."""
    from uxsentinel.core.config import JiraSettings

    settings = JiraSettings(
        enabled=True,
        url="https://jira.exemplo.com",
        email="test@exemplo.com",
        api_token="dummy-token",
        project_key="UXS",
    )
    client = JiraClient(settings)

    a11y_issue = Issue(
        categoria=IssueCategory.ACESSIBILIDADE,
        severidade=IssueSeverity.BLOQUEANTE,
        descricao="Acessibilidade [color-contrast]: Contraste insuficiente no botão",
        elemento_alvo="button.btn-primary",
        trecho_codigo="<button class='btn-primary'>Ok</button>",
        sugestao_correcao="Ajustar taxa de contraste para pelo menos 4.5:1",
        evaluator="axe-core",
    )

    desc = client._format_description(
        scenario_id="sc-01",
        scenario_title="Teste A11y",
        checkpoint_name="cp-home",
        expected_behavior="Contraste adequado",
        issue=a11y_issue,
    )

    assert "♿ Especificação de Acessibilidade e WCAG 2.2" in desc
    assert "button.btn-primary" in desc
    assert "Axe-Core Accessibility Engine" in desc


def test_resolve_axe_mode_hierarchy() -> None:
    """Testa a hierarquia estrita de resolução do modo Axe-Core."""
    # 1. CLI flag tem precedência máxima
    assert resolve_axe_mode(cli_axe=True, scenario_axe=False, config_axe=False) is True
    assert resolve_axe_mode(cli_axe=False, scenario_axe=True, config_axe=True) is False

    # 2. Cenário YAML
    assert resolve_axe_mode(cli_axe=None, scenario_axe=True, config_axe=False) is True
    assert resolve_axe_mode(cli_axe=None, scenario_axe=False, config_axe=True) is False

    # 3. Config global
    assert resolve_axe_mode(cli_axe=None, scenario_axe=None, config_axe=True) is True
    assert resolve_axe_mode(cli_axe=None, scenario_axe=None, config_axe=False) is False

    # 4. Fallback padrão é True
    assert resolve_axe_mode(cli_axe=None, scenario_axe=None, config_axe=None) is True


def test_browser_settings_default_axe() -> None:
    """Testa os valores padrão de acessibilidade no BrowserSettings."""
    bs = BrowserSettings()
    assert bs.enable_axe is True
    assert bs.axe_tags == list(DEFAULT_WCAG_TAGS)
