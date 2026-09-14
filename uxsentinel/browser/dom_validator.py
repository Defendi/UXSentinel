import logging
from typing import Any

from playwright.async_api import Page
from pydantic import BaseModel, Field

from uxsentinel.core.models import Issue, IssueCategory, IssueSeverity, StrEnum

logger = logging.getLogger("uxsentinel.browser.dom_validator")


class DOMAnomalyType(StrEnum):
    TEXT_TRUNCATION = "text_truncation"
    CONTAINER_OVERFLOW = "container_overflow"
    MODAL_OUT_OF_BOUNDS = "modal_out_of_bounds"


class DOMAnomaly(BaseModel):
    """Representação estruturada de uma anomalia matemática ou geométrica comprovada no DOM."""

    anomaly_type: DOMAnomalyType | str
    tag: str
    class_name: str = ""
    id: str = ""
    selector: str | None = None
    text_snippet: str | None = None
    scroll_width: float | None = None
    client_width: float | None = None
    scroll_height: float | None = None
    client_height: float | None = None
    bounding_box: dict[str, float] | None = None
    description: str
    severity: IssueSeverity = IssueSeverity.ALTA
    suggested_fix: str | None = None
    extra_details: dict[str, Any] = Field(default_factory=dict)


DOM_INSPECTION_SCRIPT = """
() => {
    const anomalies = [];
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const ignoredTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'PATH', 'BR', 'HR', 'HEAD', 'META', 'LINK', 'IFRAME']);

    const allElements = document.querySelectorAll('*');
    for (const el of allElements) {
        if (ignoredTags.has(el.tagName)) continue;

        // Verifica visibilidade real
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;

        const tag = el.tagName.toLowerCase();
        const className = typeof el.className === 'string' ? el.className.trim() : '';
        const id = el.id || '';
        const selector = id ? `#${id}` : (className ? `.${className.split(/\\s+/).slice(0, 2).join('.')}` : tag);

        // 1. Verificação de Truncamento de Texto
        // Tolerância de 1.5px para subpixel rendering
        const hasTextOverflowX = el.scrollWidth > el.clientWidth + 1.5;
        const isOverflowHiddenX = style.overflowX === 'hidden' || style.overflow === 'hidden' || style.textOverflow === 'ellipsis';

        if (hasTextOverflowX && isOverflowHiddenX) {
            // Verifica se o elemento tem texto direto legível
            const textContent = (el.innerText || el.textContent || '').trim();
            const hasDirectText = Array.from(el.childNodes).some(
                n => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0
            );

            if (textContent.length > 0 && (hasDirectText || el.children.length <= 2)) {
                anomalies.push({
                    anomaly_type: 'text_truncation',
                    tag: tag,
                    class_name: className,
                    id: id,
                    selector: selector,
                    text_snippet: textContent.slice(0, 60),
                    scroll_width: Math.round(el.scrollWidth),
                    client_width: Math.round(el.clientWidth),
                    scroll_height: Math.round(el.scrollHeight),
                    client_height: Math.round(el.clientHeight),
                    description: `Texto truncado no elemento <${tag}>: scrollWidth (${Math.round(el.scrollWidth)}px) > clientWidth (${Math.round(el.clientWidth)}px). Trecho: "${textContent.slice(0, 45)}..."`,
                    severity: 'alta',
                    suggested_fix: 'Ajustar largura do container, remover white-space: nowrap ou aumentar área útil do elemento.',
                });
            }
        }

        // 2. Verificação de Overflow de Container/Modal
        const isContainer = el.matches(
            'dialog, [role="dialog"], .modal, .modal-dialog, .modal-content, .card, .panel, .dropdown-menu, .popover, [role="menu"]'
        );
        const hasContainerOverflowX = el.scrollWidth > el.clientWidth + 2;
        const hasContainerOverflowY = el.scrollHeight > el.clientHeight + 2;

        if (isContainer && (hasContainerOverflowX || hasContainerOverflowY)) {
            const isHiddenOverflow = style.overflow === 'hidden' || style.overflowX === 'hidden' || style.overflowY === 'hidden';
            if (isHiddenOverflow) {
                anomalies.push({
                    anomaly_type: 'container_overflow',
                    tag: tag,
                    class_name: className,
                    id: id,
                    selector: selector,
                    scroll_width: Math.round(el.scrollWidth),
                    client_width: Math.round(el.clientWidth),
                    scroll_height: Math.round(el.scrollHeight),
                    client_height: Math.round(el.clientHeight),
                    description: `Container <${tag}> sofre de vazamento/overflow com conteúdo ocultado por overflow:hidden (largura: ${Math.round(el.scrollWidth)}px vs ${Math.round(el.clientWidth)}px, altura: ${Math.round(el.scrollHeight)}px vs ${Math.round(el.clientHeight)}px).`,
                    severity: 'alta',
                    suggested_fix: 'Permitir rolagem interna com overflow: auto ou revisar layout responsivo do modal/container.',
                });
            }
        }

        // 3. Verificação de Modal / Diálogo fora dos limites da Viewport
        if (isContainer && el.matches('dialog, [role="dialog"], .modal, .modal-dialog')) {
            const outOfBounds = rect.left < -3 || rect.top < -3 || rect.right > vw + 3 || rect.bottom > vh + 3;
            if (outOfBounds) {
                anomalies.push({
                    anomaly_type: 'modal_out_of_bounds',
                    tag: tag,
                    class_name: className,
                    id: id,
                    selector: selector,
                    bounding_box: {
                        left: Math.round(rect.left),
                        top: Math.round(rect.top),
                        right: Math.round(rect.right),
                        bottom: Math.round(rect.bottom),
                    },
                    description: `Modal ou diálogo ultrapassou os limites da tela (Viewport: ${vw}x${vh}). Posição calculada: [L:${Math.round(rect.left)}, R:${Math.round(rect.right)}, T:${Math.round(rect.top)}, B:${Math.round(rect.bottom)}].`,
                    severity: 'bloqueante',
                    suggested_fix: 'Centralizar o modal via flexbox/grid e garantir max-width: 90vw e max-height: 90vh.',
                });
            }
        }

        if (anomalies.length >= 35) break; // Trava de segurança contra excesso de dados
    }

    return anomalies;
}
"""


class DOMValidator:
    """Validador determinístico executado diretamente no DOM do Playwright
    para detecção matemática de overflow, truncamento de texto e modais fora dos limites.
    """

    async def inspect_dom(self, page: Page) -> list[DOMAnomaly]:
        """Executa a rotina JavaScript no navegador e retorna as anomalias detectadas."""
        try:
            raw_results = await page.evaluate(DOM_INSPECTION_SCRIPT)
            if not isinstance(raw_results, list):
                return []

            anomalies: list[DOMAnomaly] = []
            for item in raw_results:
                if not isinstance(item, dict):
                    continue

                sev_str = str(item.get("severity", "alta")).lower()
                sev = IssueSeverity.ALTA
                for s in IssueSeverity:
                    if s.value == sev_str:
                        sev = s
                        break

                anomalies.append(
                    DOMAnomaly(
                        anomaly_type=item.get("anomaly_type", "unknown"),
                        tag=item.get("tag", "unknown"),
                        class_name=item.get("class_name", ""),
                        id=item.get("id", ""),
                        selector=item.get("selector"),
                        text_snippet=item.get("text_snippet"),
                        scroll_width=item.get("scroll_width"),
                        client_width=item.get("client_width"),
                        scroll_height=item.get("scroll_height"),
                        client_height=item.get("client_height"),
                        bounding_box=item.get("bounding_box"),
                        description=item.get("description", "Anomalia detectada no DOM."),
                        severity=sev,
                        suggested_fix=item.get("suggested_fix"),
                    )
                )

            return anomalies
        except Exception as exc:
            logger.warning("[DOMValidator] Falha ao executar validação determinística no DOM: %s", exc)
            return []

    def anomalies_to_issues(self, anomalies: list[DOMAnomaly], viewport: str | None = None) -> list[Issue]:
        """Converte as anomalias determinísticas em objetos Issue do UXSentinel."""
        issues: list[Issue] = []
        for a in anomalies:
            issues.append(
                Issue(
                    categoria=IssueCategory.LAYOUT_MODAL,
                    severidade=a.severity,
                    descricao=f"[DOM Determinístico] {a.description}",
                    sugestao_correcao=a.suggested_fix,
                    elemento_alvo=a.selector or f"<{a.tag}>",
                    viewport=viewport,
                    evaluator="DOMValidator (Determinístico)",
                )
            )
        return issues

    def format_anomalies_summary(self, anomalies: list[DOMAnomaly]) -> str:
        """Formata um resumo textual claro das anomalias para enriquecer o contexto dos avaliadores."""
        if not anomalies:
            return ""

        lines = ["[EVIDÊNCIAS DETERMINÍSTICAS DO DOM]:"]
        for idx, a in enumerate(anomalies, start=1):
            lines.append(f"{idx}. [{a.severity.value.upper()}] {a.description}")
        return "\n".join(lines)
