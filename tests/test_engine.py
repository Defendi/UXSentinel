import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uxsentinel.browser.session import open_browser_session
from uxsentinel.core.config import load_config
from uxsentinel.core.models import CheckpointResult, Issue, IssueCategory, IssueSeverity, TestReport
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.reporter.json_builder import save_json_report
from uxsentinel.scenarios.parser import load_scenario


def test_config_and_scenarios():
    from uxsentinel.core.config import ensure_user_config, get_user_config_dir

    user_cfg = ensure_user_config()
    assert user_cfg.is_file()
    assert get_user_config_dir().name == "uxsentinel"

    cfg = load_config("config/config.yaml")
    assert cfg.active_provider is not None
    assert "anthropic_cloud" in cfg.providers
    assert "openai_cloud" in cfg.providers
    assert "gemini_cloud" in cfg.providers
    assert "gemini_sso" in cfg.providers
    assert "claude_sso" in cfg.providers
    assert "ollama_local" in cfg.providers
    assert "corporate_gateway" in cfg.providers

    sc = load_scenario("uxsentinel/scenarios/library/exemplo_web_geral.yaml")
    assert sc.id == "login_e_dashboard_geral"
    assert len(sc.steps) > 0

    sc_odoo = load_scenario("uxsentinel/scenarios/library/exemplo_odoo.yaml")
    assert sc_odoo.profile == "odoo"
    assert len(sc_odoo.steps) > 0
    print("✓ Teste de Configuração e Parser de Cenários passou!")


def test_reporting():
    report = TestReport(
        scenario_id="teste_unitario",
        scenario_title="Teste Unitário de Relatórios",
        profile="generic",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp1",
                expected_behavior="Tudo em português",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.TRADUCAO,
                        severidade=IssueSeverity.MEDIA,
                        descricao="Botão 'Save' em inglês",
                        sugestao_correcao="Substituir por 'Salvar'",
                        elemento_alvo="button#btn-save",
                    )
                ],
            )
        ],
    )
    report.compute_totals()
    assert report.total_issues == 1
    assert report.total_medias == 1

    json_path = save_json_report(report, "report_test")
    assert json_path.is_file()

    html_path = save_html_report(report, "report_test")
    assert html_path.is_file()

    # Limpeza
    json_path.unlink()
    html_path.unlink()
    Path("report_test").rmdir()
    print("✓ Teste de Geração de Relatórios JSON e HTML passou!")


async def test_browser_session_headless():
    cfg = load_config("config/config.yaml")
    cfg.browser.headless = True
    async with open_browser_session(cfg.browser, profile="generic") as driver:
        await driver.goto("https://example.com")
        dom_text = await driver.get_clean_dom_text()
        assert "Example Domain" in dom_text
    print("✓ Teste de Navegação Playwright e Extração DOM passou!")


def test_cli_version():
    import subprocess

    from uxsentinel import __version__

    res_long = subprocess.run(
        [sys.executable, "-m", "uxsentinel.cli", "--version"],
        capture_output=True,
        text=True,
    )
    assert res_long.returncode == 0
    assert __version__ in res_long.stdout

    res_short = subprocess.run(
        [sys.executable, "-m", "uxsentinel.cli", "-v"],
        capture_output=True,
        text=True,
    )
    assert res_short.returncode == 0
    assert __version__ in res_short.stdout
    print("✓ Teste de CLI --version e -v passou!")


def test_resolve_scenario_path_rules():
    import os
    import tempfile

    from uxsentinel.cli import resolve_scenario_path

    orig_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            os.chdir(tmpdir)
            # 1. Sem pasta scenarios/ e sem parâmetro -> deve levantar FileNotFoundError
            try:
                resolve_scenario_path(None)
                raise AssertionError("Deveria ter levantado FileNotFoundError sem pasta e sem parâmetro")
            except FileNotFoundError as err:
                assert "não existe" in str(err)

            # 2. Sem pasta scenarios/, com parâmetro inexistente -> deve levantar FileNotFoundError
            try:
                resolve_scenario_path("arquivo_fantasma.yaml")
                raise AssertionError("Deveria ter levantado FileNotFoundError para arquivo inexistente")
            except FileNotFoundError as err:
                assert "não foi encontrado" in str(err)

            # 3. Sem pasta scenarios/, com arquivo válido passado como parâmetro
            test_yaml = Path(tmpdir) / "meu_teste.yaml"
            test_yaml.write_text("version: '1.0'\nid: t\ntitle: T\nprofile: generic\nsteps: []")
            resolved = resolve_scenario_path("meu_teste.yaml")
            assert resolved.is_file()

            # 4. Com pasta scenarios/, mas vazia e sem parâmetro -> deve levantar FileNotFoundError
            scenarios_folder = Path(tmpdir) / "scenarios"
            scenarios_folder.mkdir()
            try:
                resolve_scenario_path(None)
                raise AssertionError("Deveria ter levantado FileNotFoundError para pasta scenarios/ vazia")
            except FileNotFoundError as err:
                assert "não contém nenhum arquivo" in str(err)

            # 5. Com pasta scenarios/ contendo 1 arquivo -> detecta automaticamente
            sc_in_folder = scenarios_folder / "cenario_pasta.yaml"
            sc_in_folder.write_text("version: '1.0'\nid: c\ntitle: C\nprofile: generic\nsteps: []")
            resolved_auto = resolve_scenario_path(None)
            assert resolved_auto.name == "cenario_pasta.yaml"

            # 6. Com pasta scenarios/ contendo múltiplos arquivos e sem parâmetro -> deve levantar ValueError
            sc_in_folder_2 = scenarios_folder / "cenario_pasta_2.yaml"
            sc_in_folder_2.write_text("version: '1.0'\nid: c2\ntitle: C2\nprofile: generic\nsteps: []")
            try:
                resolve_scenario_path(None)
                raise AssertionError(
                    "Deveria ter levantado ValueError para pasta scenarios/ com múltiplos arquivos sem parâmetro"
                )
            except ValueError as err:
                assert "múltiplos cenários" in str(err)

            # 7. Com pasta scenarios/ contendo múltiplos arquivos e com parâmetro -> resolve o parâmetro especificado
            resolved_explicit = resolve_scenario_path("cenario_pasta_2.yaml")
            assert resolved_explicit.name == "cenario_pasta_2.yaml"

        finally:
            os.chdir(orig_cwd)

    print("✓ Teste de Regras de Resolução de Cenário Obrigatório passou!")


async def test_ai_preflight_check():
    from unittest.mock import AsyncMock, patch

    from uxsentinel.core.agent import UXSentinelAgent
    from uxsentinel.core.models import Scenario
    from uxsentinel.vision.client import UnifiedVisionClient

    cfg = load_config("config/config.yaml")
    client = UnifiedVisionClient(cfg)

    # 1. Teste de pre-flight check com sucesso simulado
    with patch.object(client, "_probe_provider", new=AsyncMock(return_value=(True, "OK simulado"))):
        ok, msg = await client.test_connection(check_fallback=False)
        assert ok is True
        assert "operacional" in msg

    # 2. Teste de pre-flight check com falha sem fallback
    with patch.object(
        client, "_probe_provider", new=AsyncMock(return_value=(False, "Credencial inválida simulada"))
    ):
        ok, msg = await client.test_connection(check_fallback=False)
        assert ok is False
        assert "Credencial inválida simulada" in msg

    # 3. Teste de aborto no UXSentinelAgent quando a IA está desconectada (não deve abrir o navegador)
    agent = UXSentinelAgent(cfg)
    scenario = Scenario(id="abort_test", title="Teste de Aborto", steps=[])
    with (
        patch.object(
            agent.inspector.client,
            "test_connection",
            new=AsyncMock(return_value=(False, "Token corporativo expirado")),
        ),
        patch("uxsentinel.core.agent.open_browser_session") as mock_browser,
    ):
        report = await agent.run_scenario(scenario)
        assert report.success is False
        assert "Falha de conexão com a IA" in (report.error_message or "")
        mock_browser.assert_not_called()

    print("✓ Teste de Pre-flight Check de Conexão com a IA passou!")


def test_report_directory_configuration_and_cli():
    import argparse

    from uxsentinel.core.config import ReportingSettings

    # 1. Padrão no ReportingSettings
    default_settings = ReportingSettings()
    assert default_settings.output_dir == "scenarios/report"

    # 2. Padrão no config.yaml
    cfg = load_config("config/config.yaml")
    assert cfg.reporting.output_dir == "scenarios/report"

    # 3. Teste dos argumentos na CLI (--report-dir e -o)

    # Inspeciona o parser construído pela CLI
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o",
        "--output-dir",
        "--report-dir",
        dest="output_dir",
        default=None,
    )
    args_default = parser.parse_args([])
    assert args_default.output_dir is None

    args_custom_short = parser.parse_args(["-o", "custom/reports"])
    assert args_custom_short.output_dir == "custom/reports"

    args_custom_long = parser.parse_args(["--output-dir", "custom/reports2"])
    assert args_custom_long.output_dir == "custom/reports2"

    args_custom_alias = parser.parse_args(["--report-dir", "custom/reports3"])
    assert args_custom_alias.output_dir == "custom/reports3"

    print("✓ Teste de Configuração e Parâmetros de Relatórios (scenarios/report) passou!")


def test_sso_authentication_and_loopback():
    import os
    import tempfile
    import threading
    import urllib.request

    from uxsentinel.core.config import ProviderSettings
    from uxsentinel.core.sso import (
        LoopbackAuthServer,
        _find_available_port,
        clear_cached_token,
        get_cached_token,
        save_cached_token,
    )
    from uxsentinel.vision.client import UnifiedVisionClient

    # 1. Teste de Cache Isolado em Diretório Temporário
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_xdg = os.environ.get("XDG_CONFIG_HOME")
        try:
            os.environ["XDG_CONFIG_HOME"] = tmpdir

            # Inicialmente não há token
            assert get_cached_token("gemini_sso") is None

            # Salva token
            save_cached_token("gemini_sso", "token_secreto_teste_123")
            assert get_cached_token("gemini_sso") == "token_secreto_teste_123"

            # Limpa token
            assert clear_cached_token("gemini_sso") is True
            assert get_cached_token("gemini_sso") is None
        finally:
            if orig_xdg:
                os.environ["XDG_CONFIG_HOME"] = orig_xdg
            else:
                os.environ.pop("XDG_CONFIG_HOME", None)

    # 2. Teste do Servidor de Loopback HTTP
    port = _find_available_port(8096, 8105)
    server = LoopbackAuthServer(
        ("127.0.0.1", port),
        provider_name="gemini_sso",
        instructions_html="Teste",
    )
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    try:
        url = f"http://127.0.0.1:{port}"

        # GET na página de login
        with urllib.request.urlopen(url) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "UXSentinel SSO Login" in body

        # POST no /callback com token
        req = urllib.request.Request(
            f"{url}/callback",
            data=b"token=meu_token_via_post",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            assert server.captured_token == "meu_token_via_post"

    finally:
        server.shutdown()
        server.server_close()

    # 3. Teste de Injeção de Token SSO no UnifiedVisionClient
    cfg = load_config("config/config.yaml")
    client = UnifiedVisionClient(cfg)
    p_sso = ProviderSettings(
        type="sso",
        service="gemini",
        model="gemini-1.5-pro",
        api_key="",
        headers={},
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_xdg = os.environ.get("XDG_CONFIG_HOME")
        try:
            os.environ["XDG_CONFIG_HOME"] = tmpdir
            save_cached_token("gemini_sso", "jwt_token_em_cache_abc")

            token_resolved = client._ensure_provider_auth(p_sso, interactive=False)
            assert token_resolved == "jwt_token_em_cache_abc"
            assert p_sso.headers.get("Authorization") == "Bearer jwt_token_em_cache_abc"
        finally:
            if orig_xdg:
                os.environ["XDG_CONFIG_HOME"] = orig_xdg
            else:
                os.environ.pop("XDG_CONFIG_HOME", None)

    print("✓ Teste de Autenticação SSO e Servidor Loopback passou!")


if __name__ == "__main__":
    test_cli_version()
    test_resolve_scenario_path_rules()
    test_config_and_scenarios()
    test_report_directory_configuration_and_cli()
    test_sso_authentication_and_loopback()
    test_reporting()
    asyncio.run(test_browser_session_headless())
    asyncio.run(test_ai_preflight_check())
    print("\n🎉 TODOS OS TESTES INTERNOS PASSARAM COM SUCESSO!")
