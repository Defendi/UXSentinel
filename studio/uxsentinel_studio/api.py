"""Rotas REST da API do UXSentinel Studio (UXS-50 / STU-03 / STU-04)."""

import asyncio
import contextlib
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from uxsentinel import __version__ as core_version
from uxsentinel.core.config import (
    ensure_user_config,
    find_project_in_catalog,
    list_registered_projects,
    remove_project_from_catalog,
)
from uxsentinel.scenarios.parser import load_scenario
from uxsentinel.service import (
    ConfigService,
    ConfigUpdateDTO,
    ConnectionResult,
    ExecutionDetailDTO,
    ExecutionOptions,
    ExecutionService,
    ExecutionSummaryDTO,
    ResultsService,
    SafeConfigDTO,
    ScenarioDetailDTO,
    ScenarioService,
    ScenarioSummaryDTO,
    ValidationResult,
)
from uxsentinel_studio import __version__ as studio_version
from uxsentinel_studio.security import verify_studio_token, verify_studio_token_or_query

router = APIRouter()

# Armazenamento em memória para rastreamento de execuções ativas e recentes (Cap FIFO: 50)
MAX_RETAINED_EXECUTIONS: int = 50
EXECUTIONS: dict[str, dict[str, Any]] = {}


def _register_execution(run_id: str, data: dict[str, Any]) -> None:
    """Registra uma nova execução aplicando política FIFO com cap de retenção de memória."""
    while len(EXECUTIONS) >= MAX_RETAINED_EXECUTIONS:
        oldest_id = next(iter(EXECUTIONS))
        EXECUTIONS.pop(oldest_id, None)
    EXECUTIONS[run_id] = data


# --- DTOs de Entrada ---


class ProjectSummaryDTO(BaseModel):
    """Resumo de um projeto cadastrado no catálogo para o Studio."""

    id: str
    name: str
    path: str
    scenarios_count: int
    last_used: str
    is_active: bool


class ProjectSelectRequest(BaseModel):
    """Payload para alternar o projeto ativo no Studio."""

    project_id: str


class ProjectCreateRequest(BaseModel):
    """Payload para registrar um novo projeto no catálogo."""

    name: str
    path: str


class ScenarioCreateRequest(BaseModel):
    """Payload para criação de um novo cenário."""

    filename: str
    yaml_content: str


class ScenarioUpdateRequest(BaseModel):
    """Payload para atualização de um cenário existente."""

    yaml_content: str
    filename: str | None = None


class ScenarioValidateRequest(BaseModel):
    """Payload para validação de sintaxe e semântica de YAML."""

    yaml_content: str


class ExecutionRunRequest(BaseModel):
    """Payload para disparo de execução de cenário."""

    scenario_id: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class TestJiraRequest(BaseModel):
    """Payload para teste de conectividade com Atlassian Jira."""

    url: str
    email: str
    token: str


class TestAIRequest(BaseModel):
    """Payload para teste de conectividade com provedor multimodal."""

    provider: str


class GenerateScenarioRequest(BaseModel):
    """Payload para geração assistida de cenários via IA."""

    prompt: str


# --- Helpers Utilitários ---


def get_project_dir(request: Request) -> Path | None:
    """Recupera o diretório do projeto configurado no estado da aplicação."""
    p = getattr(request.app.state, "project_dir", None)
    return Path(p).resolve() if p is not None else None


def get_output_dir(project_dir: Path | None) -> Path:
    """Localiza o diretório de relatórios de auditoria dentro do projeto."""
    if project_dir is None:
        return Path.cwd() / "report"
    candidates = [
        project_dir / "report",
        project_dir / "scenarios" / "report",
        project_dir / "output",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return project_dir / "report"


async def publish_execution_event(run_id: str, event: str, data: Any) -> None:
    """Publica um evento SSE na fila de execução e para todos os ouvintes conectados."""
    if run_id not in EXECUTIONS:
        return
    execution = EXECUTIONS[run_id]
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    chunk = f"data: {payload}\n\n"

    if event == "log":
        msg = data.get("message") if isinstance(data, dict) else str(data)
        if msg and msg not in execution.get("logs", []):
            execution.setdefault("logs", []).append(msg)

    execution.setdefault("event_history", []).append(chunk)

    # Envia para a fila principal da execução se configurada
    main_queue = execution.get("queue")
    if main_queue and isinstance(main_queue, asyncio.Queue):
        await main_queue.put(chunk)

    # Distribui para todos os subscribers ativos
    subscribers = list(execution.get("subscribers", []))
    for q in subscribers:
        await q.put(chunk)


async def _emit_step_events(run_id: str, report: Any, scenario: Any | None) -> None:
    """Emite eventos SSE de progresso e resultado de cada passo do cenário."""
    steps_list = getattr(report, "steps", [])
    if steps_list:
        for idx, step_result in enumerate(steps_list, start=1):
            await publish_execution_event(
                run_id,
                "step",
                {
                    "step_index": idx,
                    "action": getattr(step_result, "action", ""),
                    "description": getattr(step_result, "description", ""),
                    "status": "passed" if getattr(step_result, "success", True) else "failed",
                },
            )
    elif scenario and getattr(scenario, "steps", None):
        for idx, step_def in enumerate(scenario.steps, start=1):
            await publish_execution_event(
                run_id,
                "step",
                {
                    "step_index": idx,
                    "action": getattr(step_def, "action", ""),
                    "description": getattr(step_def, "description", ""),
                    "status": "passed" if getattr(report, "success", False) else "completed",
                },
            )


async def _emit_checkpoint_events(run_id: str, report: Any) -> None:
    """Emite eventos SSE para cada checkpoint avaliado durante a auditoria."""
    for cp in getattr(report, "checkpoints", []):
        issues = getattr(cp, "issues", [])
        await publish_execution_event(
            run_id,
            "checkpoint",
            {
                "name": getattr(cp, "name", ""),
                "status": "passed" if not issues else "failed",
                "issues_count": len(issues),
                "expected_behavior": getattr(cp, "expected_behavior", ""),
            },
        )


async def _execute_scenario_task(run_id: str, options: ExecutionOptions) -> None:
    """Tarefa em segundo plano que orquestra a execução via ExecutionService."""
    service = ExecutionService()
    try:
        scenario_id = EXECUTIONS.get(run_id, {}).get("scenario_id", "desconhecido")
        await publish_execution_event(
            run_id, "log", {"message": f"Iniciando execução do cenário: {scenario_id}"}
        )
        try:
            scenario = load_scenario(str(options.scenario_path))
            await publish_execution_event(
                run_id,
                "log",
                {"message": f"Cenário carregado: '{scenario.title}' com {len(scenario.steps)} passo(s)."},
            )
        except Exception:
            scenario = None

        report = await service.run(options)
        await _emit_step_events(run_id, report, scenario)
        await _emit_checkpoint_events(run_id, report)

        result_data = {
            "success": report.success,
            "total_issues": report.total_issues,
            "duration_seconds": report.duration_seconds,
        }
        EXECUTIONS[run_id]["status"] = "completed"
        EXECUTIONS[run_id]["result"] = result_data
        EXECUTIONS[run_id]["logs"].append("Execução concluída com sucesso.")

        await publish_execution_event(run_id, "log", {"message": "Execução concluída com sucesso."})
        await publish_execution_event(run_id, "completed", result_data)
    except Exception as ex:
        err_msg = str(ex)
        EXECUTIONS[run_id]["status"] = "failed"
        EXECUTIONS[run_id]["error"] = err_msg
        EXECUTIONS[run_id]["logs"].append(f"Erro durante a execução: {err_msg}")
        await publish_execution_event(run_id, "log", {"message": f"Erro durante a execução: {err_msg}"})
        await publish_execution_event(run_id, "error", {"error": err_msg})
    finally:
        execution = EXECUTIONS.get(run_id, {})
        for q in [execution.get("queue"), *execution.get("subscribers", [])]:
            if q:
                await q.put(None)


# --- Endpoints da API ---


@router.get("/status")
async def get_status(request: Request) -> dict[str, str]:
    """Endpoint público de liveness sem autenticação."""
    project_dir = get_project_dir(request)
    return {
        "status": "ok",
        "studio_version": studio_version,
        "core_version": core_version,
        "project_dir": str(project_dir) if project_dir is not None else "",
    }


# --- Projetos ---


@router.get("/projects", response_model=list[ProjectSummaryDTO])
async def list_projects(
    request: Request,
    _: str = Depends(verify_studio_token),
) -> list[ProjectSummaryDTO]:
    """Lista todos os projetos cadastrados no catálogo global com status de ativação."""
    catalog = list_registered_projects()
    current_proj_dir = get_project_dir(request)

    result: list[ProjectSummaryDTO] = []

    for p_id, entry in catalog.items():
        entry_root = Path(entry.root_path).resolve()
        is_active = (entry_root == current_proj_dir) if current_proj_dir is not None else False

        result.append(
            ProjectSummaryDTO(
                id=p_id,
                name=entry.name,
                path=str(entry.root_path),
                scenarios_count=len(entry.scenarios),
                last_used=entry.last_run or "",
                is_active=is_active,
            )
        )

    return sorted(result, key=lambda p: (not p.is_active, p.name.lower()))


@router.post("/projects/select")
async def select_project(
    payload: ProjectSelectRequest,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Seleciona o projeto ativo no Studio alterando o workspace em memória."""
    match = find_project_in_catalog(payload.project_id)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Projeto '{payload.project_id}' não encontrado no catálogo.",
        )

    p_id, entry = match
    target_path = Path(entry.root_path).resolve()
    request.app.state.project_dir = target_path

    return {
        "success": True,
        "project_id": p_id,
        "project_name": entry.name,
        "project_dir": str(target_path),
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Cadastra um novo diretório de projeto no catálogo e o ativa no Studio."""
    proj_path = Path(payload.path).resolve()
    if not proj_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O caminho '{payload.path}' não é um diretório válido existente.",
        )

    clean_name = payload.name.strip()
    if not clean_name:
        clean_name = proj_path.name

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", clean_name.lower().strip()).strip("-") or "default"

    cfg_file = ensure_user_config()
    try:
        content = cfg_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    projects_map = data.setdefault("projects", {})
    if slug not in projects_map or not isinstance(projects_map[slug], dict):
        projects_map[slug] = {
            "name": clean_name,
            "root_path": str(proj_path),
            "scenarios": {},
            "last_run": None,
        }
    else:
        projects_map[slug]["name"] = clean_name
        projects_map[slug]["root_path"] = str(proj_path)

    cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    with contextlib.suppress(Exception):
        cfg_file.chmod(0o600)

    scen_service = ScenarioService()
    found_scenarios = scen_service.list_scenarios(proj_path, project_id=slug)
    for sc in found_scenarios:
        if sc.source == "project":
            p = scen_service.find_scenario_path(sc.id, proj_path)
            if p:
                projects_map[slug]["scenarios"][sc.id] = {
                    "id": sc.id,
                    "name": sc.title,
                    "path": str(p),
                    "last_run": None,
                }

    cfg_file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    with contextlib.suppress(Exception):
        cfg_file.chmod(0o600)

    request.app.state.project_dir = proj_path

    return {
        "success": True,
        "project_id": slug,
        "project_name": clean_name,
        "project_dir": str(proj_path),
    }


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Remove um projeto do catálogo global sem deletar arquivos físicos no disco."""
    match = find_project_in_catalog(project_id)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Projeto '{project_id}' não encontrado no catálogo.",
        )

    p_id, entry = match
    remove_project_from_catalog(p_id)

    current_dir = get_project_dir(request)
    was_active = current_dir is not None and Path(entry.root_path).resolve() == current_dir
    remaining_catalog = list_registered_projects()

    active_id: str | None = None
    if was_active:
        if remaining_catalog:
            next_id, next_entry = next(iter(remaining_catalog.items()))
            request.app.state.project_dir = Path(next_entry.root_path).resolve()
            active_id = next_id
        else:
            request.app.state.project_dir = None
            active_id = None
    else:
        if current_dir is not None:
            for r_id, r_entry in remaining_catalog.items():
                if Path(r_entry.root_path).resolve() == current_dir:
                    active_id = r_id
                    break

    active_dir = get_project_dir(request)
    return {
        "success": True,
        "message": f"Projeto '{entry.name}' removido do catálogo com sucesso.",
        "project_id": p_id,
        "active_project_id": active_id,
        "active_project_dir": str(active_dir) if active_dir is not None else "",
    }


# Cenários


@router.get("/scenarios", response_model=list[ScenarioSummaryDTO])
async def list_scenarios(
    request: Request,
    project_id: str | None = None,
    _: str = Depends(verify_studio_token),
) -> list[ScenarioSummaryDTO]:
    """Lista todos os cenários disponíveis no projeto ativo ou selecionado."""
    project_dir = get_project_dir(request)
    if project_id and project_id != "library":
        with contextlib.suppress(Exception):
            catalog = list_registered_projects()
            if project_id in catalog and catalog[project_id].root_path:
                cand_dir = Path(catalog[project_id].root_path)
                if cand_dir.is_dir():
                    project_dir = cand_dir

    if project_dir is None:
        return []

    service = ScenarioService()
    return service.list_scenarios(project_dir, project_id=project_id, include_library=False)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetailDTO)
async def get_scenario(
    scenario_id: str,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> ScenarioDetailDTO:
    """Recupera detalhes estruturados e o conteúdo YAML original de um cenário."""
    project_dir = get_project_dir(request)
    service = ScenarioService()
    try:
        return service.get_scenario(scenario_id, project_dir)
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
async def create_scenario(
    req: ScenarioCreateRequest,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Grava um novo arquivo de cenário após validação de sintaxe e semântica."""
    project_dir = get_project_dir(request)
    if not project_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum projeto selecionado.",
        )
    service = ScenarioService()
    try:
        saved_path = service.save_scenario(req.yaml_content, req.filename, project_dir)
        return {"success": True, "path": str(saved_path)}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err

    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.put("/scenarios/{scenario_id}")
async def update_scenario(
    scenario_id: str,
    req: ScenarioUpdateRequest,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Atualiza o conteúdo de um cenário existente."""
    project_dir = get_project_dir(request)
    if not project_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum projeto selecionado.",
        )
    service = ScenarioService()
    filename = req.filename or f"{scenario_id}.yaml"
    try:
        saved_path = service.save_scenario(req.yaml_content, filename, project_dir)
        return {"success": True, "path": str(saved_path)}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err

    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(
    scenario_id: str,
    request: Request,
    delete_file: bool = Query(False, description="Se True, apaga o arquivo físico do disco"),
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Exclui ou desvincula um cenário pertencente ao projeto (bloqueia exclusão da biblioteca)."""
    project_dir = get_project_dir(request)
    if not project_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum projeto selecionado.",
        )

    # Identifica o project_id ativo se houver
    active_project_id: str | None = None
    with contextlib.suppress(Exception):
        catalog = list_registered_projects()
        resolved_proj = project_dir.resolve()
        for p_id, p_entry in catalog.items():
            if p_entry.root_path and Path(p_entry.root_path).resolve() == resolved_proj:
                active_project_id = p_id
                break

    service = ScenarioService()
    try:
        deleted = service.delete_scenario(
            scenario_id,
            project_dir,
            project_id=active_project_id,
            delete_file=delete_file,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cenário '{scenario_id}' não encontrado no projeto ou protegido contra exclusão.",
            )
        return {"success": True, "delete_file": delete_file}
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post("/scenarios/validate", response_model=ValidationResult)
async def validate_scenario(
    req: ScenarioValidateRequest,
    _: str = Depends(verify_studio_token),
) -> ValidationResult:
    """Valida estaticamente um conteúdo YAML retornando erros de sintaxe ou passos."""
    service = ScenarioService()
    return service.validate_scenario(req.yaml_content)


# Execuções


@router.post("/execution/run", status_code=status.HTTP_202_ACCEPTED)
async def run_execution(
    req: ExecutionRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> dict[str, str]:
    """Inicia a execução de auditoria em segundo plano via ExecutionService."""
    project_dir = get_project_dir(request)
    scenario_path = ScenarioService().find_scenario_path(req.scenario_id, project_dir)
    if not scenario_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cenário '{req.scenario_id}' não encontrado no projeto ou biblioteca.",
        )

    run_id = secrets.token_hex(8)
    output_dir = req.overrides.get("output_dir") or str(get_output_dir(project_dir))

    main_queue: asyncio.Queue[str | None] = asyncio.Queue()

    _register_execution(
        run_id,
        {
            "run_id": run_id,
            "scenario_id": req.scenario_id,
            "status": "running",
            "current_step": 0,
            "logs": [f"Iniciando execução do cenário: {req.scenario_id}"],
            "started_at": datetime.now(UTC).isoformat(),
            "result": None,
            "error": None,
            "queue": main_queue,
            "subscribers": [],
            "event_history": [],
        },
    )

    # Prepara opções sanitizadas para o ExecutionService
    valid_fields = set(ExecutionOptions.model_fields.keys())
    sanitized_overrides = {k: v for k, v in req.overrides.items() if k in valid_fields}

    options = ExecutionOptions(
        scenario_path=scenario_path,
        output_dir=output_dir,
        **sanitized_overrides,
    )

    background_tasks.add_task(_execute_scenario_task, run_id, options)
    return {"run_id": run_id, "status": "running"}


@router.get("/execution/{run_id}")
async def get_execution_status(
    run_id: str,
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Consulta o status, progresso e logs de uma execução disparada."""
    if run_id not in EXECUTIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execução '{run_id}' não encontrada.",
        )
    ex = EXECUTIONS[run_id]
    return {
        "run_id": ex["run_id"],
        "scenario_id": ex["scenario_id"],
        "status": ex["status"],
        "current_step": ex.get("current_step", 0),
        "logs": list(ex.get("logs", [])),
        "started_at": ex.get("started_at"),
        "result": ex.get("result"),
        "error": ex.get("error"),
    }


@router.get("/execution/{run_id}/stream")
async def stream_execution(
    run_id: str,
    _: str = Depends(verify_studio_token_or_query),
) -> StreamingResponse:
    """Endpoint SSE para streaming em tempo real de logs e checkpoints da execução."""
    if run_id not in EXECUTIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execução '{run_id}' não encontrada.",
        )

    execution = EXECUTIONS[run_id]

    async def event_generator():
        sub_queue: asyncio.Queue[str | None] = asyncio.Queue()

        # Envia eventos do histórico para sincronização imediata
        history = list(execution.get("event_history", []))
        for chunk in history:
            yield chunk

        # Se a execução já finalizou, encerra o stream
        if execution.get("status") in ("completed", "failed", "error"):
            return

        execution.setdefault("subscribers", []).append(sub_queue)
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(sub_queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                if chunk is None:
                    break

                yield chunk

                # Se for evento de término, encerra o stream
                if '"event": "completed"' in chunk or '"event": "error"' in chunk:
                    break
        finally:
            subscribers = execution.get("subscribers", [])
            if sub_queue in subscribers:
                subscribers.remove(sub_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Configurações


@router.get("/config", response_model=SafeConfigDTO)
async def get_config(
    request: Request,
    _: str = Depends(verify_studio_token),
) -> SafeConfigDTO:
    """Retorna a configuração global com todos os tokens e segredos mascarados."""
    project_dir = get_project_dir(request)
    service = ConfigService()
    return service.get_safe_config(project_dir=project_dir)


@router.post("/config")
async def update_config(
    data: ConfigUpdateDTO,
    _: str = Depends(verify_studio_token),
) -> dict[str, Any]:
    """Atualiza configurações seguras e persiste com permissões restritas (0600)."""
    service = ConfigService()
    service.update_config(data)
    return {"success": True, "message": "Configurações atualizadas com sucesso."}


@router.post("/config/test-jira", response_model=ConnectionResult)
async def test_jira_connection(
    req: TestJiraRequest,
    _: str = Depends(verify_studio_token),
) -> ConnectionResult:
    """Testa a conectividade com a API do Jira sem salvar as credenciais."""
    service = ConfigService()
    return await service.test_jira_connection(url=req.url, email=req.email, token=req.token)


@router.post("/config/test-ai", response_model=ConnectionResult)
async def test_ai_connection(
    req: TestAIRequest,
    _: str = Depends(verify_studio_token),
) -> ConnectionResult:
    """Testa a conectividade com o modelo ou gateway de IA configurado."""
    service = ConfigService()
    return await service.test_ai_connection(provider=req.provider)


# Resultados e Artefatos


@router.get("/results", response_model=list[ExecutionSummaryDTO])
async def list_results(
    request: Request,
    limit: int = 50,
    _: str = Depends(verify_studio_token),
) -> list[ExecutionSummaryDTO]:
    """Lista o histórico de execuções anteriores a partir dos relatórios salvos."""
    project_dir = get_project_dir(request)
    output_dir = get_output_dir(project_dir)
    service = ResultsService()
    return service.list_executions(output_dir, limit=limit)


@router.get("/results/{execution_id}", response_model=ExecutionDetailDTO)
async def get_result_detail(
    execution_id: str,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> ExecutionDetailDTO:
    """Retorna detalhes completos de uma execução específica incluindo checkpoints e issues."""
    project_dir = get_project_dir(request)
    output_dir = get_output_dir(project_dir)
    service = ResultsService()
    try:
        return service.get_execution(execution_id, output_dir)
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get("/results/{execution_id}/artifacts/{artifact_name}")
async def get_result_artifact(
    execution_id: str,
    artifact_name: str,
    request: Request,
    _: str = Depends(verify_studio_token),
) -> FileResponse:
    """Entrega de forma segura artefatos de auditoria (HTML, screenshots, vídeos)."""
    project_dir = get_project_dir(request)
    output_dir = get_output_dir(project_dir)
    service = ResultsService()
    try:
        artifact_path = service.get_artifact(execution_id, artifact_name, output_dir)
        return FileResponse(path=str(artifact_path))
    except FileNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


# Assistente IA de Autoria


@router.post("/generate-scenario")
async def generate_scenario(
    req: GenerateScenarioRequest,
    _: str = Depends(verify_studio_token),
) -> dict[str, str]:
    """Gera um template estruturado de cenário YAML a partir de um prompt em linguagem natural."""
    clean_prompt = req.prompt.strip()
    if not clean_prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O prompt para geração do cenário não pode ser vazio.",
        )

    # Gera slug amigável para o identificador
    slug = "".join(c if c.isalnum() else "_" for c in clean_prompt.lower())[:30].strip("_")
    if not slug:
        slug = "cenario_assistente"

    yaml_content = f"""id: {slug}
title: "Auditoria: {clean_prompt}"
profile: "generic"
tags:
  - "studio"
  - "ia-generated"
steps:
  - action: goto
    url: "https://exemplo.com.br"
    description: "Navega até o ponto de partida do fluxo"
  - action: checkpoint
    name: "visao_geral"
    expected_behavior: "A tela deve estar totalmente renderizada conforme o objetivo: {clean_prompt}"
"""
    return {"yaml_content": yaml_content}
