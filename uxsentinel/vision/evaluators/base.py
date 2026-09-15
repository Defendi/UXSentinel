import json
import logging
import re
from abc import ABC, abstractmethod

from pydantic import BaseModel

from uxsentinel.core.models import Issue, IssueCategory, IssueSeverity, ScenarioExceptions
from uxsentinel.vision.client import UnifiedVisionClient

logger = logging.getLogger("uxsentinel.vision.evaluators")


class EvaluatorContext(BaseModel):
    """Contexto de execução compartilhado entre os avaliadores especializados."""

    checkpoint_name: str
    expected_behavior: str
    image_base64: str
    dom_text: str = ""
    description: str | None = None
    viewport: str | None = None
    exceptions: ScenarioExceptions | None = None


class BaseEvaluator(ABC):
    """Classe base abstrata para todos os avaliadores especializados do UXSentinel."""

    def __init__(self, client: UnifiedVisionClient):
        self.client = client

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome legível do avaliador especializado (ex: 'Linguist Agent')."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt hiperespecializado para este agente."""
        ...

    @property
    @abstractmethod
    def default_category(self) -> IssueCategory:
        """Categoria padrão associada às inconsistências encontradas por este avaliador."""
        ...

    def build_user_prompt(self, context: EvaluatorContext) -> str:
        """Constrói o prompt de usuário focado no contexto do checkpoint com cláusula de exceções."""
        dom_snippet = context.dom_text[:3500] if context.dom_text else "(Nenhum texto relevante extraído)"
        vp_info = f"\nResolução / Viewport: {context.viewport}" if context.viewport else ""

        exceptions_block = ""
        if context.exceptions and not context.exceptions.is_empty():
            lines: list[str] = []
            if context.exceptions.allowed_texts:
                lines.append(
                    f"- TEXTOS/FRASES PERMITIDAS (NÃO REPORTAR COMO ERRO): {', '.join(repr(t) for t in context.exceptions.allowed_texts)}"
                )
            if context.exceptions.ignored_selectors:
                lines.append(
                    f"- SELETORES IGNORADOS (NÃO AUDITAR): {', '.join(context.exceptions.ignored_selectors)}"
                )
            if context.exceptions.ignored_elements:
                lines.append(
                    f"- ELEMENTOS IGNORADOS (NÃO AUDITAR): {', '.join(context.exceptions.ignored_elements)}"
                )
            if context.exceptions.custom_rules:
                lines.append(
                    "- DIRETRIZES E REGRAS DE EXCEÇÃO:\n  "
                    + "\n  ".join(f"* {r}" for r in context.exceptions.custom_rules)
                )
            exceptions_block = (
                "\n\nCLÁUSULA DE EXCEÇÕES E TOLERÂNCIAS HOMOLOGADAS (OBRIGATÓRIO RESPEITAR):\n"
                + "\n".join(lines)
            )

        return f"""
Checkpoint de Auditoria: {context.checkpoint_name}{vp_info}

COMPORTAMENTO ESPERADO (Regra de Negócio):
{context.expected_behavior}
{exceptions_block}

TEXTO EXTRAÍDO DO DOM DA TELA (Auxiliar para conferência de grafia, seletores e termos):
---
{dom_snippet}
---

Analise rigorosamente a imagem em anexo sob sua ótica especializada e retorne o JSON com as inconsistências detectadas.
""".strip()

    def parse_issues(self, raw_text: str, context: EvaluatorContext) -> list[Issue]:
        """Interpreta a resposta da IA e converte em lista padronizada de Issue."""
        clean_json_str = self._extract_json(raw_text)
        try:
            parsed = json.loads(clean_json_str)
        except Exception as exc:
            logger.warning(
                "[%s] Falha ao decodificar JSON retornado pela IA: %s. Resposta bruta: %s",
                self.name,
                exc,
                raw_text[:200],
            )
            return []

        if isinstance(parsed, dict):
            raw_issues = parsed.get("issues", [])
        elif isinstance(parsed, list):
            raw_issues = parsed
        else:
            raw_issues = []

        issues: list[Issue] = []
        for item in raw_issues:
            if not isinstance(item, dict):
                continue

            desc = item.get("descricao") or item.get("description")
            if not desc:
                continue

            cat_str = str(
                item.get("categoria") or item.get("category") or self.default_category.value
            ).lower()
            sev_str = str(item.get("severidade") or item.get("severity") or "media").lower()

            category = self.default_category
            for c in IssueCategory:
                if c.value == cat_str:
                    category = c
                    break

            severity = IssueSeverity.MEDIA
            for s in IssueSeverity:
                if s.value == sev_str:
                    severity = s
                    break

            issues.append(
                Issue(
                    categoria=category,
                    severidade=severity,
                    descricao=desc.strip(),
                    sugestao_correcao=item.get("sugestao_correcao") or item.get("suggestion"),
                    elemento_alvo=item.get("elemento_alvo") or item.get("target_element"),
                    trecho_codigo=item.get("trecho_codigo") or item.get("code_snippet"),
                    viewport=context.viewport,
                    evaluator=self.name,
                )
            )

        if context.exceptions and not context.exceptions.is_empty():
            issues = [i for i in issues if not context.exceptions.matches_issue(i)]

        return issues

    def _extract_json(self, text: str) -> str:
        """Remove blocos markdown ```json ... ``` se existirem ou localiza { ... } / [ ... ]."""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1).strip()
        start_obj = text.find("{")
        start_arr = text.find("[")
        if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
            end_obj = text.rfind("}")
            if end_obj != -1:
                return text[start_obj : end_obj + 1]
        elif start_arr != -1:
            end_arr = text.rfind("]")
            if end_arr != -1:
                return text[start_arr : end_arr + 1]
        return text

    async def evaluate(self, context: EvaluatorContext) -> list[Issue]:
        """Executa a avaliação multimodal chamando o modelo de visão com o system prompt especializado."""
        prompt = self.build_user_prompt(context)
        raw_response = await self.client.analyze(
            image_base64=context.image_base64,
            user_prompt=prompt,
            system_prompt=self.system_prompt,
        )
        return self.parse_issues(raw_response, context)
