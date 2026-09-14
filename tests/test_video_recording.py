from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from uxsentinel.browser.session import BrowserSession
from uxsentinel.core.agent import UXSentinelAgent
from uxsentinel.core.config import BrowserSettings, GlobalConfig, resolve_video_mode
from uxsentinel.core.models import (
    CheckpointResult,
    Issue,
    IssueCategory,
    IssueSeverity,
    Scenario,
    TestReport,
)
from uxsentinel.integrations.jira import JiraClient
from uxsentinel.reporter.html_builder import save_html_report
from uxsentinel.reporter.video_helper import (
    convert_webm_to_mp4,
    create_session_gif,
    finalize_session_video,
    generate_gif_from_images,
    generate_gif_from_video,
    is_ffmpeg_available,
)
from uxsentinel.scenarios.parser import load_scenario


# ==============================================================================
# 1. Configuração e Resolução da Gravação de Vídeo
# ==============================================================================
def test_resolve_video_mode_hierarchy():
    """Valida a hierarquia estrita de resolução do modo de gravação de vídeo:
    1. CLI flag (--record-video/--video vs --no-video)
    2. Cenário YAML (campo 'video' no arquivo de cenário)
    3. Config global config.yaml (BrowserSettings.record_video)
    4. Fallback padrão: False
    """
    # 1. CLI sobrepõe tudo (YAML e Config)
    assert resolve_video_mode(cli_video=True, scenario_video=False, config_video=False) is True
    assert resolve_video_mode(cli_video=False, scenario_video=True, config_video=True) is False

    # 2. Cenário YAML sobrepõe Config quando CLI é None
    assert resolve_video_mode(cli_video=None, scenario_video=True, config_video=False) is True
    assert resolve_video_mode(cli_video=None, scenario_video=False, config_video=True) is False

    # 3. Config sobrepõe padrão quando CLI e Cenário são None
    assert resolve_video_mode(cli_video=None, scenario_video=None, config_video=True) is True
    assert resolve_video_mode(cli_video=None, scenario_video=None, config_video=False) is False

    # 4. Fallback padrão seguro (False = Sem gravação de vídeo)
    assert resolve_video_mode(cli_video=None, scenario_video=None, config_video=None) is False
    assert resolve_video_mode() is False


@pytest.mark.parametrize(
    ("flag", "expected_video"),
    [
        ("--record-video", True),
        ("--video", True),
        ("--no-video", False),
    ],
)
def test_cli_video_flags_parsing(flag: str, expected_video: bool):
    """Testa o parsing das flags de linha de comando de vídeo."""
    parser = argparse.ArgumentParser()
    video_group = parser.add_mutually_exclusive_group()
    video_group.add_argument(
        "--record-video",
        "--video",
        dest="record_video",
        action="store_true",
        default=None,
    )
    video_group.add_argument(
        "--no-video",
        dest="record_video",
        action="store_false",
        default=None,
    )

    args = parser.parse_args([flag])
    assert args.record_video is expected_video


def test_scenario_yaml_video_field_parsing(tmp_path: Path):
    """Verifica se o parser de cenários lê o campo 'video' corretamente."""
    # Teste 1: video: true
    f1 = tmp_path / "scenario_video_true.yaml"
    f1.write_text("id: sc_vid_1\ntitle: Video True\nvideo: true\nsteps: []\n", encoding="utf-8")
    sc1 = load_scenario(str(f1))
    assert sc1.video is True

    # Teste 2: video: false
    f2 = tmp_path / "scenario_video_false.yaml"
    f2.write_text("id: sc_vid_2\ntitle: Video False\nvideo: false\nsteps: []\n", encoding="utf-8")
    sc2 = load_scenario(str(f2))
    assert sc2.video is False

    # Teste 3: video: "yes" (string)
    f3 = tmp_path / "scenario_video_str.yaml"
    f3.write_text("id: sc_vid_3\ntitle: Video Str\nvideo: 'yes'\nsteps: []\n", encoding="utf-8")
    sc3 = load_scenario(str(f3))
    assert sc3.video is True

    # Teste 4: ausente
    f4 = tmp_path / "scenario_video_none.yaml"
    f4.write_text("id: sc_vid_4\ntitle: Video None\nsteps: []\n", encoding="utf-8")
    sc4 = load_scenario(str(f4))
    assert sc4.video is None


def test_browser_settings_defaults():
    """Valida defaults e customizações em BrowserSettings."""
    b = BrowserSettings()
    assert b.record_video is False
    assert b.record_video_dir is None
    assert b.record_video_size is None

    b_custom = BrowserSettings(
        record_video=True,
        record_video_dir="custom/videos",
        record_video_size={"width": 1280, "height": 720},
    )
    assert b_custom.record_video is True
    assert b_custom.record_video_dir == "custom/videos"
    assert b_custom.record_video_size == {"width": 1280, "height": 720}


# ==============================================================================
# 2. Sessão do Navegador (Playwright) com Gravação de Vídeo
# ==============================================================================
@pytest.mark.asyncio
async def test_browser_session_records_video(tmp_path: Path):
    """Valida se BrowserSession repassa parâmetros de gravação ao BrowserContext do Playwright."""
    video_dir = tmp_path / "session_videos"
    settings = BrowserSettings(
        record_video=True,
        record_video_dir=str(video_dir),
        viewport_width=1280,
        viewport_height=720,
    )

    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_video = AsyncMock()

    dummy_video_file = video_dir / "playwright_temp.webm"
    dummy_video_file.parent.mkdir(parents=True, exist_ok=True)
    dummy_video_file.write_text("dummy video content", encoding="utf-8")

    mock_video.path = AsyncMock(return_value=str(dummy_video_file))
    mock_page.video = mock_video
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("uxsentinel.browser.session.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        session = BrowserSession(settings)
        driver = await session.start()

        # Verifica se new_context recebeu os parâmetros de vídeo
        mock_browser.new_context.assert_awaited_once()
        _, kwargs = mock_browser.new_context.call_args
        assert kwargs["record_video_dir"] == str(video_dir)
        assert kwargs["record_video_size"] == {"width": 1280, "height": 720}
        assert driver.session is session

        # Fecha a sessão e verifica a captura do caminho do vídeo
        await session.close()
        assert session.video_path == str(dummy_video_file)
        assert driver.video_path == str(dummy_video_file)


# ==============================================================================
# 3. Utilitário de Vídeo e GIF (video_helper.py)
# ==============================================================================
def test_video_helper_is_ffmpeg_available():
    """Testa detecção do ffmpeg via shutil.which."""
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        assert is_ffmpeg_available() is True

    with patch("shutil.which", return_value=None):
        assert is_ffmpeg_available() is False


def test_video_helper_convert_webm_to_mp4_success(tmp_path: Path):
    """Testa conversão bem-sucedida de webm para mp4 via ffmpeg."""
    src = tmp_path / "input.webm"
    src.write_text("fake webm", encoding="utf-8")
    dest = tmp_path / "output.mp4"

    def mock_subprocess_run(cmd, *args, **kwargs):
        dest.write_text("fake mp4", encoding="utf-8")
        m = MagicMock()
        m.returncode = 0
        return m

    with (
        patch("uxsentinel.reporter.video_helper.is_ffmpeg_available", return_value=True),
        patch("subprocess.run", side_effect=mock_subprocess_run),
    ):
        res = convert_webm_to_mp4(src, dest)
        assert res == dest
        assert res.is_file()


def test_video_helper_convert_webm_to_mp4_failures(tmp_path: Path):
    """Testa tratamento de erro na conversão webm para mp4."""
    # Arquivo de origem não existe
    assert convert_webm_to_mp4(tmp_path / "non_existent.webm") is None

    src = tmp_path / "input.webm"
    src.write_text("fake webm", encoding="utf-8")

    # ffmpeg não disponível
    with patch("uxsentinel.reporter.video_helper.is_ffmpeg_available", return_value=False):
        assert convert_webm_to_mp4(src) is None

    # ffmpeg falha com returncode != 0
    with (
        patch("uxsentinel.reporter.video_helper.is_ffmpeg_available", return_value=True),
        patch("subprocess.run") as mock_run,
    ):
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = b"FFmpeg conversion error"
        mock_run.return_value = mock_res
        assert convert_webm_to_mp4(src) is None


def test_video_helper_generate_gif_from_video(tmp_path: Path):
    """Testa geração de GIF com ffmpeg."""
    src = tmp_path / "input.webm"
    src.write_text("fake webm", encoding="utf-8")
    dest = tmp_path / "output.gif"

    def mock_run(cmd, *args, **kwargs):
        dest.write_text("fake gif", encoding="utf-8")
        m = MagicMock()
        m.returncode = 0
        return m

    with (
        patch("uxsentinel.reporter.video_helper.is_ffmpeg_available", return_value=True),
        patch("subprocess.run", side_effect=mock_run),
    ):
        res = generate_gif_from_video(src, dest)
        assert res == dest
        assert res.is_file()


def test_video_helper_generate_gif_from_images_pillow(tmp_path: Path):
    """Testa fallback de geração de GIF a partir de imagens com Pillow."""
    # Cria imagens reais temporárias para teste
    img1_path = tmp_path / "frame1.png"
    img2_path = tmp_path / "frame2.png"

    img1 = Image.new("RGB", (200, 100), color="blue")
    img1.save(img1_path)
    img2 = Image.new("RGB", (200, 100), color="red")
    img2.save(img2_path)

    out_gif = tmp_path / "session.gif"
    res = generate_gif_from_images([img1_path, img2_path], out_gif, duration_ms=500)

    assert res == out_gif
    assert res.is_file()
    assert res.stat().st_size > 0

    # Teste defensivo com lista vazia ou inexistente
    assert generate_gif_from_images([], out_gif) is None
    assert generate_gif_from_images([tmp_path / "inexistente.png"], out_gif) is None


def test_video_helper_create_session_gif_priority(tmp_path: Path):
    """Testa a estratégia de create_session_gif: prioriza ffmpeg, faz fallback para Pillow."""
    vid = tmp_path / "test.webm"
    vid.write_text("fake webm", encoding="utf-8")
    out_gif = tmp_path / "out.gif"

    # 1. Quando vídeo existe e ffmpeg está disponível
    with (
        patch("uxsentinel.reporter.video_helper.is_ffmpeg_available", return_value=True),
        patch("uxsentinel.reporter.video_helper.generate_gif_from_video") as mock_vid_gif,
    ):
        out_gif.write_text("gif", encoding="utf-8")
        mock_vid_gif.return_value = out_gif
        res = create_session_gif(video_path=vid, output_gif=out_gif)
        assert res == out_gif
        mock_vid_gif.assert_called_once()

    # 2. Quando vídeo não existe ou ffmpeg falha, faz fallback para screenshots
    with (
        patch("uxsentinel.reporter.video_helper.is_ffmpeg_available", return_value=False),
        patch("uxsentinel.reporter.video_helper.generate_gif_from_images") as mock_img_gif,
    ):
        img = tmp_path / "shot.png"
        img.write_text("img", encoding="utf-8")
        mock_img_gif.return_value = out_gif
        res = create_session_gif(video_path=None, checkpoint_screenshots=[img], output_gif=out_gif)
        assert res == out_gif
        mock_img_gif.assert_called_once()


def test_video_helper_finalize_session_video(tmp_path: Path):
    """Testa renomeação/movimentação do vídeo do Playwright para destino amigável."""
    raw = tmp_path / "temp_123.webm"
    raw.write_text("webm video content", encoding="utf-8")
    dest_dir = tmp_path / "reports" / "videos"

    final = finalize_session_video(
        raw_video_path=raw,
        output_dir=dest_dir,
        scenario_id="fluxo_checkout",
        try_mp4_conversion=False,
    )

    assert final.name == "fluxo_checkout_session.webm"
    assert final.is_file()
    assert dest_dir.is_dir()


# ==============================================================================
# 4. Player no Dashboard HTML (html_builder.py)
# ==============================================================================
def test_html_report_renders_video_player_and_gif(tmp_path: Path):
    """Valida se o relatório HTML renderiza a seção de vídeo e GIF quando disponíveis."""
    report = TestReport(
        scenario_id="sc_video_test",
        scenario_title="Cenário com Vídeo",
        profile="generic",
        provider_used="anthropic_cloud",
        video_path=str(tmp_path / "videos" / "sc_video_test_session.webm"),
        gif_path=str(tmp_path / "videos" / "sc_video_test_session.gif"),
    )

    html_file = save_html_report(report, str(tmp_path))
    content = html_file.read_text(encoding="utf-8")

    # Verifica tags do player HTML5 e GIF
    assert "<video controls" in content
    assert 'type="video/webm"' in content
    assert "videos/sc_video_test_session.webm" in content
    assert "videos/sc_video_test_session.gif" in content
    assert "🎬 Gravação de Sessão e Evidência Dinâmica" in content


def test_html_report_does_not_render_video_when_absent(tmp_path: Path):
    """Valida que o player de vídeo NÃO é exibido quando não há gravação."""
    report = TestReport(
        scenario_id="sc_no_video",
        scenario_title="Cenário Sem Vídeo",
        profile="generic",
        provider_used="anthropic_cloud",
        video_path=None,
        gif_path=None,
    )

    html_file = save_html_report(report, str(tmp_path))
    content = html_file.read_text(encoding="utf-8")

    assert "<video controls" not in content
    assert "🎬 Gravação de Sessão e Evidência Dinâmica" not in content


# ==============================================================================
# 5. Anexos no Atlassian Jira (jira.py)
# ==============================================================================
@pytest.mark.asyncio
async def test_jira_client_attach_file_to_issue(tmp_path: Path):
    """Testa upload multipart com X-Atlassian-Token: no-check no Jira."""
    dummy_file = tmp_path / "test_evidence.webm"
    dummy_file.write_text("binary-video-data", encoding="utf-8")

    settings = MagicMock()
    settings.url = "https://empresa.atlassian.net"
    settings.email = "qa@empresa.com"
    settings.api_token = "token123"
    settings.project_key = "UXS"
    settings.issue_type = "Bug"
    settings.labels = ["uxsentinel"]

    client = JiraClient(settings)

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = [{"id": "10001", "filename": "test_evidence.webm"}]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        ok = await client.attach_file_to_issue("UXS-42", dummy_file)

        assert ok is True
        mock_post.assert_awaited_once()
        call_url = mock_post.call_args[0][0]
        call_kwargs = mock_post.call_args[1]

        assert "rest/api/2/issue/UXS-42/attachments" in call_url
        assert "files" in call_kwargs
        assert call_kwargs["files"]["file"][0] == "test_evidence.webm"


@pytest.mark.asyncio
async def test_jira_client_attach_file_unconfigured_or_missing(tmp_path: Path):
    """Testa tratamento defensivo quando o Jira não está configurado ou o arquivo não existe."""
    settings = MagicMock()
    settings.url = ""
    settings.email = ""
    settings.api_token = ""
    settings.project_key = ""
    settings.issue_type = "Bug"
    settings.labels = []

    client = JiraClient(settings)

    # Jira não configurado
    dummy = tmp_path / "dummy.png"
    dummy.write_text("x", encoding="utf-8")
    assert await client.attach_file_to_issue("UXS-1", dummy) is False

    # Arquivo inexistente
    client.url = "https://teste.atlassian.net"
    client.api_token = "tok"
    client.project_key = "UXS"
    assert await client.attach_file_to_issue("UXS-1", tmp_path / "inexistente.mp4") is False


@pytest.mark.asyncio
async def test_jira_create_issues_attaches_video_and_gif(tmp_path: Path):
    """Valida se create_issues_from_report chama attach_file_to_issue para vídeo e GIF."""
    video_file = tmp_path / "session.webm"
    video_file.write_text("video", encoding="utf-8")
    gif_file = tmp_path / "session.gif"
    gif_file.write_text("gif", encoding="utf-8")

    issue = Issue(
        categoria=IssueCategory.TRADUCAO,
        severidade=IssueSeverity.ALTA,
        descricao="Texto em inglês detectado",
    )
    cp = CheckpointResult(
        name="cp1",
        expected_behavior="Tudo em PT-BR",
        status="problemas_encontrados",
        issues=[issue],
    )
    report = TestReport(
        scenario_id="sc_jira_test",
        scenario_title="Jira Anexos",
        profile="generic",
        provider_used="anthropic_cloud",
        checkpoints=[cp],
        video_path=str(video_file),
        gif_path=str(gif_file),
    )

    settings = MagicMock()
    settings.url = "https://empresa.atlassian.net"
    settings.email = "qa@empresa.com"
    settings.api_token = "token123"
    settings.project_key = "UXS"
    settings.issue_type = "Bug"
    settings.labels = ["uxsentinel"]

    client = JiraClient(settings)

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"key": "UXS-99"}

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch.object(client, "attach_file_to_issue", new_callable=AsyncMock) as mock_attach,
    ):
        mock_post.return_value = mock_resp
        created = await client.create_issues_from_report(report)

        assert len(created) == 1
        assert created[0] == "https://empresa.atlassian.net/browse/UXS-99"

        # Verifica se attach_file_to_issue foi chamado para o GIF e para o Vídeo
        attached_paths = [call.args[1] for call in mock_attach.call_args_list]
        assert str(gif_file) in attached_paths
        assert str(video_file) in attached_paths


# ==============================================================================
# 6. Orquestração no Agente
# ==============================================================================
@pytest.mark.asyncio
async def test_agent_orchestrates_video_and_gif(tmp_path: Path):
    """Valida o fluxo do UXSentinelAgent ao gerar vídeo e GIF da sessão."""
    cfg = GlobalConfig()
    cfg.reporting.output_dir = str(tmp_path / "report")
    cfg.browser.record_video = True

    scenario = Scenario(
        id="sc_orch_test",
        title="Orchestration Test",
        steps=[],
    )

    raw_video = tmp_path / "mock_raw_playwright.webm"
    raw_video.write_text("raw-webm", encoding="utf-8")

    agent = UXSentinelAgent(cfg)

    # Mock da conectividade com IA e da sessão
    agent.inspector.client.test_connection = AsyncMock(return_value=(True, "OK"))

    mock_driver = MagicMock()
    mock_driver.video_path = str(raw_video)
    mock_driver.healing_events = []
    mock_driver.page = AsyncMock()

    class MockSessionContext:
        async def __aenter__(self):
            return mock_driver

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    with (
        patch("uxsentinel.core.agent.open_browser_session", return_value=MockSessionContext()),
        patch("uxsentinel.reporter.video_helper.is_ffmpeg_available", return_value=False),
    ):
        rep = await agent.run_scenario(scenario)

        assert rep.video_path is not None
        assert Path(rep.video_path).is_file()
        assert Path(rep.video_path).name == "sc_orch_test_session.webm"
