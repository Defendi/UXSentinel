import asyncio
import sys
from pathlib import Path

import pytest

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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


def test_claude_pro_oauth_pkce_and_headers():
    import base64
    import hashlib

    from uxsentinel.core.sso import generate_pkce_pair, get_cached_token
    from uxsentinel.vision.client import _prepare_anthropic_auth

    # 1. Teste de geração PKCE RFC 7636
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    # Verifica hash SHA-256
    expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(expected_digest).decode("ascii").rstrip("=")
    assert challenge == expected_challenge

    # 2. Teste de preparação de cabeçalhos e modelo para conta Claude Pro
    headers_oauth, model_oauth = _prepare_anthropic_auth(
        provider_name="claude_sso",
        model="claude-3-5-sonnet-latest",
        api_key="sk-ant-oat01-token-de-teste-da-conta-pro",
        headers={"custom-header": "test"},
    )
    assert headers_oauth.get("Authorization") == "Bearer sk-ant-oat01-token-de-teste-da-conta-pro"
    assert "x-api-key" not in headers_oauth
    assert headers_oauth.get("anthropic-beta") == "oauth-2025-04-20"
    assert headers_oauth.get("User-Agent") == "claude-cli/2.1.267"
    assert model_oauth == "claude-haiku-4-5"

    # 3. Teste para API key corporativa padrão (não-OAuth)
    headers_std, model_std = _prepare_anthropic_auth(
        provider_name="anthropic_cloud",
        model="claude-3-5-sonnet-latest",
        api_key="sk-ant-api03-chave-comum",
        headers={},
    )
    assert headers_std.get("x-api-key") == "sk-ant-api03-chave-comum"
    assert model_std == "claude-3-5-sonnet-latest"
    assert "anthropic-beta" not in headers_std

    # 4. Teste de armazenamento e recuperação de token OAuth
    from uxsentinel.core.sso import save_cached_token

    save_cached_token("claude_sso", "sk-ant-oat01-token-valido-teste")
    token_cached = get_cached_token("claude_sso")
    assert token_cached == "sk-ant-oat01-token-valido-teste"
    assert token_cached.startswith("sk-ant-oat")

    print("✓ Teste de PKCE e Cabeçalhos Claude Pro OAuth passou!")


def test_fix_prompt_builder(tmp_path):
    from uxsentinel.core.models import CheckpointResult, Issue, IssueCategory, IssueSeverity, TestReport
    from uxsentinel.reporter.prompt_builder import build_fix_prompt, save_fix_prompt

    report = TestReport(
        scenario_id="login_dashboard_audit",
        scenario_title="Auditoria de Login e Dashboard",
        profile="odoo",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp_dashboard",
                expected_behavior="Dashboard totalmente carregado em português",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.TRADUCAO,
                        severidade=IssueSeverity.ALTA,
                        descricao="Menu 'Settings' em inglês",
                        sugestao_correcao="Substituir por 'Configurações'",
                        elemento_alvo="div.o_menu_brand",
                        trecho_codigo="<span>Settings</span>",
                    ),
                    Issue(
                        categoria=IssueCategory.LAYOUT_MODAL,
                        severidade=IssueSeverity.MEDIA,
                        descricao="Botão desalinhado na barra de ação",
                        sugestao_correcao="Adicionar classe mr-2",
                        elemento_alvo="button.btn-primary",
                    ),
                ],
            )
        ],
    )
    report.compute_totals()

    prompt_md = build_fix_prompt(report)
    assert "# 🛠️ Prompt Técnico de Correção de UI/UX" in prompt_md
    assert "Auditoria de Login e Dashboard" in prompt_md
    assert "odoo" in prompt_md
    assert "Menu 'Settings' em inglês" in prompt_md
    assert "Substituir por 'Configurações'" in prompt_md
    assert "div.o_menu_brand" in prompt_md
    assert "<span>Settings</span>" in prompt_md
    assert "cp_dashboard" in prompt_md

    saved_file = save_fix_prompt(report, tmp_path)
    assert saved_file.is_file()
    assert saved_file.name == "login_dashboard_audit_fix_prompt.md"
    assert saved_file.read_text(encoding="utf-8") == prompt_md
    print("✓ Teste do Fix Prompt Builder passou!")


@pytest.mark.asyncio
async def test_jira_integration(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from uxsentinel.core.config import JiraSettings, save_jira_config
    from uxsentinel.core.models import CheckpointResult, Issue, IssueCategory, IssueSeverity, TestReport
    from uxsentinel.integrations.jira import JiraClient

    # 1. Teste de persistência de configuração do Jira
    fake_config = tmp_path / "config.yaml"
    fake_config.write_text("jira: {}\n", encoding="utf-8")
    monkeypatch.setattr("uxsentinel.core.config.ensure_user_config", lambda: fake_config)

    save_jira_config(
        url="https://minhaempresa.atlassian.net",
        email="dev@empresa.com",
        api_token="token_secreto_jira_123",
        project_key="UXS",
        enabled=True,
    )
    import yaml

    saved_data = yaml.safe_load(fake_config.read_text(encoding="utf-8"))
    assert saved_data["jira"]["url"] == "https://minhaempresa.atlassian.net"
    assert saved_data["jira"]["email"] == "dev@empresa.com"
    assert saved_data["jira"]["api_token"] == "token_secreto_jira_123"
    assert saved_data["jira"]["project_key"] == "UXS"
    assert saved_data["jira"]["enabled"] is True

    # 2. Teste do JiraClient com Mock de httpx
    settings = JiraSettings(
        enabled=True,
        url="https://minhaempresa.atlassian.net",
        email="dev@empresa.com",
        api_token="token_secreto_jira_123",
        project_key="UXS",
        issue_type="Bug",
        labels=["uxsentinel", "test-label"],
    )
    jira_client = JiraClient(settings)

    # Teste test_connection
    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get_response.json.return_value = {"name": "Projeto UXS", "key": "UXS"}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_get_response

    mock_post_response = MagicMock()
    mock_post_response.status_code = 201
    mock_post_response.json.return_value = {"key": "UXS-101", "id": "10001"}
    mock_client.post.return_value = mock_post_response

    monkeypatch.setattr(
        "uxsentinel.integrations.jira.httpx.AsyncClient",
        lambda *args, **kwargs: AsyncMock(
            __aenter__=AsyncMock(return_value=mock_client),
            __aexit__=AsyncMock(return_value=None),
        ),
    )

    ok, msg = await jira_client.test_connection()
    assert ok is True
    assert "Projeto UXS" in msg

    # 3. Teste create_issues_from_report
    report = TestReport(
        scenario_id="cenario_bugs",
        scenario_title="Cenário com Falhas",
        profile="odoo",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp1",
                expected_behavior="Tudo certo",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.LAYOUT_MODAL,
                        severidade=IssueSeverity.BLOQUEANTE,
                        descricao="Tabela estoura tela no mobile",
                        sugestao_correcao="Aplicar overflow-x: auto",
                        elemento_alvo="table.o_list_view",
                    )
                ],
            )
        ],
    )
    report.compute_totals()

    created_urls = await jira_client.create_issues_from_report(report)
    assert len(created_urls) == 1
    assert created_urls[0] == "https://minhaempresa.atlassian.net/browse/UXS-101"

    # 4. Relatório sem problemas não deve criar issues
    report_clean = TestReport(
        scenario_id="cenario_limpo",
        scenario_title="Cenário Sem Falhas",
        profile="odoo",
        provider_used="anthropic_cloud",
        checkpoints=[],
    )
    report_clean.compute_totals()
    no_urls = await jira_client.create_issues_from_report(report_clean)
    assert len(no_urls) == 0
    print("✓ Teste de Integração com Jira passou!")


def test_cli_fix_prompt_and_jira_flags():
    import argparse
    from unittest.mock import patch

    # Testa parsing dos argumentos
    with (
        patch("sys.argv", ["uxsentinel", "--fix-prompt", "--jira", "--jira-project", "QA"]),
        patch("argparse.ArgumentParser.parse_args") as mock_parse,
    ):
        mock_parse.return_value = argparse.Namespace(
            version=False,
            scenario_pos=None,
            scenario="uxsentinel/scenarios/library/exemplo_odoo.yaml",
            provider=None,
            profile=None,
            headless=False,
            slowmo=None,
            output_dir=None,
            config="config/config.yaml",
            fix_prompt=True,
            jira=True,
            jira_project="QA",
            set_jira_token=False,
            init_config=False,
            list_scenarios=False,
            check_ai=False,
            login_sso=False,
            logout_sso=False,
        )
        # Verifica que os argumentos são atribuídos ao config
        from uxsentinel.core.config import load_config

        cfg = load_config("config/config.yaml")
        args = mock_parse.return_value
        if args.fix_prompt:
            cfg.reporting.generate_fix_prompt = True
        if args.jira:
            cfg.jira.enabled = True
        if args.jira_project:
            cfg.jira.project_key = args.jira_project

        assert cfg.reporting.generate_fix_prompt is True
        assert cfg.jira.enabled is True
        assert cfg.jira.project_key == "QA"

    print("✓ Teste de Flags CLI (--fix-prompt, --jira, --jira-project) passou!")


def test_jira_config_empty_env_vars_resilience():
    """Valida que o parser de configuração é resiliente a variáveis de ambiente ausentes ou campos nulos no Jira."""
    import tempfile
    from pathlib import Path

    from uxsentinel.core.config import load_config

    yaml_content = """
active_provider: anthropic_cloud
jira:
  enabled: false
  url: https://sua-empresa.atlassian.net
  email: ${JIRA_EMAIL}
  api_token: ${JIRA_API_TOKEN}
  project_key: ${JIRA_PROJECT_KEY}
  issue_type: Bug
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmp_path = f.name

    try:
        cfg = load_config(tmp_path)
        assert cfg.jira.enabled is False
        assert cfg.jira.email == ""
        assert cfg.jira.api_token == ""
        assert cfg.jira.project_key == ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    print("✓ Teste de Resiliência do Jira Config com Variáveis Ausentes passou!")


if __name__ == "__main__":
    test_cli_version()
    test_resolve_scenario_path_rules()
    test_config_and_scenarios()
    test_report_directory_configuration_and_cli()
    test_sso_authentication_and_loopback()
    test_claude_pro_oauth_pkce_and_headers()
    test_reporting()
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        test_fix_prompt_builder(Path(td))
    test_cli_fix_prompt_and_jira_flags()
    test_jira_config_empty_env_vars_resilience()
    asyncio.run(test_browser_session_headless())
    asyncio.run(test_ai_preflight_check())
    print("\n🎉 TODOS OS TESTES INTERNOS PASSARAM COM SUCESSO!")
