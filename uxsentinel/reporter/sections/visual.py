"""Renderização de discrepâncias visuais, comparações baseline e detalhamento de checkpoints."""

from __future__ import annotations

from pathlib import Path

from uxsentinel.core.models import (
    CheckpointResult,
    IssueSeverity,
    VisualDiffResult,
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


def get_severity_icon(sev: IssueSeverity | str) -> str:
    key = getattr(sev, "value", str(sev)).lower()
    return SEVERITY_ICONS.get(key, SEVERITY_ICONS.get(sev, "⚠️"))


def get_severity_label(sev: IssueSeverity | str) -> str:
    key = getattr(sev, "value", str(sev)).lower()
    return SEVERITY_LABELS.get(key, SEVERITY_LABELS.get(sev, str(key).upper()))


def calc_rel_path(path_str: str | None, base_dir: Path | None) -> str:
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


def render_visual_diff(
    diff: VisualDiffResult | None, cp_name: str, base_dir: Path | None = None
) -> list[str]:
    """Renderiza a seção de regressão visual comparativa contra o baseline."""
    if not diff:
        return []

    lines: list[str] = ["#### 👁️ Auditoria de Regressão Visual (Baseline)", ""]
    diff_icon = "⚡" if diff.has_diff else "✅"
    diff_status = "Divergência Detectada" if diff.has_diff else "Visualmente Conforme"
    lines.append(
        f"- **Resultado:** {diff_icon} **{diff_status}** ({diff.diff_percentage:.2f}% de alteração de pixels)"
    )

    rel_base = calc_rel_path(diff.baseline_path, base_dir)
    lines.append(f"- **Baseline Homologado:** [{rel_base}]({rel_base})")

    if diff.diff_image_path:
        rel_diff_img = calc_rel_path(diff.diff_image_path, base_dir)
        lines.append(f"- **Máscara de Diferença (#E11D48):** [{rel_diff_img}]({rel_diff_img})")
        lines.append("")
        lines.append(f"![Máscara de Diff: {cp_name}]({rel_diff_img})")

    lines.append("")
    return lines


def render_checkpoint_details(
    checkpoints: list[CheckpointResult],
    base_dir: Path | None = None,
) -> list[str]:
    """Renderiza a Seção 5: Detalhamento Técnico por Checkpoint com screenshots, diffs, a11y e issues."""
    from uxsentinel.reporter.sections.a11y import render_axe_violations
    from uxsentinel.reporter.sections.css import render_css_violations

    lines: list[str] = ["## 📍 5. Detalhamento Técnico por Checkpoint", ""]

    if not checkpoints:
        lines.append("🎉 **Nenhuma inconformidade visual, de UX ou de idioma foi detectada.**")
        lines.append("")
        lines.append("---")
        lines.append("")
        return lines

    for idx, cp in enumerate(checkpoints, start=1):
        cp_status_icon = "✅" if cp.status == "ok" else "⚠️"
        vp_label = f" — `{cp.viewport}`" if cp.viewport else ""
        lines.append(f"### 5.{idx} Checkpoint: `{cp.name}`{vp_label} {cp_status_icon}")
        lines.append("")
        lines.append("**Comportamento Esperado da Regra:**")
        lines.append(f"> {cp.expected_behavior}")
        lines.append("")

        # Screenshot principal
        if cp.screenshot_path:
            rel_scr = calc_rel_path(cp.screenshot_path, base_dir)
            lines.append(f"![Captura Checkpoint: {cp.name}]({rel_scr})")
            lines.append("")

        # Comparação Visual (Baseline / Diff)
        if cp.visual_diff:
            lines.extend(render_visual_diff(cp.visual_diff, cp.name, base_dir))

        # Auditoria de Acessibilidade WCAG 2.2 AA (Axe-Core)
        if cp.a11y_violations:
            lines.extend(render_axe_violations(cp.a11y_violations, cp.a11y_score))

        # Auditoria de CSS (UXS-47)
        if cp.css_audit and cp.css_audit.violations:
            lines.extend(render_css_violations(cp.css_audit))

        # Inconformidades de Usabilidade / Heurísticas (Issues)
        if cp.issues:
            lines.append("#### 🔍 Inconformidades e Falhas de Usabilidade Detectadas")
            lines.append("")
            for issue_idx, issue in enumerate(cp.issues, start=1):
                icon = get_severity_icon(issue.severidade)
                sev_label = get_severity_label(issue.severidade)
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

    return lines
