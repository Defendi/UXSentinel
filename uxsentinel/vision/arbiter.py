import json
import logging
import re

from uxsentinel.core.models import Issue, IssueSeverity
from uxsentinel.vision.client import UnifiedVisionClient

logger = logging.getLogger("uxsentinel.vision.arbiter")

DEVILS_ADVOCATE_SYSTEM_PROMPT = """
Você é o Devil's Advocate Arbiter do UXSentinel, o juiz cético e impiedoso contra falsos positivos, alucinações de IA e julgamentos puramente subjetivos em auditorias visuais de software corporativo.

Sua ÚNICA missão é auditar criticamente uma lista de inconsistências classificadas preliminarmente com severidade CRÍTICA (Bloqueante) ou ALTA (Major).
Sua postura é: IN DUBIO PRO REO (Na dúvida, descarte ou rebaixe).
Apenas sustente como BLOQUEANTE ou ALTA se houver EVIDÊNCIA VISUAL OU GEOMÉTRICA CONCRETA, IRREFUTÁVEL e CLARA na imagem anexa de que a funcionalidade está quebrada ou gravemente comprometida.

Regras de Julgamento:
1. DESCARTAR (veredicto: "descartar"):
   - Alucinações da IA avaliadora anterior (ex: alega que um texto ou botão está em inglês, mas na imagem anexa está em português correto).
   - Alegações de sobreposição, corte de texto ou quebra de layout que NÃO são visíveis na imagem.
   - Termos técnicos corporativos normais (ex: 'Status', 'Lead', 'Dashboard', 'Login', 'Logout', 'Feedback').
   - Falsos positivos onde o comportamento é claramente aceitável ou esperado.
2. REBAIXAR (veredicto: "rebaixar"):
   - O apontamento existe visualmente, porém é puramente cosmético, estilístico, espaçamento sutil ou preferência de design sem prejuízo à usabilidade.
   - Ajustar para severidade "media" ou "baixa".
3. MANTER (veredicto: "manter"):
   - O problema é comprovado matematicamente ou visualmente na imagem, impede a compreensão do usuário, quebra componentes ou bloqueia a tarefa de negócio.

Formato de Resposta Obrigatório (JSON estrito, sem markdown ao redor):
{
  "arbitration": [
    {
      "id": 1,
      "veredicto": "manter" | "rebaixar" | "descartar",
      "severidade_final": "bloqueante" | "alta" | "media" | "baixa",
      "justificativa": "Razão concisa comprovada pela evidência visual observada"
    }
  ]
}
""".strip()


class DevilsAdvocateArbiter:
    """Árbitro reverso que desafia severamente apontamentos de alta gravidade (Bloqueante / Alta)
    para erradicar alucinações e falsos positivos através de análise cética multimodal.
    """

    def __init__(
        self,
        client: UnifiedVisionClient,
        threshold_severities: list[IssueSeverity] | None = None,
        enabled: bool = True,
    ):
        self.client = client
        self.threshold_severities = threshold_severities or [
            IssueSeverity.BLOQUEANTE,
            IssueSeverity.ALTA,
        ]
        self.enabled = enabled

    async def arbitrate(
        self,
        issues: list[Issue],
        image_base64: str,
        checkpoint_name: str,
        expected_behavior: str,
        dom_text: str = "",
        viewport: str | None = None,
    ) -> list[Issue]:
        """Avalia as inconsistências de alta gravidade contra a evidência visual e descarta alucinações."""
        if not self.enabled or not issues or not image_base64:
            return issues

        # Separa as issues que precisam ser desafiadas daquelas já em severidade baixa/média
        candidates: list[tuple[int, Issue]] = []
        unchallenged: list[Issue] = []

        for idx, issue in enumerate(issues, start=1):
            if issue.severidade in self.threshold_severities:
                candidates.append((idx, issue))
            else:
                unchallenged.append(issue)

        if not candidates:
            # Nenhuma issue crítica ou alta para arbitrar
            return issues

        logger.info(
            "[DevilsAdvocateArbiter] Desafiando %d inconsistências de alta severidade no checkpoint '%s'...",
            len(candidates),
            checkpoint_name,
        )

        candidates_payload = [
            {
                "id": cid,
                "categoria": issue.categoria.value,
                "severidade": issue.severidade.value,
                "descricao": issue.descricao,
                "elemento_alvo": issue.elemento_alvo,
                "sugestao_correcao": issue.sugestao_correcao,
            }
            for cid, issue in candidates
        ]

        vp_info = f"\nResolução da Viewport: {viewport}" if viewport else ""
        dom_snippet = dom_text[:2000] if dom_text else "(Nenhum texto do DOM disponível)"

        user_prompt = f"""
Checkpoint Auditado: {checkpoint_name}{vp_info}
Comportamento Esperado: {expected_behavior}

TRECHO AUXILIAR DO DOM:
{dom_snippet}

INCONSISTÊNCIAS DE ALTA SEVERIDADE PARA ARBITRAGEM (DESAFIO CÉTICO):
{json.dumps(candidates_payload, ensure_ascii=False, indent=2)}

Analise a imagem com ceticismo forense. Confirme apenas o que tiver prova visual irrefutável.
Descarte alucinações e rebaixe apontamentos meramente cosméticos.
Retorne o JSON de arbitragem.
""".strip()

        try:
            raw_response = await self.client.analyze(
                image_base64=image_base64,
                user_prompt=user_prompt,
                system_prompt=DEVILS_ADVOCATE_SYSTEM_PROMPT,
            )
            return self._process_verdicts(raw_response, candidates, unchallenged)
        except Exception as exc:
            logger.warning(
                "[DevilsAdvocateArbiter] Falha na arbitragem do checkpoint '%s': %s. Mantendo issues originais como fallback seguro.",
                checkpoint_name,
                exc,
            )
            return issues

    def _extract_json(self, text: str) -> str:
        text = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1).strip()
        start_obj = text.find("{")
        if start_obj != -1:
            end_obj = text.rfind("}")
            if end_obj != -1:
                return text[start_obj : end_obj + 1]
        return text

    def _process_verdicts(
        self,
        raw_response: str,
        candidates: list[tuple[int, Issue]],
        unchallenged: list[Issue],
    ) -> list[Issue]:
        clean_json = self._extract_json(raw_response)
        verdicts_list: list[dict] = []

        try:
            parsed = json.loads(clean_json)
            if isinstance(parsed, dict):
                verdicts_list = parsed.get("arbitration", [])
            elif isinstance(parsed, list):
                verdicts_list = parsed
        except Exception as err:
            logger.warning(
                "[DevilsAdvocateArbiter] Erro ao decodificar veredictos: %s. Resposta bruta: %s",
                err,
                raw_response[:200],
            )
            return [issue for _, issue in candidates] + unchallenged

        verdict_by_id = {int(v.get("id", 0)): v for v in verdicts_list if isinstance(v, dict)}

        final_candidates: list[Issue] = []
        for cid, original_issue in candidates:
            v_data = verdict_by_id.get(cid)
            if not v_data:
                # Não mencionado pelo árbitro: mantém issue original
                final_candidates.append(original_issue)
                continue

            veredicto = str(v_data.get("veredicto", "manter")).strip().lower()
            justificativa = str(v_data.get("justificativa", "")).strip()

            if veredicto == "descartar":
                logger.info(
                    "[DevilsAdvocateArbiter] DESCARTADA (Falso positivo/Alucinação): '%s' | Motivo: %s",
                    original_issue.descricao,
                    justificativa,
                )
                continue

            elif veredicto == "rebaixar":
                target_sev_str = str(v_data.get("severidade_final", "media")).strip().lower()
                new_sev = IssueSeverity.MEDIA
                for s in IssueSeverity:
                    if s.value == target_sev_str:
                        new_sev = s
                        break
                # Garante que seja de fato rebaixada
                if new_sev in self.threshold_severities:
                    new_sev = IssueSeverity.MEDIA

                logger.info(
                    "[DevilsAdvocateArbiter] REBAIXADA de %s para %s: '%s' | Motivo: %s",
                    original_issue.severidade.value,
                    new_sev.value,
                    original_issue.descricao,
                    justificativa,
                )

                ev_tag = (
                    f"{original_issue.evaluator}, DevilsAdvocate:rebaixado"
                    if original_issue.evaluator
                    else "DevilsAdvocate:rebaixado"
                )
                adjusted_issue = original_issue.model_copy(
                    update={
                        "severidade": new_sev,
                        "evaluator": ev_tag,
                    }
                )
                final_candidates.append(adjusted_issue)

            else:
                # manter
                ev_tag = (
                    f"{original_issue.evaluator}, DevilsAdvocate:confirmado"
                    if original_issue.evaluator
                    else "DevilsAdvocate:confirmado"
                )
                confirmed_issue = original_issue.model_copy(update={"evaluator": ev_tag})
                final_candidates.append(confirmed_issue)

        all_issues = final_candidates + unchallenged
        # Ordena por severidade decrescente
        from uxsentinel.vision.evaluators.orchestrator import SEVERITY_WEIGHTS

        all_issues.sort(key=lambda item: SEVERITY_WEIGHTS.get(item.severidade, 0), reverse=True)
        return all_issues
