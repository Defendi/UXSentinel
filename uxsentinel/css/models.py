"""Modelos de dados para Auditoria e Inspeção de CSS (UXS-47)."""

from __future__ import annotations

from enum import Enum

try:
    from enum import StrEnum
except ImportError:

    class StrEnum(str, Enum):  # noqa: UP042
        pass


from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from uxsentinel.core.models import Issue


class CSSIssueCategory(StrEnum):
    OVERFLOW = "overflow"
    Z_INDEX = "z_index"
    TYPOGRAPHY = "typography"
    RESPONSIVENESS = "responsiveness"
    SPECIFICITY = "specificity"
    DUPLICATION = "duplication"
    MODERN_CSS = "modern_css"
    OTHER = "other"


class CSSSeverity(StrEnum):
    BLOQUEANTE = "bloqueante"
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class CSSViolation(BaseModel):
    rule_id: str
    category: CSSIssueCategory
    severity: CSSSeverity
    selector: str | None = None
    property_name: str | None = None
    value: str | None = None
    description: str
    suggestion: str | None = None
    snippet: str | None = None
    source: str = "runtime"  # runtime ou static


class CSSAuditReport(BaseModel):
    total_rules_inspected: int = 0
    violations: list[CSSViolation] = Field(default_factory=list)
    score: float = 100.0
    summary: dict[str, int] = Field(default_factory=dict)

    def calculate_score(self) -> float:
        """Calcula o score de qualidade CSS (0.0 a 100.0) de forma determinística."""
        weights = {
            CSSSeverity.BLOQUEANTE: 25.0,
            CSSSeverity.ALTA: 10.0,
            CSSSeverity.MEDIA: 4.0,
            CSSSeverity.BAIXA: 1.0,
        }
        penalty = 0.0
        summary_counts: dict[str, int] = {
            CSSSeverity.BLOQUEANTE.value: 0,
            CSSSeverity.ALTA.value: 0,
            CSSSeverity.MEDIA.value: 0,
            CSSSeverity.BAIXA.value: 0,
        }

        for v in self.violations:
            sev = v.severity
            sev_key = getattr(sev, "value", str(sev))
            if sev_key in summary_counts:
                summary_counts[sev_key] += 1
            penalty += weights.get(sev, 2.0)

        self.summary = summary_counts
        self.score = max(0.0, round(100.0 - penalty, 1))
        return self.score

    def to_issues(self, viewport: str | None = None) -> list[Issue]:
        """Converte as violações de CSS em instâncias unificadas de Issue do UXSentinel."""
        from uxsentinel.core.models import Issue, IssueCategory, IssueSeverity

        issues: list[Issue] = []
        for v in self.violations:
            sev_map = {
                CSSSeverity.BLOQUEANTE: IssueSeverity.BLOQUEANTE,
                CSSSeverity.ALTA: IssueSeverity.ALTA,
                CSSSeverity.MEDIA: IssueSeverity.MEDIA,
                CSSSeverity.BAIXA: IssueSeverity.BAIXA,
            }
            mapped_sev = sev_map.get(v.severity, IssueSeverity.MEDIA)

            # Categoria de issue: usa CSS se disponível ou LAYOUT como compatibilidade
            cat = getattr(IssueCategory, "CSS", IssueCategory.LAYOUT)

            desc = f"CSS [{v.rule_id}]: {v.description}"
            issues.append(
                Issue(
                    categoria=cat,
                    severidade=mapped_sev,
                    descricao=desc,
                    sugestao_correcao=v.suggestion,
                    elemento_alvo=v.selector,
                    trecho_codigo=v.snippet
                    or (f"{v.property_name}: {v.value};" if v.property_name else None),
                    viewport=viewport,
                    evaluator="css_inspector",
                )
            )
        return issues
