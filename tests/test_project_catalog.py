import stat
from pathlib import Path

import pytest
import yaml

from uxsentinel.cli import EXIT_SUCESSO, async_main, list_registered_projects_cli
from uxsentinel.core.config import (
    ProjectCatalogEntry,
    ProjectScenarioItem,
    infer_project_metadata,
    list_registered_projects,
    register_project_scenario,
)
from uxsentinel.scenarios.parser import load_scenario


def test_infer_project_metadata_from_yaml_field(tmp_path: Path):
    scenario_file = tmp_path / "cenario.yaml"
    scenario_file.write_text("project: Sistema de Vendas\nsteps: []\n", encoding="utf-8")

    project_id, project_name, root = infer_project_metadata(scenario_file, {"project": "Sistema de Vendas"})
    assert project_id == "sistema-de-vendas"
    assert project_name == "Sistema de Vendas"
    assert root == tmp_path


def test_infer_project_metadata_from_projeto_field_pt(tmp_path: Path):
    scenario_file = tmp_path / "cenario.yaml"
    scenario_file.write_text("projeto: Meu Portal\nsteps: []\n", encoding="utf-8")

    project_id, project_name, root = infer_project_metadata(scenario_file, {"projeto": "Meu Portal"})
    assert project_id == "meu-portal"
    assert project_name == "Meu Portal"
    assert root == tmp_path


def test_infer_project_metadata_from_pyproject_toml(tmp_path: Path):
    proj_root = tmp_path / "erp_system"
    scenarios_dir = proj_root / "scenarios"
    scenarios_dir.mkdir(parents=True)

    pyproject = proj_root / "pyproject.toml"
    pyproject.write_text('[project]\nname = "erp-corporativo"\nversion = "1.0.0"\n', encoding="utf-8")

    scenario_file = scenarios_dir / "login.yaml"
    scenario_file.write_text("title: Login\nsteps: []\n", encoding="utf-8")

    project_id, project_name, root = infer_project_metadata(scenario_file, {})
    assert project_id == "erp-corporativo"
    assert project_name == "erp-corporativo"
    assert root == proj_root


def test_infer_project_metadata_from_package_json(tmp_path: Path):
    proj_root = tmp_path / "portal_web"
    scenarios_dir = proj_root / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True)

    pkg_json = proj_root / "package.json"
    pkg_json.write_text('{"name": "portal-cliente", "version": "2.0.0"}', encoding="utf-8")

    scenario_file = scenarios_dir / "checkout.yaml"
    scenario_file.write_text("title: Checkout\nsteps: []\n", encoding="utf-8")

    project_id, project_name, root = infer_project_metadata(scenario_file, {})
    assert project_id == "portal-cliente"
    assert project_name == "portal-cliente"
    assert root == proj_root


def test_infer_project_metadata_scenarios_folder_fallback(tmp_path: Path):
    proj_root = tmp_path / "loja_virtual"
    scenarios_dir = proj_root / "scenarios"
    scenarios_dir.mkdir(parents=True)

    scenario_file = scenarios_dir / "carrinho.yaml"
    scenario_file.write_text("title: Carrinho\nsteps: []\n", encoding="utf-8")

    project_id, project_name, root = infer_project_metadata(scenario_file, {})
    assert project_id == "loja-virtual"
    assert project_name == "loja_virtual"
    assert root == proj_root


def test_register_project_scenario_accumulates_and_preserves_multiple_scenarios(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    proj_dir = tmp_path / "meu_projeto"
    proj_dir.mkdir()

    scen_a = proj_dir / "login.yaml"
    scen_a.write_text("id: cenario_login\ntitle: Login de Usuário\nsteps: []\n", encoding="utf-8")

    scen_b = proj_dir / "checkout.yaml"
    scen_b.write_text("id: cenario_checkout\ntitle: Fluxo de Checkout\nsteps: []\n", encoding="utf-8")

    # 1. Registra cenário A
    register_project_scenario(
        scenario_path=scen_a,
        scenario_data={"id": "cenario_login", "title": "Login de Usuário", "project": "App E-commerce"},
        config_path=cfg_file,
    )

    data1 = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert "projects" in data1
    assert "app-e-commerce" in data1["projects"]
    assert "cenario_login" in data1["projects"]["app-e-commerce"]["scenarios"]
    assert data1["projects"]["app-e-commerce"]["name"] == "App E-commerce"
    assert data1["projects"]["app-e-commerce"]["root_path"] == str(proj_dir)

    # Verifica permissões 0600
    modo = stat.S_IMODE(cfg_file.stat().st_mode)
    assert modo == 0o600, f"esperado 0600, obtido {oct(modo)}"

    # 2. Registra cenário B no mesmo projeto
    register_project_scenario(
        scenario_path=scen_b,
        scenario_data={
            "id": "cenario_checkout",
            "title": "Fluxo de Checkout",
            "project": "App E-commerce",
        },
        config_path=cfg_file,
    )

    data2 = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    scenarios_map = data2["projects"]["app-e-commerce"]["scenarios"]

    # Ambos os cenários devem existir preservados e acumulados!
    assert "cenario_login" in scenarios_map
    assert "cenario_checkout" in scenarios_map
    assert scenarios_map["cenario_login"]["name"] == "Login de Usuário"
    assert scenarios_map["cenario_checkout"]["name"] == "Fluxo de Checkout"

    # 3. Atualiza cenário A
    register_project_scenario(
        scenario_path=scen_a,
        scenario_data={
            "id": "cenario_login",
            "title": "Login de Usuário Atualizado",
            "project": "App E-commerce",
        },
        config_path=cfg_file,
    )

    data3 = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert (
        data3["projects"]["app-e-commerce"]["scenarios"]["cenario_login"]["name"]
        == "Login de Usuário Atualizado"
    )
    assert "cenario_checkout" in data3["projects"]["app-e-commerce"]["scenarios"]


def test_register_project_scenario_with_explicit_project_name(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    scenario_file = tmp_path / "teste.yaml"
    scenario_file.write_text("title: Teste\nsteps: []\n", encoding="utf-8")

    register_project_scenario(
        scenario_path=scenario_file,
        scenario_data={"title": "Teste"},
        project_name="Plataforma de Pagamentos",
        config_path=cfg_file,
    )

    catalog = list_registered_projects(cfg_file)
    assert "plataforma-de-pagamentos" in catalog
    entry = catalog["plataforma-de-pagamentos"]
    assert entry.name == "Plataforma de Pagamentos"
    assert "teste" in entry.scenarios


def test_list_registered_projects_empty_or_missing(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist.yaml"
    assert list_registered_projects(non_existent) == {}

    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("", encoding="utf-8")
    assert list_registered_projects(empty_file) == {}


def test_list_registered_projects_structure(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_content = """
projects:
  projeto-alpha:
    name: "Projeto Alpha"
    root_path: "/workspace/alpha"
    last_run: "2026-09-22T12:00:00Z"
    scenarios:
      s1:
        id: "s1"
        name: "Cenário 1"
        path: "/workspace/alpha/scenarios/s1.yaml"
        last_run: "2026-09-22T12:00:00Z"
"""
    cfg_file.write_text(cfg_content, encoding="utf-8")

    catalog = list_registered_projects(cfg_file)
    assert len(catalog) == 1
    assert "projeto-alpha" in catalog

    entry = catalog["projeto-alpha"]
    assert isinstance(entry, ProjectCatalogEntry)
    assert entry.name == "Projeto Alpha"
    assert entry.root_path == "/workspace/alpha"
    assert len(entry.scenarios) == 1
    assert "s1" in entry.scenarios

    scen = entry.scenarios["s1"]
    assert isinstance(scen, ProjectScenarioItem)
    assert scen.name == "Cenário 1"
    assert scen.path == "/workspace/alpha/scenarios/s1.yaml"


def test_load_scenario_triggers_auto_registration(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    scenario_file = tmp_path / "scenarios" / "login.yaml"
    scenario_file.parent.mkdir(parents=True)
    scenario_file.write_text(
        "id: fluxo_auth\ntitle: Autenticação\nproject: Portal SSO\nsteps: []\n",
        encoding="utf-8",
    )

    loaded = load_scenario(str(scenario_file))
    assert loaded.id == "fluxo_auth"

    cfg_file = tmp_path / "config" / "uxsentinel" / "config.yaml"
    assert cfg_file.is_file()

    catalog = list_registered_projects(cfg_file)
    assert "portal-sso" in catalog
    assert "fluxo_auth" in catalog["portal-sso"].scenarios


def test_cli_list_projects_empty(capsys, tmp_path: Path):
    cfg_file = tmp_path / "empty_cfg.yaml"
    cfg_file.write_text("projects: {}\n", encoding="utf-8")

    list_registered_projects_cli(cfg_file)
    captured = capsys.readouterr()
    assert "Nenhum projeto cadastrado" in captured.out


def test_cli_list_projects_with_entries(capsys, tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
projects:
  financeiro:
    name: "Módulo Financeiro"
    root_path: "/opt/financeiro"
    last_run: "2026-09-22T14:30:00Z"
    scenarios:
      fatura:
        id: "fatura"
        name: "Emissão de Fatura"
        path: "/opt/financeiro/scenarios/fatura.yaml"
        last_run: "2026-09-22T14:30:00Z"
""",
        encoding="utf-8",
    )

    list_registered_projects_cli(cfg_file)
    captured = capsys.readouterr()
    assert "Catálogo de Projetos & Cenários Registrados" in captured.out
    assert "financeiro" in captured.out
    assert "Módulo" in captured.out
    assert "Financeiro" in captured.out
    assert "Fatura" in captured.out


@pytest.mark.asyncio
async def test_cli_main_list_projects_flag(monkeypatch, tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("projects: {}\n", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["uxsentinel", "--list-projects", "-c", str(cfg_file)])
    exit_code = await async_main()
    assert exit_code == EXIT_SUCESSO


@pytest.mark.asyncio
async def test_cli_project_name_override(monkeypatch, tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("projects: {}\n", encoding="utf-8")

    scenario_file = tmp_path / "scenarios" / "login.yaml"
    scenario_file.parent.mkdir(parents=True)
    scenario_file.write_text("title: Teste CLI\nsteps: []\n", encoding="utf-8")

    # Passa --project-name e invoca load_scenario diretamente com o parâmetro
    loaded = load_scenario(str(scenario_file), project_name="Meu Projeto CLI")
    assert loaded.title == "Teste CLI"

    register_project_scenario(
        scenario_path=scenario_file,
        project_name="Meu Projeto CLI",
        config_path=cfg_file,
    )
    catalog = list_registered_projects(cfg_file)
    assert "meu-projeto-cli" in catalog
    assert catalog["meu-projeto-cli"].name == "Meu Projeto CLI"
