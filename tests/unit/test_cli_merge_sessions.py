"""Testes unitários herméticos para os comandos e flags de mesclagem na CLI (UXS-92)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from uxsentinel.cli import EXIT_ERRO_EXECUCAO, EXIT_SUCESSO, async_main
from uxsentinel.core.models import CheckpointResult, TestReport


@pytest.fixture(autouse=True)
def _config_isolado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante isolamento completo de configuração XDG."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


@pytest.fixture
def session_reports(tmp_path: Path) -> tuple[Path, Path]:
    """Cria dois arquivos de relatório de auditoria para teste."""
    rep1 = TestReport(
        scenario_id="sessao_login",
        scenario_title="Sessão de Login",
        started_at=datetime(2026, 9, 25, 10, 0, 0, tzinfo=UTC),
        duration_seconds=12.5,
        checkpoints=[
            CheckpointResult(
                name="cp_login",
                timestamp=datetime(2026, 9, 25, 10, 1, 0, tzinfo=UTC),
                expected_behavior="Formulário visível",
            )
        ],
    )
    rep2 = TestReport(
        scenario_id="sessao_checkout",
        scenario_title="Sessão de Checkout",
        started_at=datetime(2026, 9, 25, 10, 15, 0, tzinfo=UTC),
        duration_seconds=22.5,
        checkpoints=[
            CheckpointResult(
                name="cp_checkout",
                timestamp=datetime(2026, 9, 25, 10, 16, 0, tzinfo=UTC),
                expected_behavior="Botão de pagamento habilitado",
            )
        ],
    )

    f1 = tmp_path / "login_report.json"
    f2 = tmp_path / "checkout_report.json"

    f1.write_text(json.dumps(rep1.model_dump(mode="json")), encoding="utf-8")
    f2.write_text(json.dumps(rep2.model_dump(mode="json")), encoding="utf-8")

    return f1, f2


@pytest.mark.asyncio
async def test_cli_merge_sessions_success(
    session_reports: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valida a execução de sucesso do comando --merge-sessions com arquivo de saída."""
    f1, f2 = session_reports
    output_file = tmp_path / "consolidado_report.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "uxsentinel",
            "--merge-sessions",
            str(f1),
            str(f2),
            "--merge-output",
            str(output_file),
        ],
    )

    with patch("uxsentinel.cli.console.print") as mock_print:
        exit_code = await async_main()

    assert exit_code == EXIT_SUCESSO
    assert output_file.is_file()
    assert mock_print.called

    # Verifica o conteúdo mesclado gravado
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(data["checkpoints"]) == 2
    assert data["duration_seconds"] == 35.0


@pytest.mark.asyncio
async def test_cli_merge_sessions_missing_file(
    session_reports: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garante retorno de EXIT_ERRO_EXECUCAO quando algum arquivo informado não existe."""
    f1, _ = session_reports
    f_inexistente = tmp_path / "arquivo_fantasma.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "uxsentinel",
            "--merge-sessions",
            str(f1),
            str(f_inexistente),
        ],
    )

    with patch("uxsentinel.cli.console.print"):
        exit_code = await async_main()

    assert exit_code == EXIT_ERRO_EXECUCAO


@pytest.mark.asyncio
async def test_cli_merge_sessions_empty_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante erro de execução quando a flag é chamada sem sessões."""
    monkeypatch.setattr("sys.argv", ["uxsentinel", "merge-sessions"])

    with patch("uxsentinel.cli.console.print"):
        exit_code = await async_main()

    assert exit_code == EXIT_ERRO_EXECUCAO


@pytest.mark.asyncio
async def test_cli_merge_sessions_positional_mode(
    session_reports: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valida execução quando invocado com o argumento posicional merge-sessions."""
    f1, f2 = session_reports
    output_file = tmp_path / "pos_out.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "uxsentinel",
            "merge-sessions",
            "--merge-sessions",
            str(f1),
            str(f2),
            "--merge-output",
            str(output_file),
        ],
    )

    with patch("uxsentinel.cli.console.print"):
        exit_code = await async_main()

    assert exit_code == EXIT_SUCESSO
    assert output_file.is_file()
