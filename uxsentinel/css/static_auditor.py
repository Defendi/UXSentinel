"""Auditor estático de código CSS (UXS-47)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from uxsentinel.css.models import CSSAuditReport, CSSIssueCategory, CSSSeverity, CSSViolation

logger = logging.getLogger("uxsentinel.css.static_auditor")

# Expressão para remover comentários CSS
COMMENT_REGEX = re.compile(r"/\*.*?\*/", re.DOTALL)

# Expressão para capturar blocos seletor { declaracoes }
# Suporta at-rules ignorando @media, @keyframes, etc. ou capturando regras internas
RULE_REGEX = re.compile(r"([^{}]+)\{([^{}]+)\}", re.DOTALL)


def _clean_css(css_text: str) -> str:
    """Remove comentários do CSS."""
    return COMMENT_REGEX.sub("", css_text)


class CSSStaticAuditor:
    """Auditor de regras e boas práticas CSS estático."""

    @classmethod
    def audit_text(cls, css_text: str, filename: str | None = None) -> CSSAuditReport:
        report = CSSAuditReport()
        if not css_text or not css_text.strip():
            return report

        clean_text = _clean_css(css_text)
        rules = RULE_REGEX.findall(clean_text)
        report.total_rules_inspected = len(rules)

        violations: list[CSSViolation] = []

        # 4. Detecções Modern CSS no escopo geral / por regra
        # Sugestão de CSS custom properties (se houver muitas cores hex repetidas sem variáveis)
        has_custom_props = "--" in clean_text
        hex_colors = re.findall(r"#(?:[0-9a-fA-F]{3,8})", clean_text)
        if len(hex_colors) >= 8 and not has_custom_props:
            violations.append(
                CSSViolation(
                    rule_id="css-modern-custom-properties",
                    category=CSSIssueCategory.MODERN_CSS,
                    severity=CSSSeverity.BAIXA,
                    selector=":root",
                    property_name="variables",
                    description=f"Identificadas {len(hex_colors)} definições literais de cor sem o uso de variáveis CSS custom properties (--*).",
                    suggestion="Considere centralizar temas e paletas de cores no seletor :root com CSS Variables (ex: var(--primary-color)).",
                    snippet=":root { --primary-color: #3b82f6; }",
                    source="static",
                )
            )

        # Sugestão de aspect-ratio se houver padding hack (padding-top/bottom em %)
        if re.search(r"padding-(?:top|bottom)\s*:\s*\d+(?:\.\d+)?%", clean_text, re.IGNORECASE):
            violations.append(
                CSSViolation(
                    rule_id="css-modern-aspect-ratio",
                    category=CSSIssueCategory.MODERN_CSS,
                    severity=CSSSeverity.BAIXA,
                    selector="*",
                    property_name="aspect-ratio",
                    description="Detecção de possível hack de proporção com padding percentual.",
                    suggestion="Substitua o clássico padding hack pela propriedade nativa moderna aspect-ratio (ex: aspect-ratio: 16 / 9).",
                    snippet="element { aspect-ratio: 16 / 9; }",
                    source="static",
                )
            )

        # Sugestão de clamp() para responsividade fluida se houver muitos media queries de font-size
        font_size_px = re.findall(r"font-size\s*:\s*\d+px", clean_text, re.IGNORECASE)
        if len(font_size_px) >= 6 and "@media" in clean_text and "clamp(" not in clean_text:
            violations.append(
                CSSViolation(
                    rule_id="css-modern-clamp-fluid-typography",
                    category=CSSIssueCategory.MODERN_CSS,
                    severity=CSSSeverity.BAIXA,
                    selector="*",
                    property_name="font-size",
                    description="Múltiplas definições de font-size em pixels identificadas sem o uso da função clamp().",
                    suggestion="Utilize clamp() para tipografia e espaçamentos fluidos e responsivos (ex: font-size: clamp(1rem, 2.5vw, 2rem)).",
                    snippet="font-size: clamp(1rem, 2vw, 1.5rem);",
                    source="static",
                )
            )

        # Sugestão de :has() se houver aninhamentos complexos JS para seleção de pai
        # (Auditoria de boas práticas)

        for raw_selector, raw_body in rules:
            selector = raw_selector.strip()
            # Ignora at-rules puras (@keyframes 0% etc)
            if selector.startswith("@") and not selector.startswith(("@media", "@supports")):
                continue

            # Quebra seletores múltiplos separados por vírgula (fora de parênteses)
            sub_selectors = [s.strip() for s in re.split(r",(?![^(]*\))", selector) if s.strip()]

            # 2. Alta Especificidade / Chaining Excessivo
            for sub_sel in sub_selectors:
                if sub_sel.startswith("@"):
                    continue

                # Contagem de IDs
                ids = re.findall(r"#[a-zA-Z0-9_-]+", sub_sel)
                if len(ids) > 3:
                    violations.append(
                        CSSViolation(
                            rule_id="css-high-specificity-ids",
                            category=CSSIssueCategory.SPECIFICITY,
                            severity=CSSSeverity.ALTA,
                            selector=sub_sel,
                            property_name="selector",
                            value=str(len(ids)),
                            description=f"Seletor com especificidade abusiva contendo {len(ids)} IDs encadeados: '{sub_sel}'.",
                            suggestion="Evite encadear múltiplos IDs no mesmo seletor. Prefira classes modulares (BEM ou utilitárias).",
                            snippet=f"{sub_sel} {{ ... }}",
                            source="static",
                        )
                    )

                # Contagem de classes e tags combinadas
                # Remove seletores pseudo-classes com argumentos para análise limpa
                simplified = re.sub(r":\w+\([^)]*\)", "", sub_sel)
                # Conta tokens separados por combinadores (espaço, >, +, ~)
                tokens = re.split(r"[\s>+~]+", simplified)
                tokens = [t for t in tokens if t.strip()]
                classes = re.findall(r"\.[a-zA-Z0-9_-]+", sub_sel)

                if len(tokens) > 4 or len(classes) > 4:
                    violations.append(
                        CSSViolation(
                            rule_id="css-excessive-chaining",
                            category=CSSIssueCategory.SPECIFICITY,
                            severity=CSSSeverity.MEDIA,
                            selector=sub_sel,
                            property_name="selector",
                            value=f"{len(tokens)} tokens / {len(classes)} classes",
                            description=f"Seletor com encadeamento excessivo de {len(tokens)} níveis: '{sub_sel}'.",
                            suggestion="Simplifique o seletor para no máximo 3 níveis para evitar dependência rígida da estrutura HTML.",
                            snippet=f"{sub_sel} {{ ... }}",
                            source="static",
                        )
                    )

            # Analisa o corpo da regra (declarações)
            declarations = [d.strip() for d in raw_body.split(";") if d.strip()]
            seen_properties: dict[str, str] = {}

            for decl in declarations:
                if ":" not in decl:
                    continue
                prop_name, prop_val = decl.split(":", 1)
                prop_name = prop_name.strip().lower()
                prop_val = prop_val.strip()

                # 1. Uso de !important
                if "!important" in prop_val.lower():
                    violations.append(
                        CSSViolation(
                            rule_id="css-important-usage",
                            category=CSSIssueCategory.SPECIFICITY,
                            severity=CSSSeverity.MEDIA,
                            selector=selector,
                            property_name=prop_name,
                            value=prop_val,
                            description=f"Uso de '!important' na propriedade '{prop_name}'. Quebra a cascata natural de especificidade.",
                            suggestion="Resolva a prioridade reestruturando a especificidade dos seletores ou a ordem de importação.",
                            snippet=f"{selector} {{ {prop_name}: {prop_val}; }}",
                            source="static",
                        )
                    )

                # 3. Propriedades Duplicadas dentro do mesmo bloco
                # Normaliza valor
                norm_val = prop_val.lower().replace(" ", "")
                if prop_name in seen_properties:
                    prev_val = seen_properties[prop_name]
                    norm_prev = prev_val.lower().replace(" ", "")
                    # Se mesmo valor ou valor redundante
                    if norm_val == norm_prev:
                        violations.append(
                            CSSViolation(
                                rule_id="css-duplicate-property",
                                category=CSSIssueCategory.DUPLICATION,
                                severity=CSSSeverity.BAIXA,
                                selector=selector,
                                property_name=prop_name,
                                value=prop_val,
                                description=f"Propriedade duplicada '{prop_name}' com valor idêntico dentro da mesma regra.",
                                suggestion="Remova a declaração redundante para manter o código CSS enxuto.",
                                snippet=f"{selector} {{ {prop_name}: {prev_val}; ... {prop_name}: {prop_val}; }}",
                                source="static",
                            )
                        )
                    else:
                        violations.append(
                            CSSViolation(
                                rule_id="css-overridden-property",
                                category=CSSIssueCategory.DUPLICATION,
                                severity=CSSSeverity.BAIXA,
                                selector=selector,
                                property_name=prop_name,
                                value=prop_val,
                                description=f"Propriedade '{prop_name}' declarada mais de uma vez no mesmo bloco (valor anterior '{prev_val}' substituído por '{prop_val}').",
                                suggestion="Mantenha apenas o valor pretendido, a menos que seja um fallback intencional para navegadores legados.",
                                snippet=f"{selector} {{ {prop_name}: {prev_val}; ... {prop_name}: {prop_val}; }}",
                                source="static",
                            )
                        )
                else:
                    seen_properties[prop_name] = prop_val

        report.violations = violations
        report.calculate_score()
        return report

    @classmethod
    def audit_file(cls, file_path: str | Path) -> CSSAuditReport:
        p = Path(file_path)
        if not p.is_file():
            report = CSSAuditReport()
            report.violations.append(
                CSSViolation(
                    rule_id="css-file-not-found",
                    category=CSSIssueCategory.OTHER,
                    severity=CSSSeverity.ALTA,
                    description=f"Arquivo CSS não encontrado: {p}",
                    source="static",
                )
            )
            report.calculate_score()
            return report

        try:
            content = p.read_text(encoding="utf-8")
            return cls.audit_text(content, filename=p.name)
        except Exception as exc:
            report = CSSAuditReport()
            report.violations.append(
                CSSViolation(
                    rule_id="css-file-read-error",
                    category=CSSIssueCategory.OTHER,
                    severity=CSSSeverity.ALTA,
                    description=f"Falha ao ler arquivo CSS '{p.name}': {exc}",
                    source="static",
                )
            )
            report.calculate_score()
            return report
