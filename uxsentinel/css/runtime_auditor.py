"""Auditor de CSS em tempo de execução via Playwright (UXS-47)."""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page

from uxsentinel.css.models import CSSAuditReport, CSSIssueCategory, CSSSeverity, CSSViolation

logger = logging.getLogger("uxsentinel.css.runtime_auditor")

RUNTIME_CSS_SCRIPT = r"""
() => {
    const violations = [];
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const docEl = document.documentElement;
    const body = document.body;

    const ignoredTags = new Set([
        'SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'PATH', 'HEAD', 'META', 'LINK', 'IFRAME'
    ]);

    // 1. Horizontal Overflow / Viewport Break na raiz
    const docScrollWidth = Math.max(docEl.scrollWidth, body ? body.scrollWidth : 0);
    const docClientWidth = docEl.clientWidth;
    const hasDocOverflowX = docScrollWidth > docClientWidth + 2;

    const allElements = document.querySelectorAll('*');
    for (const el of allElements) {
        if (ignoredTags.has(el.tagName)) continue;

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') continue;

        const rect = el.getBoundingClientRect();
        const tag = el.tagName.toLowerCase();
        const id = el.id ? `#${el.id}` : '';
        const className = typeof el.className === 'string' && el.className.trim()
            ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}`
            : '';
        const selector = id || className || tag;

        // 1. Horizontal Overflow / Viewport Break
        if (hasDocOverflowX && rect.width > 0 && rect.height > 0) {
            if (rect.right > vw + 1) {
                violations.push({
                    rule_id: 'css-horizontal-overflow',
                    category: 'overflow',
                    severity: 'bloqueante',
                    selector: selector,
                    property_name: 'overflow-x',
                    value: style.overflowX,
                    description: `Elemento <${tag}> estoura a viewport horizontalmente (right: ${Math.round(rect.right)}px > vw: ${vw}px) causando barra de rolagem horizontal indesejada.`,
                    suggestion: 'Aplicar max-width: 100%, overflow-x: hidden no container pai ou revisar margens/larguras fixas.',
                    snippet: el.outerHTML ? el.outerHTML.slice(0, 120) : null
                });
            }
        }

        // 2. Z-Index Abusive & Invisible Overlays
        const rawZIndex = style.zIndex;
        const zIndexNum = parseInt(rawZIndex, 10);
        if (!isNaN(zIndexNum) && zIndexNum >= 10000) {
            violations.push({
                rule_id: 'css-zindex-abusive',
                category: 'z_index',
                severity: 'alta',
                selector: selector,
                property_name: 'z-index',
                value: String(zIndexNum),
                description: `Elemento <${tag}> possui z-index excessivo (${zIndexNum} >= 10000), o que distorce a hierarquia de camadas da interface.`,
                suggestion: 'Organizar stacking contexts com variáveis ou escalas padronizadas (ex: z-10 a z-50).',
                snippet: `${selector} { z-index: ${zIndexNum}; }`
            });
        }

        const isFixedOrAbsolute = style.position === 'fixed' || style.position === 'absolute';
        if (isFixedOrAbsolute && rect.width >= vw * 0.9 && rect.height >= vh * 0.8) {
            const isOpacityZero = parseFloat(style.opacity) === 0;
            const bg = style.backgroundColor;
            const isTransparentBg = bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)';
            const pointerEvents = style.pointerEvents;

            if ((isOpacityZero || isTransparentBg) && pointerEvents !== 'none' && !el.innerText?.trim()) {
                violations.push({
                    rule_id: 'css-zindex-invisible-overlay',
                    category: 'z_index',
                    severity: 'bloqueante',
                    selector: selector,
                    property_name: 'pointer-events',
                    value: pointerEvents,
                    description: `Overlay invisível ou transparente com posição ${style.position} cobre quase toda a tela interceptando cliques e interações.`,
                    suggestion: 'Adicionar pointer-events: none no elemento transparente ou remover elemento inativo do DOM.',
                    snippet: `${selector} { position: ${style.position}; pointer-events: ${pointerEvents}; opacity: ${style.opacity}; }`
                });
            }
        }

        // 3. Typography & Readability
        const fontSizePx = parseFloat(style.fontSize);
        const hasTextContent = !!(el.innerText && el.innerText.trim().length > 0 && Array.from(el.childNodes).some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0));

        if (hasTextContent && !isNaN(fontSizePx) && fontSizePx > 0 && fontSizePx < 11) {
            violations.push({
                rule_id: 'css-typography-small-font',
                category: 'typography',
                severity: 'media',
                selector: selector,
                property_name: 'font-size',
                value: style.fontSize,
                description: `Elemento com texto possui tamanho de fonte ilegível (${style.fontSize} < 11px).`,
                suggestion: 'Utilizar font-size de no mínimo 12px ou 0.75rem para manter legibilidade.',
                snippet: `${selector} { font-size: ${style.fontSize}; }`
            });
        }

        const lineHeight = style.lineHeight;
        const lineHeightPx = parseFloat(lineHeight);
        if (hasTextContent && !isNaN(lineHeightPx) && !isNaN(fontSizePx) && fontSizePx > 0) {
            const ratio = lineHeightPx / fontSizePx;
            if (ratio < 1.1 && ratio > 0) {
                violations.push({
                    rule_id: 'css-typography-cramped-line-height',
                    category: 'typography',
                    severity: 'baixa',
                    selector: selector,
                    property_name: 'line-height',
                    value: lineHeight,
                    description: `Elemento de texto com line-height excessivamente apertado (${ratio.toFixed(2)} < 1.1), comprometendo a legibilidade.`,
                    suggestion: 'Definir line-height entre 1.4 e 1.6 para parágrafos e textos corridos.',
                    snippet: `${selector} { line-height: ${lineHeight}; font-size: ${style.fontSize}; }`
                });
            }
        }

        if (hasTextContent && style.color && style.backgroundColor) {
            const c = style.color.replace(/\s+/g, '');
            const bg = style.backgroundColor.replace(/\s+/g, '');
            if (c === bg && c !== 'rgba(0,0,0,0)' && c !== 'transparent') {
                violations.push({
                    rule_id: 'css-typography-low-contrast',
                    category: 'typography',
                    severity: 'alta',
                    selector: selector,
                    property_name: 'color',
                    value: style.color,
                    description: `Elemento possui cor de texto idêntica à cor de fundo (${style.color}), tornando o texto completamente invisível.`,
                    suggestion: 'Garantir contraste adequado entre cor do texto e cor de fundo.',
                    snippet: `${selector} { color: ${style.color}; background-color: ${style.backgroundColor}; }`
                });
            }
        }

        // 4. Fixed Width vs Viewport
        const inlineWidth = el.style.width;
        if (inlineWidth && inlineWidth.endsWith('px')) {
            const widthPx = parseFloat(inlineWidth);
            if (!isNaN(widthPx) && widthPx > vw) {
                violations.push({
                    rule_id: 'css-fixed-width-overflow',
                    category: 'responsiveness',
                    severity: 'bloqueante',
                    selector: selector,
                    property_name: 'width',
                    value: inlineWidth,
                    description: `Elemento com largura fixa de ${widthPx}px excede a largura da viewport atual (${vw}px), quebrando a responsividade.`,
                    suggestion: 'Substituir largura fixa por max-width: 100% ou unidades relativas (%, vw, rem).',
                    snippet: `${selector} { width: ${inlineWidth}; }`
                });
            }
        }

        // 5. Flexbox/Grid Overflow
        const display = style.display;
        if (display === 'flex' || display === 'inline-flex' || display === 'grid' || display === 'inline-grid') {
            const isRowFlex = display.includes('flex') && (style.flexDirection === 'row' || style.flexDirection === 'row-reverse' || !style.flexDirection);
            const isNoWrap = style.flexWrap === 'nowrap';

            if (isRowFlex && isNoWrap && el.scrollWidth > el.clientWidth + 2 && style.overflowX !== 'auto' && style.overflowX !== 'scroll') {
                violations.push({
                    rule_id: 'css-flexbox-child-overflow',
                    category: 'overflow',
                    severity: 'alta',
                    selector: selector,
                    property_name: 'flex-wrap',
                    value: style.flexWrap,
                    description: `Container flex com filhos transbordando a largura do pai (${el.scrollWidth}px > ${el.clientWidth}px) com flex-wrap: nowrap e overflow não rolável.`,
                    suggestion: 'Adicionar flex-wrap: wrap, min-width: 0 nos filhos flex ou overflow-x: auto no container.',
                    snippet: `${selector} { display: ${display}; flex-wrap: ${style.flexWrap}; }`
                });
            } else if (display.includes('grid') && el.scrollWidth > el.clientWidth + 2 && style.overflowX !== 'auto' && style.overflowX !== 'scroll') {
                violations.push({
                    rule_id: 'css-grid-child-overflow',
                    category: 'overflow',
                    severity: 'alta',
                    selector: selector,
                    property_name: 'display',
                    value: display,
                    description: `Container grid com colunas/filhos transbordando a largura (${el.scrollWidth}px > ${el.clientWidth}px) sem rolagem configurada.`,
                    suggestion: 'Usar minmax(0, 1fr) nas colunas de grid em vez de 1fr ou larguras absolutas.',
                    snippet: `${selector} { display: ${display}; grid-template-columns: ${style.gridTemplateColumns}; }`
                });
            }
        }
    }

    return {
        total_inspected: allElements.length,
        violations: violations
    };
}
"""


class CSSRuntimeAuditor:
    """Auditor em tempo de execução que inspeciona o DOM renderizado no Playwright."""

    @classmethod
    async def audit(cls, page: Page) -> CSSAuditReport:
        report = CSSAuditReport()
        if not page:
            return report

        try:
            raw_res: dict[str, Any] = await page.evaluate(RUNTIME_CSS_SCRIPT)
        except Exception as exc:
            logger.warning(f"Falha ao executar script JS de auditoria de CSS: {exc}")
            return report

        if isinstance(raw_res, list):
            raw_violations = raw_res
            total_inspected = len(raw_violations)
        elif isinstance(raw_res, dict):
            total_inspected = raw_res.get("total_inspected", 0)
            raw_violations = raw_res.get("violations", [])
        else:
            total_inspected = 0
            raw_violations = []

        parsed_violations: list[CSSViolation] = []
        for v in raw_violations:
            cat_str = v.get("category", "other")
            try:
                cat = CSSIssueCategory(cat_str)
            except ValueError:
                cat = CSSIssueCategory.OTHER

            sev_str = v.get("severity", "media")
            try:
                sev = CSSSeverity(sev_str)
            except ValueError:
                sev = CSSSeverity.MEDIA

            parsed_violations.append(
                CSSViolation(
                    rule_id=v.get("rule_id", "css-unknown"),
                    category=cat,
                    severity=sev,
                    selector=v.get("selector"),
                    property_name=v.get("property_name"),
                    value=v.get("value"),
                    description=v.get("description", "Inconformidade de CSS detectada."),
                    suggestion=v.get("suggestion"),
                    snippet=v.get("snippet"),
                    source="runtime",
                )
            )

        report.total_rules_inspected = total_inspected
        report.violations = parsed_violations
        report.calculate_score()
        return report
