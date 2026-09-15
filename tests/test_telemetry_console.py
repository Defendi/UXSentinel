"""Testes unitários herméticos para o módulo de Telemetria e Diagnósticos do Console Chromium."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from uxsentinel.browser.telemetry import (
    BrowserTelemetryCollector,
    ConsoleLogEntry,
    NetworkFailureEntry,
    PagePerformanceMetrics,
)
from uxsentinel.core.config import resolve_devtools_mode
from uxsentinel.core.models import (
    TestReport,
)
from uxsentinel.reporter.html_builder import build_html_report
from uxsentinel.reporter.markdown_builder import build_markdown_report


@pytest.fixture
def mock_page():
    page = MagicMock()
    page.url = "http://localhost:8069/web"
    page.on = MagicMock()
    page.evaluate = AsyncMock()
    return page


def test_console_log_models():
    """Valida a criação e tipagem dos modelos de telemetria."""
    log_entry = ConsoleLogEntry(
        type="error",
        text="Uncaught TypeError: Cannot read property of undefined",
        location="http://localhost:8069/web/static/src/core.js:42",
    )
    assert log_entry.type == "error"
    assert "Uncaught TypeError" in log_entry.text
    assert log_entry.location is not None

    net_entry = NetworkFailureEntry(
        url="http://localhost:8069/api/v1/chat/messages",
        method="POST",
        status=500,
        error_text="Internal Server Error",
    )
    assert net_entry.status == 500
    assert net_entry.method == "POST"

    perf_entry = PagePerformanceMetrics(
        url="http://localhost:8069/web",
        ttfb_ms=120.5,
        dom_interactive_ms=350.2,
        load_time_ms=850.0,
        dns_time_ms=15.0,
        tcp_time_ms=25.0,
    )
    assert perf_entry.ttfb_ms == 120.5
    assert perf_entry.load_time_ms == 850.0


def test_browser_telemetry_collector_attach(mock_page):
    """Verifica se os listeners de eventos do Playwright são devidamente conectados."""
    collector = BrowserTelemetryCollector(capture_console=True)
    collector.attach(mock_page)

    assert mock_page.on.call_count == 3
    event_names = [call[0][0] for call in mock_page.on.call_args_list]
    assert "console" in event_names
    assert "pageerror" in event_names
    assert "requestfailed" in event_names


def test_browser_telemetry_collector_disabled(mock_page):
    """Verifica que nenhum listener é anexado se capture_console estiver desativado."""
    collector = BrowserTelemetryCollector(capture_console=False)
    collector.attach(mock_page)
    assert mock_page.on.call_count == 0


def test_browser_telemetry_collector_events():
    """Verifica o processamento de mensagens de console, erros de página e falhas de rede."""
    collector = BrowserTelemetryCollector()

    # 1. Mensagem de console comum e erro
    msg_info = MagicMock()
    msg_info.type = "info"
    msg_info.text = "Iniciando aplicação OWL"
    msg_info.location = {"url": "app.js", "lineNumber": 10}
    collector._handle_console(msg_info)

    msg_err = MagicMock()
    msg_err.type = "error"
    msg_err.text = "Falha ao renderizar componente"
    msg_err.location = {"url": "app.js", "lineNumber": 50}
    collector._handle_console(msg_err)

    # 2. Exceção não tratada na página (pageerror)
    collector._handle_page_error(RuntimeError("Falha de script externa"))

    # 3. Requisição de rede com falha
    req_mock = MagicMock()
    req_mock.url = "http://localhost:8069/api/fail"
    req_mock.method = "GET"
    req_mock.failure = {"errorText": "net::ERR_CONNECTION_REFUSED"}
    req_mock.response.return_value = None
    collector._handle_request_failed(req_mock)

    assert len(collector.console_logs) == 3
    assert len(collector.get_errors()) == 2
    assert len(collector.network_failures) == 1
    assert collector.network_failures[0].error_text == "net::ERR_CONNECTION_REFUSED"

    collector.clear()
    assert len(collector.console_logs) == 0
    assert len(collector.network_failures) == 0


@pytest.mark.asyncio
async def test_browser_telemetry_capture_performance(mock_page):
    """Valida a extração de métricas de navegação W3C via JavaScript assíncrono."""
    mock_page.evaluate.return_value = {
        "url": "http://localhost:8069/web",
        "ttfb_ms": 115.4,
        "dom_interactive_ms": 420.0,
        "load_time_ms": 950.0,
        "dns_time_ms": 10.2,
        "tcp_time_ms": 20.1,
    }

    collector = BrowserTelemetryCollector()
    collector.attach(mock_page)

    metrics = await collector.capture_performance_metrics()
    assert metrics is not None
    assert metrics.ttfb_ms == 115.4
    assert metrics.load_time_ms == 950.0
    assert len(collector.performance_history) == 1


def test_resolve_devtools_mode_hierarchy():
    """Valida a hierarquia estrita de precedência para ativação do DevTools."""
    # 1. CLI flag tem prioridade máxima
    assert (
        resolve_devtools_mode(
            cli_devtools=True,
            scenario_devtools=False,
            config_devtools=False,
        )
        is True
    )
    assert (
        resolve_devtools_mode(
            cli_devtools=False,
            scenario_devtools=True,
            config_devtools=True,
        )
        is False
    )

    # 2. Cenário YAML sobrepõe o config global
    assert (
        resolve_devtools_mode(
            cli_devtools=None,
            scenario_devtools=True,
            config_devtools=False,
        )
        is True
    )
    assert (
        resolve_devtools_mode(
            cli_devtools=None,
            scenario_devtools=False,
            config_devtools=True,
        )
        is False
    )

    # 3. Config global quando CLI e YAML forem None
    assert (
        resolve_devtools_mode(
            cli_devtools=None,
            scenario_devtools=None,
            config_devtools=True,
        )
        is True
    )

    # 4. Fallback padrão é False
    assert (
        resolve_devtools_mode(
            cli_devtools=None,
            scenario_devtools=None,
            config_devtools=None,
        )
        is False
    )


def test_test_report_compute_totals_with_console_logs():
    """Valida o cálculo de totais de erros e warnings de console no TestReport."""
    report = TestReport(
        scenario_id="sc_test_console",
        scenario_title="Teste de Console",
        started_at=datetime.now(),
        console_logs=[
            ConsoleLogEntry(type="error", text="Erro 1"),
            ConsoleLogEntry(type="critical", text="Erro Crítico 2"),
            ConsoleLogEntry(type="warning", text="Aviso 1"),
            ConsoleLogEntry(type="warn", text="Aviso 2"),
            ConsoleLogEntry(type="info", text="Informação"),
            ConsoleLogEntry(type="log", text="Log genérico"),
        ],
    )
    report.compute_totals()

    assert report.total_console_errors == 2
    assert report.total_console_warnings == 2


def test_markdown_report_includes_telemetry():
    """Verifica se o relatório MarkText Markdown inclui a seção 6 de telemetria e diagnósticos."""
    report = TestReport(
        scenario_id="sc_telemetry_md",
        scenario_title="Cenário de Telemetria",
        started_at=datetime.now(),
        console_logs=[
            ConsoleLogEntry(type="error", text="Exceção no módulo JS", location="app.js:25"),
            ConsoleLogEntry(type="warning", text="Recurso descontinuado na API"),
        ],
        network_failures=[
            NetworkFailureEntry(
                url="http://localhost:8069/api/fail", method="POST", status=502, error_text="Bad Gateway"
            ),
        ],
        performance_metrics=PagePerformanceMetrics(
            url="http://localhost:8069/web",
            ttfb_ms=150.0,
            dom_interactive_ms=300.0,
            load_time_ms=800.0,
        ),
    )
    report.compute_totals()

    md_output = build_markdown_report(report)

    assert "6. Telemetria do Console Chromium & Performance da Aplicação (W3C)" in md_output
    assert "Métricas W3C de Tempo de Carregamento da Página" in md_output
    assert "800 ms" in md_output
    assert "150 ms" in md_output
    assert "Requisições de Rede com Falha" in md_output
    assert "Bad Gateway" in md_output
    assert "Logs e Mensagens do Console Chromium" in md_output
    assert "Exceção no módulo JS" in md_output
    assert "Erros de Console Chromium (JS)" in md_output


def test_html_report_includes_telemetry():
    """Verifica se o dashboard HTML inclui cards e tabela de diagnósticos do Chromium."""
    report = TestReport(
        scenario_id="sc_telemetry_html",
        scenario_title="Cenário HTML Telemetria",
        started_at=datetime.now(),
        console_logs=[
            ConsoleLogEntry(type="error", text="Falha crítica de script"),
        ],
        network_failures=[
            NetworkFailureEntry(
                url="http://localhost:8069/api/test", method="GET", status=404, error_text="Not Found"
            ),
        ],
        performance_metrics=PagePerformanceMetrics(
            url="http://localhost:8069/test",
            ttfb_ms=90.0,
            dom_interactive_ms=250.0,
            load_time_ms=750.0,
        ),
    )
    report.compute_totals()

    html_output = build_html_report(report)

    assert "Diagnósticos da Aplicação: Console Chromium & Performance (W3C)" in html_output
    assert "Métricas de Navegação e Carregamento" in html_output
    assert "750 ms" in html_output
    assert "90 ms" in html_output
    assert "Requisições de Rede com Falha (HTTP)" in html_output
    assert "Not Found" in html_output
    assert "Mensagens e Logs Capturados do Console (Chromium DevTools)" in html_output
    assert "Falha crítica de script" in html_output
    assert "Erros Console (JS)" in html_output


@pytest.mark.asyncio
async def test_browser_session_devtools_args(monkeypatch):
    """Garante que a flag --auto-open-devtools-for-tabs é passada via args para o Chromium."""
    from uxsentinel.browser.session import BrowserSession
    from uxsentinel.core.config import BrowserSettings

    mock_playwright = MagicMock()
    mock_chromium = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_playwright.chromium = mock_chromium
    mock_playwright.stop = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()
    mock_page.add_init_script = AsyncMock()
    mock_page.close = AsyncMock()
    mock_page.video = None

    mock_async_playwright = MagicMock()
    mock_async_playwright.start = AsyncMock(return_value=mock_playwright)

    monkeypatch.setattr("uxsentinel.browser.session.async_playwright", lambda: mock_async_playwright)

    settings = BrowserSettings(devtools=True, headless=True)
    session = BrowserSession(settings=settings, devtools=True)

    driver = await session.start()
    assert driver is not None

    mock_chromium.launch.assert_called_once()
    kwargs = mock_chromium.launch.call_args[1]
    assert kwargs.get("headless") is False
    assert "--auto-open-devtools-for-tabs" in kwargs.get("args", [])
    assert "devtools" not in kwargs

    await session.close()
