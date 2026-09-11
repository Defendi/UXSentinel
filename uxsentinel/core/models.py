from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class IssueSeverity(StrEnum):
    BLOQUEANTE = "bloqueante"
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class IssueCategory(StrEnum):
    TRADUCAO = "traducao"
    TEXTO_TECNICO = "texto_tecnico"
    LAYOUT_MODAL = "layout_modal"
    REGRA_NEGOCIO = "regra_negocio"
    ACESSIBILIDADE = "acessibilidade"
    OUTRO = "outro"


class Issue(BaseModel):
    categoria: IssueCategory
    severidade: IssueSeverity
    descricao: str
    sugestao_correcao: str | None = None
    elemento_alvo: str | None = None


class CheckpointResult(BaseModel):
    name: str
    description: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    screenshot_path: str | None = None
    expected_behavior: str
    status: str = "ok"  # 'ok', 'problemas_encontrados', 'erro_execucao'
    issues: list[Issue] = Field(default_factory=list)
    dom_summary: str | None = None
    raw_response: str | None = None


class StepAction(BaseModel):
    action: str
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    timeout: int | None = None
    description: str | None = None
    name: str | None = None
    expected_behavior: str | None = None
    criteria: list[str] | None = None


class Scenario(BaseModel):
    id: str
    title: str
    description: str | None = None
    profile: str = "generic"
    provider: str | None = None
    tags: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    steps: list[StepAction] = Field(default_factory=list)


class TestReport(BaseModel):
    scenario_id: str
    scenario_title: str
    profile: str
    provider_used: str
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None
    duration_seconds: float = 0.0
    checkpoints: list[CheckpointResult] = Field(default_factory=list)
    total_issues: int = 0
    total_bloqueantes: int = 0
    total_altas: int = 0
    total_medias: int = 0
    total_baixas: int = 0
    success: bool = True
    error_message: str | None = None

    def compute_totals(self) -> None:
        self.total_issues = 0
        self.total_bloqueantes = 0
        self.total_altas = 0
        self.total_medias = 0
        self.total_baixas = 0

        has_bloqueante_or_alta = False
        for cp in self.checkpoints:
            for issue in cp.issues:
                self.total_issues += 1
                if issue.severidade == IssueSeverity.BLOQUEANTE:
                    self.total_bloqueantes += 1
                    has_bloqueante_or_alta = True
                elif issue.severidade == IssueSeverity.ALTA:
                    self.total_altas += 1
                    has_bloqueante_or_alta = True
                elif issue.severidade == IssueSeverity.MEDIA:
                    self.total_medias += 1
                elif issue.severidade == IssueSeverity.BAIXA:
                    self.total_baixas += 1

        if has_bloqueante_or_alta or self.error_message:
            self.success = False
        else:
            self.success = True
