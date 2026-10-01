"""Módulo de resolução de seletores robustos para o Recorder (UXS-94).

Analisa um nó DOM / ElementHandle do Playwright e infere a identificação de elemento
mais resiliente e legível, seguindo estritamente a hierarquia de robustez:
1. TESTID (data-testid, data-test, data-cy)
2. ROLE (role semântico + accessible name)
3. LABEL (label associado a inputs)
4. TEXT (texto visível estável)
5. CSS (ID estático ou classes semânticas estáveis)
6. XPATH (caminho canônico como último recurso)
"""

import logging
from typing import Any

from playwright.async_api import ElementHandle

from uxsentinel.browser.recorder.models import (
    RecordedTarget,
    SelectorCandidate,
    SelectorStrategy,
)

logger = logging.getLogger("uxsentinel.browser.recorder.resolver")

ELEMENT_INSPECTION_SCRIPT = """
(element, testIdAttrs) => {
    if (!element || element.nodeType !== 1) {
        return null;
    }

    // 1. Snippet HTML bruto
    let outerHtml = null;
    try {
        outerHtml = element.outerHTML || null;
    } catch (_) {}

    // 2. Test ID
    let testIdVal = null;
    const attrsToCheck = (Array.isArray(testIdAttrs) && testIdAttrs.length > 0)
        ? testIdAttrs
        : ['data-testid', 'data-test', 'data-cy'];
    for (const attr of attrsToCheck) {
        if (element.hasAttribute && element.hasAttribute(attr)) {
            const val = element.getAttribute(attr);
            if (val && val.trim().length > 0) {
                testIdVal = val.trim();
                break;
            }
        }
    }

    // 3. Role e Accessible Name
    let role = null;
    let accessibleName = null;
    const tag = (element.tagName || '').toLowerCase();

    // Determinar Role
    if (element.hasAttribute && element.hasAttribute('role')) {
        const rawRole = element.getAttribute('role');
        if (rawRole && rawRole.trim().length > 0) {
            role = rawRole.trim();
        }
    }
    if (!role) {
        const implicitRoles = {
            'button': 'button',
            'a': element.hasAttribute && element.hasAttribute('href') ? 'link' : null,
            'select': 'combobox',
            'textarea': 'textbox',
            'h1': 'heading',
            'h2': 'heading',
            'h3': 'heading',
            'h4': 'heading',
            'h5': 'heading',
            'h6': 'heading',
            'img': 'img',
        };
        if (tag === 'input') {
            const type = (element.getAttribute('type') || 'text').toLowerCase();
            if (['button', 'submit', 'reset'].includes(type)) {
                role = 'button';
            } else if (type === 'checkbox') {
                role = 'checkbox';
            } else if (type === 'radio') {
                role = 'radio';
            } else {
                role = 'textbox';
            }
        } else if (implicitRoles[tag]) {
            role = implicitRoles[tag];
        } else if (['button', 'a', 'input', 'select', 'textarea'].includes(tag)) {
            role = tag;
        }
    }

    // Determinar Accessible Name
    if (element.hasAttribute && element.hasAttribute('aria-label')) {
        const ariaLabel = element.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.trim().length > 0) {
            accessibleName = ariaLabel.trim();
        }
    } else if (element.hasAttribute && element.hasAttribute('aria-labelledby')) {
        const ids = element.getAttribute('aria-labelledby').split(/\\s+/);
        const labels = [];
        for (const id of ids) {
            const labelEl = document.getElementById(id);
            if (labelEl) {
                const txt = (labelEl.innerText || labelEl.textContent || '').trim();
                if (txt) labels.push(txt);
            }
        }
        if (labels.length > 0) {
            accessibleName = labels.join(' ');
        }
    }
    if (!accessibleName) {
        if (tag === 'button' || role === 'button') {
            const txt = (element.innerText || element.textContent || element.value || '').trim();
            if (txt) accessibleName = txt;
        } else if (tag === 'a' || role === 'link') {
            const txt = (element.innerText || element.textContent || '').trim();
            if (txt) accessibleName = txt;
        } else if (tag === 'img' && element.hasAttribute && element.hasAttribute('alt')) {
            const alt = element.getAttribute('alt');
            if (alt && alt.trim().length > 0) accessibleName = alt.trim();
        }
    }

    // 4. Label associado (input / textarea / select)
    let labelText = null;
    if (element.id) {
        try {
            const escapedId = (window.CSS && CSS.escape) ? CSS.escape(element.id) : element.id;
            const labelEl = document.querySelector(`label[for="${escapedId}"]`);
            if (labelEl) {
                const txt = (labelEl.innerText || labelEl.textContent || '').trim();
                if (txt) labelText = txt;
            }
        } catch (_) {}
    }
    if (!labelText && element.closest) {
        try {
            const parentLabel = element.closest('label');
            if (parentLabel) {
                const txt = (parentLabel.innerText || parentLabel.textContent || '').trim();
                if (txt) labelText = txt;
            }
        } catch (_) {}
    }

    // 5. Texto visível estável
    let visibleText = null;
    const rawText = (element.innerText || element.textContent || '').trim();
    if (rawText && rawText.length > 0 && rawText.length <= 100) {
        visibleText = rawText.replace(/\\s+/g, ' ');
    }

    // 6. CSS estável
    let cssSelector = null;
    const isStableId = (id) => {
        if (!id || typeof id !== 'string') return false;
        if (/[:\\/\\\\]/.test(id)) return false;
        if (/^[0-9a-f]{8,}$/i.test(id)) return false;
        if (/__\\d+/.test(id)) return false;
        if (/ember\\d+/.test(id)) return false;
        return true;
    };

    if (element.id && isStableId(element.id)) {
        const escapedId = (window.CSS && CSS.escape) ? CSS.escape(element.id) : element.id;
        cssSelector = `#${escapedId}`;
    } else if (element.classList && element.classList.length > 0) {
        const stableClasses = [];
        const isUnstableClass = (cls) => {
            if (/[:\\[\\]\\/\\\\]/.test(cls)) return true;
            if (/^[a-z0-9_-]{15,}$/i.test(cls)) return true;
            if (/^(css|sc)-[a-z0-9]+/i.test(cls)) return true;
            if (/^style_/.test(cls)) return true;
            return false;
        };

        for (const cls of Array.from(element.classList)) {
            if (!isUnstableClass(cls) && cls.trim().length > 1) {
                stableClasses.push(cls.trim());
            }
        }

        if (stableClasses.length > 0) {
            const classPart = stableClasses.slice(0, 2).map(c => {
                const esc = (window.CSS && CSS.escape) ? CSS.escape(c) : c;
                return `.${esc}`;
            }).join('');
            cssSelector = `${tag}${classPart}`;
        }
    }
    if (!cssSelector && tag) {
        cssSelector = tag;
    }

    // 7. XPath canônico
    let xpath = null;
    try {
        let current = element;
        let path = '';
        while (current && current.nodeType === 1 && current !== document.documentElement) {
            if (current === document.body) {
                path = '/html/body' + path;
                break;
            }
            let index = 1;
            let sibling = current.previousElementSibling;
            while (sibling) {
                if (sibling.tagName === current.tagName) {
                    index++;
                }
                sibling = sibling.previousElementSibling;
            }
            const currTag = current.tagName.toLowerCase();
            path = '/' + currTag + '[' + index + ']' + path;
            current = current.parentElement;
        }
        xpath = path || null;
    } catch (_) {}

    return {
        tag: tag,
        testId: testIdVal,
        role: role,
        accessibleName: accessibleName,
        labelText: labelText,
        visibleText: visibleText,
        cssSelector: cssSelector,
        xpath: xpath,
        outerHtml: outerHtml,
    };
}
"""


class ElementResolver:
    """Inferência de identificação de elementos DOM resiliente e legível.

    Implementa a cascata de resolução estrita definida no UXS-94:
    1. TESTID (data-testid, data-test, data-cy)
    2. ROLE (role semântico + accessible name inequívoco)
    3. LABEL (label for ou label envelopante)
    4. TEXT (texto visível estável)
    5. CSS (ID estável ou classes semânticas)
    6. XPATH (caminho canônico como último recurso)
    """

    DEFAULT_TEST_ID_ATTRIBUTES: list[str] = [
        "data-testid",
        "data-test",
        "data-cy",
    ]

    def __init__(
        self,
        test_id_attributes: list[str] | None = None,
    ) -> None:
        """Inicializa o resolver com atributos de teste customizáveis.

        Args:
            test_id_attributes: Lista de nomes de atributos de teste a considerar.
                Padrão: ["data-testid", "data-test", "data-cy"].
        """
        self.test_id_attributes = (
            list(test_id_attributes)
            if test_id_attributes is not None
            else list(self.DEFAULT_TEST_ID_ATTRIBUTES)
        )

    async def resolve(
        self,
        element: ElementHandle | dict[str, Any],
        raw_html_snippet: str | None = None,
    ) -> RecordedTarget:
        """Resolve o elemento DOM em um RecordedTarget com seletor primário e fallbacks.

        Args:
            element: ElementHandle do Playwright ou dicionário de dados a inspecionar.
            raw_html_snippet: Snippet HTML bruto opcional para depuração ou fallback.

        Returns:
            RecordedTarget estruturado com o seletor primário e fallbacks ordenados.
        """
        snippet: str | None = None
        if isinstance(raw_html_snippet, str) and raw_html_snippet.strip():
            snippet = raw_html_snippet.strip()
        else:
            attr_snippet = getattr(element, "raw_html_snippet", None)
            if isinstance(attr_snippet, str) and attr_snippet.strip():
                snippet = attr_snippet.strip()

        if isinstance(element, dict):
            return self._build_target(element, snippet)

        try:
            raw_data = await element.evaluate(
                ELEMENT_INSPECTION_SCRIPT,
                self.test_id_attributes,
            )
            if not isinstance(raw_data, dict):
                return RecordedTarget(
                    primary=None,
                    fallbacks=[],
                    raw_html_snippet=snippet,
                )
            return self._build_target(raw_data, snippet)
        except Exception as exc:
            logger.warning(
                "Falha ao inspecionar elemento no DOM para resolução de seletor: %s",
                exc,
                exc_info=True,
            )
            return RecordedTarget(
                primary=None,
                fallbacks=[],
                raw_html_snippet=snippet,
            )

    def resolve_target_data(
        self,
        raw_data: dict[str, Any] | None,
        raw_html_snippet: str | None = None,
    ) -> RecordedTarget | None:
        """Resolve um dicionário de metadados do elemento em RecordedTarget."""
        if not raw_data or not isinstance(raw_data, dict):
            return None
        return self._build_target(raw_data, fallback_snippet=raw_html_snippet)

    def _build_target(
        self,
        raw_data: dict[str, Any],
        fallback_snippet: str | None = None,
    ) -> RecordedTarget:
        """Constrói o RecordedTarget aplicando a hierarquia estrita de seletores.

        Args:
            raw_data: Dicionário retornado pela inspeção do DOM ou mock.
            fallback_snippet: Snippet HTML previamente capturado.

        Returns:
            RecordedTarget com candidate primary e fallbacks ordenados.
        """
        test_id_keys = [
            "testId",
            "test_id",
            *self.test_id_attributes,
            *self.DEFAULT_TEST_ID_ATTRIBUTES,
        ]
        test_id = self._extract_str(raw_data, *test_id_keys)
        role = self._extract_str(raw_data, "role")
        accessible_name = self._extract_str(
            raw_data,
            "accessibleName",
            "accessible_name",
            "name",
            "aria-label",
        )
        label_text = self._extract_str(
            raw_data,
            "labelText",
            "label_text",
            "label",
        )
        visible_text = self._extract_str(
            raw_data,
            "visibleText",
            "visible_text",
            "text",
        )
        css_selector = self._extract_str(
            raw_data,
            "cssSelector",
            "css_selector",
            "css",
        )
        xpath = self._extract_str(raw_data, "xpath")

        outer_html = fallback_snippet or self._extract_str(
            raw_data,
            "outerHtml",
            "outer_html",
            "raw_html_snippet",
        )

        candidates: list[SelectorCandidate] = []

        # Nível 1: TESTID
        if test_id:
            candidates.append(
                SelectorCandidate(
                    strategy=SelectorStrategy.TESTID,
                    value=test_id,
                )
            )

        # Nível 2: ROLE (role semântico + accessible name inequívoco)
        if role and accessible_name:
            candidates.append(
                SelectorCandidate(
                    strategy=SelectorStrategy.ROLE,
                    value=role,
                    name=accessible_name,
                )
            )

        # Nível 3: LABEL
        if label_text:
            candidates.append(
                SelectorCandidate(
                    strategy=SelectorStrategy.LABEL,
                    value=label_text,
                )
            )

        # Nível 4: TEXT
        if visible_text:
            candidates.append(
                SelectorCandidate(
                    strategy=SelectorStrategy.TEXT,
                    value=visible_text,
                )
            )

        # Nível 5: CSS
        if css_selector:
            candidates.append(
                SelectorCandidate(
                    strategy=SelectorStrategy.CSS,
                    value=css_selector,
                )
            )

        # Nível 6: XPATH
        if xpath:
            candidates.append(
                SelectorCandidate(
                    strategy=SelectorStrategy.XPATH,
                    value=xpath,
                )
            )

        if not candidates:
            return RecordedTarget(
                primary=None,
                fallbacks=[],
                raw_html_snippet=outer_html,
            )

        primary = candidates[0]
        raw_fallbacks = candidates[1:]

        # Regra: Sempre que primary for diferente de XPATH, garantir XPATH como fallback se disponível
        if (
            xpath
            and primary.strategy != SelectorStrategy.XPATH
            and not any(fb.strategy == SelectorStrategy.XPATH for fb in raw_fallbacks)
        ):
            raw_fallbacks.append(
                SelectorCandidate(
                    strategy=SelectorStrategy.XPATH,
                    value=xpath,
                )
            )

        # Deduplicação mantendo a ordem estrita
        fallbacks: list[SelectorCandidate] = []
        for fb in raw_fallbacks:
            if fb != primary and fb not in fallbacks:
                fallbacks.append(fb)

        return RecordedTarget(
            primary=primary,
            fallbacks=fallbacks,
            raw_html_snippet=outer_html,
        )

    @staticmethod
    def _extract_str(data: dict[str, Any], *keys: str) -> str | None:
        """Extrai a primeira string não vazia correspondente a uma das chaves."""
        for key in keys:
            val = data.get(key)
            if isinstance(val, str):
                trimmed = val.strip()
                if trimmed:
                    return trimmed
        return None
