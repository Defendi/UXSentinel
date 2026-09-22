"""Testes herméticos para ConfigService (UXS-33)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uxsentinel.service.config_service import ConfigService, ConfigUpdateDTO


def test_config_service_masks_secrets(tmp_path: Path):
    """Garante que SafeConfigDTO mascara todos os tokens e senhas reais."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """active_provider: "anthropic_cloud"
jira:
  enabled: true
  url: "https://mycorp.atlassian.net"
  email: "qa@mycorp.com"
  api_token: "SEGREDO_SUPER_CONFIDENCIAL_12345"
  project_key: "PROJ"
providers:
  anthropic_cloud:
    type: "api"
    service: "anthropic"
    model: "claude-3-5-sonnet"
    api_key: "CHAVE_SECRETA_ANTHROPIC"
""",
        encoding="utf-8",
    )

    service = ConfigService(config_file)
    safe = service.get_safe_config()

    # Nenhum valor real deve vazar
    assert "SEGREDO_SUPER_CONFIDENCIAL_12345" not in str(safe.model_dump())
    assert "CHAVE_SECRETA_ANTHROPIC" not in str(safe.model_dump())

    # Indicadores de status
    assert safe.jira.api_token.configured is True
    assert safe.providers["anthropic_cloud"].has_api_key is True
    assert safe.jira.email == "qa@mycorp.com"


def test_config_service_persists_with_0600_permissions(tmp_path: Path):
    """Valida gravação segura com permissões 0600 em disco."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("active_provider: 'anthropic_cloud'\n", encoding="utf-8")

    service = ConfigService(config_file)
    service.update_config(ConfigUpdateDTO(browser_headless=True, browser_slow_mo_ms=500))

    assert config_file.is_file()
    # Verifica permissão 0600 (apenas proprietário tem leitura/escrita)
    stat = config_file.stat()
    assert (stat.st_mode & 0o777) == 0o600

    safe = service.get_safe_config()
    assert safe.browser.headless is True
    assert safe.browser.slow_mo_ms == 500


@pytest.mark.asyncio
async def test_config_service_test_jira_connection_mocked():
    """Valida teste de conexão HTTP com o Jira Cloud isolado com mocks."""
    service = ConfigService()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        # 1. Sucesso 200
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"displayName": "Engenheiro QA"}
        mock_get.return_value = mock_resp

        res_ok = await service.test_jira_connection(
            url="https://empresa.atlassian.net",
            email="qa@empresa.com",
            token="token123",
        )
        assert res_ok.valid is True
        assert "Engenheiro QA" in res_ok.message

        # 2. Falha 401
        mock_resp.status_code = 401
        res_fail = await service.test_jira_connection(
            url="https://empresa.atlassian.net",
            email="qa@empresa.com",
            token="token_errado",
        )
        assert res_fail.valid is False
        assert "não autorizado" in res_fail.message


@pytest.mark.asyncio
async def test_config_service_test_ai_connection_mocked():
    """Valida teste de conectividade com LLM isolado por mock."""
    service = ConfigService()

    with patch(
        "uxsentinel.service.config_service.UnifiedVisionClient.analyze", new_callable=AsyncMock
    ) as mock_analyze:
        mock_analyze.return_value = "OK"

        res = await service.test_ai_connection("gemini_sso")
        assert res.valid is True
        assert "conectado com sucesso" in res.message


def test_config_service_resolves_config_files_locations(tmp_path: Path):
    """Valida resolução e status de caminhos em ConfigFilesDTO."""
    proj_dir = tmp_path / "meu_projeto"
    proj_dir.mkdir(parents=True)
    cfg_file = proj_dir / "uxsentinel.yaml"
    cfg_file.write_text("active_provider: 'anthropic_cloud'\n", encoding="utf-8")
    env_file = proj_dir / ".env"
    env_file.write_text("API_KEY=123\n", encoding="utf-8")

    service = ConfigService()
    safe = service.get_safe_config(project_dir=proj_dir)

    assert safe.config_files is not None
    cf = safe.config_files
    assert cf.project_dir == str(proj_dir.resolve())
    assert cf.project_config_path == str(cfg_file.resolve())
    assert cf.project_config_exists is True
    assert cf.env_path == str(env_file.resolve())
    assert cf.env_exists is True
    assert cf.active_config_path == str(cfg_file.resolve())
    assert isinstance(cf.user_config_exists, bool)
