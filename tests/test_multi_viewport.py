import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import (
    CANONICAL_VIEWPORTS,
    DEFAULT_FALLBACK_VIEWPORT,
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    StepAction,
    TestReport,
    ViewportConfig,
    parse_viewport_spec,
    parse_viewports,
    resolve_viewports,
)
from uxsentinel.integrations.jira import JiraClient
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.scenarios.parser import load_scenario

# ==============================================================================
# 1. Testes de Modelos, Presets e Resolução de Viewport
# ==============================================================================


def test_canonical_viewport_presets():
    """Valida os presets canônicos: desktop (1440x900), tablet (768x1024), mobile (375x812, is_mobile=True)."""
    assert "desktop" in CANONICAL_VIEWPORTS
    assert "tablet" in CANONICAL_VIEWPORTS
    assert "mobile" in CANONICAL_VIEWPORTS

    desktop = parse_viewport_spec("desktop")
    assert desktop.name == "desktop"
    assert desktop.width == 1440
    assert desktop.height == 900
    assert desktop.is_mobile is False
    assert desktop.label == "desktop (1440x900)"

    tablet = parse_viewport_spec("tablet")
    assert tablet.name == "tablet"
    assert tablet.width == 768
    assert tablet.height == 1024
    assert tablet.is_mobile is False
    assert tablet.label == "tablet (768x1024)"

    mobile = parse_viewport_spec("mobile")
    assert mobile.name == "mobile"
    assert mobile.width == 375
    assert mobile.height == 812
    assert mobile.is_mobile is True
    assert mobile.label == "mobile (375x812)"


def test_custom_viewport_parsing():
    """Valida o parser para resoluções customizadas LARGURAxALTURA e nomeadas."""
    # 1920x1080 (desktop widescreen)
    vp_fhd = parse_viewport_spec("1920x1080")
    assert vp_fhd.name == "1920x1080"
    assert vp_fhd.width == 1920
    assert vp_fhd.height == 1080
    assert vp_fhd.is_mobile is False

    # 412x915 (Android mobile moderno - deve detectar proporção mobile)
    vp_android = parse_viewport_spec("412x915")
    assert vp_android.name == "412x915"
    assert vp_android.width == 412
    assert vp_android.height == 915
    assert vp_android.is_mobile is True

    # Com espaços e maiúsculas
    vp_spaced = parse_viewport_spec(" 1280 X 720 ")
    assert vp_spaced.width == 1280
    assert vp_spaced.height == 720

    # Custom nomeado
    vp_named = parse_viewport_spec("ultrawide:2560x1080")
    assert vp_named.name == "ultrawide"
    assert vp_named.width == 2560
    assert vp_named.height == 1080

    # Passando o próprio ViewportConfig
    vp_instance = ViewportConfig(name="teste", width=1000, height=800)
    assert parse_viewport_spec(vp_instance) is vp_instance

    # Formato inválido
    with pytest.raises(ValueError):
        parse_viewport_spec("resolucao_invalida")


def test_parse_viewports_list_and_csv():
    """Valida parse_viewports aceitando strings separadas por vírgula, listas ou dicionários."""
    # String separada por vírgula
    vps1 = parse_viewports("desktop, mobile, 800x600")
    assert len(vps1) == 3
    assert vps1[0].name == "desktop"
    assert vps1[1].name == "mobile"
    assert vps1[2].width == 800

    # Lista de strings
    vps2 = parse_viewports(["desktop", "tablet"])
    assert len(vps2) == 2
    assert vps2[0].name == "desktop"
    assert vps2[1].name == "tablet"

    # None ou vazio
    assert parse_viewports(None) == []
    assert parse_viewports("") == []


def test_resolve_viewports_precedence():
    """Valida a precedência estrita:
    1. CLI flag (--viewports / --viewport)
    2. Cenário YAML (campo 'viewports')
    3. Config global (BrowserSettings.viewports)
    4. Fallback padrão: desktop padrão 1280x800
    """
    cli_vp = "mobile"
    sc_vp = ["tablet"]
    cfg_vp = ["desktop"]

    # 1. CLI sobrepõe Cenário e Config
    resolved_1 = resolve_viewports(cli_viewports=cli_vp, scenario_viewports=sc_vp, config_viewports=cfg_vp)
    assert len(resolved_1) == 1
    assert resolved_1[0].name == "mobile"

    # 2. Cenário sobrepõe Config quando CLI é None
    resolved_2 = resolve_viewports(cli_viewports=None, scenario_viewports=sc_vp, config_viewports=cfg_vp)
    assert len(resolved_2) == 1
    assert resolved_2[0].name == "tablet"

    # 3. Config sobrepõe Fallback quando CLI e Cenário são None
    resolved_3 = resolve_viewports(cli_viewports=None, scenario_viewports=None, config_viewports=cfg_vp)
    assert len(resolved_3) == 1
    assert resolved_3[0].name == "desktop"
    assert resolved_3[0].width == 1440

    # 4. Fallback padrão seguro (desktop 1280x800)
    resolved_4 = resolve_viewports(cli_viewports=None, scenario_viewports=None, config_viewports=None)
    assert len(resolved_4) == 1
    assert resolved_4[0].name == DEFAULT_FALLBACK_VIEWPORT.name
    assert resolved_4[0].width == 1280
    assert resolved_4[0].height == 800


# ==============================================================================
# 2. Testes de Parsing de Cenários YAML
# ==============================================================================


def test_scenario_yaml_viewports_field(tmp_path: Path):
    """Valida o parsing do campo 'viewports' em cenários YAML (lista, string e vazio)."""
    # 1. viewports como lista de presets
    sc_file_list = tmp_path / "sc_vp_list.yaml"
    sc_file_list.write_text(
        "id: sc1\ntitle: T1\nviewports:\n  - desktop\n  - tablet\n  - mobile\nsteps: []\n",
        encoding="utf-8",
    )
    sc1 = load_scenario(str(sc_file_list))
    assert sc1.viewports == ["desktop", "tablet", "mobile"]

    # 2. viewports como string separada por vírgula
    sc_file_str = tmp_path / "sc_vp_str.yaml"
    sc_file_str.write_text(
        "id: sc2\ntitle: T2\nviewports: 'desktop, 375x812'\nsteps: []\n",
        encoding="utf-8",
    )
    sc2 = load_scenario(str(sc_file_str))
    assert sc2.viewports == ["desktop", "375x812"]

    # 3. sem viewports
    sc_file_none = tmp_path / "sc_vp_none.yaml"
    sc_file_none.write_text("id: sc3\ntitle: T3\nsteps: []\n", encoding="utf-8")
    sc3 = load_scenario(str(sc_file_none))
    assert sc3.viewports is None


# ==============================================================================
# 3. Testes de CLI Flags (--viewports e --viewport)
# ==============================================================================


def test_cli_viewports_flags():
    """Valida as flags de linha de comando --viewports e --viewport e exclusão mútua."""
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--viewports", type=str, default=None)
    group.add_argument("--viewport", type=str, default=None)

    # Flag --viewports
    args1 = parser.parse_args(["--viewports", "desktop,tablet,mobile"])
    assert args1.viewports == "desktop,tablet,mobile"
    assert args1.viewport is None

    # Flag --viewport
    args2 = parser.parse_args(["--viewport", "1280x720"])
    assert args2.viewport == "1280x720"
    assert args2.viewports is None

    # Conflito mútuo
    with pytest.raises(SystemExit):
        parser.parse_args(["--viewports", "desktop", "--viewport", "mobile"])


# ==============================================================================
# 4. Testes de Execução Multi-Viewport pelo Agente (Hermético com Mocks)
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_multi_viewport_execution(tmp_path: Path):
    """Garante que o agente executa a matriz multi-viewport configurada redimensionando a página e carimbando os checkpoints."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)

    # Mock da IA
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    def mock_inspect(**kwargs):
        return CheckpointResult(
            name=kwargs["checkpoint_name"],
            expected_behavior=kwargs["expected_behavior"],
            screenshot_path=kwargs.get("screenshot_path"),
            status="ok",
            issues=[],
        )

    agent.inspector.inspect = AsyncMock(side_effect=mock_inspect)

    scenario = Scenario(
        id="resp_test",
        title="Auditoria Responsiva",
        viewports=["desktop", "mobile"],  # Matriz de 2 viewports
        steps=[
            StepAction(action="goto", url="https://example.com"),
            StepAction(action="checkpoint", name="home_screen"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="Conteúdo da página")
    mock_driver.set_viewport = AsyncMock()
    mock_driver.page = AsyncMock()

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver

        report = await agent.run_scenario(scenario)

        assert report.success is True
        assert len(report.viewports_tested) == 2
        assert "desktop (1440x900)" in report.viewports_tested
        assert "mobile (375x812)" in report.viewports_tested

        # Deve ter redimensionado a viewport para cada configuração
        viewport_calls = [c[0] for c in mock_driver.set_viewport.call_args_list]
        assert (1440, 900) in viewport_calls
        assert (375, 812) in viewport_calls

        # Deve ter avaliado 2 checkpoints (um para cada viewport)
        assert len(report.checkpoints) == 2
        cp_desktop = report.checkpoints[0]
        cp_mobile = report.checkpoints[1]

        assert cp_desktop.viewport == "desktop (1440x900)"
        assert cp_mobile.viewport == "mobile (375x812)"

        # Checkpoints devem ter nomes distintos para evitar colisão
        assert "desktop" in cp_desktop.name
        assert "mobile" in cp_mobile.name

        # Screenshots devem ter nomes distintos por viewport
        assert "desktop" in cp_desktop.screenshot_path
        assert "mobile" in cp_mobile.screenshot_path


@pytest.mark.asyncio
async def test_agent_set_viewport_step_action(tmp_path: Path):
    """Valida a execução de passo explícito com action 'set_viewport'."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    agent = UXSentinelAgent(cfg)

    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "IA Conectada"))

    scenario = Scenario(
        id="step_vp_test",
        title="Passo Set Viewport",
        steps=[
            StepAction(action="set_viewport", value="tablet"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.set_viewport = AsyncMock()

    with (
        patch("uxsentinel.core.agent.open_browser_session") as mock_open_session,
        patch("uxsentinel.core.agent.console.print"),
    ):
        mock_open_session.return_value.__aenter__.return_value = mock_driver

        report = await agent.run_scenario(scenario)
        assert report.success is True
        mock_driver.set_viewport.assert_any_call(768, 1024)


# ==============================================================================
# 5. Testes de Visualização no Dashboard HTML
# ==============================================================================


def test_html_builder_viewport_filters(tmp_path: Path):
    """Valida que o relatório HTML contém filtros e separadores por viewport."""
    report = TestReport(
        scenario_id="multi_vp_report",
        scenario_title="Relatório Multi-Viewport",
        profile="generic",
        provider_used="anthropic_cloud",
        viewports_tested=["desktop (1440x900)", "mobile (375x812)"],
        checkpoints=[
            CheckpointResult(
                name="cp_desktop",
                viewport="desktop (1440x900)",
                expected_behavior="Desktop layout",
                status="ok",
                issues=[],
            ),
            CheckpointResult(
                name="cp_mobile",
                viewport="mobile (375x812)",
                expected_behavior="Mobile layout",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.LAYOUT_MODAL,
                        severidade=IssueSeverity.ALTA,
                        descricao="Botão transborda no viewport mobile",
                        viewport="mobile (375x812)",
                    )
                ],
            ),
        ],
    )
    report.compute_totals()

    html_file = save_html_report(report, str(tmp_path))
    assert html_file.is_file()

    html_content = html_file.read_text(encoding="utf-8")

    # Verifica meta-info com viewports testadas
    assert "Viewports:" in html_content
    assert "desktop (1440x900)" in html_content
    assert "mobile (375x812)" in html_content

    # Verifica a existência dos botões de filtro
    assert "viewport-filter-btn" in html_content
    assert "Todas as Resoluções" in html_content
    assert "filterViewport(" in html_content

    # Verifica data-viewport nos cards
    assert 'data-viewport="desktop (1440x900)"' in html_content
    assert 'data-viewport="mobile (375x812)"' in html_content

    # Verifica badges de viewport nos checkpoints e issues
    assert "📱 mobile (375x812)" in html_content or "mobile (375x812)" in html_content


# ==============================================================================
# 6. Testes de Integração com Jira
# ==============================================================================


@pytest.mark.asyncio
async def test_jira_integration_includes_viewport():
    """Valida que o cliente Jira formata a descrição e labels com metadados da viewport em quebras responsivas."""
    from uxsentinel.core.config import JiraSettings

    settings = JiraSettings(
        enabled=True,
        url="https://empresa.atlassian.net",
        email="qa@empresa.com",
        api_token="token123",
        project_key="UXS",
    )
    client = JiraClient(settings)

    issue = Issue(
        categoria=IssueCategory.LAYOUT_MODAL,
        severidade=IssueSeverity.ALTA,
        descricao="Menu hambúrguer quebrado",
        viewport="mobile (375x812)",
    )

    desc = client._format_description(
        scenario_id="sc_resp",
        scenario_title="Responsividade Menu",
        checkpoint_name="cp_menu_mobile",
        expected_behavior="Menu deve ser expansível em mobile",
        issue=issue,
        viewport="mobile (375x812)",
    )

    # Verifica que a resolução afetada é exibida de forma destacada no Jira
    assert "*Dispositivo / Resolução:* mobile (375x812)" in desc
    assert "Resolução / Dispositivo Afetado" in desc
    assert "*Viewport:* mobile (375x812)" in desc


@pytest.mark.asyncio
async def test_jira_create_issues_labels_and_summary():
    """Garante que a abertura de card inclui o prefixo do viewport no summary e labels correspondentes."""
    from uxsentinel.core.config import JiraSettings

    settings = JiraSettings(
        enabled=True,
        url="https://empresa.atlassian.net",
        email="qa@empresa.com",
        api_token="token123",
        project_key="UXS",
    )
    client = JiraClient(settings)

    report = TestReport(
        scenario_id="sc_resp",
        scenario_title="Auditoria Responsiva",
        profile="generic",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp_mobile",
                viewport="mobile (375x812)",
                expected_behavior="Menu visível",
                status="problemas_encontrados",
                issues=[
                    Issue(
                        categoria=IssueCategory.LAYOUT_MODAL,
                        severidade=IssueSeverity.ALTA,
                        descricao="Quebra em mobile",
                        viewport="mobile (375x812)",
                    )
                ],
            )
        ],
    )

    captured_payloads = []

    async def mock_post(url, json=None, **kwargs):
        captured_payloads.append(json)
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"key": "UXS-101"}
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        cards = await client.create_issues_from_report(report)

        assert len(cards) == 1
        assert "https://empresa.atlassian.net/browse/UXS-101" in cards[0]
        assert len(captured_payloads) == 1

        fields = captured_payloads[0]["fields"]
        assert "[UXSentinel][MOBILE]" in fields["summary"]
        assert "viewport-mobile" in fields["labels"]
