"""Testes herméticos para ScenarioService (UXS-32)."""

from pathlib import Path

import pytest

from uxsentinel.service.scenario_service import ScenarioService


def test_scenario_service_lists_project_and_library_scenarios(tmp_path: Path):
    """Valida se a listagem agrupa cenários locais e da biblioteca interna."""
    service = ScenarioService()

    # Cria cenário local de teste no tmp_path
    local_dir = tmp_path / "scenarios"
    local_dir.mkdir()
    (local_dir / "teste_local.yaml").write_text(
        """version: "1.0"
id: "local_01"
title: "Cenário Local de Teste"
profile: "generic"
steps:
  - action: "goto"
    url: "https://example.com"
""",
        encoding="utf-8",
    )

    scenarios = service.list_scenarios(tmp_path)
    ids = [s.id for s in scenarios]

    assert "local_01" in ids
    local_sc = next(s for s in scenarios if s.id == "local_01")
    assert local_sc.source == "project"
    assert local_sc.step_count == 1

    # Verifica se a biblioteca interna foi incluída
    library_items = [s for s in scenarios if s.source == "library"]
    assert len(library_items) > 0


def test_scenario_service_crud_lifecycle(tmp_path: Path):
    """Valida ciclo completo: salvar, buscar, validar e excluir cenário."""
    service = ScenarioService()

    valid_yaml = """version: "1.0"
id: "crud_test"
title: "Teste CRUD"
steps:
  - action: "goto"
    url: "https://example.com/login"
  - action: "click"
    selector: "button.submit"
"""

    # 1. Salvar
    saved_path = service.save_scenario(valid_yaml, "crud_test.yaml", tmp_path)
    assert saved_path.is_file()

    # 2. Obter detalhe
    detail = service.get_scenario("crud_test", tmp_path)
    assert detail.id == "crud_test"
    assert len(detail.steps) == 2
    assert detail.steps[0].action == "goto"
    assert detail.steps[1].selector == "button.submit"

    # 3. Excluir
    deleted = service.delete_scenario("crud_test", tmp_path)
    assert deleted is True
    assert not saved_path.exists()


def test_scenario_service_path_traversal_protection(tmp_path: Path):
    """Garante que qualquer tentativa de path traversal seja bloqueada com PermissionError."""
    service = ScenarioService()

    with pytest.raises(PermissionError):
        service.get_scenario("../../etc/passwd", tmp_path)

    with pytest.raises(PermissionError):
        service.save_scenario("steps: []", "../malicious.yaml", tmp_path)

    with pytest.raises(PermissionError):
        service.delete_scenario("/root/scenario", tmp_path)


def test_scenario_service_validation_rules():
    """Valida se as regras de sintaxe e de passos retornam erros estruturados."""
    service = ScenarioService()

    # YAML inválido por sintaxe
    res1 = service.validate_scenario("steps: [invalido")
    assert res1.valid is False
    assert any(e.field == "syntax" for e in res1.errors)

    # YAML sem passos
    res2 = service.validate_scenario("title: 'Sem passos'")
    assert res2.valid is False
    assert any(e.field == "steps" for e in res2.errors)

    # Ação goto sem url
    res3 = service.validate_scenario("""steps:
  - action: "goto"
""")
    assert res3.valid is False
    assert any(e.field == "url" for e in res3.errors)

    # Ação click sem seletor
    res4 = service.validate_scenario("""steps:
  - action: "click"
""")
    assert res4.valid is False
    assert any(e.field == "selector" for e in res4.errors)
