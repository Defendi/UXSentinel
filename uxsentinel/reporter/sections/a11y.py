"""Renderização da matriz e violações de acessibilidade Axe-Core no relatório Markdown."""

from __future__ import annotations

from uxsentinel.core.models import AxeViolation


def render_axe_violations(violations: list[AxeViolation], a11y_score: float | None = None) -> list[str]:
    """Renderiza a tabela detalhada de violações WCAG 2.2 AA (Axe-Core)."""
    if not violations:
        return []

    score_txt = f"{a11y_score:.1f}%" if a11y_score is not None else "-"
    lines: list[str] = [
        f"#### ♿ Acessibilidade WCAG 2.2 AA (Axe-Core — Score: {score_txt})",
        "",
        "| Severidade | Regra / ID | Explicação em Português | Alvo CSS | Orientação de Correção | Especificação |",
        "| :---: | :--- | :--- | :--- | :--- | :---: |",
    ]

    for v in violations:
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
        fix_hint = (first_node.failure_summary if first_node else None) or "Revisar marcação acessível."
        spec_link = f"[Deque/WCAG ↗]({v.help_url})" if v.help_url else "-"

        # Limpa quebras de linha para manter a tabela MarkText perfeita
        clean_exp = " ".join(explanation.splitlines()).replace("|", "\\|")
        clean_fix = " ".join(fix_hint.splitlines()).replace("|", "\\|")

        lines.append(f"| {imp_label} | `{v.id}` | {clean_exp} | {target_css} | {clean_fix} | {spec_link} |")

    lines.append("")
    return lines
