"""Módulos modulares de renderização de seções do relatório Markdown."""

from __future__ import annotations

from uxsentinel.reporter.sections.a11y import render_axe_violations
from uxsentinel.reporter.sections.css import render_css_violations
from uxsentinel.reporter.sections.header import render_executive_summary, render_header
from uxsentinel.reporter.sections.timeline import (
    render_action_guide,
    render_console_and_performance,
    render_dynamic_evidence,
    render_healed_steps,
    render_semantic_steps,
)
from uxsentinel.reporter.sections.visual import render_checkpoint_details, render_visual_diff

__all__ = [
    "render_action_guide",
    "render_axe_violations",
    "render_css_violations",
    "render_checkpoint_details",
    "render_console_and_performance",
    "render_dynamic_evidence",
    "render_executive_summary",
    "render_healed_steps",
    "render_header",
    "render_semantic_steps",
    "render_visual_diff",
]
