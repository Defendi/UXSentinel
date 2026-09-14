"""Módulo de Telemetria e Diagnósticos de Console do Chromium e Performance Web."""

from __future__ import annotations

import contextlib
import inspect
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from playwright.async_api import ConsoleMessage, Page, Request
    from playwright.async_api import Error as PlaywrightError


class ConsoleLogEntry(BaseModel):
    """Entrada de log de console capturada do navegador."""

    type: str = "log"  # error, warning, info, log, debug, etc.
    text: str
    timestamp: datetime = Field(default_factory=datetime.now)
    location: str | None = None
    args: list[str] = Field(default_factory=list)


class NetworkFailureEntry(BaseModel):
    """Falha em requisição de rede interceptada (4xx, 5xx, CORS, conexão)."""

    url: str
    method: str = "GET"
    status: int | None = None
    error_text: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class PagePerformanceMetrics(BaseModel):
    """Métricas de performance e tempo de carregamento da página (W3C Navigation Timing)."""

    url: str
    ttfb_ms: float = 0.0  # Time to First Byte (tempo até o primeiro byte)
    dom_interactive_ms: float = 0.0  # Tempo até o DOM ficar interativo
    load_time_ms: float = 0.0  # Tempo total de carregamento da página
    dns_time_ms: float = 0.0  # Resolução de DNS
    tcp_time_ms: float = 0.0  # Handshake TCP / SSL
    timestamp: datetime = Field(default_factory=datetime.now)


class BrowserTelemetryCollector:
    """Coletor assíncrono de eventos de console, requisições com erro e tempos de carregamento."""

    def __init__(self, capture_console: bool = True) -> None:
        self.capture_console = capture_console
        self.console_logs: list[ConsoleLogEntry] = []
        self.network_failures: list[NetworkFailureEntry] = []
        self.performance_history: list[PagePerformanceMetrics] = []
        self._page: Page | None = None

    def attach(self, page: Page) -> None:
        """Conecta os listeners de telemetria à página do Playwright."""
        self._page = page
        if not self.capture_console or not hasattr(page, "on"):
            return

        with contextlib.suppress(Exception):
            res1 = page.on("console", self._handle_console)
            if inspect.iscoroutine(res1):
                res1.close()
            res2 = page.on("pageerror", self._handle_page_error)
            if inspect.iscoroutine(res2):
                res2.close()
            res3 = page.on("requestfailed", self._handle_request_failed)
            if inspect.iscoroutine(res3):
                res3.close()

    def _handle_console(self, msg: ConsoleMessage) -> None:
        """Processa mensagens de console emitidas pela aplicação web."""
        try:
            loc = msg.location
            loc_str = f"{loc.get('url', '')}:{loc.get('lineNumber', '')}" if loc else None
            entry = ConsoleLogEntry(
                type=msg.type.lower(),
                text=msg.text,
                location=loc_str,
            )
            self.console_logs.append(entry)
        except Exception:
            pass

    def _handle_page_error(self, exc: PlaywrightError | Exception) -> None:
        """Processa exceções de JavaScript não tratadas na página (window.onerror)."""
        try:
            entry = ConsoleLogEntry(
                type="error",
                text=f"Exceção Não Tratada: {exc}",
            )
            self.console_logs.append(entry)
        except Exception:
            pass

    def _handle_request_failed(self, request: Request) -> None:
        """Processa requisições de rede com falha de conexão ou abortadas."""
        try:
            failure = request.failure
            err_msg = failure if isinstance(failure, str) else (failure.get("errorText") if failure else None)
            response = request.response()
            status_code = response.status if response else None

            entry = NetworkFailureEntry(
                url=request.url,
                method=request.method,
                status=status_code,
                error_text=err_msg or "Falha de conexão / abortada",
            )
            self.network_failures.append(entry)
        except Exception:
            pass

    async def capture_performance_metrics(self, page: Page | None = None) -> PagePerformanceMetrics | None:
        """Extrai métricas reais de tempo de carregamento via W3C Navigation Timing API."""
        p = page or self._page
        if not p:
            return None

        script = """
        () => {
            const nav = performance.getEntriesByType('navigation')[0];
            if (!nav) return null;
            return {
                url: window.location.href,
                ttfb_ms: Math.max(0, nav.responseStart - nav.requestStart),
                dom_interactive_ms: Math.max(0, nav.domInteractive - nav.startTime),
                load_time_ms: Math.max(0, nav.loadEventEnd > 0 ? (nav.loadEventEnd - nav.startTime) : (nav.domContentLoadedEventEnd - nav.startTime)),
                dns_time_ms: Math.max(0, nav.domainLookupEnd - nav.domainLookupStart),
                tcp_time_ms: Math.max(0, nav.connectEnd - nav.connectStart)
            };
        }
        """
        with contextlib.suppress(Exception):
            data: dict[str, Any] | None = await p.evaluate(script)
            if data and isinstance(data, dict):
                metrics = PagePerformanceMetrics(
                    url=str(data.get("url") or p.url),
                    ttfb_ms=round(float(data.get("ttfb_ms", 0.0)), 1),
                    dom_interactive_ms=round(float(data.get("dom_interactive_ms", 0.0)), 1),
                    load_time_ms=round(float(data.get("load_time_ms", 0.0)), 1),
                    dns_time_ms=round(float(data.get("dns_time_ms", 0.0)), 1),
                    tcp_time_ms=round(float(data.get("tcp_time_ms", 0.0)), 1),
                )
                self.performance_history.append(metrics)
                return metrics
        return None

    def get_errors(self) -> list[ConsoleLogEntry]:
        """Retorna apenas logs classificados como erro."""
        return [log for log in self.console_logs if log.type in ("error", "critical")]

    def get_warnings(self) -> list[ConsoleLogEntry]:
        """Retorna apenas logs classificados como aviso / warning."""
        return [log for log in self.console_logs if log.type in ("warn", "warning")]

    def clear(self) -> None:
        """Limpa as coletas registradas."""
        self.console_logs.clear()
        self.network_failures.clear()
        self.performance_history.clear()
