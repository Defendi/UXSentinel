"""Testes herméticos para o assistente interativo de configuração da CLI (UXS-28).

Cobre:
- Funções de persistência: save_active_provider, save_default_viewports, save_jira_config.
- Permissões estritas de arquivo (0o600).
- Subcomando 'uxsentinel config' e flag '--configure'.
- Menus e fluxos interativos (IA, Viewport, Jira, Assistente completo, Teste de conexões).
- Mascaramento estrito de segredos e tokens sensíveis.
- 100% hermético sem chamadas de rede reais.
"""

import stat
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from uxsentinel.cli import (
    EXIT_SUCESSO,
    async_main,
    handle_interactive_config,
)
from uxsentinel.core.config import (
    ViewportConfig,
    load_config,
    save_active_provider,
    save_default_viewports,
    save_jira_config,
)


@pytest.fixture
def temp_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configura ambiente isolado com XDG_CONFIG_HOME temporário."""
    cfg_dir = tmp_path / "config" / "uxsentinel"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "config.yaml"
    cfg_file.write_text(
        """active_provider: "gemini_cloud"
browser:
  headless: false
  viewport:
    width: 1280
    height: 720
jira:
  enabled: false
  url: "https://empresa-mock.atlassian.net"
  email: "qa@empresa.com"
  api_token: "TOKEN_PREEXISTENTE_123"
  project_key: "UXS"
providers:
  gemini_cloud:
    type: "api"
    service: "gemini"
    model: "gemini-1.5-pro"
    api_key: "AIzaSy_CHAVE_PREEXISTENTE_999"
  anthropic_cloud:
    type: "api"
    service: "anthropic"
    model: "claude-3-5-sonnet"
    api_key: "sk-ant-CHAVE_PREEXISTENTE_888"
""",
        encoding="utf-8",
    )
    cfg_file.chmod(0o600)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return cfg_file


# ---------------------------------------------------------------------------
# 1. Testes de Persistência e Permissões (save_*)
# ---------------------------------------------------------------------------


def test_save_active_provider_persists_and_sets_0600(temp_config_file: Path):
    """Garante que save_active_provider persiste credenciais e aplica chmod 0600."""
    saved_path = save_active_provider(
        provider_name="anthropic_cloud",
        api_key="sk-ant-NOVA_CHAVE_123",
        config_path=temp_config_file,
    )

    assert saved_path == temp_config_file
    mode = stat.S_IMODE(saved_path.stat().st_mode)
    assert mode == 0o600

    data = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
    assert data["active_provider"] == "anthropic_cloud"
    assert data["providers"]["anthropic_cloud"]["api_key"] == "sk-ant-NOVA_CHAVE_123"


def test_save_active_provider_ollama_and_gateway(temp_config_file: Path):
    """Garante que save_active_provider grava base_url e model para Ollama e Gateway."""
    # Ollama Local
    save_active_provider(
        provider_name="ollama_local",
        base_url="http://127.0.0.1:11434",
        model="qwen2-vl:latest",
        config_path=temp_config_file,
    )
    data = yaml.safe_load(temp_config_file.read_text(encoding="utf-8"))
    assert data["active_provider"] == "ollama_local"
    assert data["providers"]["ollama_local"]["base_url"] == "http://127.0.0.1:11434"
    assert data["providers"]["ollama_local"]["model"] == "qwen2-vl:latest"

    # Gateway Corporativo
    save_active_provider(
        provider_name="corporate_gateway",
        base_url="https://gateway.empresa.internal/v1",
        model="corp-vision",
        api_key="corp-token-xyz",
        config_path=temp_config_file,
    )
    data = yaml.safe_load(temp_config_file.read_text(encoding="utf-8"))
    assert data["active_provider"] == "corporate_gateway"
    assert data["providers"]["corporate_gateway"]["base_url"] == "https://gateway.empresa.internal/v1"
    assert data["providers"]["corporate_gateway"]["api_key"] == "corp-token-xyz"


def test_save_default_viewports_presets_and_custom(temp_config_file: Path):
    """Garante que save_default_viewports salva resoluções e aplica chmod 0600."""
    # Resolução customizada
    saved_path = save_default_viewports(
        width=1600,
        height=900,
        clear_viewports=True,
        config_path=temp_config_file,
    )
    assert saved_path == temp_config_file
    mode = stat.S_IMODE(saved_path.stat().st_mode)
    assert mode == 0o600

    data = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
    assert data["browser"]["viewport"]["width"] == 1600
    assert data["browser"]["viewport"]["height"] == 900
    assert "viewports" not in data["browser"]

    # Multi-viewports como lista de strings
    save_default_viewports(
        viewports=["desktop", "tablet", "mobile"],
        config_path=temp_config_file,
    )
    data = yaml.safe_load(temp_config_file.read_text(encoding="utf-8"))
    assert data["browser"]["viewports"] == ["desktop", "tablet", "mobile"]

    # Multi-viewports com modelos ViewportConfig
    vp_models = [
        ViewportConfig(name="wide", width=2560, height=1440, is_mobile=False),
        ViewportConfig(name="phone", width=390, height=844, is_mobile=True),
    ]
    save_default_viewports(viewports=vp_models, config_path=temp_config_file)
    data = yaml.safe_load(temp_config_file.read_text(encoding="utf-8"))
    assert len(data["browser"]["viewports"]) == 2
    assert data["browser"]["viewports"][0]["name"] == "wide"
    assert data["browser"]["viewports"][0]["width"] == 2560


def test_save_jira_config_persists_and_sets_0600(temp_config_file: Path):
    """Garante que save_jira_config salva configurações e aplica chmod 0600."""
    saved_path = save_jira_config(
        url="https://jira.corp.internal",
        email="dev@corp.internal",
        api_token="TOKEN_SECRETO_987",
        project_key="UXS",
        enabled=True,
        config_path=temp_config_file,
    )

    assert saved_path == temp_config_file
    mode = stat.S_IMODE(saved_path.stat().st_mode)
    assert mode == 0o600

    data = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
    assert data["jira"]["url"] == "https://jira.corp.internal"
    assert data["jira"]["email"] == "dev@corp.internal"
    assert data["jira"]["api_token"] == "TOKEN_SECRETO_987"
    assert data["jira"]["project_key"] == "UXS"
    assert data["jira"]["enabled"] is True


# ---------------------------------------------------------------------------
# 2. Testes de Menus e Fluxos do Assistente Interativo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_interactive_config_exit(temp_config_file: Path):
    """Garante que a opção 6 (ou 'sair'/'q') sai do assistente sem erros."""
    cfg = load_config(str(temp_config_file))

    with patch("rich.prompt.Prompt.ask", side_effect=["6"]):
        res = await handle_interactive_config(cfg)
        assert res == 0

    with patch("rich.prompt.Prompt.ask", side_effect=["sair"]):
        res = await handle_interactive_config(cfg)
        assert res == 0

    with patch("rich.prompt.Prompt.ask", side_effect=[EOFError]):
        res = await handle_interactive_config(cfg)
        assert res == 0


@pytest.mark.asyncio
async def test_interactive_config_ai_provider_flow_cloud(temp_config_file: Path):
    """Testa configuração de provedor de IA na nuvem com API Key e teste de conexão imediato."""
    cfg = load_config(str(temp_config_file))

    # Fluxo: Escolher Opção 1 (IA) -> Provedor 4 (anthropic_cloud) -> Manter chave (Enter vazio) -> Testar conexão (Sim) -> Sair (6)
    prompts_answers = [
        "1",  # Menu principal: IA
        "4",  # Provedor: anthropic_cloud
        "",  # Nova API Key: Enter (manter chave atual)
        "6",  # Menu principal: Sair
    ]

    with (
        patch("rich.prompt.Prompt.ask", side_effect=prompts_answers),
        patch("rich.prompt.Confirm.ask", side_effect=[True]),  # Testar conexão agora? Sim
        patch(
            "uxsentinel.vision.client.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
        ) as mock_test_conn,
    ):
        mock_test_conn.return_value = (True, "Anthropic Claude operacional.")

        res = await handle_interactive_config(cfg)
        assert res == 0
        assert cfg.active_provider == "anthropic_cloud"
        mock_test_conn.assert_awaited_once_with(check_fallback=False)


@pytest.mark.asyncio
async def test_interactive_config_ai_provider_flow_ollama(temp_config_file: Path):
    """Testa configuração do Ollama local com URL e modelo personalizados."""
    cfg = load_config(str(temp_config_file))

    # Fluxo: Menu IA -> 6 (ollama_local) -> URL -> Model -> Não testar -> Sair
    prompts_answers = [
        "1",  # Menu principal: IA
        "6",  # Provedor: ollama_local
        "http://localhost:11434",  # URL do Ollama
        "qwen2-vl:7b",  # Modelo de visão
        "6",  # Menu principal: Sair
    ]

    with (
        patch("rich.prompt.Prompt.ask", side_effect=prompts_answers),
        patch("rich.prompt.Confirm.ask", side_effect=[False]),  # Não testar agora
    ):
        res = await handle_interactive_config(cfg)
        assert res == 0
        assert cfg.active_provider == "ollama_local"
        assert cfg.providers["ollama_local"].base_url == "http://localhost:11434"
        assert cfg.providers["ollama_local"].model == "qwen2-vl:7b"


@pytest.mark.asyncio
async def test_interactive_config_viewport_presets(temp_config_file: Path):
    """Testa seleção de presets canônicos e customizados de Viewport."""
    cfg = load_config(str(temp_config_file))

    # 1. Preset FullHD (opção 2)
    with patch("rich.prompt.Prompt.ask", side_effect=["2", "2", "6"]):
        # Menu 2 (Viewport) -> Preset 2 (FullHD 1920x1080) -> Menu 6 (Sair)
        res = await handle_interactive_config(cfg)
        assert res == 0
        assert cfg.browser.viewport_width == 1920
        assert cfg.browser.viewport_height == 1080
        assert cfg.browser.viewports is None

    # 2. Resolução Customizada (opção 5: 1600x900)
    with patch("rich.prompt.Prompt.ask", side_effect=["2", "5", "1600", "900", "6"]):
        # Menu 2 -> Preset 5 -> 1600 -> 900 -> Sair
        res = await handle_interactive_config(cfg)
        assert res == 0
        assert cfg.browser.viewport_width == 1600
        assert cfg.browser.viewport_height == 900

    # 3. Multi-viewport responsivo (opção 6)
    with patch("rich.prompt.Prompt.ask", side_effect=["2", "6", "6"]):
        res = await handle_interactive_config(cfg)
        assert res == 0
        assert cfg.browser.viewports == ["desktop", "tablet", "mobile"]


@pytest.mark.asyncio
async def test_interactive_config_jira_flow(temp_config_file: Path):
    """Testa configuração completa da integração Atlassian Jira com teste de conectividade."""
    cfg = load_config(str(temp_config_file))

    # Menu 3 (Jira) -> Ativar: Sim -> URL -> Email -> Manter Token (Enter) -> Proj -> Testar: Sim -> Sair
    prompts_answers = [
        "3",  # Menu principal: Jira
        "https://novojira.atlassian.net",  # URL Jira
        "qa-novo@empresa.com",  # E-mail
        "",  # Manter token pré-existente
        "UXS",  # Chave do projeto
        "6",  # Menu principal: Sair
    ]
    confirm_answers = [
        True,  # Habilitar integração com Jira? Sim
        True,  # Testar conectividade com o Jira agora? Sim
    ]

    with (
        patch("rich.prompt.Prompt.ask", side_effect=prompts_answers),
        patch("rich.prompt.Confirm.ask", side_effect=confirm_answers),
        patch(
            "uxsentinel.integrations.jira.JiraClient.test_connection",
            new_callable=AsyncMock,
        ) as mock_jira_conn,
    ):
        mock_jira_conn.return_value = (True, "Conexão com projeto UXS validada.")

        res = await handle_interactive_config(cfg)
        assert res == 0
        assert cfg.jira.enabled is True
        assert cfg.jira.url == "https://novojira.atlassian.net"
        assert cfg.jira.email == "qa-novo@empresa.com"
        assert cfg.jira.api_token == "TOKEN_PREEXISTENTE_123"  # Preservado
        mock_jira_conn.assert_awaited_once()


@pytest.mark.asyncio
async def test_interactive_config_run_full_wizard(temp_config_file: Path):
    """Testa opção 4: Assistente completo passo a passo."""
    cfg = load_config(str(temp_config_file))

    prompts_answers = [
        "4",  # Menu: Assistente Completo
        # Passo 1: IA (gemini_cloud)
        "1",  # Provedor 1 (gemini_cloud)
        "",  # Manter chave atual
        # Passo 2: Viewport
        "1",  # Desktop 1440x900
        # Passo 3: Jira
        "https://meujira.atlassian.net",
        "qa@empresa.com",
        "",  # Manter token
        "UXS",
        # Retorno ao menu principal -> Sair
        "6",
    ]
    confirms = [
        False,  # Não testar IA agora
        True,  # Habilitar Jira?
        False,  # Não testar Jira agora
    ]

    with (
        patch("rich.prompt.Prompt.ask", side_effect=prompts_answers),
        patch("rich.prompt.Confirm.ask", side_effect=confirms),
    ):
        res = await handle_interactive_config(cfg)
        assert res == 0
        assert cfg.active_provider == "gemini_cloud"
        assert cfg.browser.viewport_width == 1440
        assert cfg.browser.viewport_height == 900
        assert cfg.jira.enabled is True


@pytest.mark.asyncio
async def test_interactive_config_test_current_connections(temp_config_file: Path):
    """Testa opção 5: Testar conexões atuais (IA e Jira)."""
    cfg = load_config(str(temp_config_file))
    cfg.jira.enabled = True
    cfg.jira.url = "https://mock.atlassian.net"
    cfg.jira.api_token = "mock-token"

    prompts_answers = [
        "5",  # Menu: Testar Conexões Atuais
        "6",  # Menu: Sair
    ]

    with (
        patch("rich.prompt.Prompt.ask", side_effect=prompts_answers),
        patch(
            "uxsentinel.vision.client.UnifiedVisionClient.test_connection",
            new_callable=AsyncMock,
        ) as mock_ai_conn,
        patch(
            "uxsentinel.integrations.jira.JiraClient.test_connection",
            new_callable=AsyncMock,
        ) as mock_jira_conn,
    ):
        mock_ai_conn.return_value = (True, "Gemini OK")
        mock_jira_conn.return_value = (True, "Jira OK")

        res = await handle_interactive_config(cfg)
        assert res == 0
        mock_ai_conn.assert_awaited_once_with(check_fallback=False)
        mock_jira_conn.assert_awaited_once()


# ---------------------------------------------------------------------------
# 3. Testes de Invocação via CLI (uxsentinel config / --configure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_invocation_config_subcommand(temp_config_file: Path):
    """Valida acionamento via comando posicional 'uxsentinel config'."""
    with (
        patch("sys.argv", ["uxsentinel", "config", "--config", str(temp_config_file)]),
        patch("rich.prompt.Prompt.ask", side_effect=["6"]),
    ):
        code = await async_main()
        assert code == EXIT_SUCESSO


@pytest.mark.asyncio
async def test_cli_invocation_configure_flag(temp_config_file: Path):
    """Valida acionamento via flag 'uxsentinel --configure'."""
    with (
        patch("sys.argv", ["uxsentinel", "--configure", "--config", str(temp_config_file)]),
        patch("rich.prompt.Prompt.ask", side_effect=["6"]),
    ):
        code = await async_main()
        assert code == EXIT_SUCESSO


@pytest.mark.asyncio
async def test_cli_invocation_configure_positional(temp_config_file: Path):
    """Valida acionamento via comando posicional 'uxsentinel configure'."""
    with (
        patch("sys.argv", ["uxsentinel", "configure", "--config", str(temp_config_file)]),
        patch("rich.prompt.Prompt.ask", side_effect=["6"]),
    ):
        code = await async_main()
        assert code == EXIT_SUCESSO
