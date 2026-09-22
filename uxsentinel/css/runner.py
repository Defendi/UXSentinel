"""Orquestrador e Inspetor Geral de CSS Híbrido (UXS-47)."""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import Page

from uxsentinel.css.models import CSSAuditReport
from uxsentinel.css.runtime_auditor import CSSRuntimeAuditor
from uxsentinel.css.static_auditor import CSSStaticAuditor

logger = logging.getLogger("uxsentinel.css.runner")

# Script para extrair CSS de tags <style> e folhas de estilo vinculadas com sucesso
EXTRACT_STYLES_SCRIPT = """
() => {
    const cssSnippets = [];

    // 1. Extrai tags <style> inline
    const styles = document.querySelectorAll('style');
    for (const s of styles) {
        if (s.textContent && s.textContent.trim()) {
            cssSnippets.push(s.textContent.trim());
        }
    }

    // 2. Extrai CSS rules de folhas de estilo vinculadas (mesma origem ou acessíveis)
    try {
        for (let i = 0; i < document.styleSheets.length; i++) {
            const sheet = document.styleSheets[i];
            // Se for tag <style>, já capturamos
            if (sheet.ownerNode && sheet.ownerNode.tagName === 'STYLE') continue;
            try {
                const rules = sheet.cssRules || sheet.rules;
                if (rules) {
                    const ruleTexts = [];
                    for (let j = 0; j < rules.length; j++) {
                        ruleTexts.push(rules[j].cssText);
                    }
                    if (ruleTexts.length > 0) {
                        cssSnippets.push(ruleTexts.join('\n'));
                    }
                }
            } catch (e) {
                // Cross-origin stylesheet security restriction (CORS) - ignora silenciosamente
            }
        }
    } catch (err) {
        // Fallback
    }

    return cssSnippets;
}
"""


class CSSInspector:
    """Inspetor híbrido que executa auditoria de CSS em tempo de execução e estática."""

    @classmethod
    async def audit_page(cls, page: Page, viewport: str | None = None) -> CSSAuditReport:
        """Executa auditoria híbrida de CSS completa na página atual do Playwright.

        Combina:
        1. Auditoria geométrica de runtime no DOM (overflow horizontal, z-index, tipografia, larguras fixas, flexbox/grid).
        2. Extração de <style> e CSS rules carregadas com auditoria estática (!important, especificidade, duplicação, modern css).
        """
        combined_report = CSSAuditReport()
        if not page:
            return combined_report

        # 1. Runtime Audit
        runtime_report = await CSSRuntimeAuditor.audit(page)

        # 2. Extract DOM CSS Text
        css_texts: list[str] = []
        try:
            css_texts = await page.evaluate(EXTRACT_STYLES_SCRIPT)
        except Exception as exc:
            logger.debug(f"Não foi possível extrair CSS do DOM: {exc}")

        if isinstance(css_texts, list):
            valid_texts = [c for c in css_texts if isinstance(c, str)]
            full_css = "\n\n".join(valid_texts)
        elif isinstance(css_texts, str):
            full_css = css_texts
        else:
            full_css = ""
        static_report = CSSStaticAuditor.audit_text(full_css) if full_css.strip() else CSSAuditReport()

        # Combina relatórios
        combined_report.total_rules_inspected = (
            runtime_report.total_rules_inspected + static_report.total_rules_inspected
        )
        combined_report.violations = list(runtime_report.violations) + list(static_report.violations)
        combined_report.calculate_score()
        return combined_report

    @classmethod
    def audit_file_or_dir(cls, path: Path | str) -> CSSAuditReport:
        """Audita arquivo ou diretório contendo arquivos CSS no disco."""
        target = Path(path)
        combined = CSSAuditReport()

        if not target.exists():
            from uxsentinel.css.models import CSSIssueCategory, CSSSeverity, CSSViolation

            combined.violations.append(
                CSSViolation(
                    rule_id="css-path-not-found",
                    category=CSSIssueCategory.OTHER,
                    severity=CSSSeverity.ALTA,
                    description=f"Caminho não encontrado para auditoria CSS: {target}",
                    source="static",
                )
            )
            combined.calculate_score()
            return combined

        if target.is_file():
            return CSSStaticAuditor.audit_file(target)

        # Se for diretório, varre recursivamente arquivos .css
        css_files = list(target.rglob("*.css"))
        if not css_files:
            return combined

        all_violations = []
        total_rules = 0

        for f in css_files:
            rep = CSSStaticAuditor.audit_file(f)
            total_rules += rep.total_rules_inspected
            all_violations.extend(rep.violations)

        combined.total_rules_inspected = total_rules
        combined.violations = all_violations
        combined.calculate_score()
        return combined
