"""Serviço para recuperação de histórico de execuções e artefatos de auditoria (UXS-34)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class IssueDetailDTO(BaseModel):
    """Detalhes de uma inconsistência encontrada durante a auditoria."""

    id: str
    severity: str  # bloqueante, alta, media, baixa
    title: str
    category: str
    checkpoint_name: str
    description: str
    fix_suggestion: str | None = None
    screenshot_url: str | None = None
    target_element: str | None = None


class CheckpointSummaryDTO(BaseModel):
    """Resumo de um checkpoint contendo pontuação e evidência visual."""

    name: str
    description: str | None = None
    timestamp: datetime
    screenshot_url: str | None = None
    expected_behavior: str
    status: str
    issue_count: int = 0
    a11y_score: float | None = None


class ExecutionSummaryDTO(BaseModel):
    """Resumo de uma rodada de execução para exibição em listas e dashboards."""

    id: str
    scenario_id: str
    scenario_title: str
    status: str  # 'passed', 'failed', 'error'
    issue_count: int = 0
    bloqueante_count: int = 0
    alta_count: int = 0
    executed_at: datetime
    duration_seconds: float = 0.0
    report_html_url: str | None = None
    has_video: bool = False
    has_gif: bool = False


class ExecutionDetailDTO(ExecutionSummaryDTO):
    """Detalhe completo de uma execução contendo checkpoints e issues."""

    provider_used: str = "default"
    viewports: list[str] = Field(default_factory=list)
    checkpoints: list[CheckpointSummaryDTO] = Field(default_factory=list)
    issues: list[IssueDetailDTO] = Field(default_factory=list)
    error_message: str | None = None


class ResultsService:
    """Serviço de consulta e entrega segura de relatórios e artefatos."""

    @staticmethod
    def _sanitize_path_component(name: str) -> None:
        """Impede path traversal garantindo que o nome do artefato seja estritamente local."""
        if not name or ".." in name or name.startswith("/") or "\\" in name:
            raise PermissionError(f"Caminho não permitido ou tentativa de path traversal detectada: {name}")

    def list_executions(self, output_dir: Path | str, limit: int = 50) -> list[ExecutionSummaryDTO]:
        """Lista as execuções mais recentes a partir dos relatórios JSON encontrados no diretório."""
        out_path = Path(output_dir).resolve()
        if not out_path.is_dir():
            return []

        executions: list[ExecutionSummaryDTO] = []
        for json_file in out_path.glob("*_report.json"):
            try:
                raw_data = json.loads(json_file.read_text(encoding="utf-8"))
                scenario_id = raw_data.get("scenario_id", json_file.stem.replace("_report", ""))
                scenario_title = raw_data.get("scenario_title", scenario_id)

                success = raw_data.get("success", False)
                err_msg = raw_data.get("error_message")
                status = "error" if err_msg else ("passed" if success else "failed")

                started_str = raw_data.get("started_at")
                if started_str:
                    try:
                        executed_at = datetime.fromisoformat(started_str)
                    except ValueError:
                        stat = json_file.stat()
                        executed_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                else:
                    stat = json_file.stat()
                    executed_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

                html_file = out_path / f"{scenario_id}_report.html"
                report_html_url = (
                    f"/api/results/{scenario_id}/artifacts/{html_file.name}" if html_file.is_file() else None
                )

                video_path = raw_data.get("video_path")
                gif_path = raw_data.get("gif_path")

                executions.append(
                    ExecutionSummaryDTO(
                        id=scenario_id,
                        scenario_id=scenario_id,
                        scenario_title=scenario_title,
                        status=status,
                        issue_count=raw_data.get("total_issues", 0),
                        bloqueante_count=raw_data.get("total_bloqueantes", 0),
                        alta_count=raw_data.get("total_altas", 0),
                        executed_at=executed_at,
                        duration_seconds=raw_data.get("duration_seconds", 0.0),
                        report_html_url=report_html_url,
                        has_video=bool(video_path and Path(video_path).is_file()),
                        has_gif=bool(gif_path and Path(gif_path).is_file()),
                    )
                )
            except Exception:
                continue

        # Ordena por data decrescente (mais recentes primeiro)
        executions.sort(key=lambda x: x.executed_at, reverse=True)
        return executions[:limit]

    def get_execution(self, execution_id: str, output_dir: Path | str) -> ExecutionDetailDTO:
        """Obtém detalhes de uma execução específica a partir do JSON de relatório correspondente."""
        self._sanitize_path_component(execution_id)
        out_path = Path(output_dir).resolve()
        json_file = out_path / f"{execution_id}_report.json"

        if not json_file.is_file():
            raise FileNotFoundError(f"Relatório de execução '{execution_id}' não encontrado em {output_dir}")

        raw_data = json.loads(json_file.read_text(encoding="utf-8"))
        scenario_id = raw_data.get("scenario_id", execution_id)
        scenario_title = raw_data.get("scenario_title", scenario_id)

        success = raw_data.get("success", False)
        err_msg = raw_data.get("error_message")
        status = "error" if err_msg else ("passed" if success else "failed")

        started_str = raw_data.get("started_at")
        if started_str:
            try:
                executed_at = datetime.fromisoformat(started_str)
            except ValueError:
                stat = json_file.stat()
                executed_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        else:
            stat = json_file.stat()
            executed_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

        html_file = out_path / f"{scenario_id}_report.html"
        report_html_url = (
            f"/api/results/{scenario_id}/artifacts/{html_file.name}" if html_file.is_file() else None
        )

        # Checkpoints e Issues
        checkpoints: list[CheckpointSummaryDTO] = []
        issues: list[IssueDetailDTO] = []

        for cp in raw_data.get("checkpoints", []):
            cp_name = cp.get("name", "checkpoint")
            cp_status = cp.get("status", "ok")
            screenshot_path = cp.get("screenshot_path")
            screenshot_url = (
                f"/api/results/{scenario_id}/artifacts/{Path(screenshot_path).name}"
                if screenshot_path
                else None
            )

            cp_issues = cp.get("issues", [])
            checkpoints.append(
                CheckpointSummaryDTO(
                    name=cp_name,
                    description=cp.get("description"),
                    timestamp=datetime.fromisoformat(cp.get("timestamp"))
                    if cp.get("timestamp")
                    else executed_at,
                    screenshot_url=screenshot_url,
                    expected_behavior=cp.get("expected_behavior", ""),
                    status=cp_status,
                    issue_count=len(cp_issues),
                    a11y_score=cp.get("a11y_score"),
                )
            )

            for idx, iss in enumerate(cp_issues, start=1):
                sev = iss.get("severidade", "media")
                sev_val = sev.get("value") if isinstance(sev, dict) else str(sev)
                issues.append(
                    IssueDetailDTO(
                        id=f"{cp_name}_{idx}",
                        severity=sev_val,
                        title=iss.get("descricao", "Inconformidade detectada"),
                        category=str(iss.get("categoria", "geral")),
                        checkpoint_name=cp_name,
                        description=iss.get("descricao", ""),
                        fix_suggestion=iss.get("sugestao_correcao"),
                        screenshot_url=screenshot_url,
                        target_element=iss.get("elemento_alvo"),
                    )
                )

        video_path = raw_data.get("video_path")
        gif_path = raw_data.get("gif_path")

        return ExecutionDetailDTO(
            id=scenario_id,
            scenario_id=scenario_id,
            scenario_title=scenario_title,
            status=status,
            issue_count=raw_data.get("total_issues", len(issues)),
            bloqueante_count=raw_data.get("total_bloqueantes", 0),
            alta_count=raw_data.get("total_altas", 0),
            executed_at=executed_at,
            duration_seconds=raw_data.get("duration_seconds", 0.0),
            report_html_url=report_html_url,
            has_video=bool(video_path and Path(video_path).is_file()),
            has_gif=bool(gif_path and Path(gif_path).is_file()),
            provider_used=raw_data.get("provider_used", "default"),
            viewports=raw_data.get("viewports_tested", []),
            checkpoints=checkpoints,
            issues=issues,
            error_message=err_msg,
        )

    def get_artifact(self, execution_id: str, artifact_name: str, output_dir: Path | str) -> Path:
        """Resolve e valida o caminho físico do artefato, bloqueando path traversal."""
        self._sanitize_path_component(execution_id)
        self._sanitize_path_component(artifact_name)

        out_path = Path(output_dir).resolve()
        artifact_file = (out_path / artifact_name).resolve()

        # Trava de segurança mandatória: o arquivo deve estar dentro do output_dir
        if not str(artifact_file).startswith(str(out_path)):
            raise PermissionError(f"Acesso negado ao artefato fora do diretório de saída: {artifact_name}")

        if not artifact_file.is_file():
            raise FileNotFoundError(f"Artefato '{artifact_name}' não encontrado em {output_dir}")

        return artifact_file
