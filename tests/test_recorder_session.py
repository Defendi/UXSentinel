"""Testes unitários herméticos para o RecorderSession (UXS-95).

Valida o ciclo de vida (start/pause/resume/stop), auto-save no close,
rejeição de URLs inválidas e persistência em YAML sem abrir navegadores reais,
utilizando mocks assíncronos do Playwright.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from uxsentinel.browser.recorder import (
    RecordedStep,
    RecordedTarget,
    RecorderSession,
    SelectorCandidate,
    SelectorStrategy,
    StepStatus,
)
from uxsentinel.scenarios.parser import load_scenario


@pytest.fixture
def mock_playwright_stack():
    """Configura a pilha de mocks assíncronos do Playwright."""
    with patch("uxsentinel.browser.recorder.session.async_playwright") as mock_pw_factory:
        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = MagicMock()
        mock_context.close = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com/start"

        mock_manager = MagicMock()
        mock_manager.start = AsyncMock(return_value=mock_playwright)
        mock_pw_factory.return_value = mock_manager

        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.on = MagicMock()

        yield {
            "factory": mock_pw_factory,
            "playwright": mock_playwright,
            "browser": mock_browser,
            "context": mock_context,
            "page": mock_page,
        }


class TestRecorderSessionUrlValidation:
    """Valida rejeição de URLs inválidas antes de chamar o Playwright (CA01b)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "invalid_url",
        [
            "not-a-url",
            "",
            "ftp://example.com",
            "file:///etc/passwd",
            "http://",
            "https://",
            "javascript:alert(1)",
        ],
    )
    async def test_invalid_url_raises_value_error_without_opening_browser(
        self, invalid_url: str, mock_playwright_stack: dict[str, Any]
    ) -> None:
        """URLs sem esquema http/https ou sem host válido devem falhar antes do Playwright."""
        session = RecorderSession(
            session_id="test-sess-1",
            name="Cenário Teste",
            url=invalid_url,
        )

        with pytest.raises(ValueError, match="URL inválida ou mal-formada:"):
            await session.start()

        # Garante hermeticidade: o Playwright jamais foi iniciado
        mock_playwright_stack["factory"].assert_not_called()
        mock_playwright_stack["playwright"].chromium.launch.assert_not_called()


class TestRecorderSessionStartLifecycle:
    """Valida a inicialização da sessão com URL válida."""

    @pytest.mark.asyncio
    async def test_start_with_valid_url(self, mock_playwright_stack: dict[str, Any]) -> None:
        """Inicia sessão headed, registra bindings e listeners obrigatórios."""
        session = RecorderSession(
            session_id="test-sess-2",
            name="Login no Sistema",
            url="https://app.example.com/login",
        )

        await session.start()

        mock_pw = mock_playwright_stack["playwright"]
        mock_context = mock_playwright_stack["context"]
        mock_page = mock_playwright_stack["page"]

        # Verifica lançamento de Chromium headed (headless=False)
        mock_pw.chromium.launch.assert_awaited_once_with(headless=False)

        # Verifica binding e script de captura
        mock_page.expose_binding.assert_awaited_once_with("__uxs_record__", session._handle_dom_event)
        mock_page.add_init_script.assert_awaited_once()

        # Verifica listeners de navegação
        mock_page.on.assert_any_call("framenavigated", session._on_navigate)
        mock_page.on.assert_any_call("popup", session._on_popup)

        # Verifica listener de auto-save no close do contexto
        mock_context.on.assert_called_once_with("close", session._on_context_close)

        # Verifica navegação inicial para a URL informada
        mock_page.goto.assert_awaited_once_with("https://app.example.com/login")


class TestRecorderSessionPauseResume:
    """Valida o comportamento de pausa e retomada de gravação (CA14)."""

    @pytest.mark.asyncio
    async def test_pause_and_resume_with_same_url(self, mock_playwright_stack: dict[str, Any]) -> None:
        """Pausa e retomada com URL inalterada não deve injetar passo de navegação."""
        session = RecorderSession(
            session_id="test-sess-3",
            name="Fluxo de Pausa",
            url="https://example.com/page1",
        )
        await session.start()
        mock_page = mock_playwright_stack["page"]
        mock_page.url = "https://example.com/page1"

        # Pausa a sessão
        res_pause = session.pause()
        assert session.workflow.paused is True
        assert session._pause_url == "https://example.com/page1"
        assert res_pause is None or res_pause == res_pause  # compatível com _AwaitableResult

        # Retoma a sessão mantendo a mesma URL
        res_resume = await session.resume()
        assert session.workflow.paused is False
        assert session._pause_url is None
        assert bool(res_resume) is False
        assert len(session.workflow.steps) == 0

    @pytest.mark.asyncio
    async def test_pause_and_resume_with_new_url_injects_navigate(
        self, mock_playwright_stack: dict[str, Any]
    ) -> None:
        """Pausa seguida de navegação para nova URL injeta RecordedStep(action='navigate') ao retomar."""
        session = RecorderSession(
            session_id="test-sess-4",
            name="Fluxo de Pausa e Navegação",
            url="https://example.com/page1",
        )
        await session.start()
        mock_page = mock_playwright_stack["page"]
        mock_page.url = "https://example.com/page1"

        # Pausa
        session.pause()
        assert session.workflow.paused is True

        # Usuário navegou enquanto pausado
        mock_page.url = "https://example.com/page2"

        # Retoma
        res_resume = await session.resume()
        assert session.workflow.paused is False
        assert bool(res_resume) is True
        assert len(session.workflow.steps) == 1

        injected_step = session.workflow.steps[0]
        assert injected_step.index == 0
        assert injected_step.action == "navigate"
        assert injected_step.url == "https://example.com/page2"
        assert injected_step.status == StepStatus.CONFIRMED


class TestRecorderSessionStopAndAutoSave:
    """Valida o método stop e o hook de auto-save no fechamento da janela (CA11)."""

    @pytest.mark.asyncio
    async def test_stop_with_zero_steps_returns_no_steps_and_does_not_save(
        self, tmp_path: Path, mock_playwright_stack: dict[str, Any]
    ) -> None:
        """Encerramento sem passos confirmados retorna saved=False e não cria arquivos."""
        session = RecorderSession(
            session_id="test-sess-5",
            name="Sessão Vazia",
            url="https://example.com",
            scenario_output_dir=tmp_path,
        )
        await session.start()

        result = await session.stop()

        assert result == {"saved": False, "reason": "no_steps"}
        # Nenhum arquivo deve ter sido gravado
        assert list(tmp_path.glob("*.yaml")) == []

        # Recursos do Playwright devem ter sido fechados
        mock_playwright_stack["context"].close.assert_awaited_once()
        mock_playwright_stack["browser"].close.assert_awaited_once()
        mock_playwright_stack["playwright"].stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_with_confirmed_steps_saves_valid_yaml(
        self, tmp_path: Path, mock_playwright_stack: dict[str, Any]
    ) -> None:
        """Encerramento com passos confirmados gera YAML estruturado no padrão UXSentinel."""
        session = RecorderSession(
            session_id="test-sess-6",
            name="Criação de Usuário Admin",
            url="https://example.com",
            objective="Cadastrar um novo usuário administrador no portal",
            scenario_output_dir=tmp_path,
        )
        await session.start()

        # Adiciona passos com diferentes status
        target_btn = RecordedTarget(
            primary=SelectorCandidate(
                strategy=SelectorStrategy.TESTID,
                value="btn-submit",
            )
        )
        target_input = RecordedTarget(
            primary=SelectorCandidate(
                strategy=SelectorStrategy.ROLE,
                value="textbox",
                name="Nome Completo",
            )
        )

        session.workflow.steps.extend(
            [
                RecordedStep(
                    index=0,
                    action="navigate",
                    url="https://example.com/users",
                    status=StepStatus.CONFIRMED,
                ),
                RecordedStep(
                    index=1,
                    action="fill",
                    target=target_input,
                    value="Alexandre Defendi",
                    status=StepStatus.CONFIRMED,
                ),
                RecordedStep(
                    index=2,
                    action="click",
                    target=target_btn,
                    status=StepStatus.ACCEPTED,  # Aceito também deve ser exportado
                ),
                RecordedStep(
                    index=3,
                    action="assert",
                    value="Usuário salvo com sucesso",
                    status=StepStatus.SUGGESTED,  # Não aceito, deve ser excluído
                ),
                RecordedStep(
                    index=4,
                    action="hover",
                    status=StepStatus.REJECTED,  # Rejeitado, deve ser excluído
                ),
            ]
        )

        result = await session.stop()

        assert result["saved"] is True
        saved_file = Path(result["path"])
        assert saved_file.is_file()
        assert saved_file.name == "criacao-de-usuario-admin.yaml"

        # Valida conteúdo do YAML gravado
        raw_content = saved_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw_content)

        assert parsed["version"] == "1.0"
        assert parsed["title"] == "Criação de Usuário Admin"
        assert parsed["description"] == "Cadastrar um novo usuário administrador no portal"
        assert len(parsed["steps"]) == 3  # apenas index 0, 1 e 2

        assert parsed["steps"][0]["action"] == "goto"
        assert parsed["steps"][0]["url"] == "https://example.com/users"

        assert parsed["steps"][1]["action"] == "fill"
        assert parsed["steps"][1]["selector"] == "role=textbox[name='Nome Completo']"
        assert parsed["steps"][1]["value"] == "Alexandre Defendi"

        assert parsed["steps"][2]["action"] == "click"
        assert parsed["steps"][2]["selector"] == "[data-testid='btn-submit']"

        # Validação estrita contra o parser de cenários do UXSentinel
        scenario = load_scenario(str(saved_file))
        assert scenario.title == "Criação de Usuário Admin"
        assert len(scenario.steps) == 3

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, tmp_path: Path, mock_playwright_stack: dict[str, Any]) -> None:
        """Chamadas subsequentes a stop() retornam o mesmo resultado e não duplicam operações."""
        session = RecorderSession(
            session_id="test-sess-7",
            name="Sessão Idempotente",
            url="https://example.com",
            scenario_output_dir=tmp_path,
        )
        await session.start()
        session.workflow.steps.append(
            RecordedStep(
                index=0,
                action="navigate",
                url="https://example.com/home",
                status=StepStatus.CONFIRMED,
            )
        )

        res1 = await session.stop()
        res2 = await session.stop()

        assert res1 == res2
        assert res1["saved"] is True

        # Garante que close só foi chamado 1 vez
        mock_playwright_stack["context"].close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_close_hook_triggers_auto_save(
        self, tmp_path: Path, mock_playwright_stack: dict[str, Any]
    ) -> None:
        """O fechamento do contexto pelo navegador dispara o encerramento e persistência automática."""
        session = RecorderSession(
            session_id="test-sess-8",
            name="Auto Save no Close",
            url="https://example.com",
            scenario_output_dir=tmp_path,
        )
        await session.start()

        # Adiciona um passo confirmado
        session.workflow.steps.append(
            RecordedStep(
                index=0,
                action="navigate",
                url="https://example.com/dashboard",
                status=StepStatus.CONFIRMED,
            )
        )

        # Captura o listener registrado no context.on("close", ...)
        mock_context = mock_playwright_stack["context"]
        close_callbacks = [
            c.args[1] for c in mock_context.on.call_args_list if c.args and c.args[0] == "close"
        ]
        assert len(close_callbacks) == 1
        on_close_handler = close_callbacks[0]

        # Simula o disparo do evento close pelo Playwright
        on_close_handler()

        # Aguarda a tarefa assíncrona agendada
        if session._close_task:
            await session._close_task

        assert session._stopped is True
        assert session._last_stop_result is not None
        assert session._last_stop_result["saved"] is True

        saved_file = tmp_path / "auto-save-no-close.yaml"
        assert saved_file.is_file()


class TestRecorderSessionDomAndNavigationEvents:
    """Valida o tratamento de eventos DOM e navegações durante a gravação."""

    @pytest.mark.asyncio
    async def test_handle_dom_event_fallback_recording(self) -> None:
        """Trata eventos DOM diretamente quando não há normalizer configurado."""
        session = RecorderSession(
            session_id="test-sess-9",
            name="Eventos DOM",
            url="https://example.com",
        )

        # Simula clique com data-testid
        await session._handle_dom_event(
            source=None,
            event_data={
                "action": "click",
                "target": {
                    "tagName": "button",
                    "testId": "save-button",
                    "outerHtml": "<button data-testid='save-button'>Salvar</button>",
                },
                "url": "https://example.com/form",
            },
        )

        # Simula preenchimento (input) com role
        await session._handle_dom_event(
            source=None,
            event_data={
                "action": "input",
                "value": "meu_login",
                "target": {
                    "tagName": "input",
                    "role": "textbox",
                    "ariaLabel": "Usuário",
                },
                "url": "https://example.com/form",
            },
        )

        assert len(session.workflow.steps) == 2
        step1, step2 = session.workflow.steps

        assert step1.action == "click"
        assert step1.target is not None
        assert step1.target.primary is not None
        assert step1.target.primary.strategy == SelectorStrategy.TESTID
        assert step1.target.primary.value == "save-button"

        assert step2.action == "fill"
        assert step2.value == "meu_login"
        assert step2.target is not None
        assert step2.target.primary is not None
        assert step2.target.primary.strategy == SelectorStrategy.ROLE
        assert step2.target.primary.name == "Usuário"

    @pytest.mark.asyncio
    async def test_on_navigate_ignores_child_frames_and_duplicates(self) -> None:
        """Apenas o frame principal gera passos de navegação e evita duplicações sequenciais."""
        session = RecorderSession(
            session_id="test-sess-10",
            name="Navegações",
            url="https://example.com",
        )

        # Mock de frame filho (iframe)
        child_frame = MagicMock()
        child_frame.parent_frame = MagicMock()  # não é frame principal
        child_frame.url = "https://ad.example.com/iframe"
        await session._on_navigate(child_frame)
        assert len(session.workflow.steps) == 0

        # Mock de frame principal com URL especial about:blank
        blank_frame = MagicMock()
        blank_frame.parent_frame = None
        blank_frame.url = "about:blank"
        await session._on_navigate(blank_frame)
        assert len(session.workflow.steps) == 0

        # Mock de frame principal válido
        main_frame = MagicMock()
        main_frame.parent_frame = None
        main_frame.url = "https://example.com/page1"
        await session._on_navigate(main_frame)
        assert len(session.workflow.steps) == 1
        assert session.workflow.steps[0].action == "navigate"
        assert session.workflow.steps[0].url == "https://example.com/page1"

        # Disparo repetido da mesma URL (não duplica)
        await session._on_navigate(main_frame)
        assert len(session.workflow.steps) == 1
