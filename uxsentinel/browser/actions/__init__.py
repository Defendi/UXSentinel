from __future__ import annotations

from typing import TYPE_CHECKING

from uxsentinel.browser.actions.ai import (
    AiActionHandler,
    AiAssertActionHandler,
    AiClickActionHandler,
    AiFillActionHandler,
)
from uxsentinel.browser.actions.assertions import (
    AssertInvalidActionHandler,
    AssertOptionsActionHandler,
    AssertReadonlyActionHandler,
    AssertRequiredActionHandler,
)
from uxsentinel.browser.actions.checkpoint import CheckpointActionHandler
from uxsentinel.browser.actions.context import ActionContext, BaseActionHandler
from uxsentinel.browser.actions.forms import (
    ClearActionHandler,
    ClickActionHandler,
    FillActionHandler,
    SelectActionHandler,
    TypeActionHandler,
    UploadFileActionHandler,
)
from uxsentinel.browser.actions.navigation import (
    DragAndDropActionHandler,
    GotoActionHandler,
    HoverActionHandler,
    KeyboardActionHandler,
    PauseActionHandler,
    ScrollActionHandler,
    SetViewportActionHandler,
    WaitModalActionHandler,
    WaitModalCloseActionHandler,
    WaitUntilReadyActionHandler,
)

if TYPE_CHECKING:
    pass


class ActionRegistry:
    """Registro central e gerenciador de handlers de ações semânticas."""

    def __init__(self) -> None:
        self._handlers: dict[str, BaseActionHandler] = {}
        self._register_defaults()

    def register(self, action_name: str | list[str], handler: BaseActionHandler) -> None:
        """Registra um handler para uma ou mais ações."""
        if isinstance(action_name, str):
            self._handlers[action_name.lower().strip()] = handler
        else:
            for name in action_name:
                self._handlers[name.lower().strip()] = handler

    def get(self, action_name: str) -> BaseActionHandler | None:
        """Obtém o handler correspondente à ação informada."""
        return self._handlers.get(action_name.lower().strip())

    async def execute(self, ctx: ActionContext) -> None:
        """Localiza e executa o handler para o passo contido no contexto."""
        action = ctx.step.action.lower().strip()
        handler = self.get(action)
        if not handler:
            raise ValueError(f"Ação desconhecida: '{ctx.step.action}'")
        await handler.execute(ctx)

    def _register_defaults(self) -> None:
        """Registra os handlers padrão do UXSentinel."""
        # Navegação e Esperas
        goto_handler = GotoActionHandler()
        self.register("goto", goto_handler)

        set_viewport_handler = SetViewportActionHandler()
        self.register("set_viewport", set_viewport_handler)

        scroll_handler = ScrollActionHandler()
        self.register("scroll", scroll_handler)

        hover_handler = HoverActionHandler()
        self.register("hover", hover_handler)

        drag_handler = DragAndDropActionHandler()
        self.register(["drag_and_drop", "drag_drop", "arrastar"], drag_handler)

        keyboard_handler = KeyboardActionHandler()
        self.register(["press", "keyboard", "teclar"], keyboard_handler)

        wait_ready_handler = WaitUntilReadyActionHandler()
        self.register(["wait_until_ready", "wait_odoo_ready", "wait_navigation"], wait_ready_handler)

        wait_modal_handler = WaitModalActionHandler()
        self.register(["wait_modal", "wait_for_modal"], wait_modal_handler)

        wait_modal_close_handler = WaitModalCloseActionHandler()
        self.register("wait_modal_close", wait_modal_close_handler)

        pause_handler = PauseActionHandler()
        self.register(["pause", "sleep", "aguardar"], pause_handler)

        # Formulários
        click_handler = ClickActionHandler()
        self.register(["click", "clicar"], click_handler)

        fill_handler = FillActionHandler()
        self.register(["fill", "preencher"], fill_handler)

        type_handler = TypeActionHandler()
        self.register(["type", "digitar"], type_handler)

        clear_handler = ClearActionHandler()
        self.register(["clear", "limpar"], clear_handler)

        select_handler = SelectActionHandler()
        self.register(["select", "dropdown", "choose", "selecionar"], select_handler)

        upload_handler = UploadFileActionHandler()
        self.register(["upload_file", "upload", "anexar_arquivo"], upload_handler)

        # Asserções
        assert_required_handler = AssertRequiredActionHandler()
        self.register(["assert_required", "check_required", "validar_obrigatorio"], assert_required_handler)

        assert_invalid_handler = AssertInvalidActionHandler()
        self.register(
            ["assert_invalid", "check_invalid", "validar_erro", "validar_invalido"], assert_invalid_handler
        )

        assert_readonly_handler = AssertReadonlyActionHandler()
        self.register(
            ["assert_readonly", "check_readonly", "validar_somente_leitura"], assert_readonly_handler
        )

        assert_options_handler = AssertOptionsActionHandler()
        self.register(["assert_options", "check_options", "validar_opcoes"], assert_options_handler)

        # Ações de Inteligência Artificial Multimodal
        self.register("ai_click", AiClickActionHandler())
        self.register("ai_fill", AiFillActionHandler())
        self.register("ai_assert", AiAssertActionHandler())
        self.register("ai_action", AiActionHandler())

        # Checkpoints visuais
        self.register("checkpoint", CheckpointActionHandler())


default_action_registry = ActionRegistry()

__all__ = [
    "ActionContext",
    "ActionRegistry",
    "BaseActionHandler",
    "default_action_registry",
]
