"""Módulo responsável pela mesclagem e consolidação de sessões de auditoria (UXS-92)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from uxsentinel.core.models import TestReport


def _normalize_datetime(dt: datetime | None) -> datetime:
    """Normaliza um objeto datetime para UTC caso seja naive para comparação segura.

    Args:
        dt: Data e hora a ser normalizada.

    Returns:
        Datetime com fuso horário UTC configurado.
    """
    if dt is None:
        return datetime.min.replace(tzinfo=UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def merge_test_reports(
    reports: list[TestReport],
    scenario_id: str | None = None,
    scenario_title: str | None = None,
) -> TestReport:
    """Consolida múltiplos relatórios de teste em uma única sessão unificada.

    Args:
        reports: Lista contendo instâncias de TestReport a serem mescladas.
        scenario_id: Identificador opcional para o relatório resultante.
        scenario_title: Título opcional para o relatório resultante.

    Returns:
        Nova instância de TestReport contendo o histórico consolidado e totais recalculados.

    Raises:
        ValueError: Se a lista de relatórios estiver vazia.
    """
    if not reports:
        raise ValueError("A lista de relatórios para mesclagem não pode estar vazia.")

    if len(reports) == 1:
        single = reports[0].model_copy(deep=True)
        if scenario_id is not None:
            single.scenario_id = scenario_id
        if scenario_title is not None:
            single.scenario_title = scenario_title
        return single

    # 1. Metadados do cenário
    merged_scenario_id = scenario_id if scenario_id is not None else reports[0].scenario_id
    merged_scenario_title = scenario_title if scenario_title is not None else reports[0].scenario_title

    # 2. Perfil e Provedor (se todos iguais, mantém; se divergentes, separa por vírgula)
    profiles: list[str] = []
    for rep in reports:
        if rep.profile and rep.profile not in profiles:
            profiles.append(rep.profile)
    merged_profile = ", ".join(profiles) if profiles else "generic"

    providers: list[str] = []
    for rep in reports:
        if rep.provider_used and rep.provider_used not in providers:
            providers.append(rep.provider_used)
    merged_provider = ", ".join(providers) if providers else "default"

    # 3. Timestamps e Duração
    min_started_at = min((rep.started_at for rep in reports), key=_normalize_datetime)

    finished_candidates = [rep.finished_at for rep in reports if rep.finished_at is not None]
    max_finished_at = max(finished_candidates, key=_normalize_datetime) if finished_candidates else None

    total_duration = sum(rep.duration_seconds for rep in reports)

    # 4. Viewports únicas mantendo ordem cronológica de descoberta
    seen_viewports: set[str] = set()
    merged_viewports: list[str] = []
    for rep in reports:
        for vp in rep.viewports_tested:
            if vp and vp not in seen_viewports:
                seen_viewports.add(vp)
                merged_viewports.append(vp)

    # 5. Checkpoints ordenados estritamente por timestamp
    all_checkpoints = [cp.model_copy(deep=True) for rep in reports for cp in rep.checkpoints]
    all_checkpoints.sort(key=lambda cp: _normalize_datetime(cp.timestamp))

    # 6. Coleções de eventos e telemetria
    merged_semantic_steps = [step.model_copy(deep=True) for rep in reports for step in rep.semantic_steps]
    merged_healed_steps = [step.model_copy(deep=True) for rep in reports for step in rep.healed_steps]
    merged_healing_events = [ev.model_copy(deep=True) for rep in reports for ev in rep.healing_events]
    merged_console_logs = [log.model_copy(deep=True) for rep in reports for log in rep.console_logs]
    merged_network_failures = [nf.model_copy(deep=True) for rep in reports for nf in rep.network_failures]
    merged_perf_history = [perf.model_copy(deep=True) for rep in reports for perf in rep.performance_history]

    # 7. Artefatos de mídia e métricas pontuais (preserva primeiros válidos ou último perfil)
    video_path = next((rep.video_path for rep in reports if rep.video_path), None)
    gif_path = next((rep.gif_path for rep in reports if rep.gif_path), None)
    markdown_path = next((rep.markdown_path for rep in reports if rep.markdown_path), None)
    archived_report_path = next(
        (rep.archived_report_path for rep in reports if rep.archived_report_path), None
    )
    perf_metrics = next(
        (rep.performance_metrics for rep in reversed(reports) if rep.performance_metrics), None
    )

    error_messages = [rep.error_message for rep in reports if rep.error_message]
    merged_error_message = "; ".join(error_messages) if error_messages else None

    # 8. Montagem do TestReport consolidado
    merged_report = TestReport(
        scenario_id=merged_scenario_id,
        scenario_title=merged_scenario_title,
        profile=merged_profile,
        provider_used=merged_provider,
        started_at=min_started_at,
        finished_at=max_finished_at,
        duration_seconds=total_duration,
        checkpoints=all_checkpoints,
        healed_steps=merged_healed_steps,
        healing_events=merged_healing_events,
        semantic_steps=merged_semantic_steps,
        video_path=video_path,
        gif_path=gif_path,
        markdown_path=markdown_path,
        archived_report_path=archived_report_path,
        viewports_tested=merged_viewports,
        console_logs=merged_console_logs,
        network_failures=merged_network_failures,
        performance_metrics=perf_metrics,
        performance_history=merged_perf_history,
        error_message=merged_error_message,
    )

    # 9. Recalcular contadores consolidados, acessibilidade, CSS e status de sucesso
    merged_report.compute_totals()

    return merged_report


def merge_session_files(
    file_paths: list[Path | str],
    output_file: Path | str | None = None,
    scenario_id: str | None = None,
    scenario_title: str | None = None,
) -> tuple[TestReport, Path | None]:
    """Carrega arquivos JSON de sessões de auditoria, mescla seus relatórios e opcionalmente salva o resultado.

    Args:
        file_paths: Lista de caminhos para os arquivos JSON de relatório.
        output_file: Caminho de arquivo ou diretório opcional para salvar o JSON mesclado.
        scenario_id: Identificador opcional para o relatório consolidado.
        scenario_title: Título opcional para o relatório consolidado.

    Returns:
        Tupla contendo a instância de TestReport mesclada e o Path do arquivo salvo (ou None se não salvo).

    Raises:
        ValueError: Se a lista de arquivos estiver vazia.
        FileNotFoundError: Se algum arquivo de sessão não existir.
    """
    if not file_paths:
        raise ValueError("A lista de relatórios para mesclagem não pode estar vazia.")

    reports: list[TestReport] = []
    for fp in file_paths:
        path_obj = Path(fp).resolve()
        if not path_obj.is_file():
            raise FileNotFoundError(f"Arquivo de sessão não encontrado: {fp}")
        content = path_obj.read_text(encoding="utf-8")
        reports.append(TestReport.model_validate_json(content))

    merged_report = merge_test_reports(
        reports=reports,
        scenario_id=scenario_id,
        scenario_title=scenario_title,
    )

    saved_path: Path | None = None
    if output_file is not None:
        out_path = Path(output_file)
        if out_path.is_dir() or str(output_file).endswith(("/", "\\")):
            saved_path = out_path / f"{merged_report.scenario_id}_report.json"
        else:
            saved_path = out_path

        saved_path.parent.mkdir(parents=True, exist_ok=True)
        dump_data = merged_report.model_dump(mode="json")
        saved_path.write_text(json.dumps(dump_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return merged_report, saved_path
