"""Escape de conteúdo dinâmico no relatório HTML.

Descrições vindas do modelo de visão e logs de console ecoam texto da própria
página auditada. Sem autoescape, uma página maliciosa consegue executar script
no relatório que o time de QA abre no navegador.
"""

from datetime import datetime

from uxsentinel.core.models import (
    CheckpointResult,
    ConsoleLogEntry,
    Issue,
    IssueCategory,
    IssueSeverity,
    TestReport,
)
from uxsentinel.reporter.html_builder import build_html_report

PAYLOAD = "<script>alert('xss')</script>"


def _report_with(issue_descricao: str = PAYLOAD, console_text: str = PAYLOAD) -> TestReport:
    checkpoint = CheckpointResult(
        name="checkpoint_hostil",
        expected_behavior="Tela deve abrir sem erros",
        status="problemas_encontrados",
        issues=[
            Issue(
                severidade=IssueSeverity.ALTA,
                categoria=IssueCategory.REGRA_NEGOCIO,
                descricao=issue_descricao,
                elemento_seletor="div#conteudo",
                sugestao_correcao="Sanitizar entrada do usuário.",
            )
        ],
        console_logs=[ConsoleLogEntry(type="error", text=console_text)],
    )

    report = TestReport(
        scenario_id="cenario_hostil",
        scenario_title="Auditoria de pagina hostil",
        profile="generic",
        provider_used="ollama_local",
        started_at=datetime(2026, 9, 15, 10, 0, 0),
        finished_at=datetime(2026, 9, 15, 10, 0, 5),
        duration_seconds=5.0,
        success=False,
        checkpoints=[checkpoint],
    )
    report.compute_totals()
    return report


def test_issue_description_is_escaped_in_html_report() -> None:
    html = build_html_report(_report_with())

    assert PAYLOAD not in html
    assert "&lt;script&gt;" in html
