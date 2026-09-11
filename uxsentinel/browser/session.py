from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from uxsentinel.browser.drivers.base_driver import BaseDriver
from uxsentinel.browser.drivers.generic_driver import GenericDriver
from uxsentinel.browser.drivers.odoo_driver import OdooDriver
from uxsentinel.browser.visual_overlay import OVERLAY_INJECTION_SCRIPT
from uxsentinel.core.config import BrowserSettings


class BrowserSession:
    """Gerencia o ciclo de vida do navegador Playwright e do driver selecionado."""

    def __init__(self, settings: BrowserSettings, profile: str = "generic"):
        self.settings = settings
        self.profile = profile.lower().strip()
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.driver: BaseDriver | None = None

    async def start(self) -> BaseDriver:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.settings.headless,
            slow_mo=self.settings.slow_mo_ms,
        )

        self.context = await self.browser.new_context(
            viewport={
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            },
            ignore_https_errors=True,
        )

        self.page = await self.context.new_page()

        # Injeta os estilos e scripts de feedback visual em todas as páginas
        if self.settings.highlight_clicks:
            await self.page.add_init_script(OVERLAY_INJECTION_SCRIPT)

        # Seleciona o driver apropriado para o perfil
        if self.profile == "odoo":
            self.driver = OdooDriver(self.page, highlight_clicks=self.settings.highlight_clicks)
        else:
            self.driver = GenericDriver(self.page, highlight_clicks=self.settings.highlight_clicks)

        return self.driver

    async def close(self) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


@asynccontextmanager
async def open_browser_session(
    settings: BrowserSettings, profile: str = "generic"
) -> AsyncGenerator[BaseDriver, None]:
    session = BrowserSession(settings, profile)
    driver = await session.start()
    try:
        yield driver
    finally:
        await session.close()
