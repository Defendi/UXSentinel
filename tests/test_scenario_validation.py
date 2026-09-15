"""Validação estrutural de cenários YAML.

Um cenário malformado precisa falhar de forma explícita. Silenciosamente virar um
cenário de zero passos faria a auditoria "passar" sem ter executado nada.
"""

import tempfile
from pathlib import Path

import pytest

from uxsentinel.scenarios.parser import load_scenario


def _load_from_yaml(content: str):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        return load_scenario(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_steps_that_is_not_a_list_raises_clear_error():
    with pytest.raises(ValueError, match="steps"):
        _load_from_yaml(
            """
id: cenario_malformado
title: Steps declarado como texto
steps: "click no botao"
"""
        )


def test_step_entry_that_is_not_a_mapping_raises_clear_error():
    with pytest.raises(ValueError, match="passo"):
        _load_from_yaml(
            """
id: cenario_malformado_2
title: Item de step invalido
steps:
  - action: "goto"
    url: "https://exemplo.test"
  - "wait_until_ready"
"""
        )
