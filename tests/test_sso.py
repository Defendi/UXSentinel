"""Testes unitários herméticos para o gerenciador de autenticação SSO."""

import json
from unittest.mock import MagicMock, patch

from uxsentinel.core.sso import (
    CLAUDE_OAUTH_MANUAL_REDIRECT_URL,
    clear_cached_token,
    exchange_claude_oauth_code,
    generate_pkce_pair,
    get_cached_token,
    refresh_claude_oauth_token,
    save_cached_token,
)


def test_generate_pkce_pair():
    """Gera code_verifier e code_challenge base64url válidos conforme RFC 7636."""
    verifier, challenge = generate_pkce_pair()
    assert isinstance(verifier, str)
    assert isinstance(challenge, str)
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert "=" not in challenge
    assert "+" not in challenge
    assert "/" not in challenge


def test_save_and_get_cached_token(tmp_path, monkeypatch):
    """Testa salvar e recuperar token do cache seguro."""
    test_cache = tmp_path / "test_sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    assert get_cached_token("test_provider") is None

    save_cached_token("test_provider", "token_abc123", expires_in=3600, refresh_token="refresh_xyz")
    assert get_cached_token("test_provider") == "token_abc123"

    data = json.loads(test_cache.read_text(encoding="utf-8"))
    assert data["test_provider"]["token"] == "token_abc123"
    assert data["test_provider"]["refresh_token"] == "refresh_xyz"
    assert "expires_at" in data["test_provider"]


def test_clear_cached_token(tmp_path, monkeypatch):
    """Testa remoção de token específico e limpeza total do cache."""
    test_cache = tmp_path / "test_sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    save_cached_token("prov1", "tok1")
    save_cached_token("prov2", "tok2")

    assert get_cached_token("prov1") == "tok1"
    assert get_cached_token("prov2") == "tok2"

    cleared = clear_cached_token("prov1")
    assert cleared is True
    assert get_cached_token("prov1") is None
    assert get_cached_token("prov2") == "tok2"

    clear_all = clear_cached_token(None)
    assert clear_all is True
    assert not test_cache.exists()


def test_exchange_claude_oauth_code_success():
    """Testa troca de authorization_code por tokens Anthropic com mock hermético."""
    mock_resp_data = {
        "access_token": "sk-ant-oat01-test-token",
        "refresh_token": "sk-ant-ort01-test-refresh",
        "expires_in": 3600,
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        token, expires_in, refresh_tok = exchange_claude_oauth_code(
            code_or_raw="cai_test_code#test_state",
            code_verifier="test_verifier_string_43_chars_long_12345",
            redirect_uri=CLAUDE_OAUTH_MANUAL_REDIRECT_URL,
            state="test_state",
        )

        assert token == "sk-ant-oat01-test-token"
        assert expires_in == 3600
        assert refresh_tok == "sk-ant-ort01-test-refresh"


def test_refresh_claude_oauth_token_success(tmp_path, monkeypatch):
    """Testa renovação de token OAuth Claude via refresh_token com mock hermético."""
    test_cache = tmp_path / "test_sso_cache.json"
    monkeypatch.setattr("uxsentinel.core.sso.get_sso_cache_file", lambda: test_cache)

    mock_resp_data = {
        "access_token": "sk-ant-oat01-renewed-token",
        "refresh_token": "sk-ant-ort01-new-refresh",
        "expires_in": 7200,
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        new_token = refresh_claude_oauth_token("sk-ant-ort01-old-refresh")
        assert new_token == "sk-ant-oat01-renewed-token"

        cached = get_cached_token("claude_sso")
        assert cached == "sk-ant-oat01-renewed-token"
