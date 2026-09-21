"""Renderização de passos executados, evidências dinâmicas, autocura, telemetria e guia de ação."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from uxsentinel.core.models import (
    ConsoleLogEntry,
    HealingEvent,
    NetworkFailureEntry,
    PagePerformanceMetrics,
    SemanticStepResult,
)
from uxsentinel.reporter.sections.visual import calc_rel_path


def render_dynamic_evidence(
    video_path: str | None,
    gif_path: str | None,
    base_dir: Path | None = None,
) -> list[str]:
    """Renderiza a Seção 2: Gravação de Sessão e Evidências Dinâmicas."""
    if not video_path and not gif_path:
        return []

    lines: list[str] = [
        "## 🎬 2. Gravação de Sessão e Evidências Dinâmicas",
        "",
    ]
    if video_path:
        rel_video = calc_rel_path(video_path, base_dir)
        lines.append(f"- 🎥 **Vídeo Completo da Sessão (HTML5/WebM):** [{rel_video}]({rel_video})")
    if gif_path:
        rel_gif = calc_rel_path(gif_path, base_dir)
        lines.append(f"- 🎞️ **Resumo Animado dos Momentos Críticos (GIF):** [{rel_gif}]({rel_gif})")
        lines.append("")
        lines.append(f"![Resumo Animado da Sessão]({rel_gif})")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def render_healed_steps(healed_steps: list[HealingEvent]) -> list[str]:
    """Renderiza a Seção 3: Registro de Auto-Cura de Seletores (Self-Healing)."""
    if not healed_steps:
        return []

    lines: list[str] = [
        "## 🩹 3. Registro de Auto-Cura de Seletores (Self-Healing)",
        "",
        (
            "> Os seletores abaixo sofreram `TimeoutError` ou falha de localização no DOM e foram recuperados "
            "automaticamente pelo UXSentinel através da **Árvore de Acessibilidade** ou por **Visão Multimodal LMM**."
        ),
        "",
        "| Passo | Ação | Seletor Original | Estratégia Adotada | Sugestão de Correção para o YAML |",
        "| :---: | :--- | :--- | :--- | :--- |",
    ]
    for h in healed_steps:
        passo_num = str(h.step_index) if h.step_index is not None else "-"
        sugestao = h.yaml_fix_suggestion or h.recovered_selector or "-"
        lines.append(
            f"| {passo_num} | `{h.action}` | `{h.original_selector}` | `{h.strategy}` | `{sugestao}` |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def render_semantic_steps(semantic_steps: list[SemanticStepResult]) -> list[str]:
    """Renderiza a Seção 4: Ações Semânticas Declarativas em Linguagem Natural."""
    if not semantic_steps:
        return []

    lines: list[str] = [
        "## 🤖 4. Ações Semânticas Declarativas em Linguagem Natural",
        "",
        (
            "> Passos semânticos interpretados em tempo de execução através do entendimento cognitivo "
            "da viewport e acessibilidade."
        ),
        "",
        "| Passo | Ação | Alvo Declarado | Status | Resolução / Justificativa |",
        "| :---: | :--- | :--- | :---: | :--- |",
    ]
    for sem in semantic_steps:
        passo_num = str(sem.step_index) if sem.step_index is not None else "-"
        st = "✅ Concluído" if sem.passed else "❌ Falhou"
        just = sem.reasoning or sem.resolved_selector or "-"
        target_str = sem.target.replace('"', '\\"')
        lines.append(f'| {passo_num} | `{sem.action}` | **"{target_str}"** | {st} | {just} |')
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def render_console_and_performance(
    console_logs: list[ConsoleLogEntry],
    network_failures: list[NetworkFailureEntry],
    performance_metrics: PagePerformanceMetrics | None,
) -> list[str]:
    """Renderiza a Seção 6: Telemetria do Console Chromium & Performance W3C."""
    if not console_logs and not network_failures and not performance_metrics:
        return []

    lines: list[str] = [
        "## 🖥️ 6. Telemetria do Console Chromium & Performance da Aplicação (W3C)",
        "",
        (
            "> Diagnósticos em tempo de execução capturados diretamente da engine Chromium, incluindo tempos reais "
            "de carregamento via W3C Navigation Timing API, requisições de rede com falha e logs emitidos pelo JavaScript."
        ),
        "",
    ]

    # Métricas de Performance W3C
    if performance_metrics:
        pm = performance_metrics
        load_eval = (
            "🟢 Rápido (<2s)"
            if pm.load_time_ms < 2000
            else "🟡 Moderado (2-4s)"
            if pm.load_time_ms < 4000
            else "🔴 Lento (>4s)"
        )
        ttfb_eval = (
            "🟢 Excelente (<200ms)"
            if pm.ttfb_ms < 200
            else "🟡 Aceitável (<500ms)"
            if pm.ttfb_ms < 500
            else "🔴 Alto (>500ms)"
        )
        lines.extend(
            [
                "### ⚡ 6.1 Métricas W3C de Tempo de Carregamento da Página",
                "",
                f"- **URL Avaliada:** `{pm.url}`",
                "",
                "| Métrica W3C | Tempo Medido | Avaliação de Experiência |",
                "| :--- | :---: | :---: |",
                f"| **Tempo Total de Carregamento (Page Load)** | **{pm.load_time_ms:.0f} ms** | {load_eval} |",
                f"| **Time to First Byte (TTFB)** | **{pm.ttfb_ms:.0f} ms** | {ttfb_eval} |",
                f"| **Processamento do DOM (DOM Interactive)** | **{pm.dom_interactive_ms:.0f} ms** | 🖥️ |",
                f"| **Resolução de Domínio (DNS Lookup)** | **{pm.dns_time_ms:.0f} ms** | 🌐 |",
                f"| **Conexão TCP / Handshake SSL** | **{pm.tcp_time_ms:.0f} ms** | 🔒 |",
                "",
            ]
        )

    # Falhas de Rede HTTP
    if network_failures:
        lines.extend(
            [
                "### 🌐 6.2 Requisições de Rede com Falha (HTTP 4xx/5xx/CORS/Aborted)",
                "",
                "| Método | Status HTTP | URL Alvo | Motivo / Diagnóstico |",
                "| :---: | :---: | :--- | :--- |",
            ]
        )
        for net in network_failures:
            st_code = f"`{net.status}`" if net.status else "`FALHA`"
            err_desc = net.error_text or "Falha de conexão ou CORS"
            lines.append(f"| `{net.method}` | {st_code} | `{net.url}` | {err_desc} |")
        lines.append("")

    # Logs e Exceções do Console
    if console_logs:
        lines.extend(
            [
                "### 📜 6.3 Logs e Mensagens do Console Chromium",
                "",
                "| Tipo | Mensagem Registrada | Localização no Código |",
                "| :---: | :--- | :--- |",
            ]
        )
        for c_log in console_logs:
            type_icon = {
                "error": "🔴 ERRO",
                "critical": "🔴 CRÍTICO",
                "warning": "🟡 AVISO",
                "warn": "🟡 AVISO",
                "info": "🔵 INFO",
            }.get(c_log.type.lower(), f"⚪ {c_log.type.upper()}")
            clean_text = " ".join(c_log.text.splitlines()).replace("|", "\\|")
            loc = f"`{c_log.location}`" if c_log.location else "-"
            lines.append(f"| {type_icon} | {clean_text} | {loc} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    return lines


def render_action_guide(scenario_id: str) -> list[str]:
    """Renderiza a Seção 7: Guia de Ação Rápida e Comandos Úteis."""
    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    return [
        "## 🛠️ 7. Guia de Ação Rápida e Comandos Úteis",
        "",
        "- **Inspecionar ao vivo com o Console/DevTools do Chromium acoplado:**",
        "  ```bash",
        f"  uxsentinel -s {scenario_id} --devtools",
        "  ```",
        "- **Gerar prompt técnico de correção para IAs (Claude, Cursor, Copilot):**",
        "  ```bash",
        f"  uxsentinel -s {scenario_id} --fix-prompt",
        "  ```",
        "- **Atualizar referências homologadas de baseline visual:**",
        "  ```bash",
        f"  uxsentinel -s {scenario_id} --update-baseline",
        "  ```",
        "- **Executar testes em modo silencioso (Headless) em CI/CD:**",
        "  ```bash",
        f"  uxsentinel -s {scenario_id} --headless",
        "  ```",
        "",
        "---",
        (
            f"*Relatório gerado automaticamente pelo **UXSentinel** em {now_str}. "
            "Compatível com o editor MarkText, Obsidian, Typora e GitHub Flavored Markdown (GFM).*"
        ),
    ]
