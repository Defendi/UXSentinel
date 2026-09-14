import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from playwright.async_api import Page
from pydantic import BaseModel, Field

logger = logging.getLogger("uxsentinel.browser.som")


class InteractiveMark(BaseModel):
    """Representa um elemento interativo marcado visualmente com uma tag numérica SoM."""

    id: int
    tag: str
    text: str = ""
    selector: str
    role: str | None = None
    box: dict[str, float] = Field(default_factory=dict)


SOM_INJECTION_SCRIPT = """
() => {
    // Remove container anterior caso já exista
    const oldContainer = document.getElementById('uxsentinel-som-container');
    if (oldContainer) oldContainer.remove();

    const container = document.createElement('div');
    container.id = 'uxsentinel-som-container';
    container.style.cssText = 'position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 2147483647;';
    document.body.appendChild(container);

    const interactiveSelectors = [
        'button',
        'a[href]',
        'input',
        'select',
        'textarea',
        '[role="button"]',
        '[role="link"]',
        '[role="menuitem"]',
        '[role="tab"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[tabindex]:not([tabindex="-1"])'
    ].join(', ');

    const elements = Array.from(document.querySelectorAll(interactiveSelectors));
    const marks = [];
    let currentId = 1;

    const scrollX = window.scrollX || window.pageXOffset || 0;
    const scrollY = window.scrollY || window.pageYOffset || 0;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    for (const el of elements) {
        if (currentId > 99) break; // Limite razoável para não poluir a tela

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

        const rect = el.getBoundingClientRect();
        // Apenas elementos visíveis na viewport atual
        if (rect.width < 8 || rect.height < 8) continue;
        if (rect.bottom < 0 || rect.top > vh || rect.right < 0 || rect.left > vw) continue;

        const tag = el.tagName.toLowerCase();
        const rawText = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.value || '').trim();
        const cleanText = rawText.slice(0, 40);

        let sel = el.id ? `#${el.id}` : '';
        if (!sel && typeof el.className === 'string' && el.className.trim()) {
            sel = `.${el.className.trim().split(/\\s+/).slice(0, 2).join('.')}`;
        }
        if (!sel) sel = tag;

        // Cria o badge SoM visual
        const badge = document.createElement('div');
        badge.className = 'uxsentinel-som-badge';
        badge.textContent = `[${currentId}]`;
        badge.style.cssText = `
            position: absolute;
            left: ${Math.max(0, rect.left + scrollX)}px;
            top: ${Math.max(0, rect.top + scrollY)}px;
            background: #e11d48;
            color: #ffffff;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 11px;
            font-weight: 800;
            line-height: 1;
            padding: 2px 4px;
            border-radius: 3px;
            border: 1px solid #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.6);
            pointer-events: none;
            z-index: 2147483647;
        `;
        container.appendChild(badge);

        marks.push({
            id: currentId,
            tag: tag,
            text: cleanText,
            selector: sel,
            role: el.getAttribute('role') || null,
            box: {
                x: Math.round(rect.left),
                y: Math.round(rect.top),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
            }
        });

        currentId++;
    }

    return marks;
}
"""

SOM_REMOVAL_SCRIPT = """
() => {
    const container = document.getElementById('uxsentinel-som-container');
    if (container) container.remove();
    const badges = document.querySelectorAll('.uxsentinel-som-badge');
    badges.forEach(b => b.remove());
    return true;
}
"""

FOCAL_ELEMENTS_DETECTION_SCRIPT = """
() => {
    const focalSelectors = [
        'dialog[open]',
        '.modal.show',
        '.modal:not([style*="display: none"])',
        '[role="dialog"]:not([aria-hidden="true"])',
        '.swal2-modal',
        '.o_dialog',
        'table',
        '.table',
        '.o_list_table'
    ];

    const results = [];
    const elements = document.querySelectorAll(focalSelectors.join(', '));

    for (const el of elements) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

        const rect = el.getBoundingClientRect();
        if (rect.width <= 20 || rect.height <= 20) continue;

        const tag = el.tagName.toLowerCase();
        let sel = el.id ? `#${el.id}` : '';
        if (!sel && typeof el.className === 'string' && el.className.trim()) {
            sel = `.${el.className.trim().split(/\\s+/).slice(0, 2).join('.')}`;
        }
        if (!sel) sel = tag;

        const isModal = el.matches('dialog, [role="dialog"], .modal, .o_dialog, .swal2-modal');

        results.push({
            type: isModal ? 'modal' : 'table',
            tag: tag,
            selector: sel,
            box: {
                x: Math.round(rect.left),
                y: Math.round(rect.top),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
            }
        });
    }

    return results;
}
"""


class SetOfMarksManager:
    """Gerenciador de Set-of-Marks (SoM) e Smart Cropping para Playwright.

    Injeta marcadores visuais numéricos sobre elementos interativos para permitir
    que modelos de visão identifiquem precisamente os alvos sem alucinações de coordenadas.
    Também gerencia o recorte inteligente de componentes em foco (modais, tabelas).
    """

    async def inject_markers(self, page: Page) -> list[InteractiveMark]:
        """Injeta badges numéricos [1], [2], [3] nos elementos interativos visíveis."""
        try:
            raw_marks = await page.evaluate(SOM_INJECTION_SCRIPT)
            if not isinstance(raw_marks, list):
                return []
            return [InteractiveMark(**item) for item in raw_marks if isinstance(item, dict)]
        except Exception as exc:
            logger.warning("[SetOfMarksManager] Falha ao injetar marcadores SoM: %s", exc)
            return []

    async def remove_markers(self, page: Page) -> bool:
        """Remove completamente todos os marcadores SoM injetados."""
        try:
            await page.evaluate(SOM_REMOVAL_SCRIPT)
            return True
        except Exception as exc:
            logger.warning("[SetOfMarksManager] Falha ao remover marcadores SoM: %s", exc)
            return False

    @asynccontextmanager
    async def apply_som(self, page: Page) -> AsyncGenerator[list[InteractiveMark], None]:
        """Context manager seguro que garante a injeção e remoção limpa dos marcadores SoM."""
        marks: list[InteractiveMark] = []
        try:
            marks = await self.inject_markers(page)
            yield marks
        finally:
            await self.remove_markers(page)

    async def detect_focal_elements(self, page: Page) -> list[dict[str, Any]]:
        """Detecta elementos focais (como modais ativos e tabelas de dados) candidatos a smart cropping."""
        try:
            results = await page.evaluate(FOCAL_ELEMENTS_DETECTION_SCRIPT)
            return results if isinstance(results, list) else []
        except Exception as exc:
            logger.warning("[SetOfMarksManager] Falha ao detectar elementos focais: %s", exc)
            return []

    async def crop_focal_element(self, page: Page, selector: str, output_path: str) -> str | None:
        """Recorta um elemento focal específico da página e salva como imagem em disco."""
        try:
            locator = page.locator(selector).first
            if await locator.is_visible():
                await locator.screenshot(path=output_path)
                return output_path
        except Exception as exc:
            logger.warning("[SetOfMarksManager] Falha ao recortar elemento focal '%s': %s", selector, exc)
        return None
