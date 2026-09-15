import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import (
    GlobalConfig,
    resolve_archive_dir,
    resolve_archive_mode,
)
from uxsentinel.core.models import Scenario, StepAction
from uxsentinel.reporter.archiver import archive_previous_reports


def test_archive_previous_reports_success(tmp_path: Path) -> None:
    """Testa compactação e arquivamento íntegro de relatórios anteriores em arquivo ZIP."""
    out_dir = tmp_path / "scenarios" / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    videos_dir = out_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    # Cria artefatos da execução anterior
    (out_dir / "cenario_report.html").write_text("<html>Dashboard Anterior</html>", encoding="utf-8")
    (out_dir / "cenario_report.json").write_text('{"status": "ok"}', encoding="utf-8")
    (out_dir / "cenario_report.md").write_text("# Relatório Anterior", encoding="utf-8")
    (out_dir / "cenario_cp1.png").write_bytes(b"\x89PNG\r\n\x1a\nFakeImageBytes")
    (videos_dir / "sessao.webm").write_bytes(b"FakeWebmVideoContent")

    zip_res = archive_previous_reports(out_dir, label="fluxo_cadastro")

    assert zip_res is not None
    assert zip_res.is_file()
    assert zip_res.parent == out_dir / "archive"
    assert "fluxo_cadastro" in zip_res.name
    assert zip_res.name.endswith("_archive.zip")

    # Verifica integridade do arquivo ZIP gerado
    with zipfile.ZipFile(zip_res, "r") as zf:
        names = zf.namelist()
        assert "cenario_report.html" in names
        assert "cenario_report.json" in names
        assert "cenario_report.md" in names
        assert "cenario_cp1.png" in names
        assert "videos/sessao.webm" in names

        # Valida conteúdo interno
        assert zf.read("cenario_report.html").decode("utf-8") == "<html>Dashboard Anterior</html>"
        assert zf.read("videos/sessao.webm") == b"FakeWebmVideoContent"

    # Valida limpeza do diretório de relatórios principal
    assert not (out_dir / "cenario_report.html").exists()
    assert not (out_dir / "cenario_report.json").exists()
    assert not (out_dir / "cenario_report.md").exists()
    assert not (out_dir / "cenario_cp1.png").exists()
    assert not (videos_dir / "sessao.webm").exists()
    assert not videos_dir.exists()  # Pasta vazia deve ser removida

    # Pasta archive deve ser preservada intacta
    assert (out_dir / "archive").is_dir()
    assert zip_res.exists()


def test_archive_idempotent_when_empty_or_nonexistent(tmp_path: Path) -> None:
    """Testa que diretórios vazios, inexistentes ou contendo apenas archive não geram zips supérfluos."""
    non_existent = tmp_path / "nao_existe"
    assert archive_previous_reports(non_existent) is None

    empty_dir = tmp_path / "empty_report"
    empty_dir.mkdir()
    assert archive_previous_reports(empty_dir) is None

    # Diretório que contém apenas a pasta archive (já existente)
    archive_only = tmp_path / "archive_only"
    (archive_only / "archive").mkdir(parents=True)
    (archive_only / "archive" / "old_run.zip").write_bytes(b"PK00FakeOldZip")
    assert archive_previous_reports(archive_only) is None

    # Nenhum zip novo deve ter sido gerado
    assert len(list((archive_only / "archive").iterdir())) == 1


def test_archive_does_not_nest_archives(tmp_path: Path) -> None:
    """Testa que execuções sucessivas não colocam arquivos ZIP anteriores dentro dos novos ZIPs."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True)

    # Rodada 1
    (out_dir / "report_rodada1.html").write_text("Rodada 1", encoding="utf-8")
    zip_rodada1 = archive_previous_reports(out_dir, label="rodada1")
    assert zip_rodada1 is not None and zip_rodada1.is_file()

    # Rodada 2
    (out_dir / "report_rodada2.html").write_text("Rodada 2", encoding="utf-8")
    zip_rodada2 = archive_previous_reports(out_dir, label="rodada2")
    assert zip_rodada2 is not None and zip_rodada2.is_file()

    # Verifica que zip_rodada1 NÃO está contido em zip_rodada2
    with zipfile.ZipFile(zip_rodada2, "r") as zf2:
        names = zf2.namelist()
        assert "report_rodada2.html" in names
        assert not any("rodada1" in n for n in names)
        assert not any(n.endswith(".zip") for n in names)

    # Ambos os zips estão preservados no diretório archive
    assert zip_rodada1.exists()
    assert zip_rodada2.exists()


def test_archive_custom_archive_dir(tmp_path: Path) -> None:
    """Testa arquivamento com diretório de arquivo explicitamente customizado."""
    out_dir = tmp_path / "report"
    out_dir.mkdir(parents=True)
    custom_archive = tmp_path / "meu_historico"

    (out_dir / "antigo.html").write_text("antigo", encoding="utf-8")
    zip_res = archive_previous_reports(out_dir, archive_dir=custom_archive, label="teste_custom")

    assert zip_res is not None
    assert zip_res.parent == custom_archive
    assert not (out_dir / "antigo.html").exists()
    assert zip_res.is_file()


def test_resolve_archive_mode_and_dir() -> None:
    """Testa a hierarquia estrita de resolução de arquivamento (CLI > Cenário > Config > Fallback)."""
    # 1. CLI Override vence tudo
    assert resolve_archive_mode(cli_archive=True, scenario_archive=False, config_archive=False) is True
    assert resolve_archive_mode(cli_archive=False, scenario_archive=True, config_archive=True) is False

    # 2. Cenário vence Config
    assert resolve_archive_mode(cli_archive=None, scenario_archive=True, config_archive=False) is True
    assert resolve_archive_mode(cli_archive=None, scenario_archive=False, config_archive=True) is False

    # 3. Config vence Fallback
    assert resolve_archive_mode(cli_archive=None, scenario_archive=None, config_archive=False) is False
    assert resolve_archive_mode(cli_archive=None, scenario_archive=None, config_archive=True) is True

    # 4. Fallback padrão é True
    assert resolve_archive_mode(cli_archive=None, scenario_archive=None, config_archive=None) is True

    # Resolução de archive_dir
    assert (
        resolve_archive_dir(
            cli_archive_dir="/cli/dir", scenario_archive_dir="/scen/dir", config_archive_dir="/cfg/dir"
        )
        == "/cli/dir"
    )
    assert (
        resolve_archive_dir(
            cli_archive_dir=None, scenario_archive_dir="/scen/dir", config_archive_dir="/cfg/dir"
        )
        == "/scen/dir"
    )
    assert (
        resolve_archive_dir(cli_archive_dir=None, scenario_archive_dir=None, config_archive_dir="/cfg/dir")
        == "/cfg/dir"
    )
    assert (
        resolve_archive_dir(cli_archive_dir=None, scenario_archive_dir=None, config_archive_dir=None) is None
    )


@pytest.mark.asyncio
async def test_agent_run_scenario_archives_previous_reports(tmp_path: Path) -> None:
    """Testa que o UXSentinelAgent arquiva automaticamente relatórios anteriores antes de nova execução."""
    out_dir = tmp_path / "scenarios" / "report"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Cria artefato da rodada anterior
    (out_dir / "antigo_relatorio.html").write_text("<h1>Rodada Anterior</h1>", encoding="utf-8")

    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(out_dir)
    cfg.reporting.archive_previous_reports = True

    scenario = Scenario(
        id="cenario_novo",
        title="Cenário Novo Teste",
        steps=[StepAction(action="goto", url="http://localhost:8000/teste")],
    )

    agent = UXSentinelAgent(cfg)

    # Mock da conexão com IA e da sessão do browser para teste hermético rápido
    with (
        patch.object(agent.inspector.client, "test_connection", AsyncMock(return_value=(True, "OK"))),
        patch("uxsentinel.core.agent.open_browser_session") as mock_session_ctx,
    ):
        mock_driver = AsyncMock()
        mock_driver.healing_events = []
        mock_driver.page = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_driver

        report = await agent.run_scenario(scenario)

        # O relatório corrente deve ter gravado o path do arquivo arquivado
        assert report.archived_report_path is not None
        archived_zip = Path(report.archived_report_path)
        assert archived_zip.is_file()
        assert "cenario_novo" in archived_zip.name

        # Verifica que o arquivo antigo foi empacotado no zip e não está mais solto no out_dir
        assert not (out_dir / "antigo_relatorio.html").exists()
        with zipfile.ZipFile(archived_zip, "r") as zf:
            assert "antigo_relatorio.html" in zf.namelist()
