"""Modelos de dados intermediários do Recorder (Modo Assistido).

Desacopla a captura de eventos no navegador da serialização para YAML
e da interface do Studio.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StepStatus(StrEnum):
    """Status de ciclo de vida de um passo gravado."""

    CONFIRMED = "confirmed"
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class SelectorStrategy(StrEnum):
    """Estratégias de seleção de elementos capturados."""

    TESTID = "data-testid"
    ROLE = "role"
    LABEL = "label"
    TEXT = "text"
    CSS = "css"
    XPATH = "xpath"


class SelectorCandidate(BaseModel):
    """Candidato a seletor para localização de elemento no DOM."""

    model_config = ConfigDict(extra="forbid")

    strategy: SelectorStrategy = Field(
        ...,
        description="Estratégia utilizada para localizar o elemento.",
    )
    value: str = Field(
        ...,
        description="Valor da expressão do seletor.",
    )
    name: str | None = Field(
        default=None,
        description="Nome acessível complementar (usado em conjunto com a estratégia role).",
    )


class RecordedTarget(BaseModel):
    """Identificação estruturada do elemento alvo da ação."""

    model_config = ConfigDict(extra="forbid")

    primary: SelectorCandidate | None = Field(
        default=None,
        description="Seletor preferido de maior robustez, ou None se não resolúvel.",
    )
    fallbacks: list[SelectorCandidate] = Field(
        default_factory=list,
        description="Lista de seletores alternativos ordenados por prioridade.",
    )
    raw_html_snippet: str | None = Field(
        default=None,
        description="Snippet HTML bruto do elemento capturado para depuração.",
    )


class RecordedStep(BaseModel):
    """Representação intermediária de uma ação ou evento gravado."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(
        ...,
        ge=0,
        description="Índice sequencial do passo no workflow.",
    )
    action: str = Field(
        ...,
        description="Tipo de ação executada (ex: fill, click, navigate, assert, select, hover).",
    )
    target: RecordedTarget | None = Field(
        default=None,
        description="Elemento alvo da ação, se aplicável.",
    )
    value: str | None = Field(
        default=None,
        description="Valor associado à ação (ex: texto preenchido, opção selecionada).",
    )
    url: str | None = Field(
        default=None,
        description="URL associada à navegação ou contexto da ação.",
    )
    screenshot_path: str | None = Field(
        default=None,
        description="Caminho opcional do screenshot capturado no momento do passo.",
    )
    status: StepStatus = Field(
        default=StepStatus.CONFIRMED,
        description="Status do passo (ex: confirmado, sugerido, aceito).",
    )
    advisor_justification: str | None = Field(
        default=None,
        description="Justificativa fornecida pelo RecorderAdvisor para sugestões.",
    )
    advisor_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nível de confiança da sugestão (entre 0.0 e 1.0).",
    )


class RecordedWorkflow(BaseModel):
    """Modelo intermediário de workflow gravado, independente de YAML."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(
        ...,
        description="Identificador único da sessão de gravação.",
    )
    name: str = Field(
        ...,
        description="Nome identificador do workflow.",
    )
    url: str = Field(
        ...,
        description="URL inicial da gravação.",
    )
    objective: str | None = Field(
        default=None,
        description="Objetivo de negócio ou descrição do cenário gravado.",
    )
    steps: list[RecordedStep] = Field(
        default_factory=list,
        description="Lista ordenada de passos registrados.",
    )
    created_at: str = Field(
        ...,
        description="Timestamp ISO 8601 da criação da gravação.",
    )
    paused: bool = Field(
        default=False,
        description="Indica se a sessão de gravação está pausada.",
    )
