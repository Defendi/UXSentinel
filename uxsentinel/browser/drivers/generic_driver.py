import contextlib

from uxsentinel.browser.drivers.base_driver import BaseDriver


class GenericDriver(BaseDriver):
    """Driver para aplicações web universais (HTML5, React, Vue, Bootstrap, etc.)."""

    MODAL_SELECTORS = [
        "dialog[open]",
        ".modal.show",
        "[role='dialog'][aria-modal='true']",
        "[role='dialog']",
        ".modal-dialog",
    ]

    async def wait_until_ready(self, timeout: int = 10000) -> None:
        with contextlib.suppress(Exception):
            await self.page.wait_for_load_state("networkidle", timeout=min(timeout, 3000))
        # Pequeno delay para transições e CSS renders
        await self.page.wait_for_timeout(250)

    async def wait_for_modal(self, timeout: int = 10000) -> bool:
        combined_selector = ", ".join(self.MODAL_SELECTORS)
        try:
            await self.page.wait_for_selector(combined_selector, state="visible", timeout=timeout)
            await self.page.wait_for_timeout(300)  # aguarda animação de fade/slide terminar
            return True
        except Exception:
            return False

    async def wait_modal_close(self, timeout: int = 10000) -> bool:
        combined_selector = ", ".join(self.MODAL_SELECTORS)
        try:
            await self.page.wait_for_selector(combined_selector, state="hidden", timeout=timeout)
            await self.page.wait_for_timeout(250)
            return True
        except Exception:
            return False
