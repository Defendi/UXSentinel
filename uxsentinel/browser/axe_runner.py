"""Motor de Acessibilidade Axe-Core para Playwright e validação WCAG 2.2."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from uxsentinel.core.models import (
    AxeNodeResult,
    AxeViolation,
    Issue,
    IssueCategory,
    IssueSeverity,
)

logger = logging.getLogger("uxsentinel.browser.axe_runner")

# Tags padrão WCAG (2.0, 2.1 e 2.2 AA)
DEFAULT_WCAG_TAGS: list[str] = [
    "wcag2a",
    "wcag2aa",
    "wcag21a",
    "wcag21aa",
    "wcag22aa",
]

# Pesos para cálculo determinístico de A11y Score
IMPACT_WEIGHTS: dict[str, float] = {
    "critical": 10.0,
    "serious": 5.0,
    "moderate": 2.0,
    "minor": 1.0,
}

_CACHED_AXE_SCRIPT: str | None = None
_CACHED_AXE_LOCALE: dict[str, Any] | None = None

COMMON_FAILURE_TRANSLATIONS: list[tuple[str, str]] = [
    ("Fix any of the following:", "Corrija qualquer um dos seguintes:"),
    ("Fix all of the following:", "Corrija todos os seguintes:"),
    ("The element does not have a lang attribute", "O elemento <html> não possui um atributo 'lang'"),
    (
        "user-scalable=no on tag disables zooming on mobile devices",
        "user-scalable=no na tag <meta> desabilita o zoom em dispositivos móveis",
    ),
    ("aria-label attribute does not exist or is empty", "O atributo 'aria-label' não existe ou está vazio"),
    (
        "aria-labelledby attribute does not exist, references elements that do not exist or references elements that are empty",
        "O atributo 'aria-labelledby' não existe ou faz referência a elementos inexistentes ou vazios",
    ),
    ("Element has no title attribute", "O elemento não possui o atributo 'title'"),
    ("Element has insufficient color contrast of", "O elemento tem contraste de cor insuficiente de"),
    ("Expected contrast ratio of", "Contraste esperado no valor de"),
    ("Element does not have an accessible name", "O elemento não possui um nome acessível"),
    (
        "Element does not have text that is visible to screen readers",
        "O elemento não possui texto visível para leitores de tela",
    ),
    (
        "aria-hidden='true' is present on the document body",
        "aria-hidden='true' está presente no elemento <body>",
    ),
    ("Heading has no text", "O título não possui texto"),
    ("Table header has no text", "O cabeçalho da tabela não possui texto"),
    ("Images must have alternate text", "Imagens devem ter texto alternativo"),
    ("Document does not have a title", "O documento não possui um elemento <title>"),
]


def translate_failure_summary(summary: str | None) -> str | None:
    """Traduz termos e prefixos comuns de resumo de falha do axe-core para Português do Brasil."""
    if not summary:
        return summary

    translated = summary
    for en_text, pt_text in COMMON_FAILURE_TRANSLATIONS:
        if en_text in translated:
            translated = translated.replace(en_text, pt_text)
    return translated


def get_axe_locale() -> dict[str, Any]:
    """Carrega o catálogo de localização pt-BR oficial do axe-core dos assets empacotados.

    Garante execução nativa em Português do Brasil em ambientes locais e CI sem acesso externo.
    """
    global _CACHED_AXE_LOCALE
    if _CACHED_AXE_LOCALE is not None:
        return _CACHED_AXE_LOCALE

    candidates = [
        Path(__file__).resolve().parent.parent / "assets" / "axe_pt_BR.json",
        Path.cwd() / "uxsentinel" / "assets" / "axe_pt_BR.json",
    ]

    for cand in candidates:
        if cand.is_file():
            try:
                content = cand.read_text(encoding="utf-8")
                if content.strip():
                    _CACHED_AXE_LOCALE = json.loads(content)
                    return _CACHED_AXE_LOCALE
            except Exception as err:
                logger.warning("Falha ao ler axe_pt_BR.json de %s: %s", cand, err)

    _CACHED_AXE_LOCALE = {}
    return _CACHED_AXE_LOCALE


def get_axe_script() -> str:
    """Carrega o script JS minificado do axe-core a partir dos assets locais empacotados.

    Garante funcionamento 100% offline em ambientes CI sem acesso à internet.
    """
    global _CACHED_AXE_SCRIPT
    if _CACHED_AXE_SCRIPT is not None:
        return _CACHED_AXE_SCRIPT

    candidates = [
        Path(__file__).resolve().parent.parent / "assets" / "axe.min.js",
        Path.cwd() / "uxsentinel" / "assets" / "axe.min.js",
    ]

    for cand in candidates:
        if cand.is_file():
            try:
                content = cand.read_text(encoding="utf-8")
                if content.strip():
                    _CACHED_AXE_SCRIPT = content
                    return _CACHED_AXE_SCRIPT
            except OSError as err:
                logger.warning("Falha ao ler axe.min.js de %s: %s", cand, err)

    # Fallback caso os assets não estejam instalados ou acessíveis
    raise FileNotFoundError(
        "Script do axe-core ('axe.min.js') não encontrado em uxsentinel/assets/axe.min.js."
    )


def calculate_a11y_score(violations: list[AxeViolation]) -> float:
    """Calcula determinísticamente a pontuação de acessibilidade (A11y Score de 0 a 100%).

    Ponderado pela severidade das violações (critical, serious, moderate, minor)
    e pela contagem de nós afetados com amortecimento logarítmico/linear limitado.
    """
    if not violations:
        return 100.0

    total_deduction = 0.0
    for v in violations:
        impact = (v.impact or "moderate").lower()
        base_weight = IMPACT_WEIGHTS.get(impact, 2.0)
        node_count = max(1, len(v.nodes))
        # Fator de amortecimento para múltiplos nós na mesma regra
        node_multiplier = 1.0 + 0.25 * min(node_count - 1, 8)
        total_deduction += base_weight * node_multiplier

    score = max(0.0, 100.0 - total_deduction)
    return round(score, 1)


def _is_english_text(text: str | None) -> bool:
    """Verifica se o texto contém padrões e marcadores característicos da língua inglesa."""
    if not text:
        return False
    en_markers = (
        "ensure",
        "must",
        "should",
        "does not",
        "do not",
        "elements",
        "documents",
        "cannot",
        "fix any",
        "fix all",
    )
    text_lower = text.lower()
    return any(marker in text_lower for marker in en_markers)


def parse_axe_results(raw_violations: list[dict[str, Any]]) -> list[AxeViolation]:
    """Converte o payload bruto de violações retornado pelo axe.run() nos modelos Pydantic v2."""
    parsed: list[AxeViolation] = []
    locale_rules = get_axe_locale().get("rules", {})

    for item in raw_violations:
        rule_id = item.get("id", "unknown-rule")
        rule_loc = locale_rules.get(rule_id, {})

        desc = item.get("description", "")
        # Se a descrição estiver em inglês ou vazia, usa a do locale pt_BR
        if not desc or _is_english_text(desc):
            desc = rule_loc.get("description") or desc

        help_text = item.get("help")
        if not help_text or _is_english_text(help_text):
            help_text = rule_loc.get("help") or help_text

        nodes: list[AxeNodeResult] = []
        for n in item.get("nodes", []):
            target_val = n.get("target", [])
            target_list = target_val if isinstance(target_val, list) else [str(target_val)]
            # achata seletores caso venham aninhados
            flat_targets: list[str] = []
            for t in target_list:
                if isinstance(t, list):
                    flat_targets.extend(str(sub) for sub in t)
                else:
                    flat_targets.append(str(t))

            raw_summary = n.get("failureSummary")
            translated_summary = translate_failure_summary(raw_summary)

            nodes.append(
                AxeNodeResult(
                    target=flat_targets,
                    html=n.get("html", ""),
                    failure_summary=translated_summary,
                    impact=n.get("impact"),
                )
            )

        parsed.append(
            AxeViolation(
                id=rule_id,
                impact=item.get("impact"),
                description=desc,
                help_url=item.get("helpUrl"),
                help=help_text,
                tags=item.get("tags", []),
                nodes=nodes,
            )
        )
    return parsed


def convert_violations_to_issues(
    violations: list[AxeViolation],
    viewport: str | None = None,
    min_severity: str = "serious",
) -> list[Issue]:
    """Converte violações de acessibilidade em instâncias de Issue para o fluxo unificado do Sentinel.

    Por padrão, converte violações graves ('critical' e 'serious').
    """
    issues: list[Issue] = []

    for v in violations:
        impact = (v.impact or "moderate").lower()

        if min_severity == "serious" and impact not in ("critical", "serious"):
            continue

        if impact == "critical":
            sev = IssueSeverity.BLOQUEANTE
        elif impact == "serious":
            sev = IssueSeverity.ALTA
        elif impact == "moderate":
            sev = IssueSeverity.MEDIA
        else:
            sev = IssueSeverity.BAIXA

        first_node = v.nodes[0] if v.nodes else None
        target_el = first_node.target[0] if (first_node and first_node.target) else None
        html_snip = first_node.html if first_node else None

        sugestao_parts: list[str] = []
        if first_node and first_node.failure_summary:
            sugestao_parts.append(first_node.failure_summary)
        elif v.description:
            sugestao_parts.append(v.description)
        if v.help_url:
            sugestao_parts.append(f"Guia de correção: {v.help_url}")
        sugestao = "\n".join(sugestao_parts) if sugestao_parts else None

        regra_desc = v.help or v.description
        desc_prefix = f"Acessibilidade [{v.id}]: {regra_desc}"
        desc = f"{desc_prefix} ({len(v.nodes)} elementos afetados)" if len(v.nodes) > 1 else desc_prefix

        issues.append(
            Issue(
                categoria=IssueCategory.ACESSIBILIDADE,
                severidade=sev,
                descricao=desc,
                sugestao_correcao=sugestao,
                elemento_alvo=target_el,
                trecho_codigo=html_snip,
                viewport=viewport,
                evaluator="axe-core",
            )
        )

    return issues


class AxeRunner:
    """Orquestrador de execução do Axe-Core sobre páginas do Playwright."""

    def __init__(self, tags: list[str] | None = None):
        self.tags = tags or list(DEFAULT_WCAG_TAGS)

    async def inject(self, page: Any) -> bool:
        """Injeta o script do axe-core na página do Playwright se ainda não estiver presente."""
        try:
            is_present = await page.evaluate("() => typeof window.axe !== 'undefined'")
            if not is_present:
                script = get_axe_script()
                await page.evaluate(script)
            return True
        except Exception as exc:
            logger.warning("Não foi possível injetar o axe-core na página: %s", exc)
            return False

    async def run(
        self,
        page: Any,
        context: Any = None,
        tags: list[str] | None = None,
    ) -> list[AxeViolation]:
        """Executa axe.run() na página informada e retorna a lista de violações normalizadas."""
        injected = await self.inject(page)
        if not injected:
            return []

        active_tags = tags or self.tags
        run_payload = {
            "tags": active_tags,
            "context": context,
            "locale": get_axe_locale(),
        }

        eval_js = """
        async (payload) => {
            if (typeof window.axe === 'undefined') {
                return { error: 'axe-core não encontrado no escopo global window' };
            }
            try {
                if (payload.locale && Object.keys(payload.locale).length > 0) {
                    window.axe.configure({ locale: payload.locale });
                }
                const options = {
                    runOnly: {
                        type: 'tag',
                        values: payload.tags
                    }
                };
                const results = await window.axe.run(payload.context || document, options);
                return {
                    violations: results.violations || [],
                    passes_count: (results.passes || []).length,
                    incomplete_count: (results.incomplete || []).length,
                };
            } catch (err) {
                return { error: err.message || String(err) };
            }
        }
        """

        try:
            res = await page.evaluate(eval_js, run_payload)
            if not isinstance(res, dict):
                logger.warning("Resposta inesperada do axe-core: %s", res)
                return []

            if "error" in res:
                logger.warning("axe.run() retornou erro: %s", res["error"])
                return []

            raw_violations = res.get("violations", [])
            return parse_axe_results(raw_violations)
        except Exception as exc:
            logger.warning("Falha durante a execução do axe-core na página: %s", exc)
            return []
