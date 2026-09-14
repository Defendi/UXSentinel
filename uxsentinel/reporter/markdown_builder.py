"""Gerador de Relatórios de Auditoria em formato Markdown compatível com MarkText, Obsidian e GitHub."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from uxsentinel.core.models import (
    IssueSeverity,
    TestReport,
)

SEVERITY_ICONS = {
    IssueSeverity.BLOQUEANTE: "🔴",
    IssueSeverity.ALTA: "🟠",
    IssueSeverity.MEDIA: "🟡",
    IssueSeverity.BAIXA: "🔵",
    "bloqueante": "🔴",
    "critical": "🔴",
    "alta": "🟠",
    "major": "🟠",
    "media": "🟡",
    "baixa": "🔵",
}

SEVERITY_LABELS = {
    IssueSeverity.BLOQUEANTE: "BLOQUEANTE (Crítico)",
    IssueSeverity.ALTA: "ALTA (Grave)",
    IssueSeverity.MEDIA: "MÉDIA (Moderada)",
    IssueSeverity.BAIXA: "BAIXA (Cosmética)",
    "bloqueante": "BLOQUEANTE (Crítico)",
    "critical": "BLOQUEANTE (Crítico)",
    "alta": "ALTA (Grave)",
    "major": "ALTA (Grave)",
    "media": "MÉDIA (Moderada)",
    "baixa": "BAIXA (Cosmética)",
}


def _get_severity_icon(sev: IssueSeverity | str) -> str:
    key = getattr(sev, "value", str(sev)).lower()
    return SEVERITY_ICONS.get(key, SEVERITY_ICONS.get(sev, "⚠️"))


def _get_severity_label(sev: IssueSeverity | str) -> str:
    key = getattr(sev, "value", str(sev)).lower()
    return SEVERITY_LABELS.get(key, SEVERITY_LABELS.get(sev, str(key).upper()))


def _calc_rel_path(path_str: str | None, base_dir: Path | None) -> str:
    """Calcula caminho relativo seguro a partir do diretório base do relatório."""
    if not path_str:
        return ""
    if base_dir:
        try:
            return str(Path(path_str).resolve().relative_to(base_dir.resolve()))
        except Exception:
            try:
                return str(Path(path_str).relative_to(base_dir))
            except Exception:
                pass
    return str(path_str)


def build_markdown_report(report: TestReport, output_dir: str | Path | None = None) -> str:
    """Constrói um relatório de auditoria completo em Markdown formatado para o editor MarkText.

    Utiliza tabelas CommonMark/GFM alinhadas, badges visuais, links relativos de imagens
    para renderização direta no MarkText e detalhamento minucioso de acessibilidade e heurísticas.
    """
    base_dir = Path(output_dir) if output_dir else None

    # Status geral
    is_success = report.total_bloqueantes == 0 and report.total_altas == 0 and report.success
    status_icon = "✅" if is_success else "⚠️"
    status_text = "CONFORME (Aprovado)" if is_success else "PROBLEMAS ENCONTRADOS (Requer Atenção)"

    lines: list[str] = []

    # Cabeçalho Executivo
    lines.append(f"# 🛡️ Relatório de Auditoria Visual & UX — {report.scenario_title}")
    lines.append("")
    lines.append("> **UXSentinel — Agente Universal de Visual QA, Usabilidade e Acessibilidade**")
    lines.append(f"> **Status Geral:** {status_icon} **{status_text}**  ")
    lines.append(
        f"> **Data/Hora:** {report.started_at.strftime('%d/%m/%Y às %H:%M:%S')} | "
        f"**Duração:** {report.duration_seconds:.1f}s | "
        f"**Perfil:** `{report.profile}` | "
        f"**Provedor IA:** `{report.provider_used}`"
    )
    if report.viewports_tested:
        vps = ", ".join(f"`{vp}`" for vp in report.viewports_tested)
        lines.append(f"> **Resoluções Testadas:** {vps}")
    lines.append(f"> **Identificador do Cenário:** `{report.scenario_id}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Resumo Executivo e Métricas
    lines.append("## 📊 1. Resumo Executivo e Indicadores de Qualidade")
    lines.append("")
    lines.append("| Indicador de Qualidade | Resultado | Avaliação |")
    lines.append("| :--- | :---: | :---: |")

    total_checkpoints = len(report.checkpoints)
    checkpoints_ok = sum(1 for cp in report.checkpoints if cp.status == "ok")
    checkpoints_issues = sum(1 for cp in report.checkpoints if cp.status != "ok")
    report_status_str = "APROVADO" if is_success else "REPROVADO"
    lines.append(f"| **Status Consolidado do Cenário** | `{report_status_str}` | {status_icon} |")
    lines.append(f"| **Total de Checkpoints Analisados** | **{total_checkpoints}** | 📍 |")
    lines.append(f"| **Checkpoints Conformes** | **{checkpoints_ok}** | ✅ |")
    lines.append(f"| **Checkpoints com Apontamentos** | **{checkpoints_issues}** | ⚠️ |")

    a11y_display = f"{report.a11y_score:.1f}%" if report.a11y_score is not None else "100.0%"
    lines.append(f"| **A11y Score Médio (WCAG 2.2 AA)** | **{a11y_display}** | ♿ |")

    lines.append(
        f"| **Inconformidades Bloqueantes** | **{report.total_bloqueantes}** | "
        f"{'🔴' if report.total_bloqueantes > 0 else '🟢'} |"
    )
    lines.append(
        f"| **Inconformidades de Severidade Alta** | **{report.total_altas}** | "
        f"{'🟠' if report.total_altas > 0 else '🟢'} |"
    )
    lines.append(f"| **Inconformidades de Severidade Média** | **{report.total_medias}** | 🟡 |")
    lines.append(f"| **Inconformidades de Severidade Baixa** | **{report.total_baixas}** | 🔵 |")

    healed_count = len(report.healed_steps)
    lines.append(f"| **Seletores Auto-Curados (Self-Healing)** | **{healed_count}** | 🩹 |")

    semantic_count = len(report.semantic_steps)
    lines.append(f"| **Ações Semânticas em Linguagem Natural** | **{semantic_count}** | 🤖 |")

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
            f"| **Tempo de Carregamento Web (W3C)** | **{report.performance_metrics.load_time_ms:.0f}ms** (TTFB: {report.performance_metrics.ttfb_ms:.0f}ms) | ⚡ |"
        )
    lines.append("")

    # 2. Gravação de Sessão e Evidências Dinâmicas
    if report.video_path or report.gif_path:
        lines.append("## 🎬 2. Gravação de Sessão e Evidências Dinâmicas")
        lines.append("")
        if report.video_path:
            rel_video = _calc_rel_path(report.video_path, base_dir)
            lines.append(f"- 🎥 **Vídeo Completo da Sessão (HTML5/WebM):** [{rel_video}]({rel_video})")
        if report.gif_path:
            rel_gif = _calc_rel_path(report.gif_path, base_dir)
            lines.append(f"- 🎞️ **Resumo Animado dos Momentos Críticos (GIF):** [{rel_gif}]({rel_gif})")
            lines.append("")
            lines.append(f"![Resumo Animado da Sessão]({rel_gif})")
        lines.append("")
        lines.append("---")
        lines.append("")

    # 3. Auto-Cura de Seletores (Self-Healing)
    if report.healed_steps:
        lines.append("## 🩹 3. Registro de Auto-Cura de Seletores (Self-Healing)")
        lines.append("")
        lines.append(
            "> Os seletores abaixo sofreram `TimeoutError` ou falha de localização no DOM e foram recuperados "
            "automaticamente pelo UXSentinel através da **Árvore de Acessibilidade** ou por **Visão Multimodal LMM**."
        )
        lines.append("")
        lines.append(
            "| Passo | Ação | Seletor Original | Estratégia Adotada | Sugestão de Correção para o YAML |"
        )
        lines.append("| :---: | :--- | :--- | :--- | :--- |")
        for h in report.healed_steps:
            passo_num = str(h.step_index) if h.step_index is not None else "-"
            sugestao = h.yaml_fix_suggestion or h.recovered_selector or "-"
            lines.append(
                f"| {passo_num} | `{h.action}` | `{h.original_selector}` | `{h.strategy}` | `{sugestao}` |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")

    # 4. Ações Semânticas em Linguagem Natural
    if report.semantic_steps:
        lines.append("## 🤖 4. Ações Semânticas Declarativas em Linguagem Natural")
        lines.append("")
        lines.append(
            "> Passos semânticos interpretados em tempo de execução através do entendimento cognitivo "
            "da viewport e acessibilidade."
        )
        lines.append("")
        lines.append("| Passo | Ação | Alvo Declarado | Status | Resolução / Justificativa |")
        lines.append("| :---: | :--- | :--- | :---: | :--- |")
        for sem in report.semantic_steps:
            passo_num = str(sem.step_index) if sem.step_index is not None else "-"
            st = "✅ Concluído" if sem.passed else "❌ Falhou"
            just = sem.reasoning or sem.resolved_selector or "-"
            target_str = sem.target.replace('"', '\\"')
            lines.append(f'| {passo_num} | `{sem.action}` | **"{target_str}"** | {st} | {just} |')
        lines.append("")
        lines.append("---")
        lines.append("")

    # 5. Detalhamento por Checkpoint
    lines.append("## 📍 5. Detalhamento Técnico por Checkpoint")
    lines.append("")

    if not report.checkpoints:
        lines.append("🎉 **Nenhuma inconformidade visual, de UX ou de idioma foi detectada.**")
        lines.append("")
        lines.append("---")
        lines.append("")
    else:
        for idx, cp in enumerate(report.checkpoints, start=1):
            cp_status_icon = "✅" if cp.status == "ok" else "⚠️"
            vp_label = f" — `{cp.viewport}`" if cp.viewport else ""
            lines.append(f"### 5.{idx} Checkpoint: `{cp.name}`{vp_label} {cp_status_icon}")
            lines.append("")
            lines.append("**Comportamento Esperado da Regra:**")
            lines.append(f"> {cp.expected_behavior}")
            lines.append("")

            # Screenshot principal
            if cp.screenshot_path:
                rel_scr = _calc_rel_path(cp.screenshot_path, base_dir)
                lines.append(f"![Captura Checkpoint: {cp.name}]({rel_scr})")
                lines.append("")

            # Comparação Visual (Baseline / Diff)
            if cp.visual_diff:
                lines.append("#### 👁️ Auditoria de Regressão Visual (Baseline)")
                lines.append("")
                diff_icon = "⚡" if cp.visual_diff.has_diff else "✅"
                diff_status = "Divergência Detectada" if cp.visual_diff.has_diff else "Visualmente Conforme"
                lines.append(
                    f"- **Resultado:** {diff_icon} **{diff_status}** ({cp.visual_diff.diff_percentage:.2f}% de alteração de pixels)"
                )
                rel_base = _calc_rel_path(cp.visual_diff.baseline_path, base_dir)
                lines.append(f"- **Baseline Homologado:** [{rel_base}]({rel_base})")
                if cp.visual_diff.diff_image_path:
                    rel_diff_img = _calc_rel_path(cp.visual_diff.diff_image_path, base_dir)
                    lines.append(f"- **Máscara de Diferença (#E11D48):** [{rel_diff_img}]({rel_diff_img})")
                    lines.append("")
                    lines.append(f"![Máscara de Diff: {cp.name}]({rel_diff_img})")
                lines.append("")

            # Auditoria de Acessibilidade WCAG 2.2 AA (Axe-Core)
            if cp.a11y_violations:
                score_txt = f"{cp.a11y_score:.1f}%" if cp.a11y_score is not None else "-"
                lines.append(f"#### ♿ Acessibilidade WCAG 2.2 AA (Axe-Core — Score: {score_txt})")
                lines.append("")
                lines.append(
                    "| Severidade | Regra / ID | Explicação em Português | Alvo CSS | Orientação de Correção | Especificação |"
                )
                lines.append("| :---: | :--- | :--- | :--- | :--- | :---: |")

                for v in cp.a11y_violations:
                    imp = (v.impact or "moderate").lower()
                    imp_label = {
                        "critical": "🔴 CRÍTICO",
                        "serious": "🟠 GRAVE",
                        "moderate": "🟡 MODERADO",
                        "minor": "🔵 LEVE",
                    }.get(imp, imp.upper())

                    first_node = v.nodes[0] if v.nodes else None
                    targets = " > ".join(first_node.target) if (first_node and first_node.target) else "html"
                    target_css = f"`{targets}`"
                    explanation = v.help or v.description
                    fix_hint = (
                        first_node.failure_summary if first_node else None
                    ) or "Revisar marcação acessível."
                    spec_link = f"[Deque/WCAG ↗]({v.help_url})" if v.help_url else "-"

                    # Limpa quebras de linha para manter a tabela MarkText perfeita
                    clean_exp = " ".join(explanation.splitlines()).replace("|", "\\|")
                    clean_fix = " ".join(fix_hint.splitlines()).replace("|", "\\|")

                    lines.append(
                        f"| {imp_label} | `{v.id}` | {clean_exp} | {target_css} | {clean_fix} | {spec_link} |"
                    )
                lines.append("")

            # Inconformidades de Usabilidade / Heurísticas (Issues)
            if cp.issues:
                lines.append("#### 🔍 Inconformidades e Falhas de Usabilidade Detectadas")
                lines.append("")
                for issue_idx, issue in enumerate(cp.issues, start=1):
                    icon = _get_severity_icon(issue.severidade)
                    sev_label = _get_severity_label(issue.severidade)
                    evaluator_str = f" | Avaliador: `{issue.evaluator}`" if issue.evaluator else ""

                    lines.append(
                        f"**{icon} Inconformidade #{issue_idx} — {sev_label}** "
                        f"(Categoria: `{issue.categoria.value}`{evaluator_str})"
                    )
                    lines.append("")
                    lines.append(f"- **Defeito Observado:** {issue.descricao}")
                    if issue.elemento_alvo:
                        lines.append(f"- **Elemento Afetado:** `{issue.elemento_alvo}`")
                    if issue.trecho_codigo:
                        lines.append("- **Trecho de Código no DOM:**")
                        lines.append("  ```html")
                        lines.append(f"  {issue.trecho_codigo.strip()}")
                        lines.append("  ```")
                    if issue.sugestao_correcao:
                        lines.append(f"- 💡 **Sugestão de Correção:** {issue.sugestao_correcao}")
                    lines.append("")
            else:
                lines.append("🎉 **Nenhuma inconformidade de UI/UX encontrada neste checkpoint.**")
                lines.append("")

            lines.append("---")
            lines.append("")

    # 6. Telemetria do Console Chromium & Diagnósticos de Performance (W3C)
    if report.console_logs or report.network_failures or report.performance_metrics:
        lines.append("## 🖥️ 6. Telemetria do Console Chromium & Performance da Aplicação (W3C)")
        lines.append("")
        lines.append(
            "> Diagnósticos em tempo de execução capturados diretamente da engine Chromium, incluindo tempos reais "
            "de carregamento via W3C Navigation Timing API, requisições de rede com falha e logs emitidos pelo JavaScript."
        )
        lines.append("")

        # Métricas de Performance W3C
        if report.performance_metrics:
            pm = report.performance_metrics
            lines.append("### ⚡ 6.1 Métricas W3C de Tempo de Carregamento da Página")
            lines.append("")
            lines.append(f"- **URL Avaliada:** `{pm.url}`")
            lines.append("")
            lines.append("| Métrica W3C | Tempo Medido | Avaliação de Experiência |")
            lines.append("| :--- | :---: | :---: |")
            lines.append(
                f"| **Tempo Total de Carregamento (Page Load)** | **{pm.load_time_ms:.0f} ms** | "
                f"{'🟢 Rápido (<2s)' if pm.load_time_ms < 2000 else '🟡 Moderado (2-4s)' if pm.load_time_ms < 4000 else '🔴 Lento (>4s)'} |"
            )
            lines.append(
                f"| **Time to First Byte (TTFB)** | **{pm.ttfb_ms:.0f} ms** | "
                f"{'🟢 Excelente (<200ms)' if pm.ttfb_ms < 200 else '🟡 Aceitável (<500ms)' if pm.ttfb_ms < 500 else '🔴 Alto (>500ms)'} |"
            )
            lines.append(
                f"| **Processamento do DOM (DOM Interactive)** | **{pm.dom_interactive_ms:.0f} ms** | 🖥️ |"
            )
            lines.append(f"| **Resolução de Domínio (DNS Lookup)** | **{pm.dns_time_ms:.0f} ms** | 🌐 |")
            lines.append(f"| **Conexão TCP / Handshake SSL** | **{pm.tcp_time_ms:.0f} ms** | 🔒 |")
            lines.append("")

        # Falhas de Rede HTTP
        if report.network_failures:
            lines.append("### 🌐 6.2 Requisições de Rede com Falha (HTTP 4xx/5xx/CORS/Aborted)")
            lines.append("")
            lines.append("| Método | Status HTTP | URL Alvo | Motivo / Diagnóstico |")
            lines.append("| :---: | :---: | :--- | :--- |")
            for net in report.network_failures:
                st_code = f"`{net.status}`" if net.status else "`FALHA`"
                err_desc = net.error_text or "Falha de conexão ou CORS"
                lines.append(f"| `{net.method}` | {st_code} | `{net.url}` | {err_desc} |")
            lines.append("")

        # Logs e Exceções do Console
        if report.console_logs:
            lines.append("### 📜 6.3 Logs e Mensagens do Console Chromium")
            lines.append("")
            lines.append("| Tipo | Mensagem Registrada | Localização no Código |")
            lines.append("| :---: | :--- | :--- |")
            for c_log in report.console_logs:
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

    # 7. Guia de Ação Rápida e Comandos Úteis
    lines.append("## 🛠️ 7. Guia de Ação Rápida e Comandos Úteis")
    lines.append("")
    lines.append("- **Inspecionar ao vivo com o Console/DevTools do Chromium acoplado:**")
    lines.append("  ```bash")
    lines.append(f"  uxsentinel -s {report.scenario_id} --devtools")
    lines.append("  ```")
    lines.append("- **Gerar prompt técnico de correção para IAs (Claude, Cursor, Copilot):**")
    lines.append("  ```bash")
    lines.append(f"  uxsentinel -s {report.scenario_id} --fix-prompt")
    lines.append("  ```")
    lines.append("- **Atualizar referências homologadas de baseline visual:**")
    lines.append("  ```bash")
    lines.append(f"  uxsentinel -s {report.scenario_id} --update-baseline")
    lines.append("  ```")
    lines.append("- **Executar testes em modo silencioso (Headless) em CI/CD:**")
    lines.append("  ```bash")
    lines.append(f"  uxsentinel -s {report.scenario_id} --headless")
    lines.append("  ```")
    lines.append("")
    lines.append("---")
    lines.append(
        f"*Relatório gerado automaticamente pelo **UXSentinel** em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}. "
        "Compatível com o editor MarkText, Obsidian, Typora e GitHub Flavored Markdown (GFM).*"
    )

    return "\n".join(lines)


def save_markdown_report(report: TestReport, output_dir: str | Path) -> Path:
    """Gera e salva o relatório em documento Markdown (.md) no diretório de saída especificado."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / f"{report.scenario_id}_report.md"

    md_content = build_markdown_report(report=report, output_dir=out_path)
    report_file.write_text(md_content, encoding="utf-8")
    return report_file
