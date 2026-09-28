from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uxsentinel.cli import EXIT_ERRO_EXECUCAO, EXIT_SUCESSO, async_main, handle_list_ollama_models
from uxsentinel.core.config import GlobalConfig, ProviderSettings


@pytest.fixture
def mock_config():
    cfg = GlobalConfig()
    cfg.active_provider = "ollama_local"
    cfg.providers["ollama_local"] = ProviderSettings(
        type="local",
        service="ollama",
        base_url="http://localhost:11434",
        model="qwen2.5-vl:7b",
    )
    return cfg


@pytest.mark.asyncio
async def test_handle_list_ollama_models_success(mock_config, capsys):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5-vl:7b", "size": 4000000000, "modified_at": "2024-10-15T12:00:00Z"},
            {"name": "llama3:8b", "size": 4000000000, "modified_at": "2024-10-15T12:00:00Z"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    mock_client_instance = AsyncMock()
    mock_client_instance.get.return_value = mock_resp

    mock_client = MagicMock()
    mock_client.__aenter__.return_value = mock_client_instance

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("uxsentinel.cli.console.print") as mock_print,
    ):
        exit_code = await handle_list_ollama_models(mock_config)

    assert exit_code == EXIT_SUCESSO

    # Capture calls to console.print to check the table
    # the table itself is printed via console.print(table)
    table_printed = False
    for call in mock_print.call_args_list:
        args, kwargs = call
        if (
            len(args) > 0
            and hasattr(args[0], "title")
            and args[0].title == "Modelos Instalados no Ollama Local"
        ):
            table_printed = True

    assert table_printed


@pytest.mark.asyncio
async def test_handle_list_ollama_models_connection_error(mock_config):
    mock_client = MagicMock()
    mock_client.__aenter__.side_effect = Exception("Connection refused")

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("uxsentinel.cli.console.print") as mock_print,
    ):
        exit_code = await handle_list_ollama_models(mock_config)

    assert exit_code == EXIT_ERRO_EXECUCAO

    # check that we printed the error message and tip
    printed_texts = [call[0][0] for call in mock_print.call_args_list if isinstance(call[0][0], str)]
    assert any("Ollama inatingível ou erro na consulta" in t for t in printed_texts)
    assert any("sudo systemctl start ollama" in t for t in printed_texts)


@pytest.mark.asyncio
async def test_cli_list_ollama_models_flag():
    # test --list-ollama-models flag via async_main
    with (
        patch("sys.argv", ["uxsentinel", "--list-ollama-models", "--config", "none"]),
        patch("uxsentinel.cli.handle_list_ollama_models", new_callable=AsyncMock) as mock_handle,
        patch("uxsentinel.cli.load_config", return_value=GlobalConfig()),
    ):
        mock_handle.return_value = EXIT_SUCESSO
        exit_code = await async_main()
        assert exit_code == EXIT_SUCESSO
        mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_cli_list_ollama_models_positional():
    # test list-ollama-models positional via async_main
    with (
        patch("sys.argv", ["uxsentinel", "list-ollama-models", "--config", "none"]),
        patch("uxsentinel.cli.handle_list_ollama_models", new_callable=AsyncMock) as mock_handle,
        patch("uxsentinel.cli.load_config", return_value=GlobalConfig()),
    ):
        mock_handle.return_value = EXIT_SUCESSO
        exit_code = await async_main()
        assert exit_code == EXIT_SUCESSO
        mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_cli_model_override():
    # test -m / --model flag
    mock_cfg = GlobalConfig()
    mock_cfg.active_provider = "ollama_local"
    # Ensure it's not populated initially to test the population
    if "ollama_local" in mock_cfg.providers:
        del mock_cfg.providers["ollama_local"]

    with (
        patch("sys.argv", ["uxsentinel", "--check-ai", "-m", "custom-model:test", "--config", "none"]),
        patch("uxsentinel.cli.handle_check_ai", new_callable=AsyncMock) as mock_check,
        patch("uxsentinel.cli.load_config", return_value=mock_cfg),
    ):
        mock_check.return_value = EXIT_SUCESSO
        exit_code = await async_main()
        assert exit_code == EXIT_SUCESSO

        assert mock_cfg.providers["ollama_local"].model == "custom-model:test"
