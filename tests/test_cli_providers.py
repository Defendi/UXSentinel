from unittest.mock import patch

import pytest

from uxsentinel.cli import EXIT_SUCESSO, async_main


@pytest.mark.asyncio
async def test_cli_list_providers_flag(capsys):
    """Valida execução com --list-providers retornando código 0 e exibindo provedores."""
    with patch("sys.argv", ["uxsentinel", "--list-providers"]):
        result = await async_main()
        assert result == EXIT_SUCESSO

        captured = capsys.readouterr()
        assert "Provedores de LLM/IA Compatíveis no UXSentinel" in captured.out
        assert "gemini_cloud" in captured.out
        assert "openai_cloud" in captured.out
        assert "● Ativo" in captured.out


@pytest.mark.asyncio
async def test_cli_list_providers_positional(capsys):
    """Valida execução posicional com list-providers retornando código 0."""
    with patch("sys.argv", ["uxsentinel", "list-providers"]):
        result = await async_main()
        assert result == EXIT_SUCESSO

        captured = capsys.readouterr()
        assert "Provedores de LLM/IA Compatíveis no UXSentinel" in captured.out


@pytest.mark.asyncio
async def test_cli_list_providers_active_provider_marked(capsys):
    """Valida que o provedor ativo é sinalizado corretamente."""
    with (
        patch("sys.argv", ["uxsentinel", "--list-providers"]),
        patch("uxsentinel.cli.load_config") as mock_load_config,
    ):
        from uxsentinel.core.config import GlobalConfig

        mock_cfg = GlobalConfig()
        mock_cfg.active_provider = "ollama_local"
        mock_load_config.return_value = mock_cfg

        result = await async_main()
        assert result == EXIT_SUCESSO

        captured = capsys.readouterr()
        assert "ollama_local" in captured.out
        assert "● Ativo" in captured.out
