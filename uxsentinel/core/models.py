from datetime import datetime
from enum import Enum

try:
    from enum import StrEnum
except ImportError:
    # Compatibilidade com Python < 3.11
    class StrEnum(str, Enum):  # noqa: UP042
        pass


from pydantic import BaseModel, Field

from uxsentinel.browser.telemetry import (
    ConsoleLogEntry,
    NetworkFailureEntry,
    PagePerformanceMetrics,
)


class IssueSeverity(StrEnum):
    BLOQUEANTE = "bloqueante"
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"
    CRITICAL = "bloqueante"
    MAJOR = "alta"


class IssueCategory(StrEnum):
    TRADUCAO = "traducao"
    TEXTO_TECNICO = "texto_tecnico"
    LAYOUT_MODAL = "layout_modal"
    LAYOUT = "layout"
    REGRA_NEGOCIO = "regra_negocio"
    ACESSIBILIDADE = "acessibilidade"
    OUTRO = "outro"


class ViewportConfig(BaseModel):
    name: str
    width: int
    height: int
    is_mobile: bool = False

    @property
    def label(self) -> str:
        return f"{self.name} ({self.width}x{self.height})"

    def __str__(self) -> str:
        return self.label


CANONICAL_VIEWPORTS: dict[str, ViewportConfig] = {
    "desktop": ViewportConfig(name="desktop", width=1440, height=900, is_mobile=False),
    "tablet": ViewportConfig(name="tablet", width=768, height=1024, is_mobile=False),
    "mobile": ViewportConfig(name="mobile", width=375, height=812, is_mobile=True),
}

DEFAULT_FALLBACK_VIEWPORT = ViewportConfig(name="desktop", width=1280, height=800, is_mobile=False)


def parse_viewport_spec(spec: str | ViewportConfig | dict) -> ViewportConfig:
    if isinstance(spec, ViewportConfig):
        return spec
    if isinstance(spec, dict):
        return ViewportConfig(**spec)
    if isinstance(spec, str):
        clean = spec.strip().lower()
        if clean in CANONICAL_VIEWPORTS:
            return CANONICAL_VIEWPORTS[clean]
        import re

        match = re.match(r"^(\d+)\s*[xX]\s*(\d+)$", clean)
        if match:
            w = int(match.group(1))
            h = int(match.group(2))
            is_mobile = (w <= 500) or (w < h and w <= 768)
            return ViewportConfig(name=f"{w}x{h}", width=w, height=h, is_mobile=is_mobile)
        match_named = re.match(r"^([a-zA-Z0-9_\-]+)[:=](\d+)\s*[xX]\s*(\d+)$", clean)
        if match_named:
            name = match_named.group(1)
            w = int(match_named.group(2))
            h = int(match_named.group(3))
            is_mobile = (w <= 500) or (w < h and w <= 768)
            return ViewportConfig(name=name, width=w, height=h, is_mobile=is_mobile)
        raise ValueError(
            f"Formato de viewport inválido: '{spec}'. Use presets conhecidos ('desktop', 'tablet', 'mobile') ou 'LARGURAxALTURA' (ex: '1920x1080')."
        )
    raise TypeError(f"Tipo de viewport inválido: {type(spec)}")


def parse_viewports(
    specs: str | list[str | ViewportConfig | dict] | None,
) -> list[ViewportConfig]:
    if not specs:
        return []
    if isinstance(specs, str):
        items = [s.strip() for s in specs.split(",") if s.strip()]
        return [parse_viewport_spec(item) for item in items]
    result: list[ViewportConfig] = []
    for item in specs:
        if isinstance(item, str) and "," in item:
            for sub in item.split(","):
                if sub.strip():
                    result.append(parse_viewport_spec(sub.strip()))
        else:
            result.append(parse_viewport_spec(item))
    return result


def resolve_viewports(
    cli_viewports: str | list[str] | None = None,
    scenario_viewports: list[str | ViewportConfig] | str | None = None,
    config_viewports: list[str | ViewportConfig] | str | None = None,
) -> list[ViewportConfig]:
    """Resolve a lista de viewports com a precedência estrita:
    1. CLI (--viewports / --viewport)
    2. Cenário YAML (campo 'viewports')
    3. Config global (BrowserSettings.viewports)
    4. Fallback padrão: desktop padrão 1280x800
    """
    if cli_viewports:
        vps = parse_viewports(cli_viewports)
        if vps:
            return vps

    if scenario_viewports:
        vps = parse_viewports(scenario_viewports)
        if vps:
            return vps

    if config_viewports:
        vps = parse_viewports(config_viewports)
        if vps:
            return vps

    return [DEFAULT_FALLBACK_VIEWPORT]


class Issue(BaseModel):
    categoria: IssueCategory
    severidade: IssueSeverity
    descricao: str
    sugestao_correcao: str | None = None
    elemento_alvo: str | None = None
    trecho_codigo: str | None = None
    viewport: str | None = None
    evaluator: str | None = None


# Alias para conformidade e semântica de inconsistência
Inconsistency = Issue


class AxeNodeResult(BaseModel):
    target: list[str] = Field(default_factory=list)
    html: str = ""
    failure_summary: str | None = None
    impact: str | None = None


class AxeViolation(BaseModel):
    id: str
    impact: str | None = None  # "critical", "serious", "moderate", "minor"
    description: str
    help_url: str | None = None
    help: str | None = None
    tags: list[str] = Field(default_factory=list)
    nodes: list[AxeNodeResult] = Field(default_factory=list)


class HealingStrategy(StrEnum):
    ACCESSIBILITY = "accessibility"
    VISION_COORDINATES = "vision_coordinates"
    SEMANTIC_MATCH = "semantic_match"


class HealingEvent(BaseModel):
    step_index: int | None = None
    action: str
    original_selector: str
    strategy: HealingStrategy | str
    recovered_selector: str | None = None
    coordinates: dict[str, float] | tuple[float, float] | None = None
    yaml_fix_suggestion: str | None = None
    confidence: float | None = None
    description: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


# Alias para conformidade e interoperabilidade
HealedStep = HealingEvent


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class VisualDiffResult(BaseModel):
    baseline_path: str
    current_path: str
    diff_image_path: str | None = None
    diff_percentage: float
    has_diff: bool
    threshold: float = 0.1
    bounding_boxes: list[BoundingBox] = Field(default_factory=list)
    total_pixels: int = 0
    diff_pixels: int = 0


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
    healed_events: list[HealingEvent] = Field(default_factory=list)
    viewport: str | None = None
    a11y_score: float | None = None
    a11y_violations: list[AxeViolation] = Field(default_factory=list)
    visual_diff: VisualDiffResult | None = None
    console_logs: list[ConsoleLogEntry] = Field(default_factory=list)
    network_failures: list[NetworkFailureEntry] = Field(default_factory=list)
    performance_metrics: PagePerformanceMetrics | None = None


class SemanticStrategy(StrEnum):
    ACCESSIBILITY = "accessibility"
    VISION_COORDINATES = "vision_coordinates"
    VISION_SELECTOR = "vision_selector"
    LMM_ASSERTION = "lmm_assertion"


class SemanticStepResult(BaseModel):
    step_index: int | None = None
    action: str  # ai_click, ai_fill, ai_assert, ai_action
    target: str
    value: str | None = None
    strategy: SemanticStrategy | str | None = None
    resolved_selector: str | None = None
    coordinates: dict[str, float] | tuple[float, float] | None = None
    confidence: float | None = None
    passed: bool = True
    reasoning: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


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
    ai_click: str | None = None
    ai_fill: str | None = None
    ai_assert: str | None = None
    ai_action: str | None = None
    target: str | None = None


# Alias para conformidade e expressividade
Step = StepAction


class Scenario(BaseModel):
    id: str
    title: str
    description: str | None = None
    profile: str = "generic"
    provider: str | None = None
    tags: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headless: bool | None = None
    devtools: bool | None = None
    video: bool | None = None
    axe: bool | None = None
    markdown: bool | None = None
    update_baseline: bool | None = None
    baseline_dir: str | None = None
    diff_threshold: float | None = None
    viewports: list[str] | list[ViewportConfig] | None = None
    steps: list[StepAction] = Field(default_factory=list)


class TestReport(BaseModel):
    __test__ = False

    scenario_id: str
    scenario_title: str
    profile: str = "generic"
    provider_used: str = "default"
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None
    duration_seconds: float = 0.0
    checkpoints: list[CheckpointResult] = Field(default_factory=list)
    healed_steps: list[HealingEvent] = Field(default_factory=list)
    healing_events: list[HealingEvent] = Field(default_factory=list)
    semantic_steps: list[SemanticStepResult] = Field(default_factory=list)
    video_path: str | None = None
    gif_path: str | None = None
    markdown_path: str | None = None
    viewports_tested: list[str] = Field(default_factory=list)
    total_issues: int = 0
    total_bloqueantes: int = 0
    total_altas: int = 0
    total_medias: int = 0
    total_baixas: int = 0
    a11y_score: float | None = None
    a11y_violations: list[AxeViolation] = Field(default_factory=list)
    console_logs: list[ConsoleLogEntry] = Field(default_factory=list)
    network_failures: list[NetworkFailureEntry] = Field(default_factory=list)
    performance_metrics: PagePerformanceMetrics | None = None
    performance_history: list[PagePerformanceMetrics] = Field(default_factory=list)
    total_console_errors: int = 0
    total_console_warnings: int = 0
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

        # Consolida métricas e violações de acessibilidade Axe-Core
        all_violations: list[AxeViolation] = []
        scores: list[float] = []
        for cp in self.checkpoints:
            if cp.a11y_violations:
                all_violations.extend(cp.a11y_violations)
            if cp.a11y_score is not None:
                scores.append(cp.a11y_score)

        self.a11y_violations = all_violations
        if scores:
            self.a11y_score = round(sum(scores) / len(scores), 1)
        elif all_violations:
            from uxsentinel.browser.axe_runner import calculate_a11y_score

            self.a11y_score = calculate_a11y_score(all_violations)

        # Consolida erros e avisos de console
        self.total_console_errors = sum(1 for log in self.console_logs if log.type in ("error", "critical"))
        self.total_console_warnings = sum(1 for log in self.console_logs if log.type in ("warn", "warning"))

        if has_bloqueante_or_alta or self.error_message:
            self.success = False
        else:
            self.success = True


class ExecutionResult(BaseModel):
    scenario_id: str
    success: bool = True
    status: str = "ok"
    healed_events: list[HealingEvent] = Field(default_factory=list)
    report: TestReport | None = None
    error_message: str | None = None
