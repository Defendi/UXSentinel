import logging
import re

from uxsentinel.core.config import DEFAULT_I18N_ALLOWLIST
from uxsentinel.core.models import Issue, IssueCategory
from uxsentinel.vision.client import UnifiedVisionClient
from uxsentinel.vision.evaluators.base import BaseEvaluator, EvaluatorContext

logger = logging.getLogger("uxsentinel.vision.evaluators.linguist")

BASE_LINGUIST_SYSTEM_PROMPT = """
Você é o Linguist Agent do UXSentinel, um Auditor Especialista em Localização de Software (i18n), Gramática e Tradução para Português do Brasil (pt-BR).

Sua ÚNICA missão é inspecionar minuciosamente a interface visual (screenshot) e o texto auxiliar extraído do DOM para identificar problemas linguísticos e de tradução.
NÃO avalie problemas de layout, quebras de alinhamento ou regras de negócio (outros avaliadores especializados cuidarão disso).

Critérios de Auditoria Linguística:
1. EXIGÊNCIA DE 100% PORTUGUÊS DO BRASIL (PT-BR):
   - Identifique qualquer botão, rótulo, cabeçalho de coluna, aba, menu, tooltip, placeholder ou mensagem em inglês ou outro idioma não localizado.
   - Exemplos comuns: 'Submit', 'Discard', 'Cancel', 'Save', 'Close', 'Filter', 'Back', 'Group By', 'Favorites', 'Search', 'Next', 'Previous', 'Pending', 'In Progress', 'Done', 'Created on', 'Select all'.
2. PRECISÃO ORTOGRÁFICA E GRAMATICAL:
   - Identifique erros de grafia, concordância, acentuação ou pontuação na UI corporativa.
   - Identifique termos com traduções artificiais ou que não façam sentido no contexto de negócio corporativo em pt-BR.
3. COERÊNCIA E PADRÃO DE TERMOS:
   - Evite misturas de termos em inglês e português na mesma sentença (ex: "Status do lead está Open").

4. GLOSSÁRIO CORPORATIVO PERMITIDO (IMPORTANTE - NÃO APONTAR COMO ERRO):
   Os termos a seguir são amplamente aceitos e utilizados no ecossistema corporativo e de tecnologia no Brasil. NÃO os reporte como erro de tradução:
   {allowlist_terms}

Matriz de Severidade Linguística:
- 'alta': Botão de ação primária, título de tela ou menu principal em inglês; erro gramatical grave que compromete a compreensão.
- 'media': Rótulos secundários, cabeçalhos de tabela, tooltips, placeholders ou abas em inglês.
- 'baixa': Sugestão de melhoria estilística de redação UX ou pequeno ajuste de pontuação.

Formato Obrigatório de Resposta:
Responda EXCLUSIVAMENTE em formato JSON válido, sem texto ou markdown extra:
{{
  "issues": [
    {{
      "categoria": "traducao",
      "severidade": "alta" | "media" | "baixa",
      "descricao": "Descrição clara em português apontando o termo não traduzido ou incorreto",
      "sugestao_correcao": "Tradução recomendada em Português do Brasil (ex: 'Substituir Close por Fechar')",
      "elemento_alvo": "Texto, botão ou seletor do elemento com a falha"
    }}
  ]
}}

Se a interface estiver 100% em português correto e sem desvios linguísticos, retorne:
{{"issues": []}}
""".strip()


class LinguistAgent(BaseEvaluator):
    """Avaliador especializado em localização, tradução para pt-BR e qualidade ortográfica da UI."""

    def __init__(self, client: UnifiedVisionClient, allowlist: list[str] | None = None):
        super().__init__(client)
        self.allowlist: list[str] = list(allowlist) if allowlist is not None else list(DEFAULT_I18N_ALLOWLIST)
        self._allowlist_set: set[str] = {term.strip().lower() for term in self.allowlist if term.strip()}

    @property
    def name(self) -> str:
        return "Linguist Agent"

    @property
    def system_prompt(self) -> str:
        terms_fmt = ", ".join(f"'{t}'" for t in self.allowlist)
        return BASE_LINGUIST_SYSTEM_PROMPT.format(allowlist_terms=terms_fmt)

    @property
    def default_category(self) -> IssueCategory:
        return IssueCategory.TRADUCAO

    def is_allowlisted(self, issue: Issue) -> bool:
        """Determina de forma determinística se a issue de tradução é um falso positivo
        referente a um termo autorizado no glossário corporativo.
        """
        if issue.categoria != IssueCategory.TRADUCAO:
            return False

        # 1. Checa elemento alvo direto
        if issue.elemento_alvo:
            clean_target = re.sub(r"[\[\]'\"`]", "", issue.elemento_alvo).strip().lower()
            if clean_target in self._allowlist_set:
                return True

        # 2. Extrai termos entre aspas na descrição ou sugestão de correção
        quoted_terms = re.findall(r"['\"`]([A-Za-z0-9_\-]+)['\"`]", issue.descricao or "")
        if not quoted_terms and issue.sugestao_correcao:
            quoted_terms = re.findall(r"['\"`]([A-Za-z0-9_\-]+)['\"`]", issue.sugestao_correcao)

        if quoted_terms:
            # Se todos os termos cotados são termos da allowlist, trata-se de falso positivo
            all_in_allowlist = all(q.strip().lower() in self._allowlist_set for q in quoted_terms)
            if all_in_allowlist:
                return True

        # 3. Análise semântica por palavras-chave na descrição
        desc_lower = (issue.descricao or "").lower()
        for term in self._allowlist_set:
            pattern = rf"\b{re.escape(term)}\b"
            if re.search(pattern, desc_lower) and (
                any(
                    marker in desc_lower
                    for marker in (
                        f"termo {term}",
                        f"palavra {term}",
                        f"botão {term}",
                        f"campo {term}",
                        f"rótulo {term}",
                        f"label {term}",
                        f"menu {term}",
                        f"aba {term}",
                        f"texto {term}",
                        f"substituir {term}",
                        f"trocar {term}",
                    )
                )
                or desc_lower.endswith(term)
                or desc_lower.startswith(term)
            ):
                return True

        return False

    def filter_allowlisted_issues(self, issues: list[Issue]) -> list[Issue]:
        """Filtra e descarta falsos positivos de termos da allowlist corporativa."""
        filtered: list[Issue] = []
        for issue in issues:
            if self.is_allowlisted(issue):
                logger.info(
                    "[LinguistAgent] Descartando falso positivo no glossário corporativo: '%s' (alvo: '%s')",
                    issue.descricao,
                    issue.elemento_alvo,
                )
                continue
            filtered.append(issue)
        return filtered

    def parse_issues(self, raw_text: str, context: EvaluatorContext) -> list[Issue]:
        issues = super().parse_issues(raw_text, context)
        return self.filter_allowlisted_issues(issues)

    async def evaluate(self, context: EvaluatorContext) -> list[Issue]:
        raw_issues = await super().evaluate(context)
        return self.filter_allowlisted_issues(raw_issues)


# Alias semântico para máxima flexibilidade e conformidade de nomenclatura
LinguistEvaluator = LinguistAgent
