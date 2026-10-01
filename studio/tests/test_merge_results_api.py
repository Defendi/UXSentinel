"""Testes herméticos para a rota POST /api/results/merge da API Studio (UXS-92)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uxsentinel.core.models import CheckpointResult, Issue, IssueCategory, IssueSeverity, TestReport
from uxsentinel_studio.server import create_app, get_session_token


@pytest.fixture
def studio_env(tmp_path: Path) -> tuple[TestClient, dict[str, str], Path]:
    """Cria ambiente hermético com diretório de relatórios e cliente FastAPI autenticado."""
    report_dir = tmp_path / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(project_dir=tmp_path)
    client = TestClient(app)
    headers = {"X-Studio-Token": get_session_token()}

    return client, headers, report_dir


def test_merge_results_api_success(studio_env: tuple[TestClient, dict[str, str], Path]) -> None:
    """Verifica mesclagem com sucesso de duas execuções através do endpoint REST."""
    client, headers, report_dir = studio_env

    rep1 = TestReport(
        scenario_id="exec_a",
        scenario_title="Execução Parte 1",
        started_at=datetime(2026, 9, 25, 10, 0, 0, tzinfo=UTC),
        duration_seconds=10.0,
        checkpoints=[
            CheckpointResult(
                name="cp_etapa1",
                timestamp=datetime(2026, 9, 25, 10, 1, 0, tzinfo=UTC),
                expected_behavior="Validar etapa 1",
                issues=[
                    Issue(
                        categoria=IssueCategory.LAYOUT,
                        severidade=IssueSeverity.MEDIA,
                        descricao="Margem incorreta",
                    )
                ],
            )
        ],
    )

    rep2 = TestReport(
        scenario_id="exec_b",
        scenario_title="Execução Parte 2",
        started_at=datetime(2026, 9, 25, 10, 10, 0, tzinfo=UTC),
        duration_seconds=15.0,
        checkpoints=[
            CheckpointResult(
                name="cp_etapa2",
                timestamp=datetime(2026, 9, 25, 10, 11, 0, tzinfo=UTC),
                expected_behavior="Validar etapa 2",
            )
        ],
    )

    (report_dir / "exec_a_report.json").write_text(json.dumps(rep1.model_dump(mode="json")), encoding="utf-8")
    (report_dir / "exec_b_report.json").write_text(json.dumps(rep2.model_dump(mode="json")), encoding="utf-8")

    payload = {
        "execution_ids": ["exec_a", "exec_b"],
        "target_id": "exec_consolidada",
    }
    resp = client.post("/api/results/merge", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == "exec_consolidada"
    assert data["scenario_id"] == "exec_consolidada"
    assert data["duration_seconds"] == 25.0
    assert len(data["checkpoints"]) == 2
    assert len(data["issues"]) == 1
    assert (report_dir / "exec_consolidada_report.json").is_file()
    assert (report_dir / "exec_consolidada_report.html").is_file()


def test_merge_results_api_validation_error(studio_env: tuple[TestClient, dict[str, str], Path]) -> None:
    """Verifica erro 422 quando menos de 2 IDs de execução são enviados."""
    client, headers, _ = studio_env

    payload = {
        "execution_ids": ["exec_sozinha"],
    }
    resp = client.post("/api/results/merge", json=payload, headers=headers)
    assert resp.status_code == 422


def test_merge_results_api_not_found(studio_env: tuple[TestClient, dict[str, str], Path]) -> None:
    """Verifica erro 404 quando um dos IDs de execução não existe no diretório."""
    client, headers, report_dir = studio_env

    rep1 = TestReport(
        scenario_id="exec_existente",
        scenario_title="Execução Existente",
        started_at=datetime(2026, 9, 25, 10, 0, 0, tzinfo=UTC),
    )
    (report_dir / "exec_existente_report.json").write_text(
        json.dumps(rep1.model_dump(mode="json")), encoding="utf-8"
    )

    payload = {
        "execution_ids": ["exec_existente", "exec_inexistente"],
    }
    resp = client.post("/api/results/merge", json=payload, headers=headers)
    assert resp.status_code == 404


def test_merge_results_api_unauthorized(studio_env: tuple[TestClient, dict[str, str], Path]) -> None:
    """Verifica recusa 401 sem cabeçalho de autenticação do Studio."""
    client, _, _ = studio_env

    payload = {
        "execution_ids": ["exec_a", "exec_b"],
    }
    resp = client.post("/api/results/merge", json=payload)
    assert resp.status_code == 401


def test_merge_results_api_path_traversal_blocked(
    studio_env: tuple[TestClient, dict[str, str], Path],
) -> None:
    """Verifica bloqueio de path traversal com status 400."""
    client, headers, _ = studio_env

    payload = {
        "execution_ids": ["../malicious", "exec_b"],
    }
    resp = client.post("/api/results/merge", json=payload, headers=headers)
    assert resp.status_code == 400
