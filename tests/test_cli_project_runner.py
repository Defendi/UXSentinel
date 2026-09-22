from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.cli import EXIT_ERRO_EXECUCAO, EXIT_SUCESSO, async_main
from uxsentinel.core.config import (
    ProjectCatalogEntry,
    find_project_in_catalog,
    find_scenario_in_project,
)
from uxsentinel.core.models import TestReport


@pytest.fixture
def sample_catalog(tmp_path: Path) -> Path:
    cfg_file = tmp_path / "config.yaml"
    cfg_content = f"""
projects:
  portal-vendas:
    name: "Portal de Vendas"
    root_path: "{tmp_path}/vendas"
    scenarios:
      login:
        id: "login"
        name: "Login de Vendedor"
        path: "{tmp_path}/vendas/scenarios/login.yaml"
      checkout:
        id: "checkout"
        name: "Finalização de Pedido"
        path: "{tmp_path}/vendas/scenarios/checkout.yaml"
  erp-financeiro:
    name: "ERP Financeiro"
    root_path: "{tmp_path}/erp"
    scenarios:
      fatura:
        id: "fatura"
        name: "Emissão de Fatura"
        path: "{tmp_path}/erp/scenarios/fatura.yaml"
"""
    cfg_file.write_text(cfg_content, encoding="utf-8")

    # Cria os arquivos físicos fictícios
    for p in [
        tmp_path / "vendas/scenarios/login.yaml",
        tmp_path / "vendas/scenarios/checkout.yaml",
        tmp_path / "erp/scenarios/fatura.yaml",
    ]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("steps: []\n", encoding="utf-8")

    return cfg_file


def test_find_project_in_catalog_exact_slug(sample_catalog: Path):
    result = find_project_in_catalog("portal-vendas", sample_catalog)
    assert result is not None
    slug, entry = result
    assert slug == "portal-vendas"
    assert entry.name == "Portal de Vendas"


def test_find_project_in_catalog_by_name(sample_catalog: Path):
    result = find_project_in_catalog("portal de vendas", sample_catalog)
    assert result is not None
    slug, entry = result
    assert slug == "portal-vendas"
    assert entry.name == "Portal de Vendas"


def test_find_project_in_catalog_partial_match(sample_catalog: Path):
    result = find_project_in_catalog("Financeiro", sample_catalog)
    assert result is not None
    slug, entry = result
    assert slug == "erp-financeiro"
    assert entry.name == "ERP Financeiro"


def test_find_project_in_catalog_not_found(sample_catalog: Path):
    assert find_project_in_catalog("projeto-fantasma", sample_catalog) is None
    assert find_project_in_catalog("", sample_catalog) is None


def test_find_scenario_in_project_by_id(sample_catalog: Path):
    result = find_project_in_catalog("portal-vendas", sample_catalog)
    assert result is not None
    _, entry = result

    scen = find_scenario_in_project(entry, "login")
    assert scen is not None
    assert scen.id == "login"
    assert scen.name == "Login de Vendedor"


def test_find_scenario_in_project_by_title(sample_catalog: Path):
    result = find_project_in_catalog("portal-vendas", sample_catalog)
    assert result is not None
    _, entry = result

    scen = find_scenario_in_project(entry, "finalização de pedido")
    assert scen is not None
    assert scen.id == "checkout"


def test_find_scenario_in_project_by_filename(sample_catalog: Path):
    result = find_project_in_catalog("portal-vendas", sample_catalog)
    assert result is not None
    _, entry = result

    scen = find_scenario_in_project(entry, "checkout.yaml")
    assert scen is not None
    assert scen.id == "checkout"


def test_find_scenario_in_project_not_found():
    entry = ProjectCatalogEntry(name="Teste", root_path="/test", scenarios={})
    assert find_scenario_in_project(entry, "inexistente") is None
    assert find_scenario_in_project(entry, "") is None


@pytest.mark.asyncio
async def test_cli_run_project_single_scenario(sample_catalog: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["uxsentinel", "--project", "ERP Financeiro", "-c", str(sample_catalog)],
    )

    mock_report = TestReport(
        scenario_id="fatura",
        scenario_title="Emissão de Fatura",
        success=True,
        total_steps=3,
        duration_seconds=1.2,
    )

    with patch("uxsentinel.cli.ExecutionService.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_report
        code = await async_main()

    assert code == EXIT_SUCESSO
    assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_cli_run_project_specific_scenario(sample_catalog: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "uxsentinel",
            "--project",
            "Portal de Vendas",
            "-s",
            "login",
            "-c",
            str(sample_catalog),
        ],
    )

    mock_report = TestReport(
        scenario_id="login",
        scenario_title="Login",
        success=True,
        total_steps=2,
        duration_seconds=0.8,
    )

    with patch("uxsentinel.cli.ExecutionService.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_report
        code = await async_main()

    assert code == EXIT_SUCESSO
    assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_cli_run_project_all_scenarios_summary(sample_catalog: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["uxsentinel", "-P", "portal-vendas", "-c", str(sample_catalog)],
    )

    mock_report1 = TestReport(
        scenario_id="login",
        scenario_title="Login",
        success=True,
        total_steps=2,
        duration_seconds=0.8,
    )
    mock_report2 = TestReport(
        scenario_id="checkout",
        scenario_title="Checkout",
        success=True,
        total_steps=4,
        duration_seconds=1.5,
    )

    with patch("uxsentinel.cli.ExecutionService.run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [mock_report1, mock_report2]
        code = await async_main()

    assert code == EXIT_SUCESSO
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_cli_project_not_found_returns_error(sample_catalog: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["uxsentinel", "--project", "inexistente", "-c", str(sample_catalog)],
    )

    code = await async_main()
    assert code == EXIT_ERRO_EXECUCAO


@pytest.mark.asyncio
async def test_cli_scenario_in_project_not_found_returns_error(sample_catalog: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "uxsentinel",
            "--project",
            "ERP Financeiro",
            "-s",
            "cenario_fantasma",
            "-c",
            str(sample_catalog),
        ],
    )

    code = await async_main()
    assert code == EXIT_ERRO_EXECUCAO


@pytest.mark.asyncio
async def test_cli_external_scenario_success(tmp_path: Path, monkeypatch):
    ext_dir = tmp_path / "externo"
    ext_dir.mkdir()
    ext_scen = ext_dir / "auditoria.yaml"
    ext_scen.write_text("steps: []\n", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["uxsentinel", "--scenario-path", str(ext_scen)])

    mock_report = TestReport(
        scenario_id="auditoria",
        scenario_title="Auditoria",
        success=True,
        total_steps=1,
    )

    with patch("uxsentinel.cli.ExecutionService.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_report
        code = await async_main()

    assert code == EXIT_SUCESSO
    assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_cli_external_scenario_missing_returns_error(tmp_path: Path, monkeypatch):
    missing_file = tmp_path / "nao_existe.yaml"
    monkeypatch.setattr("sys.argv", ["uxsentinel", "--scenario-path", str(missing_file)])

    code = await async_main()
    assert code == EXIT_ERRO_EXECUCAO


@pytest.mark.asyncio
async def test_cli_select_project_interactive(sample_catalog: Path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["uxsentinel", "--select-project", "-c", str(sample_catalog)])

    # Simula o usuário digitando "1" no prompt
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *args, **kwargs: "1")

    mock_report = TestReport(
        scenario_id="fatura",
        scenario_title="Emissão",
        success=True,
        total_steps=2,
    )

    with patch("uxsentinel.cli.ExecutionService.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_report
        code = await async_main()

    assert code == EXIT_SUCESSO


@pytest.mark.asyncio
async def test_cli_select_project_cancel(sample_catalog: Path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["uxsentinel", "--select-project", "-c", str(sample_catalog)])

    # Simula o usuário digitando "q" para cancelar
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *args, **kwargs: "q")

    code = await async_main()
    assert code == EXIT_SUCESSO
