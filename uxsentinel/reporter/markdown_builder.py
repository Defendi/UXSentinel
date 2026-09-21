"""Gerador de Relatórios de Auditoria em formato Markdown compatível com MarkText, Obsidian e GitHub."""

from __future__ import annotations

from pathlib import Path

from uxsentinel.core.models import TestReport
from uxsentinel.reporter.sections.header import (
    render_executive_summary,
    render_header,
)
from uxsentinel.reporter.sections.timeline import (
    render_action_guide,
    render_console_and_performance,
    render_dynamic_evidence,
    render_healed_steps,
    render_semantic_steps,
)
from uxsentinel.reporter.sections.visual import (
    SEVERITY_ICONS,
    SEVERITY_LABELS,
    calc_rel_path,
    get_severity_icon,
    get_severity_label,
    render_checkpoint_details,
)

__all__ = [
    "SEVERITY_ICONS",
    "SEVERITY_LABELS",
    "_calc_rel_path",
    "_get_severity_icon",
    "_get_severity_label",
    "build_markdown_report",
    "save_markdown_report",
]

# Retrocompatibilidade de exports privados caso dependências externas utilizem
_calc_rel_path = calc_rel_path
_get_severity_icon = get_severity_icon
_get_severity_label = get_severity_label


def build_markdown_report(report: TestReport, output_dir: str | Path | None = None) -> str:
    """Constrói um relatório de auditoria completo em Markdown formatado para o editor MarkText.

    Utiliza tabelas CommonMark/GFM alinhadas, badges visuais, links relativos de imagens
    para renderização direta no MarkText e detalhamento minucioso de acessibilidade e heurísticas.
    """
    base_dir = Path(output_dir) if output_dir else None

    # Pipeline modular de composição do relatório Markdown
    sections: list[list[str]] = [
        render_header(report),
        render_executive_summary(report),
        render_dynamic_evidence(report.video_path, report.gif_path, base_dir),
        render_healed_steps(report.healed_steps),
        render_semantic_steps(report.semantic_steps),
        render_checkpoint_details(report.checkpoints, base_dir),
        render_console_and_performance(
            report.console_logs,
            report.network_failures,
            report.performance_metrics,
        ),
        render_action_guide(report.scenario_id),
    ]

    # Concatenação sequencial de todas as seções renderizadas
    lines: list[str] = [line for section in sections for line in section]
    return "\n".join(lines)


def save_markdown_report(report: TestReport, output_dir: str | Path) -> Path:
    """Gera e salva o relatório em documento Markdown (.md) no diretório de saída especificado."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / f"{report.scenario_id}_report.md"

    md_content = build_markdown_report(report=report, output_dir=out_path)
    report_file.write_text(md_content, encoding="utf-8")
    return report_file
