import asyncio
import logging
import re
from difflib import SequenceMatcher

from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import Issue, IssueSeverity, ScenarioExceptions
from uxsentinel.vision.client import UnifiedVisionClient
from uxsentinel.vision.evaluators.base import BaseEvaluator, EvaluatorContext
from uxsentinel.vision.evaluators.domain import DomainQAAgent
from uxsentinel.vision.evaluators.layout import LayoutAgent
from uxsentinel.vision.evaluators.leakage import LeakageSentinel
from uxsentinel.vision.evaluators.linguist import LinguistAgent

logger = logging.getLogger("uxsentinel.vision.evaluators.orchestrator")

SEVERITY_WEIGHTS: dict[IssueSeverity, int] = {
    IssueSeverity.BLOQUEANTE: 4,
    IssueSeverity.ALTA: 3,
    IssueSeverity.MEDIA: 2,
    IssueSeverity.BAIXA: 1,
}


class MixtureOfEvaluators:
    """Orquestrador multiagente especializado que executa avaliadores de visão em paralelo,
    tolera falhas parciais e consolida/desduplica os achados com fusão inteligente.
    """

    def __init__(
        self,
        config: GlobalConfig,
        client: UnifiedVisionClient | None = None,
        evaluators: list[BaseEvaluator] | None = None,
    ):
        self.config = config
        self.client = client or UnifiedVisionClient(config)
        allowlist = getattr(config.vision, "i18n_allowlist", None)
        self.evaluators: list[BaseEvaluator] = (
            evaluators
            if evaluators is not None
            else [
                LinguistAgent(self.client, allowlist=allowlist),
                LeakageSentinel(self.client),
                LayoutAgent(self.client),
                DomainQAAgent(self.client),
            ]
        )

    async def evaluate(self, context: EvaluatorContext) -> list[Issue]:
        """Dispara todos os avaliadores especializados em paralelo via asyncio.gather.

        Tolerante a falhas parciais: se um ou mais avaliadores falharem, os demais continuam.
        """
        if not self.evaluators:
            logger.warning("Nenhum avaliador configurado no MixtureOfEvaluators.")
            return []

        logger.info(
            "Disparando Mixture of Evaluators (%d agentes) para checkpoint '%s'...",
            len(self.evaluators),
            context.checkpoint_name,
        )

        tasks = [evaluator.evaluate(context) for evaluator in self.evaluators]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        raw_issues: list[Issue] = []
        for evaluator, res in zip(self.evaluators, results, strict=False):
            if isinstance(res, BaseException):
                logger.warning(
                    "Avaliador '%s' falhou no checkpoint '%s': %s",
                    evaluator.name,
                    context.checkpoint_name,
                    res,
                    exc_info=True,
                )
                continue
            if isinstance(res, list):
                logger.info(
                    "Avaliador '%s' concluiu com %d inconformidade(s).",
                    evaluator.name,
                    len(res),
                )
                raw_issues.extend(res)

        consolidated = self.consolidate_and_deduplicate(raw_issues, exceptions=context.exceptions)
        logger.info(
            "Consolidação final: %d issues brutas reduzidas para %d issues consolidadas.",
            len(raw_issues),
            len(consolidated),
        )
        return consolidated

    def consolidate_and_deduplicate(
        self,
        issues: list[Issue],
        exceptions: ScenarioExceptions | None = None,
    ) -> list[Issue]:
        """Agrupa achados semelhantes relatados por diferentes avaliadores,
        preserva a severidade mais alta e unifica o rastreamento dos avaliadores.
        """
        if not issues:
            return []

        unique_issues: list[Issue] = []

        for candidate in issues:
            matched_index = -1
            for idx, existing in enumerate(unique_issues):
                if self._are_duplicates(existing, candidate):
                    matched_index = idx
                    break

            if matched_index >= 0:
                merged = self._merge_issues(unique_issues[matched_index], candidate)
                unique_issues[matched_index] = merged
            else:
                unique_issues.append(candidate)

        # Ordena as inconsistências por gravidade decrescente
        unique_issues.sort(
            key=lambda item: SEVERITY_WEIGHTS.get(item.severidade, 0),
            reverse=True,
        )

        if exceptions and not exceptions.is_empty():
            unique_issues = [i for i in unique_issues if not exceptions.matches_issue(i)]

        return unique_issues

    def _normalize(self, text: str | None) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip().lower()

    def _are_duplicates(self, a: Issue, b: Issue) -> bool:
        """Determina se duas inconsistências reportadas tratam do mesmo defeito."""
        norm_desc_a = self._normalize(a.descricao)
        norm_desc_b = self._normalize(b.descricao)

        elem_a = self._normalize(a.elemento_alvo)
        elem_b = self._normalize(b.elemento_alvo)

        # 1. Se ambos especificaram o mesmo elemento alvo não-vazio
        if elem_a and elem_b and elem_a == elem_b:
            # Se forem da mesma categoria ou descrições compartilharem similaridade razoável
            if a.categoria == b.categoria:
                return True
            ratio = SequenceMatcher(None, norm_desc_a, norm_desc_b).ratio()
            if ratio >= 0.45:
                return True

        # 2. Similaridade textual estrita das descrições
        ratio = SequenceMatcher(None, norm_desc_a, norm_desc_b).ratio()
        if ratio >= 0.72:
            return True

        # 3. Sobreposição de tokens de palavras-chave significativas
        words_a = set(re.findall(r"\b\w{4,}\b", norm_desc_a))
        words_b = set(re.findall(r"\b\w{4,}\b", norm_desc_b))
        if words_a and words_b:
            intersection = words_a.intersection(words_b)
            overlap_ratio = len(intersection) / min(len(words_a), len(words_b))
            if overlap_ratio >= 0.8:
                return True

        return False

    def _merge_issues(self, primary: Issue, secondary: Issue) -> Issue:
        """Funde duas inconsistências duplicadas, mantendo a maior severidade e rastreabilidade."""
        w_primary = SEVERITY_WEIGHTS.get(primary.severidade, 1)
        w_secondary = SEVERITY_WEIGHTS.get(secondary.severidade, 1)

        best_severity = primary.severidade if w_primary >= w_secondary else secondary.severidade
        best_category = primary.categoria if w_primary >= w_secondary else secondary.categoria

        # Preserva a melhor descrição ou a mais detalhada
        if w_secondary > w_primary:
            best_desc = secondary.descricao
        elif len(secondary.descricao) > len(primary.descricao) * 1.5:
            best_desc = f"{primary.descricao} ({secondary.descricao})"
        else:
            best_desc = primary.descricao

        # Mescla avaliadores responsáveis para transparência total
        evaluators: set[str] = set()
        for ev in (primary.evaluator, secondary.evaluator):
            if ev:
                for part in re.split(r",\s*", ev):
                    if part.strip():
                        evaluators.add(part.strip())
        merged_evaluators = ", ".join(sorted(evaluators)) if evaluators else None

        # Mescla elemento alvo e sugestão de correção
        target_elem = primary.elemento_alvo or secondary.elemento_alvo
        suggestion = primary.sugestao_correcao or secondary.sugestao_correcao
        if (
            primary.sugestao_correcao
            and secondary.sugestao_correcao
            and primary.sugestao_correcao != secondary.sugestao_correcao
        ):
            suggestion = (
                primary.sugestao_correcao
                if len(primary.sugestao_correcao) >= len(secondary.sugestao_correcao)
                else secondary.sugestao_correcao
            )

        code_snip = primary.trecho_codigo or secondary.trecho_codigo

        return Issue(
            categoria=best_category,
            severidade=best_severity,
            descricao=best_desc,
            sugestao_correcao=suggestion,
            elemento_alvo=target_elem,
            trecho_codigo=code_snip,
            viewport=primary.viewport or secondary.viewport,
            evaluator=merged_evaluators,
        )
