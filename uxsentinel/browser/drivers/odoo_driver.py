import contextlib

from uxsentinel.browser.drivers.base_driver import BaseDriver


class OdooDriver(BaseDriver):
    """Driver especializado para aplicações Odoo (v16, v17, v18, v19 e OWL Framework)."""

    ODOO_LOADING_SELECTOR = ".o_loading"
    ODOO_MODAL_SELECTORS = [
        ".o_dialog",
        ".modal.o_technical_modal",
        ".modal-dialog",
        ".o_act_window",
    ]
    ODOO_ERROR_SELECTORS = [
        ".o_error_dialog",
        ".o_notification.border-danger",
        ".o_notification.bg-danger",
    ]

    async def wait_until_ready(self, timeout: int = 15000) -> None:
        """Aguarda o indicador de carregamento do Odoo (.o_loading) desaparecer e o OWL assentar."""
        with contextlib.suppress(Exception):
            await self.page.wait_for_selector(
                self.ODOO_LOADING_SELECTOR,
                state="detached",
                timeout=timeout,
            )

        # Pequena pausa para os componentes OWL reativos estabilizarem a renderização
        await self.page.wait_for_timeout(350)

    async def wait_for_modal(self, timeout: int = 10000) -> bool:
        """Aguarda a renderização de diálogos do Odoo (assistentes, wizards, popups)."""
        combined = ", ".join(self.ODOO_MODAL_SELECTORS)
        try:
            await self.page.wait_for_selector(combined, state="visible", timeout=timeout)
            await self.wait_until_ready()
            return True
        except Exception:
            return False

    async def wait_modal_close(self, timeout: int = 10000) -> bool:
        combined = ", ".join(self.ODOO_MODAL_SELECTORS)
        try:
            await self.page.wait_for_selector(combined, state="hidden", timeout=timeout)
            # Confirma que o backdrop do modal foi removido
            await self.page.wait_for_selector(".modal-backdrop", state="detached", timeout=3000)
            await self.wait_until_ready()
            return True
        except Exception:
            return False

    async def check_unhandled_odoo_errors(self) -> list[str]:
        """Verifica se há janelas de erro ou notificações de falha do Odoo ativas."""
        errors: list[str] = []
        for sel in self.ODOO_ERROR_SELECTORS:
            loc = self.page.locator(sel)
            count = await loc.count()
            for i in range(count):
                if await loc.nth(i).is_visible():
                    text = await loc.nth(i).inner_text()
                    errors.append(text.strip())
        return errors
