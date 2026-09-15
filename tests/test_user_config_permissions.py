"""Permissões do arquivo de configuração do usuário.

O config de usuário guarda credenciais (token do Jira, chaves de API quando o
usuário cola o valor direto em vez de ${VAR}), então não pode nascer legível
para outros usuários da máquina.
"""

import stat
from pathlib import Path

from uxsentinel.core.config import ensure_user_config


def test_created_user_config_is_readable_only_by_owner(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    cfg_file = ensure_user_config()

    assert cfg_file.is_file()
    modo = stat.S_IMODE(cfg_file.stat().st_mode)
    assert modo == 0o600, f"esperado 0600, obtido {oct(modo)}"
