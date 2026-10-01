"""Testes unitários herméticos para mesclagem de sessões de auditoria (UXS-92)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from uxsentinel.browser.telemetry import ConsoleLogEntry
from uxsentinel.core.models import (
    AxeViolation,
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    TestReport,
)
from uxsentinel.reporter.merger import merge_session_files, merge_test_reports
from uxsentinel.service.results_service import ResultsService


def test_merge_test_reports_empty_raises_value_error() -> None:
    """Garante que tentar mesclar uma lista vazia lança ValueError."""
    with pytest.raises(ValueError, match="A lista de relatórios para mesclagem não pode estar vazia."):
        merge_test_reports([])


def test_merge_test_reports_single_report() -> None:
    """Garante que fornecer 1 relatório retorna uma cópia com overrides opcionais."""
    base_time = datetime(2026, 9, 25, 10, 0, 0, tzinfo=UTC)
    report = TestReport(
        scenario_id="cenario_unico",
        scenario_title="Cenário Único",
        profile="generic",
        provider_used="gemini_cloud",
        started_at=base_time,
        finished_at=base_time + timedelta(seconds=15),
        duration_seconds=15.0,
        viewports_tested=["desktop"],
    )

    merged = merge_test_reports([report], scenario_id="custom_id", scenario_title="Custom Title")

    assert merged is not report
    assert merged.scenario_id == "custom_id"
    assert merged.scenario_title == "Custom Title"
    assert merged.duration_seconds == 15.0
    assert merged.provider_used == "gemini_cloud"


def test_merge_test_reports_multiple_combines_metrics_and_checkpoints() -> None:
    """Verifica mesclagem profunda de múltiplos relatórios com ordenação cronológica e compute_totals."""
    t0 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=5)
    t2 = t0 + timedelta(minutes=10)
    t3 = t0 + timedelta(minutes=15)

    cp_t2 = CheckpointResult(
        name="cp_intermediario",
        timestamp=t2,
        expected_behavior="Validar meio da jornada",
        issues=[
            Issue(
                categoria=IssueCategory.LAYOUT,
                severidade=IssueSeverity.MEDIA,
                descricao="Espaçamento inconsistente",
            )
        ],
    )

    cp_t1 = CheckpointResult(
        name="cp_inicial",
        timestamp=t1,
        expected_behavior="Validar início",
        issues=[
            Issue(
                categoria=IssueCategory.REGRA_NEGOCIO,
                severidade=IssueSeverity.BLOQUEANTE,
                descricao="Botão desabilitado incorretamente",
            ),
            Issue(
                categoria=IssueCategory.CSS,
                severidade=IssueSeverity.ALTA,
                descricao="Contraste de cor reprovado",
            ),
        ],
        a11y_score=85.0,
        a11y_violations=[
            AxeViolation(
                id="color-contrast",
                impact="serious",
                description="Contraste insuficiente",
            )
        ],
    )

    cp_t3 = CheckpointResult(
        name="cp_final",
        timestamp=t3,
        expected_behavior="Validar tela final",
        issues=[
            Issue(
                categoria=IssueCategory.TEXTO_TECNICO,
                severidade=IssueSeverity.BAIXA,
                descricao="Texto de rodapé com typo",
            )
        ],
        a11y_score=95.0,
    )

    rep1 = TestReport(
        scenario_id="cenario_etapa_1",
        scenario_title="Etapa 1 da Jornada",
        profile="generic",
        provider_used="gemini_cloud",
        started_at=t0,
        finished_at=t2,
        duration_seconds=120.0,
        checkpoints=[cp_t2, cp_t1],  # Fornecidos fora de ordem propositalmente
        viewports_tested=["desktop", "tablet"],
        console_logs=[
            ConsoleLogEntry(type="error", text="Erro Javascript 404"),
            ConsoleLogEntry(type="warn", text="Aviso de depreciação"),
        ],
    )

    rep2 = TestReport(
        scenario_id="cenario_etapa_2",
        scenario_title="Etapa 2 da Jornada",
        profile="odoo",
        provider_used="anthropic_cloud",
        started_at=t2,
        finished_at=t3,
        duration_seconds=80.0,
        checkpoints=[cp_t3],
        viewports_tested=["tablet", "mobile"],  # 'tablet' duplicado para validar união única
        console_logs=[
            ConsoleLogEntry(type="error", text="Erro na conexão WebSocket"),
        ],
    )

    merged = merge_test_reports(
        [rep1, rep2], scenario_id="jornada_completa", scenario_title="Jornada Completa"
    )

    # 1. Identificadores e perfis
    assert merged.scenario_id == "jornada_completa"
    assert merged.scenario_title == "Jornada Completa"
    assert merged.profile == "generic, odoo"
    assert merged.provider_used == "gemini_cloud, anthropic_cloud"

    # 2. Viewports (união única preservando primeira aparição)
    assert merged.viewports_tested == ["desktop", "tablet", "mobile"]

    # 3. Timestamps e Duração
    assert merged.started_at == t0
    assert merged.finished_at == t3
    assert merged.duration_seconds == 200.0

    # 4. Checkpoints estritamente ordenados por timestamp
    assert len(merged.checkpoints) == 3
    assert merged.checkpoints[0].name == "cp_inicial"
    assert merged.checkpoints[1].name == "cp_intermediario"
    assert merged.checkpoints[2].name == "cp_final"

    # 5. Totais recalculados via compute_totals
    assert merged.total_issues == 4
    assert merged.total_bloqueantes == 1
    assert merged.total_altas == 1
    assert merged.total_medias == 1
    assert merged.total_baixas == 1
    assert merged.success is False  # Por ter bloqueante e alta

    # 6. Acessibilidade consolidada (média dos scores 85.0 e 95.0 = 90.0)
    assert merged.a11y_score == 90.0
    assert len(merged.a11y_violations) == 1
    assert merged.a11y_violations[0].id == "color-contrast"

    # 7. Logs de console
    assert len(merged.console_logs) == 3
    assert merged.total_console_errors == 2
    assert merged.total_console_warnings == 1


def test_merge_session_files_io(tmp_path: Path) -> None:
    """Verifica carregamento de arquivos JSON do disco e gravação do relatório consolidado."""
    rep1 = TestReport(
        scenario_id="exec_a",
        scenario_title="Execução A",
        duration_seconds=10.0,
        started_at=datetime(2026, 9, 25, 9, 0, 0, tzinfo=UTC),
        checkpoints=[
            CheckpointResult(
                name="cp_a",
                timestamp=datetime(2026, 9, 25, 9, 1, 0, tzinfo=UTC),
                expected_behavior="Esperado A",
            )
        ],
    )
    rep2 = TestReport(
        scenario_id="exec_b",
        scenario_title="Execução B",
        duration_seconds=15.0,
        started_at=datetime(2026, 9, 25, 9, 5, 0, tzinfo=UTC),
        checkpoints=[
            CheckpointResult(
                name="cp_b",
                timestamp=datetime(2026, 9, 25, 9, 6, 0, tzinfo=UTC),
                expected_behavior="Esperado B",
            )
        ],
    )

    f1 = tmp_path / "exec_a_report.json"
    f2 = tmp_path / "exec_b_report.json"
    f1.write_text(json.dumps(rep1.model_dump(mode="json")), encoding="utf-8")
    f2.write_text(json.dumps(rep2.model_dump(mode="json")), encoding="utf-8")

    out_file = tmp_path / "consolidado_report.json"
    merged, saved_path = merge_session_files(
        file_paths=[f1, f2],
        output_file=out_file,
        scenario_id="exec_consolidada",
    )

    assert saved_path == out_file
    assert out_file.is_file()
    assert merged.scenario_id == "exec_consolidada"
    assert merged.duration_seconds == 25.0
    assert len(merged.checkpoints) == 2

    # Valida integridade do JSON gerado
    parsed = json.loads(out_file.read_text(encoding="utf-8"))
    assert parsed["scenario_id"] == "exec_consolidada"
    assert len(parsed["checkpoints"]) == 2


def test_merge_session_files_not_found_raises() -> None:
    """Verifica erro amigável ao informar arquivo inexistente."""
    with pytest.raises(FileNotFoundError, match="Arquivo de sessão não encontrado"):
        merge_session_files(["/caminho/inexistente_report.json"])


def test_results_service_merge_executions(tmp_path: Path) -> None:
    """Valida o método merge_executions de ResultsService."""
    service = ResultsService()

    rep1 = TestReport(
        scenario_id="s1",
        scenario_title="Sessão 1",
        started_at=datetime(2026, 9, 25, 8, 0, 0, tzinfo=UTC),
        duration_seconds=5.0,
        checkpoints=[
            CheckpointResult(
                name="cp1",
                timestamp=datetime(2026, 9, 25, 8, 1, 0, tzinfo=UTC),
                expected_behavior="OK 1",
            )
        ],
    )
    rep2 = TestReport(
        scenario_id="s2",
        scenario_title="Sessão 2",
        started_at=datetime(2026, 9, 25, 8, 5, 0, tzinfo=UTC),
        duration_seconds=8.0,
        checkpoints=[
            CheckpointResult(
                name="cp2",
                timestamp=datetime(2026, 9, 25, 8, 6, 0, tzinfo=UTC),
                expected_behavior="OK 2",
            )
        ],
    )

    (tmp_path / "s1_report.json").write_text(json.dumps(rep1.model_dump(mode="json")), encoding="utf-8")
    (tmp_path / "s2_report.json").write_text(json.dumps(rep2.model_dump(mode="json")), encoding="utf-8")

    detail = service.merge_executions(
        execution_ids=["s1", "s2"],
        output_dir=tmp_path,
        target_id="s_consolidado",
    )

    assert detail.scenario_id == "s_consolidado"
    assert detail.duration_seconds == 13.0
    assert len(detail.checkpoints) == 2
    assert (tmp_path / "s_consolidado_report.json").is_file()
    assert (tmp_path / "s_consolidado_report.html").is_file()


def test_results_service_merge_executions_security_and_validation(tmp_path: Path) -> None:
    """Valida proteção contra path traversal e lista vazia em merge_executions."""
    service = ResultsService()

    with pytest.raises(ValueError, match="A lista de execuções para mesclagem não pode estar vazia."):
        service.merge_executions([], tmp_path)

    with pytest.raises(PermissionError):
        service.merge_executions(["../malicious"], tmp_path)

    with pytest.raises(PermissionError):
        service.merge_executions(["s1"], tmp_path, target_id="../../bad_target")

    with pytest.raises(FileNotFoundError, match="não encontrado"):
        service.merge_executions(["s_fantasma"], tmp_path)
