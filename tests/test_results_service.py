"""Testes herméticos para ResultsService (UXS-34)."""

import json
from pathlib import Path

import pytest

from uxsentinel.service.results_service import ResultsService


def test_results_service_lists_executions_ordered(tmp_path: Path):
    """Valida listagem e ordenação cronológica de execuções a partir de relatórios JSON."""
    service = ResultsService()

    # Cria dois relatórios em momentos distintos
    rep1 = {
        "scenario_id": "cenario_antigo",
        "scenario_title": "Cenário Antigo",
        "success": True,
        "started_at": "2026-09-20T10:00:00",
        "total_issues": 1,
        "total_bloqueantes": 0,
        "duration_seconds": 12.5,
    }
    rep2 = {
        "scenario_id": "cenario_novo",
        "scenario_title": "Cenário Recente",
        "success": False,
        "started_at": "2026-09-22T15:00:00",
        "total_issues": 3,
        "total_bloqueantes": 1,
        "duration_seconds": 25.0,
    }

    (tmp_path / "cenario_antigo_report.json").write_text(json.dumps(rep1), encoding="utf-8")
    (tmp_path / "cenario_novo_report.json").write_text(json.dumps(rep2), encoding="utf-8")
    (tmp_path / "cenario_novo_report.html").write_text("<html>Report</html>", encoding="utf-8")

    executions = service.list_executions(tmp_path)
    assert len(executions) == 2

    # Mais recente primeiro
    assert executions[0].scenario_id == "cenario_novo"
    assert executions[0].status == "failed"
    assert executions[0].bloqueante_count == 1
    assert executions[0].report_html_url is not None

    assert executions[1].scenario_id == "cenario_antigo"
    assert executions[1].status == "passed"


def test_results_service_get_execution_detail(tmp_path: Path):
    """Valida extração completa de checkpoints e issues de um relatório específico."""
    service = ResultsService()

    rep = {
        "scenario_id": "fluxo_vendas",
        "scenario_title": "Fluxo de Vendas",
        "success": True,
        "started_at": "2026-09-22T10:00:00",
        "provider_used": "claude_sso",
        "viewports_tested": ["1440x900"],
        "checkpoints": [
            {
                "name": "dashboard",
                "description": "Tela inicial",
                "status": "ok",
                "screenshot_path": str(tmp_path / "dashboard.png"),
                "expected_behavior": "Menus visíveis",
                "issues": [
                    {
                        "categoria": "i18n",
                        "severidade": "media",
                        "descricao": "Termo 'Settings' não traduzido",
                        "sugestao_correcao": "Traduzir para 'Configurações'",
                    }
                ],
            }
        ],
    }

    (tmp_path / "fluxo_vendas_report.json").write_text(json.dumps(rep), encoding="utf-8")

    detail = service.get_execution("fluxo_vendas", tmp_path)
    assert detail.scenario_id == "fluxo_vendas"
    assert detail.provider_used == "claude_sso"
    assert len(detail.checkpoints) == 1
    assert detail.checkpoints[0].name == "dashboard"
    assert len(detail.issues) == 1
    assert detail.issues[0].title == "Termo 'Settings' não traduzido"
    assert detail.issues[0].severity == "media"


def test_results_service_artifact_path_traversal_protection(tmp_path: Path):
    """Garante que tentativa de path traversal em artefatos levante PermissionError."""
    service = ResultsService()

    # Cria arquivo legítimo e tenta escapar do diretório
    (tmp_path / "valido.png").write_text("fake image", encoding="utf-8")

    with pytest.raises(PermissionError):
        service.get_artifact("teste", "../fora.png", tmp_path)

    with pytest.raises(PermissionError):
        service.get_artifact("teste", "/etc/shadow", tmp_path)

    # Arquivo legítimo
    artifact = service.get_artifact("teste", "valido.png", tmp_path)
    assert artifact.is_file()
