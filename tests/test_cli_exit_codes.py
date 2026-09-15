"""Códigos de saída e erros de uso da CLI.

Em CI é preciso distinguir "a auditoria reprovou" (1) de "a ferramenta não
conseguiu rodar" (2). Um YAML malformado também não pode despejar traceback cru.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from uxsentinel.cli import EXIT_ERRO_EXECUCAO, async_main, main


@pytest.fixture(autouse=True)
def _config_isolado(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


@pytest.mark.asyncio
async def test_malformed_scenario_returns_execution_error_code(tmp_path: Path, monkeypatch):
    cenario = tmp_path / "quebrado.yaml"
    cenario.write_text("id: x\ntitle: y\nsteps: 'isto nao e uma lista'\n", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["uxsentinel", "-s", str(cenario)])

    with patch("uxsentinel.cli.console.print"):
        codigo = await async_main()

    assert codigo == EXIT_ERRO_EXECUCAO


@pytest.mark.asyncio
async def test_missing_scenario_returns_execution_error_code(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["uxsentinel", "-s", str(tmp_path / "inexistente.yaml")])

    with patch("uxsentinel.cli.console.print"):
        codigo = await async_main()

    assert codigo == EXIT_ERRO_EXECUCAO


def test_unexpected_crash_exits_with_execution_error_code():
    with (
        patch("uxsentinel.cli.async_main", side_effect=RuntimeError("falha interna inesperada")),
        patch("uxsentinel.cli.console.print"),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == EXIT_ERRO_EXECUCAO
