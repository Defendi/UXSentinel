"""Testes unitários herméticos para o auto-refresh preemptivo de tokens Claude OAuth2 e auto-recuperação."""

import json
import time
from unittest.mock import patch

import httpx
import pytest

from uxsentinel.core.config import GlobalConfig, ProviderSettings
from uxsentinel.core.sso import (
    TOKEN_EXPIRY_BUFFER_SECONDS,
    get_cached_token,
    save_cached_token,
)
from uxsentinel.vision.client import UnifiedVisionClient


def test_token_expiry_buffer_constant():
    """Valida que a constante de buffer de segurança é de 300 segundos."""
    assert TOKEN_EXPIRY_BUFFER_SECONDS == 300


def test_save_cached_token_auto_expiry_for_oauth(tmp_path, monkeypatch):
    """Garante que tokens Claude OAuth (sk-ant-oat) sem expires_in recebam 3500s de expiração."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    now = 10000.0
    monkeypatch.setattr(time, "time", lambda: now)

    save_cached_token("claude_sso", "sk-ant-oat01-test12345")
    data = json.loads(test_cache.read_text(encoding="utf-8"))
    assert data["claude_sso"]["expires_at"] == now + 3500.0
    assert data["claude_sso"]["token"] == "sk-ant-oat01-test12345"


def test_save_cached_token_preserves_existing_refresh_token(tmp_path, monkeypatch):
    """Testa que salvar novo token sem refresh_token preserva o refresh_token anterior."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    save_cached_token(
        "claude_sso",
        "sk-ant-oat01-primeiro",
        expires_in=3600,
        refresh_token="ref-original-123",
    )
    data = json.loads(test_cache.read_text(encoding="utf-8"))
    assert data["claude_sso"]["refresh_token"] == "ref-original-123"

    # Atualiza token sem fornecer refresh_token
    save_cached_token("claude_sso", "sk-ant-oat01-segundo", expires_in=3600)
    data = json.loads(test_cache.read_text(encoding="utf-8"))
    assert data["claude_sso"]["token"] == "sk-ant-oat01-segundo"
    assert data["claude_sso"]["refresh_token"] == "ref-original-123"


def test_preemptive_refresh_when_expiring_soon(tmp_path, monkeypatch):
    """Valida que quando faltam menos de TOKEN_EXPIRY_BUFFER_SECONDS, o refresh preemptivo é acionado."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    current_time = 10000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    # Token que expira em 200 segundos (menos que 300s buffer)
    save_cached_token(
        "claude_sso",
        "sk-ant-oat01-quase-expirando",
        expires_in=200,
        refresh_token="ref-valido-123",
    )

    with patch(
        "uxsentinel.core.sso.refresh_claude_oauth_token",
        return_value="sk-ant-oat01-renovado-com-sucesso",
    ) as mock_refresh:
        result = get_cached_token("claude_sso")
        assert result == "sk-ant-oat01-renovado-com-sucesso"
        mock_refresh.assert_called_once_with("ref-valido-123")


def test_fallback_to_current_token_if_preemptive_refresh_fails(tmp_path, monkeypatch):
    """Se o token está dentro da margem de 300s mas ainda não expirou totalmente e o refresh falhar, retorna o atual."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    current_time = 10000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    save_cached_token(
        "claude_sso",
        "sk-ant-oat01-ainda-vivo",
        expires_in=150,
        refresh_token="ref-falho",
    )

    with patch("uxsentinel.core.sso.refresh_claude_oauth_token", return_value=None):
        result = get_cached_token("claude_sso")
        # Retorna o token atual como fallback de melhor esforço
        assert result == "sk-ant-oat01-ainda-vivo"


def test_sync_with_claude_cli_credentials_valid(tmp_path, monkeypatch):
    """Testa sincronização e importação direta de ~/.claude/.credentials.json com token ainda válido."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    current_time = 10000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    # ~/.claude/.credentials.json falso
    fake_cli_creds = tmp_path / "credentials.json"
    cli_data = {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat01-cli-valido",
            "refreshToken": "ref-cli-123",
            "expiresAt": (current_time + 1000) * 1000,  # em ms
        }
    }
    fake_cli_creds.write_text(json.dumps(cli_data), encoding="utf-8")

    with patch("pathlib.Path.home", return_value=tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / ".credentials.json").write_text(json.dumps(cli_data), encoding="utf-8")

        result = get_cached_token("claude_sso")
        assert result == "sk-ant-oat01-cli-valido"

        # Verifica se sincronizou no sso_cache.json
        cache_data = json.loads(test_cache.read_text(encoding="utf-8"))
        assert cache_data["claude_sso"]["token"] == "sk-ant-oat01-cli-valido"
        assert cache_data["claude_sso"]["refresh_token"] == "ref-cli-123"


def test_sync_with_claude_cli_credentials_expired_refreshed(tmp_path, monkeypatch):
    """Testa sincronização com ~/.claude/.credentials.json quando token CLI está vencido mas tem refreshToken."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    current_time = 10000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    cli_data = {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat01-cli-expirado",
            "refreshToken": "ref-cli-renovavel",
            "expiresAt": (current_time - 100) * 1000,  # já expirou
        }
    }
    (claude_dir / ".credentials.json").write_text(json.dumps(cli_data), encoding="utf-8")

    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch(
            "uxsentinel.core.sso.refresh_claude_oauth_token",
            return_value="sk-ant-oat01-renovado-via-cli-ref",
        ) as mock_ref,
    ):
        result = get_cached_token("claude_sso")
        assert result == "sk-ant-oat01-renovado-via-cli-ref"
        mock_ref.assert_called_once_with("ref-cli-renovavel")


def test_force_refresh_in_ensure_provider_auth(tmp_path, monkeypatch):
    """Valida que _ensure_provider_auth com force_refresh=True executa a renovação imediatamente."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    save_cached_token(
        "claude_sso",
        "sk-ant-oat01-antigo",
        expires_in=3000,
        refresh_token="ref-existente-456",
    )

    config = GlobalConfig()
    provider = ProviderSettings(
        type="sso",
        service="anthropic",
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-oat01-antigo",
        headers={"Authorization": "Bearer sk-ant-oat01-antigo"},
    )
    config.providers = {"claude_sso": provider}
    client = UnifiedVisionClient(config)

    with patch(
        "uxsentinel.core.sso.refresh_claude_oauth_token",
        return_value="sk-ant-oat01-novo-forcado",
    ) as mock_ref:
        tok = client._ensure_provider_auth(provider, interactive=False, force_refresh=True)
        assert tok == "sk-ant-oat01-novo-forcado"
        assert provider.api_key == "sk-ant-oat01-novo-forcado"
        assert provider.headers["Authorization"] == "Bearer sk-ant-oat01-novo-forcado"
        mock_ref.assert_called_once_with("ref-existente-456")


@pytest.mark.asyncio
async def test_call_anthropic_auto_recovery_on_401(tmp_path, monkeypatch):
    """Testa auto-recuperação transparente em _call_anthropic após receber HTTP 401 em provedor SSO."""
    test_cache = tmp_path / "sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    save_cached_token(
        "claude_sso",
        "sk-ant-oat01-expirado",
        expires_in=3000,
        refresh_token="ref-on-the-fly-789",
    )

    config = GlobalConfig()
    provider = ProviderSettings(
        type="sso",
        service="anthropic",
        model="claude-haiku-4-5",
        api_key="sk-ant-oat01-expirado",
        headers={"Authorization": "Bearer sk-ant-oat01-expirado"},
    )
    config.providers = {"claude_sso": provider}
    client = UnifiedVisionClient(config)

    # Primeira resposta: 401 Unauthorized; Segunda resposta: 200 OK
    resp_401 = httpx.Response(401, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    resp_200 = httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        json={"content": [{"type": "text", "text": "Análise concluída com sucesso após refresh!"}]},
    )

    call_count = 0

    async def fake_post(url, json=None, headers=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPStatusError("Unauthorized", request=resp_401.request, response=resp_401)
        return resp_200

    with (
        patch("httpx.AsyncClient.post", side_effect=fake_post),
        patch(
            "uxsentinel.core.sso.refresh_claude_oauth_token",
            return_value="sk-ant-oat01-novo-renovado",
        ) as mock_ref,
    ):
        result = await client._call_anthropic(
            provider,
            image_base64="fake-b64",
            user_prompt="Verifique o botão",
            media_type="image/png",
        )
        assert result == "Análise concluída com sucesso após refresh!"
        assert call_count == 2
        mock_ref.assert_called_once_with("ref-on-the-fly-789")
        assert provider.api_key == "sk-ant-oat01-novo-renovado"
