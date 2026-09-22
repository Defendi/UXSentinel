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


def test_scenario_service_find_scenario_path(tmp_path: Path):
    """Valida localização de caminhos de cenários locais, biblioteca e proteção contra path traversal."""
    service = ScenarioService()

    # Cria cenário local no workspace
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    scenario_file = scenarios_dir / "meu_fluxo.yaml"
    scenario_file.write_text(
        """id: meu_fluxo_id
title: "Meu Fluxo"
steps:
  - action: goto
    url: "https://example.com"
""",
        encoding="utf-8",
    )

    # 1. Encontra por ID
    found_by_id = service.find_scenario_path("meu_fluxo_id", tmp_path)
    assert found_by_id is not None
    assert found_by_id.resolve() == scenario_file.resolve()

    # 2. Encontra por nome do arquivo (stem)
    found_by_stem = service.find_scenario_path("meu_fluxo", tmp_path)
    assert found_by_stem is not None
    assert found_by_stem.resolve() == scenario_file.resolve()

    # 3. Encontra cenário da biblioteca interna embutida (ex: exemplo_odoo)
    found_lib = service.find_scenario_path("exemplo_odoo", tmp_path)
    assert found_lib is not None
    assert found_lib.is_file()

    # 4. Retorna None para cenário inexistente
    assert service.find_scenario_path("cenario_fantasma_xyz", tmp_path) is None

    # 5. Retorna None para tentativa de path traversal
    assert service.find_scenario_path("../../etc/passwd", tmp_path) is None
