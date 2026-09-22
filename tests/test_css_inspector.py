"""Testes herméticos e determinísticos para a suíte de auditoria profunda de CSS (UXS-47)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from uxsentinel.css.models import (
    CSSAuditReport,
    CSSIssueCategory,
    CSSSeverity,
    CSSViolation,
)
from uxsentinel.css.runner import CSSInspector
from uxsentinel.css.static_auditor import CSSStaticAuditor


def test_css_models_and_score_calculation():
    """Valida modelos de dados, cálculo de score e conversão para issues."""
    report = CSSAuditReport()
    assert report.score == 100.0

    v1 = CSSViolation(
        rule_id="horizontal-overflow",
        category=CSSIssueCategory.OVERFLOW,
        severity=CSSSeverity.BLOQUEANTE,
        selector=".container",
        description="Estouro horizontal de layout",
        suggestion="Adicionar overflow-x: hidden",
    )
    v2 = CSSViolation(
        rule_id="excessive-z-index",
        category=CSSIssueCategory.Z_INDEX,
        severity=CSSSeverity.ALTA,
        selector="#modal",
        description="z-index excessivo",
    )
    v3 = CSSViolation(
        rule_id="duplicate-properties",
        category=CSSIssueCategory.DUPLICATION,
        severity=CSSSeverity.MEDIA,
        selector=".card",
        description="Propriedade duplicada",
    )
    v4 = CSSViolation(
        rule_id="modern-css-aspect-ratio",
        category=CSSIssueCategory.MODERN_CSS,
        severity=CSSSeverity.BAIXA,
        selector=".thumb",
        description="Pode usar aspect-ratio",
    )

    report.violations = [v1, v2, v3, v4]
    report.calculate_score()

    # Deduções: BLOQUEANTE (25) + ALTA (10) + MEDIA (4) + BAIXA (1) = 40 -> Score: 60.0
    assert report.score == 60.0
    assert report.summary[CSSSeverity.BLOQUEANTE.value] == 1
    assert report.summary[CSSSeverity.ALTA.value] == 1
    assert report.summary[CSSSeverity.MEDIA.value] == 1
    assert report.summary[CSSSeverity.BAIXA.value] == 1

    # Teste de conversão para list[Issue] do core
    issues = report.to_issues(viewport="desktop")
    assert len(issues) == 4
    assert issues[0].severidade.value == "bloqueante"
    assert issues[0].categoria.value == "css"
    assert issues[0].evaluator == "css_inspector"
    assert issues[0].elemento_alvo == ".container"
    assert issues[0].sugestao_correcao == "Adicionar overflow-x: hidden"


def test_static_auditor_css_rules(tmp_path: Path):
    """Valida análise estática de CSS: !important, especificidade, duplicações e modern CSS."""
    css_content = """
    /* !important excessivo */
    .button {
        color: red !important;
        background-color: blue !important;
    }

    /* Alta especificidade */
    #main-content div.sidebar ul.nav li.item a.link {
        font-size: 14px;
    }

    /* Propriedades duplicadas consecutivas */
    .card {
        padding: 10px;
        display: block;
        padding: 20px;
    }

    /* Sugestão Modern CSS: aspect-ratio hack */
    .aspect-box {
        padding-top: 56.25%;
        position: relative;
    }
    """
    css_file = tmp_path / "styles.css"
    css_file.write_text(css_content, encoding="utf-8")

    auditor = CSSStaticAuditor()
    report = auditor.audit_file(css_file)

    rule_ids = {v.rule_id for v in report.violations}
    assert "css-important-usage" in rule_ids
    assert "css-excessive-chaining" in rule_ids
    assert "css-overridden-property" in rule_ids
    assert "css-modern-aspect-ratio" in rule_ids
    assert report.total_rules_inspected > 0
    assert report.score < 100.0


def test_static_auditor_directory(tmp_path: Path):
    """Testa auditoria estática recursiva de diretórios."""
    sub_dir = tmp_path / "components"
    sub_dir.mkdir()
    (sub_dir / "comp1.css").write_text(".a { color: red !important; }", encoding="utf-8")
    (sub_dir / "comp2.css").write_text(".b { display: flex; }", encoding="utf-8")

    report = CSSInspector.audit_file_or_dir(tmp_path)
    assert report.total_rules_inspected >= 2
    assert any(v.rule_id == "css-important-usage" for v in report.violations)


@pytest.mark.asyncio
async def test_runtime_auditor_mock_page():
    """Valida execução do auditor runtime em mock assíncrono do Page do Playwright."""
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(
        return_value=[
            {
                "rule_id": "horizontal-overflow",
                "category": "overflow",
                "severity": "bloqueante",
                "selector": "div.wide-table",
                "description": "Elemento ultrapassa a largura da viewport horizontalmente gerando barra de rolagem.",
                "suggestion": "Aplique max-width: 100% ou overflow-x: auto no contêiner.",
                "source": "runtime",
            },
            {
                "rule_id": "invisible-overlay",
                "category": "z_index",
                "severity": "bloqueante",
                "selector": "div.backdrop-modal",
                "description": "Elemento com z-index alto (9999) está com pointer-events ativado mas quase invisível, bloqueando interações.",
                "suggestion": "Remova o overlay do DOM ou adicione pointer-events: none.",
                "source": "runtime",
            },
        ]
    )

    report = await CSSInspector.audit_page(mock_page)

    assert mock_page.evaluate.called
    assert len(report.violations) == 2
    assert report.score == 50.0  # 100 - (25 * 2) = 50.0
    assert report.summary["bloqueante"] == 2
    rule_ids = [v.rule_id for v in report.violations]
    assert "horizontal-overflow" in rule_ids
    assert "invisible-overlay" in rule_ids
