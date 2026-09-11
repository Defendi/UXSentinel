import base64
import json
import logging
import re
from pathlib import Path

from uxsentinel.core.config import GlobalConfig
from uxsentinel.core.models import CheckpointResult, Issue, IssueCategory, IssueSeverity
from uxsentinel.vision.client import UnifiedVisionClient
from uxsentinel.vision.prompts import build_user_prompt

logger = logging.getLogger("uxsentinel.vision.inspector")


class ScreenInspector:
    """Responsável por auditar um screenshot de checkpoint contra critérios de QA e regras de negócio."""

    def __init__(self, config: GlobalConfig):
        self.config = config
        self.client = UnifiedVisionClient(config)

    async def inspect(
        self,
        checkpoint_name: str,
        expected_behavior: str,
        screenshot_path: str,
        dom_text: str = "",
        description: str | None = None,
    ) -> CheckpointResult:
        file_path = Path(screenshot_path)
        if not file_path.is_file():
            return CheckpointResult(
                name=checkpoint_name,
                description=description,
                expected_behavior=expected_behavior,
                status="erro_execucao",
                screenshot_path=screenshot_path,
                issues=[
                    Issue(
                        categoria=IssueCategory.OUTRO,
                        severidade=IssueSeverity.BLOQUEANTE,
                        descricao=f"Screenshot não encontrado no caminho: {screenshot_path}",
                    )
                ],
            )

        with open(file_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        user_prompt = build_user_prompt(
            checkpoint_name=checkpoint_name,
            expected_behavior=expected_behavior,
            dom_text=dom_text,
        )

        try:
            raw_text = await self.client.analyze(image_b64, user_prompt)
        except Exception as exc:
            logger.error("Erro ao analisar checkpoint '%s': %s", checkpoint_name, exc)
            return CheckpointResult(
                name=checkpoint_name,
                description=description,
                expected_behavior=expected_behavior,
                status="erro_execucao",
                screenshot_path=screenshot_path,
                issues=[
                    Issue(
                        categoria=IssueCategory.OUTRO,
                        severidade=IssueSeverity.ALTA,
                        descricao=f"Falha na comunicação com o provedor de IA: {exc}",
                        sugestao_correcao="Verifique as credenciais ou a disponibilidade do serviço no config.yaml",
                    )
                ],
                raw_response=str(exc),
            )

        clean_json_str = self._extract_json(raw_text)
        try:
            parsed = json.loads(clean_json_str)
            status = parsed.get("status", "ok")
            raw_issues = parsed.get("issues", [])

            issues_list: list[Issue] = []
            for item in raw_issues:
                cat_str = str(item.get("categoria", "outro")).lower()
                sev_str = str(item.get("severidade", "media")).lower()

                category = IssueCategory.OUTRO
                for c in IssueCategory:
                    if c.value == cat_str:
                        category = c
                        break

                severity = IssueSeverity.MEDIA
                for s in IssueSeverity:
                    if s.value == sev_str:
                        severity = s
                        break

                issues_list.append(
                    Issue(
                        categoria=category,
                        severidade=severity,
                        descricao=item.get("descricao", "Sem descrição"),
                        sugestao_correcao=item.get("sugestao_correcao"),
                        elemento_alvo=item.get("elemento_alvo"),
                    )
                )

            return CheckpointResult(
                name=checkpoint_name,
                description=description,
                expected_behavior=expected_behavior,
                screenshot_path=screenshot_path,
                status=status,
                issues=issues_list,
                dom_summary=dom_text[:500] if dom_text else None,
                raw_response=raw_text,
            )

        except Exception as parse_err:
            logger.warning("Falha ao interpretar JSON retornado pela IA: %s", parse_err)
            return CheckpointResult(
                name=checkpoint_name,
                description=description,
                expected_behavior=expected_behavior,
                screenshot_path=screenshot_path,
                status="erro_execucao",
                issues=[
                    Issue(
                        categoria=IssueCategory.OUTRO,
                        severidade=IssueSeverity.MEDIA,
                        descricao="A resposta da IA não pôde ser interpretada como JSON estruturado.",
                        sugestao_correcao="Ajuste o prompt ou reduza a temperatura do modelo no config.yaml",
                    )
                ],
                raw_response=raw_text,
            )

    def _extract_json(self, text: str) -> str:
        """Remove tags de markdown (```json ... ```) se presentes."""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1).strip()
        return text
