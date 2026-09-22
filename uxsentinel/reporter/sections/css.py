"""Renderização da matriz e violações de auditoria de CSS no relatório Markdown."""

from __future__ import annotations

from uxsentinel.css.models import CSSAuditReport, CSSSeverity


def render_css_violations(css_audit: CSSAuditReport | None) -> list[str]:
    """Renderiza a tabela detalhada de violações de CSS (UXS-47)."""
    if not css_audit or not css_audit.violations:
        return []

    lines: list[str] = [
        f"#### 🎨 Auditoria Profunda de CSS (Score: {css_audit.score:.1f}/100)",
        "",
        "| Severidade | Regra / Categoria | Explicação Técnica | Seletor / Alvo | Orientação de Correção |",
        "| :---: | :--- | :--- | :--- | :--- |",
    ]

    sev_labels = {
        CSSSeverity.BLOQUEANTE: "🔴 BLOQUEANTE",
        CSSSeverity.ALTA: "🟠 ALTA",
        CSSSeverity.MEDIA: "🟡 MÉDIA",
        CSSSeverity.BAIXA: "🔵 BAIXA",
    }

    for v in css_audit.violations:
        sev_txt = sev_labels.get(v.severity, str(v.severity.value).upper())
        cat_txt = f"`{v.rule_id}` ({v.category.value})"
        desc = " ".join(v.description.splitlines()).replace("|", "\\|")
        target = f"`{v.selector}`" if v.selector else (f"`{v.snippet}`" if v.snippet else "-")
        target = " ".join(target.splitlines()).replace("|", "\\|")
        suggestion = " ".join((v.suggestion or "Revisar regra CSS.").splitlines()).replace("|", "\\|")

        lines.append(f"| {sev_txt} | {cat_txt} | {desc} | {target} | {suggestion} |")

    lines.append("")
    return lines
