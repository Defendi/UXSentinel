import argparse
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uxsentinel.browser.session import BrowserSession, open_browser_session
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import BrowserSettings, GlobalConfig, resolve_display_mode
from uxsentinel.core.models import Scenario, StepAction
from uxsentinel.scenarios.parser import load_scenario


def test_resolve_display_mode_hierarchy():
    """Valida a hierarquia estrita de resolução do modo de visualização:
    1. CLI flag (precedência máxima: se fornecida, sobrepõe tudo)
    2. Cenário YAML (campo 'headless' no arquivo de cenário)
    3. Config global config.yaml (BrowserSettings.headless)
    4. Fallback padrão: False (modo visível com ritmo humano)
    """
    # 1. CLI sobrepõe tudo (YAML e Config)
    assert resolve_display_mode(cli_headless=True, scenario_headless=False, config_headless=False) is True
    assert resolve_display_mode(cli_headless=False, scenario_headless=True, config_headless=True) is False

    # 2. Cenário YAML sobrepõe Config quando CLI é None
    assert resolve_display_mode(cli_headless=None, scenario_headless=True, config_headless=False) is True
    assert resolve_display_mode(cli_headless=None, scenario_headless=False, config_headless=True) is False

    # 3. Config sobrepõe padrão quando CLI e Cenário são None
    assert resolve_display_mode(cli_headless=None, scenario_headless=None, config_headless=True) is True
    assert resolve_display_mode(cli_headless=None, scenario_headless=None, config_headless=False) is False

    # 4. Fallback padrão seguro (False = Headed / Visível)
    assert resolve_display_mode(cli_headless=None, scenario_headless=None, config_headless=None) is False
    assert resolve_display_mode() is False


@pytest.mark.parametrize(
    ("flag", "expected_headless"),
    [
        ("--headless", True),
        ("--no-gui", True),
        ("--silent", True),
        ("--headed", False),
        ("--gui", False),
        ("--visible", False),
    ],
)
def test_cli_display_flags_parsing(flag: str, expected_headless: bool):
    """Testa todas as flags simétricas de CLI (--headless/--no-gui/--silent e --headed/--gui/--visible)."""
    parser = argparse.ArgumentParser()
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument(
        "--headless",
        "--no-gui",
        "--silent",
        dest="headless",
        action="store_true",
        default=None,
    )
    display_group.add_argument(
        "--headed",
        "--gui",
        "--visible",
        dest="headless",
        action="store_false",
        default=None,
    )

    args = parser.parse_args([flag])
    assert args.headless == expected_headless


def test_cli_display_flags_default_none():
    """Testa que se nenhuma flag for informada na CLI, args.headless é None (permitindo fallback para cenário/config)."""
    parser = argparse.ArgumentParser()
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument(
        "--headless",
        "--no-gui",
        "--silent",
        dest="headless",
        action="store_true",
        default=None,
    )
    display_group.add_argument(
        "--headed",
        "--gui",
        "--visible",
        dest="headless",
        action="store_false",
        default=None,
    )

    args = parser.parse_args([])
    assert args.headless is None


@pytest.mark.parametrize(
    ("flag1", "flag2"),
    [
        ("--headless", "--headed"),
        ("--no-gui", "--gui"),
        ("--silent", "--visible"),
        ("--headless", "--gui"),
        ("--no-gui", "--visible"),
    ],
)
def test_cli_display_flags_mutual_exclusion(flag1: str, flag2: str):
    """Garante que flags conflitantes de visualização levantem erro de exclusão mútua no CLI."""
    parser = argparse.ArgumentParser()
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument(
        "--headless",
        "--no-gui",
        "--silent",
        dest="headless",
        action="store_true",
        default=None,
    )
    display_group.add_argument(
        "--headed",
        "--gui",
        "--visible",
        dest="headless",
        action="store_false",
        default=None,
    )

    with pytest.raises(SystemExit):
        parser.parse_args([flag1, flag2])


def test_scenario_yaml_headless_field(tmp_path: Path):
    """Valida o parsing do campo 'headless' em cenários YAML (booleanos e strings normalizadas)."""
    # 1. headless: true
    sc_file_true = tmp_path / "sc_true.yaml"
    sc_file_true.write_text("id: sc1\ntitle: T1\nheadless: true\nsteps: []\n", encoding="utf-8")
    sc1 = load_scenario(str(sc_file_true))
    assert sc1.headless is True

    # 2. headless: false
    sc_file_false = tmp_path / "sc_false.yaml"
    sc_file_false.write_text("id: sc2\ntitle: T2\nheadless: false\nsteps: []\n", encoding="utf-8")
    sc2 = load_scenario(str(sc_file_false))
    assert sc2.headless is False

    # 3. sem headless
    sc_file_none = tmp_path / "sc_none.yaml"
    sc_file_none.write_text("id: sc3\ntitle: T3\nsteps: []\n", encoding="utf-8")
    sc3 = load_scenario(str(sc_file_none))
    assert sc3.headless is None

    # 4. strings flexíveis ('yes', 'sim', '1', 'no', '0')
    sc_str_yes = tmp_path / "sc_yes.yaml"
    sc_str_yes.write_text("id: sc4\ntitle: T4\nheadless: 'yes'\nsteps: []\n", encoding="utf-8")
    assert load_scenario(str(sc_str_yes)).headless is True

    sc_str_no = tmp_path / "sc_no.yaml"
    sc_str_no.write_text("id: sc5\ntitle: T5\nheadless: 'no'\nsteps: []\n", encoding="utf-8")
    assert load_scenario(str(sc_str_no)).headless is False


def test_browser_session_headless_override():
    """Valida que a BrowserSession aceita parâmetro headless explícito e sobrescreve settings."""
    settings = BrowserSettings(headless=False)
    session_default = BrowserSession(settings)
    assert session_default.settings.headless is False

    session_override_true = BrowserSession(settings, headless=True)
    assert session_override_true.settings.headless is True

    settings_true = BrowserSettings(headless=True)
    session_override_false = BrowserSession(settings_true, headless=False)
    assert session_override_false.settings.headless is False


@pytest.mark.asyncio
async def test_browser_session_launches_chromium_with_resolved_mode():
    """Valida que a chamada ao Playwright launch recebe o headless resolvido."""
    mock_chromium = AsyncMock()
    mock_browser = AsyncMock()
    mock_chromium.launch.return_value = mock_browser

    mock_playwright = AsyncMock()
    mock_playwright.chromium = mock_chromium

    with patch("uxsentinel.browser.session.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        settings = BrowserSettings(headless=False, slow_mo_ms=200)

        # Teste 1: headless=True via contextmanager
        async with open_browser_session(settings, headless=True):
            pass

        mock_chromium.launch.assert_called_with(headless=True, slow_mo=200)

        # Teste 2: headless=False via contextmanager
        mock_chromium.launch.reset_mock()
        async with open_browser_session(settings, headless=False):
            pass

        mock_chromium.launch.assert_called_with(headless=False, slow_mo=200)


@pytest.mark.asyncio
async def test_uxsentinel_agent_respects_display_hierarchy(tmp_path: Path):
    """Valida que o agente executa a navegação utilizando o modo display respeitando a precedência."""
    cfg = GlobalConfig()
    cfg.browser.headless = False  # config diz False

    agent = UXSentinelAgent(cfg)

    # Mock do inspector e client para evitar conexões externas reais
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "Conexão IA OK"))

    # Cenário com headless: True
    scenario_headless = Scenario(
        id="test_sc_headless",
        title="Cenário Headless",
        headless=True,
        steps=[StepAction(action="goto", url="https://example.com")],
    )

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_driver = AsyncMock()
        mock_driver.healing_events = []
        mock_open_session.return_value.__aenter__.return_value = mock_driver

        # 1. Cenário headless: True deve sobrepor config headless: False
        report = await agent.run_scenario(scenario_headless)
        assert report.success is True

        # Verifica se o open_browser_session recebeu settings com headless=True
        call_args = mock_open_session.call_args[0]
        passed_settings: BrowserSettings = call_args[0]
        assert passed_settings.headless is True

        # 2. CLI override (headless_override=False / --headed) deve sobrepor Cenário (headless: True)
        mock_open_session.reset_mock()
        report_headed = await agent.run_scenario(scenario_headless, headless_override=False)
        assert report_headed.success is True

        call_args_headed = mock_open_session.call_args[0]
        passed_settings_headed: BrowserSettings = call_args_headed[0]
        assert passed_settings_headed.headless is False
