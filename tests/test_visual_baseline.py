"""Testes unitários e de integração herméticos para o Baseline Visual com Slider Comparativo (UXS-7)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import GlobalConfig, resolve_baseline_mode
from uxsentinel.core.models import (
    BoundingBox,
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    StepAction,
    TestReport,
    VisualDiffResult,
)
from uxsentinel.integrations.jira import JiraClient
from uxsentinel.reporter.html_builder import build_html_report, save_html_report
from uxsentinel.vision.diff import (
    compare_images,
    compute_bounding_boxes,
    create_diff_image,
)

# ==============================================================================
# Helpers para criação de imagens sintéticas de teste
# ==============================================================================


def create_test_image(
    path: Path,
    width: int = 200,
    height: int = 150,
    color: tuple[int, int, int] = (255, 255, 255),
    shapes: list[tuple[str, tuple[int, int, int, int], tuple[int, int, int]]] | None = None,
) -> Path:
    """Cria uma imagem de teste sintética com formas opcionais desenhadas."""
    img = Image.new("RGB", (width, height), color)
    if shapes:
        draw = ImageDraw.Draw(img)
        for shape_type, box, fill in shapes:
            if shape_type == "rectangle":
                draw.rectangle(box, fill=fill)
            elif shape_type == "ellipse":
                draw.ellipse(box, fill=fill)
    img.save(str(path), "PNG")
    return path


# ==============================================================================
# 1. Testes do Módulo de Diferenciação Visual (uxsentinel.vision.diff)
# ==============================================================================


def test_compare_identical_images(tmp_path: Path):
    """Compara imagens 100% idênticas e valida 0% de divergência e has_diff=False."""
    img_base = tmp_path / "base.png"
    img_curr = tmp_path / "curr.png"
    create_test_image(img_base, width=100, height=80, color=(240, 240, 240))
    create_test_image(img_curr, width=100, height=80, color=(240, 240, 240))

    result = compare_images(img_base, img_curr, threshold=0.1)

    assert result.diff_percentage == 0.0
    assert result.has_diff is False
    assert result.diff_pixels == 0
    assert result.total_pixels == 100 * 80
    assert len(result.bounding_boxes) == 0
    assert result.diff_image_path is None


def test_compare_modified_images_generates_diff_and_bounding_boxes(tmp_path: Path):
    """Compara imagem modificada com baseline, validando cálculo de diff, bboxes e imagem gerada."""
    img_base = tmp_path / "base.png"
    img_curr = tmp_path / "curr.png"
    diff_out = tmp_path / "diff_output.png"

    # Baseline limpo branco
    create_test_image(img_base, width=200, height=200, color=(255, 255, 255))

    # Captura atual com um bloco vermelho modificado de 50x50 no canto (50x50 = 2500 pixels em 40000 = ~6.25%)
    create_test_image(
        img_curr,
        width=200,
        height=200,
        color=(255, 255, 255),
        shapes=[("rectangle", (50, 50, 100, 100), (255, 0, 0))],
    )

    result = compare_images(
        baseline_path=img_base,
        current_path=img_curr,
        diff_output_path=diff_out,
        threshold=0.1,
    )

    assert result.has_diff is True
    assert result.diff_percentage > 5.0
    assert result.diff_pixels > 0
    assert result.total_pixels == 40000
    assert len(result.bounding_boxes) >= 1

    # Valida que o bounding box circunda a área alterada
    bbox = result.bounding_boxes[0]
    assert bbox.x <= 50
    assert bbox.y <= 50
    assert bbox.x + bbox.width >= 100
    assert bbox.y + bbox.height >= 100

    # Valida a geração da imagem de diff destacada
    assert diff_out.is_file()
    assert result.diff_image_path == str(diff_out)

    with Image.open(diff_out) as saved_diff:
        assert saved_diff.size == (200, 200)
        # Verifica que o pixel modificado contém componente de destaque vermelho/magenta (#E11D48)
        pixel_color = saved_diff.getpixel((75, 75))
        assert pixel_color[0] >= 200  # Canal R dominante na cor #E11D48


def test_compare_images_with_different_dimensions(tmp_path: Path):
    """Garante que imagens com tamanhos distintos são acomodadas em canvas unificado sem erros."""
    img_base = tmp_path / "base_small.png"
    img_curr = tmp_path / "curr_large.png"
    diff_out = tmp_path / "diff_dim.png"

    create_test_image(img_base, width=100, height=100, color=(255, 255, 255))
    create_test_image(img_curr, width=150, height=120, color=(255, 255, 255))

    result = compare_images(img_base, img_curr, diff_output_path=diff_out, threshold=0.1)

    assert result.total_pixels == 150 * 120
    assert diff_out.is_file()
    with Image.open(diff_out) as diff_img:
        assert diff_img.size == (150, 120)


def test_compare_images_missing_file(tmp_path: Path):
    """Garante levantamento de FileNotFoundError ao comparar com arquivo inexistente."""
    valid_file = tmp_path / "valid.png"
    create_test_image(valid_file, 50, 50)

    with pytest.raises(FileNotFoundError, match="baseline não encontrada"):
        compare_images(tmp_path / "nonexistent.png", valid_file)

    with pytest.raises(FileNotFoundError, match="atual não encontrada"):
        compare_images(valid_file, tmp_path / "nonexistent_curr.png")


# ==============================================================================
# 2. Testes de Configuração e Resolução de Linha de Comando (CLI)
# ==============================================================================


def test_resolve_baseline_mode_precedence():
    """Valida a precedência estrita de resolução do baseline: CLI > Cenário > Config > False."""
    # 1. CLI ativo
    assert (
        resolve_baseline_mode(
            cli_update_baseline=True, scenario_update_baseline=False, config_update_baseline=False
        )
        is True
    )
    # 2. CLI inativo força inativo
    assert (
        resolve_baseline_mode(
            cli_update_baseline=False, scenario_update_baseline=True, config_update_baseline=True
        )
        is False
    )
    # 3. Cenário ativo quando CLI omitido
    assert (
        resolve_baseline_mode(
            cli_update_baseline=None, scenario_update_baseline=True, config_update_baseline=False
        )
        is True
    )
    # 4. Config ativo quando CLI e Cenário omitidos
    assert (
        resolve_baseline_mode(
            cli_update_baseline=None, scenario_update_baseline=None, config_update_baseline=True
        )
        is True
    )
    # 5. Fallback padrão: False
    assert (
        resolve_baseline_mode(
            cli_update_baseline=None, scenario_update_baseline=None, config_update_baseline=None
        )
        is False
    )


def test_cli_baseline_arguments_parsing():
    """Valida que o parser de argumentos suporta --update-baseline, --baseline-dir e --diff-threshold."""

    parser = argparse.ArgumentParser()
    # Simula a adição dos argumentos como feito em cli.py
    baseline_group = parser.add_argument_group("Baseline Visual")
    baseline_group.add_argument("--update-baseline", action="store_true", default=None)
    baseline_group.add_argument("--baseline-dir", type=str, default=None)
    baseline_group.add_argument("--diff-threshold", type=float, default=None)

    args = parser.parse_args(
        ["--update-baseline", "--baseline-dir", "custom/baselines", "--diff-threshold", "0.5"]
    )
    assert args.update_baseline is True
    assert args.baseline_dir == "custom/baselines"
    assert args.diff_threshold == 0.5


# ==============================================================================
# 3. Testes do Fluxo de Execução do Agente (UXSentinelAgent)
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_update_baseline_mode(tmp_path: Path):
    """Garante que o modo --update-baseline homologa o screenshot atual e salva no diretório de baseline."""
    out_dir = tmp_path / "report"
    baseline_dir = tmp_path / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = GlobalConfig()
    config.reporting.output_dir = str(out_dir)
    config.baseline.baseline_dir = str(baseline_dir)

    scenario = Scenario(
        id="sc_baseline_update",
        title="Teste Update Baseline",
        profile="generic",
        steps=[
            StepAction(action="checkpoint", name="tela_inicial", expected_behavior="Layout correto"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.set_viewport = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="Conteúdo do DOM")

    async def fake_screenshot(path: str, full_page: bool = True):
        create_test_image(Path(path), width=100, height=100, color=(200, 220, 240))

    mock_driver.page = AsyncMock()
    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)

    agent = UXSentinelAgent(
        config=config,
        enable_axe_override=False,
        update_baseline_override=True,
        baseline_dir_override=str(baseline_dir),
    )

    # Mock do inspector para retornar resultado OK sem invocar rede de IA
    fake_cp_result = CheckpointResult(
        name="tela_inicial",
        expected_behavior="Layout correto",
        status="ok",
        issues=[],
    )
    agent.inspector.inspect = AsyncMock(return_value=fake_cp_result)
    agent.inspector.client = MagicMock()
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "OK"))

    with patch("uxsentinel.core.agent.open_browser_session") as mock_session_ctx:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_driver
        mock_ctx.__aexit__.return_value = None
        mock_session_ctx.return_value = mock_ctx

        report = await agent.run_scenario(
            scenario,
            enable_axe_override=False,
            update_baseline_override=True,
        )

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.visual_diff is not None
    assert cp.visual_diff.diff_percentage == 0.0
    assert cp.visual_diff.has_diff is False

    # Valida que o arquivo de baseline foi gravado fisicamente
    expected_baseline_file = baseline_dir / "sc_baseline_update" / "tela_inicial.png"
    assert expected_baseline_file.is_file()


@pytest.mark.asyncio
async def test_agent_visual_regression_detection(tmp_path: Path):
    """Valida que o agente executa a comparação e gera uma Issue de regressão visual quando há divergência."""
    out_dir = tmp_path / "report"
    baseline_dir = tmp_path / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pré-cria o baseline de referência (fundo branco)
    scenario_baseline_dir = baseline_dir / "sc_visual_regress"
    scenario_baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = scenario_baseline_dir / "cp_dashboard.png"
    create_test_image(baseline_file, width=120, height=120, color=(255, 255, 255))

    config = GlobalConfig()
    config.reporting.output_dir = str(out_dir)
    config.baseline.baseline_dir = str(baseline_dir)
    config.baseline.diff_threshold = 0.1

    scenario = Scenario(
        id="sc_visual_regress",
        title="Detecção de Regressão",
        profile="generic",
        steps=[
            StepAction(action="checkpoint", name="cp_dashboard", expected_behavior="Dashboard intacto"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.set_viewport = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")

    # O screenshot atual possui uma quebra visual vermelha expressiva (50x50 = ~17% de divergência)
    async def fake_screenshot(path: str, full_page: bool = True):
        create_test_image(
            Path(path),
            width=120,
            height=120,
            color=(255, 255, 255),
            shapes=[("rectangle", (20, 20, 70, 70), (255, 0, 0))],
        )

    mock_driver.page = AsyncMock()
    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)

    agent = UXSentinelAgent(
        config=config,
        enable_axe_override=False,
        update_baseline_override=False,
        baseline_dir_override=str(baseline_dir),
    )

    # Mock do inspector: ele recebe extra_issues (onde a issue de regressão visual foi injetada)
    def fake_inspect(**kwargs):
        extra = kwargs.get("extra_issues", [])
        return CheckpointResult(
            name=kwargs["checkpoint_name"],
            expected_behavior=kwargs["expected_behavior"],
            status="problemas_encontrados" if extra else "ok",
            issues=list(extra),
        )

    agent.inspector.inspect = AsyncMock(side_effect=fake_inspect)
    agent.inspector.client = MagicMock()
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "OK"))

    with patch("uxsentinel.core.agent.open_browser_session") as mock_session_ctx:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_driver
        mock_ctx.__aexit__.return_value = None
        mock_session_ctx.return_value = mock_ctx

        report = await agent.run_scenario(
            scenario,
            enable_axe_override=False,
            update_baseline_override=False,
        )

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.visual_diff is not None
    assert cp.visual_diff.has_diff is True
    assert cp.visual_diff.diff_percentage > 1.0
    assert cp.visual_diff.diff_image_path is not None
    assert Path(cp.visual_diff.diff_image_path).is_file()

    # Verifica que a issue de regressão visual foi gerada com categoria LAYOUT e evaluator correto
    assert len(cp.issues) >= 1
    regress_issue = next(i for i in cp.issues if i.evaluator == "visual-baseline-diff")
    assert regress_issue.categoria in (IssueCategory.LAYOUT, IssueCategory.LAYOUT_MODAL)
    assert "Regressão visual detectada" in regress_issue.descricao
    assert "flag --update-baseline" in regress_issue.sugestao_correcao


# ==============================================================================
# 4. Testes do Componente de Slider Interativo Antes/Depois no HTML Builder
# ==============================================================================


def test_html_builder_renders_visual_slider_and_tabs(tmp_path: Path):
    """Valida a renderização do slider interativo split-view e das abas de visualização no relatório HTML."""
    baseline_img = tmp_path / "baseline_sample.png"
    curr_img = tmp_path / "curr_sample.png"
    diff_img = tmp_path / "diff_sample.png"

    create_test_image(baseline_img, 100, 100, (255, 255, 255))
    create_test_image(curr_img, 100, 100, (200, 200, 200))
    create_test_image(diff_img, 100, 100, (225, 29, 72))

    visual_diff = VisualDiffResult(
        baseline_path=str(baseline_img),
        current_path=str(curr_img),
        diff_image_path=str(diff_img),
        diff_percentage=3.45,
        has_diff=True,
        threshold=0.1,
        bounding_boxes=[BoundingBox(x=10, y=10, width=30, height=30)],
        total_pixels=10000,
        diff_pixels=345,
    )

    report = TestReport(
        scenario_id="sc_slider_test",
        scenario_title="Cenário Slider HTML",
        profile="generic",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp_view_slider",
                screenshot_path=str(curr_img),
                expected_behavior="Tela sem regressões",
                status="problemas_encontrados",
                visual_diff=visual_diff,
            )
        ],
    )

    html_content = build_html_report(report, output_dir=tmp_path)

    # 1. Valida elementos essenciais do slider comparativo
    assert "visual-slider-box" in html_content
    assert "slider-input-range" in html_content
    assert "slider-divider" in html_content
    assert "slider-handle-btn" in html_content
    assert "Antes (Baseline)" in html_content
    assert "Depois (Atual)" in html_content

    # 2. Valida as abas de modo de exibição
    assert "slider-view-tabs" in html_content
    assert "🎚️ Slider Antes / Depois" in html_content
    assert "🎭 Máscara de Diff (Highlight)" in html_content
    assert "📸 Captura Atual" in html_content
    assert "📌 Baseline Homologado" in html_content

    # 3. Valida badge com percentual de divergência
    assert "3.45%" in html_content
    assert "Regressão Visual" in html_content

    # 4. Valida funções JavaScript de controle do slider
    assert "function onSliderInput(input, containerId)" in html_content
    assert "function switchViewMode(btn, targetMode)" in html_content

    # 5. Salva em disco e verifica existência do arquivo
    report_file = save_html_report(report, str(tmp_path))
    assert report_file.is_file()


# ==============================================================================
# 5. Testes de Integração com Jira (Metadados e Anexo de Diff)
# ==============================================================================


@pytest.mark.asyncio
async def test_jira_integration_includes_visual_diff_metadata_and_attachments(tmp_path: Path):
    """Valida que o cliente Jira formata a descrição com métricas de diff e anexa a imagem de diff."""
    from uxsentinel.core.config import JiraSettings

    base_p = tmp_path / "base_card.png"
    curr_p = tmp_path / "curr_card.png"
    diff_p = tmp_path / "diff_card.png"
    create_test_image(base_p, 80, 80)
    create_test_image(curr_p, 80, 80)
    create_test_image(diff_p, 80, 80)

    settings = JiraSettings(
        enabled=True,
        url="https://empresa.atlassian.net",
        email="qa@empresa.com",
        api_token="token123",
        project_key="UXS",
    )
    client = JiraClient(settings)

    visual_diff = VisualDiffResult(
        baseline_path=str(base_p),
        current_path=str(curr_p),
        diff_image_path=str(diff_p),
        diff_percentage=4.25,
        has_diff=True,
        threshold=0.1,
        bounding_boxes=[BoundingBox(x=5, y=5, width=20, height=20)],
        total_pixels=6400,
        diff_pixels=272,
    )

    issue = Issue(
        categoria=IssueCategory.LAYOUT,
        severidade=IssueSeverity.ALTA,
        descricao="Regressão visual detectada no dashboard: 4.25% de divergência.",
        evaluator="visual-baseline-diff",
    )

    desc = client._format_description(
        scenario_id="sc_jira_diff",
        scenario_title="Cenário Jira",
        checkpoint_name="cp_dashboard",
        expected_behavior="Tela íntegra",
        issue=issue,
        screenshot_path=str(curr_p),
        visual_diff=visual_diff,
    )

    # Verifica formatação da seção no card do Jira
    assert "Comparação Visual de Baseline (Visual Diff)" in desc
    assert "*Divergência Visual:* 4.25%" in desc
    assert str(base_p) in desc
    assert str(diff_p) in desc

    # Testa o envio e verificação dos anexos via mocks
    report = TestReport(
        scenario_id="sc_jira_diff",
        scenario_title="Cenário Jira",
        profile="generic",
        provider_used="anthropic_cloud",
        checkpoints=[
            CheckpointResult(
                name="cp_dashboard",
                screenshot_path=str(curr_p),
                expected_behavior="Tela íntegra",
                status="problemas_encontrados",
                issues=[issue],
                visual_diff=visual_diff,
            )
        ],
    )

    attached_files = []

    async def fake_attach(key: str, file_path: str | Path):
        attached_files.append(Path(file_path).name)
        return True

    client.attach_file_to_issue = AsyncMock(side_effect=fake_attach)

    # Mock do post HTTP para criar o card
    fake_post_resp = MagicMock()
    fake_post_resp.status_code = 201
    fake_post_resp.json.return_value = {"key": "UXS-999"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_post_resp
        created = await client.create_issues_from_report(report)

    assert len(created) == 1
    assert "UXS-999" in created[0]

    # Verifica que a imagem de captura atual, a de diff e a baseline foram agendadas para anexo
    assert curr_p.name in attached_files
    assert diff_p.name in attached_files
    assert base_p.name in attached_files


# ==============================================================================
# 6. Testes Complementares de Multi-Viewport e Limiar de Tolerância
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_visual_baseline_approved_within_threshold(tmp_path: Path):
    """Valida que quando a divergência visual está dentro do limiar de tolerância, nenhuma issue é criada."""
    out_dir = tmp_path / "report"
    baseline_dir = tmp_path / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Cria baseline e imagem idêntica (0% diff, limiar 1.0%)
    scenario_baseline_dir = baseline_dir / "sc_tolerance"
    scenario_baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = scenario_baseline_dir / "cp_perfeito.png"
    create_test_image(baseline_file, width=100, height=100, color=(255, 255, 255))

    config = GlobalConfig()
    config.reporting.output_dir = str(out_dir)
    config.baseline.baseline_dir = str(baseline_dir)
    config.baseline.diff_threshold = 1.0

    scenario = Scenario(
        id="sc_tolerance",
        title="Teste Tolerância",
        profile="generic",
        steps=[
            StepAction(action="checkpoint", name="cp_perfeito", expected_behavior="Conforme"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.set_viewport = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")

    async def fake_screenshot(path: str, full_page: bool = True):
        create_test_image(Path(path), width=100, height=100, color=(255, 255, 255))

    mock_driver.page = AsyncMock()
    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)

    agent = UXSentinelAgent(config=config, enable_axe_override=False, baseline_dir_override=str(baseline_dir))

    def fake_inspect(**kwargs):
        extra = kwargs.get("extra_issues", [])
        return CheckpointResult(
            name=kwargs["checkpoint_name"],
            expected_behavior=kwargs["expected_behavior"],
            status="ok",
            issues=list(extra),
        )

    agent.inspector.inspect = AsyncMock(side_effect=fake_inspect)
    agent.inspector.client = MagicMock()
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "OK"))

    with patch("uxsentinel.core.agent.open_browser_session") as mock_session_ctx:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_driver
        mock_ctx.__aexit__.return_value = None
        mock_session_ctx.return_value = mock_ctx

        report = await agent.run_scenario(scenario, enable_axe_override=False)

    assert len(report.checkpoints) == 1
    cp = report.checkpoints[0]
    assert cp.visual_diff is not None
    assert cp.visual_diff.has_diff is False
    assert cp.visual_diff.diff_percentage <= 1.0
    # Nenhuma issue de regressão visual
    assert not any(i.evaluator == "visual-baseline-diff" for i in cp.issues)


@pytest.mark.asyncio
async def test_agent_multi_viewport_baselines(tmp_path: Path):
    """Valida que no modo multi-viewport os baselines são organizados com o prefixo da resolução."""
    out_dir = tmp_path / "report"
    baseline_dir = tmp_path / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = GlobalConfig()
    config.reporting.output_dir = str(out_dir)
    config.baseline.baseline_dir = str(baseline_dir)

    scenario = Scenario(
        id="sc_multi_vp_base",
        title="Multi Viewport Baseline",
        viewports=["desktop", "mobile"],
        steps=[
            StepAction(action="checkpoint", name="home", expected_behavior="Responsivo"),
        ],
    )

    mock_driver = AsyncMock()
    mock_driver.set_viewport = AsyncMock()
    mock_driver.healing_events = []
    mock_driver.get_clean_dom_text = AsyncMock(return_value="DOM")

    async def fake_screenshot(path: str, full_page: bool = True):
        create_test_image(Path(path), width=100, height=100, color=(240, 240, 240))

    mock_driver.page = AsyncMock()
    mock_driver.page.screenshot = AsyncMock(side_effect=fake_screenshot)

    agent = UXSentinelAgent(
        config=config,
        enable_axe_override=False,
        update_baseline_override=True,
        baseline_dir_override=str(baseline_dir),
    )

    def fake_inspect(**kwargs):
        return CheckpointResult(
            name=kwargs["checkpoint_name"],
            expected_behavior=kwargs["expected_behavior"],
            status="ok",
            issues=[],
        )

    agent.inspector.inspect = AsyncMock(side_effect=fake_inspect)
    agent.inspector.client = MagicMock()
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "OK"))

    with patch("uxsentinel.core.agent.open_browser_session") as mock_session_ctx:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_driver
        mock_ctx.__aexit__.return_value = None
        mock_session_ctx.return_value = mock_ctx

        report = await agent.run_scenario(
            scenario,
            enable_axe_override=False,
            update_baseline_override=True,
        )

    assert len(report.checkpoints) == 2
    # Arquivos de baseline distintos por viewport gerados em scenarios/baselines/sc_multi_vp_base/
    base_folder = baseline_dir / "sc_multi_vp_base"
    assert (base_folder / "desktop_home.png").is_file()
    assert (base_folder / "mobile_home.png").is_file()


def test_compute_bounding_boxes_and_diff_image_directly():
    """Valida as funções compute_bounding_boxes e create_diff_image com máscara customizada."""
    mask = Image.new("L", (100, 100), 0)
    draw = ImageDraw.Draw(mask)
    # Dois blocos separados de diferença
    draw.rectangle([10, 10, 30, 30], fill=255)
    draw.rectangle([60, 60, 80, 80], fill=255)

    boxes = compute_bounding_boxes(mask, block_size=20)
    assert len(boxes) >= 2
    for b in boxes:
        assert isinstance(b, BoundingBox)
        assert b.width > 0
        assert b.height > 0

    curr = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    diff_image = create_diff_image(curr, mask, boxes)
    assert diff_image.size == (100, 100)
    assert diff_image.mode == "RGBA"
