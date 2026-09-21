"""Renderização de cabeçalho, metadata, badges e sumário executivo do relatório Markdown."""

from __future__ import annotations

from uxsentinel.core.models import TestReport


def render_header(report: TestReport) -> list[str]:
    """Renderiza o cabeçalho executivo com metadados do cenário e badges."""
    is_success = report.total_bloqueantes == 0 and report.total_altas == 0 and report.success
    status_icon = "✅" if is_success else "⚠️"
    status_text = "CONFORME (Aprovado)" if is_success else "PROBLEMAS ENCONTRADOS (Requer Atenção)"

    lines: list[str] = [
        f"# 🛡️ Relatório de Auditoria Visual & UX — {report.scenario_title}",
        "",
        "> **UXSentinel — Agente Universal de Visual QA, Usabilidade e Acessibilidade**",
        f"> **Status Geral:** {status_icon} **{status_text}**  ",
        (
            f"> **Data/Hora:** {report.started_at.strftime('%d/%m/%Y às %H:%M:%S')} | "
            f"**Duração:** {report.duration_seconds:.1f}s | "
            f"**Perfil:** `{report.profile}` | "
            f"**Provedor IA:** `{report.provider_used}`"
        ),
    ]

    if report.viewports_tested:
        vps = ", ".join(f"`{vp}`" for vp in report.viewports_tested)
        lines.append(f"> **Resoluções Testadas:** {vps}")

    lines.append(f"> **Identificador do Cenário:** `{report.scenario_id}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def render_executive_summary(report: TestReport) -> list[str]:
    """Renderiza a Seção 1: Resumo Executivo e Indicadores de Qualidade."""
    is_success = report.total_bloqueantes == 0 and report.total_altas == 0 and report.success
    status_icon = "✅" if is_success else "⚠️"
    report_status_str = "APROVADO" if is_success else "REPROVADO"

    total_checkpoints = len(report.checkpoints)
    checkpoints_ok = sum(1 for cp in report.checkpoints if cp.status == "ok")
    checkpoints_issues = sum(1 for cp in report.checkpoints if cp.status != "ok")
    a11y_display = f"{report.a11y_score:.1f}%" if report.a11y_score is not None else "100.0%"

    lines: list[str] = [
        "## 📊 1. Resumo Executivo e Indicadores de Qualidade",
        "",
        "| Indicador de Qualidade | Resultado | Avaliação |",
        "| :--- | :---: | :---: |",
        f"| **Status Consolidado do Cenário** | `{report_status_str}` | {status_icon} |",
        f"| **Total de Checkpoints Analisados** | **{total_checkpoints}** | 📍 |",
        f"| **Checkpoints Conformes** | **{checkpoints_ok}** | ✅ |",
        f"| **Checkpoints com Apontamentos** | **{checkpoints_issues}** | ⚠️ |",
        f"| **A11y Score Médio (WCAG 2.2 AA)** | **{a11y_display}** | ♿ |",
        (
            f"| **Inconformidades Bloqueantes** | **{report.total_bloqueantes}** | "
            f"{'🔴' if report.total_bloqueantes > 0 else '🟢'} |"
        ),
        (
            f"| **Inconformidades de Severidade Alta** | **{report.total_altas}** | "
            f"{'🟠' if report.total_altas > 0 else '🟢'} |"
        ),
        f"| **Inconformidades de Severidade Média** | **{report.total_medias}** | 🟡 |",
        f"| **Inconformidades de Severidade Baixa** | **{report.total_baixas}** | 🔵 |",
        f"| **Seletores Auto-Curados (Self-Healing)** | **{len(report.healed_steps)}** | 🩹 |",
        f"| **Ações Semânticas em Linguagem Natural** | **{len(report.semantic_steps)}** | 🤖 |",
    ]

    if report.total_console_errors > 0 or report.total_console_warnings > 0:
        err_icon = "🔴" if report.total_console_errors > 0 else "🟢"
        lines.append(
            f"| **Erros de Console Chromium (JS)** | **{report.total_console_errors}** | {err_icon} |"
        )
        lines.append(f"| **Avisos de Console Chromium (JS)** | **{report.total_console_warnings}** | 🟡 |")

    if report.network_failures:
        lines.append(f"| **Falhas de Rede (HTTP 4xx/5xx/CORS)** | **{len(report.network_failures)}** | 🔴 |")

    if report.performance_metrics and report.performance_metrics.load_time_ms > 0:
        lines.append(
            f"| **Tempo de Carregamento Web (W3C)** | "
            f"**{report.performance_metrics.load_time_ms:.0f}ms** "
            f"(TTFB: {report.performance_metrics.ttfb_ms:.0f}ms) | ⚡ |"
        )

    lines.append("")
    return lines
