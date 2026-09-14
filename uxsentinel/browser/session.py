from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from uxsentinel.browser.drivers.base_driver import BaseDriver
from uxsentinel.browser.drivers.generic_driver import GenericDriver
from uxsentinel.browser.drivers.odoo_driver import OdooDriver
from uxsentinel.browser.telemetry import BrowserTelemetryCollector
from uxsentinel.browser.visual_overlay import OVERLAY_INJECTION_SCRIPT
from uxsentinel.core.config import BrowserSettings
from uxsentinel.core.models import ViewportConfig

if TYPE_CHECKING:
    from uxsentinel.browser.healing import SelectorHealer


class BrowserSession:
    """Gerencia o ciclo de vida do navegador Playwright e do driver selecionado."""

    def __init__(
        self,
        settings: BrowserSettings,
        profile: str = "generic",
        healer: SelectorHealer | None = None,
        headless: bool | None = None,
        record_video: bool | None = None,
        record_video_dir: str | None = None,
        initial_viewport: ViewportConfig | None = None,
        devtools: bool | None = None,
        capture_console: bool | None = None,
    ):
        updates: dict[str, object] = {}
        if headless is not None:
            updates["headless"] = headless
        if record_video is not None:
            updates["record_video"] = record_video
        if record_video_dir is not None:
            updates["record_video_dir"] = record_video_dir
        if initial_viewport is not None:
            updates["viewport_width"] = initial_viewport.width
            updates["viewport_height"] = initial_viewport.height
        if devtools is not None:
            updates["devtools"] = devtools
        if capture_console is not None:
            updates["capture_console"] = capture_console

        # O DevTools do Chromium exige modo headed (headless=False)
        if updates.get("devtools") or (settings.devtools and updates.get("devtools") is not False):
            updates["headless"] = False

        self.settings = settings.model_copy(update=updates) if updates else settings
        self.profile = profile.lower().strip()
        self.healer = healer
        self.telemetry = BrowserTelemetryCollector(capture_console=self.settings.capture_console)
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.driver: BaseDriver | None = None
        self.video_path: str | None = None

    async def start(self) -> BaseDriver:
        self.playwright = await async_playwright().start()
        launch_kwargs: dict[str, object] = {
            "headless": False if self.settings.devtools else self.settings.headless,
            "slow_mo": self.settings.slow_mo_ms,
        }
        if self.settings.devtools:
            launch_kwargs["devtools"] = True

        self.browser = await self.playwright.chromium.launch(**launch_kwargs)

        context_kwargs: dict[str, object] = {
            "viewport": {
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            },
            "ignore_https_errors": True,
        }

        if self.settings.record_video:
            v_dir = Path(self.settings.record_video_dir or "scenarios/report/videos")
            v_dir.mkdir(parents=True, exist_ok=True)
            context_kwargs["record_video_dir"] = str(v_dir)
            if self.settings.record_video_size:
                context_kwargs["record_video_size"] = self.settings.record_video_size
            else:
                context_kwargs["record_video_size"] = {
                    "width": self.settings.viewport_width,
                    "height": self.settings.viewport_height,
                }

        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await self.context.new_page()

        # Atacha o coletor de telemetria e console à página
        self.telemetry.attach(self.page)

        # Injeta os estilos e scripts de feedback visual em todas as páginas
        if self.settings.highlight_clicks:
            await self.page.add_init_script(OVERLAY_INJECTION_SCRIPT)

        # Seleciona o driver apropriado para o perfil
        if self.profile == "odoo":
            self.driver = OdooDriver(self.page, highlight_clicks=self.settings.highlight_clicks)
        else:
            self.driver = GenericDriver(self.page, highlight_clicks=self.settings.highlight_clicks)

        self.driver.session = self
        self.driver.telemetry = self.telemetry

        if self.healer:
            self.driver.healer = self.healer

        return self.driver

    async def set_viewport(self, width: int, height: int) -> None:
        """Altera a resolução da viewport da página em tempo de execução."""
        if self.page:
            await self.page.set_viewport_size({"width": width, "height": height})
        self.settings.viewport_width = width
        self.settings.viewport_height = height

    async def close(self) -> None:
        video_ref = self.page.video if self.page else None

        if self.page:
            with contextlib.suppress(Exception):
                await self.page.close()

        if self.context:
            with contextlib.suppress(Exception):
                await self.context.close()

        if video_ref:
            with contextlib.suppress(Exception):
                raw_path = await video_ref.path()
                if raw_path:
                    self.video_path = str(raw_path)
                    if self.driver:
                        self.driver.video_path = self.video_path

        if self.browser:
            with contextlib.suppress(Exception):
                await self.browser.close()

        if self.playwright:
            with contextlib.suppress(Exception):
                await self.playwright.stop()
            with contextlib.suppress(Exception):
                await asyncio.sleep(0.05)


@asynccontextmanager
async def open_browser_session(
    settings: BrowserSettings,
    profile: str = "generic",
    healer: SelectorHealer | None = None,
    headless: bool | None = None,
    record_video: bool | None = None,
    record_video_dir: str | None = None,
    initial_viewport: ViewportConfig | None = None,
    devtools: bool | None = None,
    capture_console: bool | None = None,
) -> AsyncGenerator[BaseDriver, None]:
    session = BrowserSession(
        settings,
        profile=profile,
        healer=healer,
        headless=headless,
        record_video=record_video,
        record_video_dir=record_video_dir,
        initial_viewport=initial_viewport,
        devtools=devtools,
        capture_console=capture_console,
    )
    driver = await session.start()
    try:
        yield driver
    finally:
        await session.close()
