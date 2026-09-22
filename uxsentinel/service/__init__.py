"""Camada de serviços desacoplada do UXSentinel."""

from uxsentinel.service.config_service import (
    BrowserConfigDTO,
    ConfigService,
    ConfigUpdateDTO,
    ConnectionResult,
    JiraSafeDTO,
    ProviderSafeDTO,
    SafeConfigDTO,
)
from uxsentinel.service.execution_service import ExecutionOptions, ExecutionService
from uxsentinel.service.results_service import (
    CheckpointSummaryDTO,
    ExecutionDetailDTO,
    ExecutionSummaryDTO,
    IssueDetailDTO,
    ResultsService,
)
from uxsentinel.service.scenario_service import (
    ScenarioDetailDTO,
    ScenarioService,
    ScenarioSummaryDTO,
    StepDTO,
    StepError,
    ValidationResult,
)

__all__ = [
    "BrowserConfigDTO",
    "CheckpointSummaryDTO",
    "ConfigService",
    "ConfigUpdateDTO",
    "ConnectionResult",
    "ExecutionDetailDTO",
    "ExecutionOptions",
    "ExecutionService",
    "ExecutionSummaryDTO",
    "IssueDetailDTO",
    "JiraSafeDTO",
    "ProviderSafeDTO",
    "ResultsService",
    "SafeConfigDTO",
    "ScenarioDetailDTO",
    "ScenarioService",
    "ScenarioSummaryDTO",
    "StepDTO",
    "StepError",
    "ValidationResult",
]
