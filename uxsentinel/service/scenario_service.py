"""Serviço de gerenciamento, CRUD e validação segura de cenários YAML."""

import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from uxsentinel.core.config import (
    list_registered_projects,
    register_project_scenario,
    remove_scenario_from_catalog,
)
from uxsentinel.scenarios.parser import (
    IGNORED_YAML_FILENAMES,
    is_valid_scenario_file,
    load_scenario,
)

__all__ = [
    "IGNORED_YAML_FILENAMES",
    "ScenarioDetailDTO",
    "ScenarioService",
    "ScenarioSummaryDTO",
    "StepDTO",
    "StepError",
    "ValidationResult",
    "is_valid_scenario_file",
]


class StepDTO(BaseModel):
    """Representação estruturada de um passo de cenário para a interface."""

    index: int
    action: str
    selector: str | None = None
    value: str | None = None
    description: str | None = None
    url: str | None = None
    name: str | None = None
    expected_behavior: str | None = None


class ScenarioSummaryDTO(BaseModel):
    """Resumo de um cenário para exibição em listas e painéis."""

    id: str
    filename: str
    title: str
    profile: str = "generic"
    tags: list[str] = Field(default_factory=list)
    source: str = "project"  # 'project' ou 'library'
    step_count: int = 0
    modified_at: datetime
    project_id: str | None = None
    project_name: str | None = None
    headless: bool | None = None
    devtools: bool | None = None
    capture_console: bool | None = None
    inspect: bool | None = None


class ScenarioDetailDTO(ScenarioSummaryDTO):
    """Detalhes completos de um cenário incluindo conteúdo original e passos."""

    raw_yaml: str
    steps: list[StepDTO] = Field(default_factory=list)


class StepError(BaseModel):
    """Erro identificado na validação de um passo de cenário."""

    step_index: int
    field: str
    message: str


class ValidationResult(BaseModel):
    """Resultado da validação estática de um cenário YAML."""

    valid: bool
    errors: list[StepError] = Field(default_factory=list)


class ScenarioService:
    """Serviço para descoberta, leitura, gravação e validação de cenários."""

    @staticmethod
    def _sanitize_path_component(name: str) -> None:
        """Impede path traversal garantindo que o nome do arquivo/id seja estritamente local."""
        if not name or ".." in name or name.startswith("/") or "\\" in name:
            raise PermissionError(f"Caminho não permitido ou tentativa de path traversal detectada: {name}")

    @staticmethod
    def get_library_dir() -> Path:
        """Localiza o diretório da biblioteca de cenários embutida do UXSentinel."""
        return Path(__file__).resolve().parent.parent / "scenarios" / "library"

    @staticmethod
    def is_valid_scenario_file(path: Path | str) -> bool:
        """Verifica se o arquivo é um cenário de teste YAML válido do UXSentinel."""
        return is_valid_scenario_file(path)

    def _collect_project_scenarios(
        self,
        project_id: str,
        entry: Any,
        scenarios: list[ScenarioSummaryDTO],
        seen_ids: set[str],
    ) -> None:
        """Varre e coleta cenários válidos de um projeto cadastrado no catálogo."""
        candidate_paths: list[Path] = []
        p_name = entry.name or project_id

        if entry.root_path:
            with contextlib.suppress(Exception):
                root = Path(entry.root_path).resolve()
                if root.is_dir():
                    search_folders = [
                        root / "scenarios",
                        root / ".uxsentinel" / "scenarios",
                        root / "tests" / "scenarios",
                        root,
                    ]
                    for sdir in search_folders:
                        if not sdir.is_dir():
                            continue
                        for ext in ("*.yaml", "*.yml"):
                            for f in sdir.glob(ext):
                                candidate_paths.append(f)

        if getattr(entry, "scenarios", None):
            for s_item in entry.scenarios.values():
                if getattr(s_item, "path", None):
                    with contextlib.suppress(Exception):
                        p = Path(s_item.path).resolve()
                        if p.is_file():
                            candidate_paths.append(p)

        for yml in candidate_paths:
            yml_resolved = yml.resolve()
            if not is_valid_scenario_file(yml_resolved):
                continue
            try:
                sc = load_scenario(str(yml_resolved))
                if not sc.steps:
                    continue
                if sc.id in seen_ids:
                    continue
                seen_ids.add(sc.id)
                stat = yml_resolved.stat()
                mod_time = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                scenarios.append(
                    ScenarioSummaryDTO(
                        id=sc.id,
                        filename=yml_resolved.name,
                        title=sc.title,
                        profile=sc.profile,
                        tags=sc.tags,
                        source="project",
                        step_count=len(sc.steps),
                        modified_at=mod_time,
                        project_id=project_id,
                        project_name=p_name,
                        headless=sc.headless,
                        devtools=sc.devtools,
                        capture_console=sc.capture_console,
                        inspect=sc.inspect,
                    )
                )
            except Exception:
                continue

    def _collect_library_scenarios(
        self,
        scenarios: list[ScenarioSummaryDTO],
        seen_ids: set[str],
    ) -> None:
        """Coleta cenários válidos da biblioteca embutida do UXSentinel."""
        lib_dir = self.get_library_dir()
        if not lib_dir.is_dir():
            return
        for ext in ("*.yaml", "*.yml"):
            for yml in lib_dir.glob(ext):
                yml_resolved = yml.resolve()
                if not is_valid_scenario_file(yml_resolved):
                    continue
                try:
                    sc = load_scenario(str(yml_resolved))
                    if not sc.steps:
                        continue
                    if sc.id in seen_ids:
                        continue
                    seen_ids.add(sc.id)
                    stat = yml_resolved.stat()
                    mod_time = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                    scenarios.append(
                        ScenarioSummaryDTO(
                            id=sc.id,
                            filename=yml_resolved.name,
                            title=sc.title,
                            profile=sc.profile,
                            tags=sc.tags,
                            source="library",
                            step_count=len(sc.steps),
                            modified_at=mod_time,
                            project_id="library",
                            project_name="Biblioteca Embutida",
                            headless=sc.headless,
                            devtools=sc.devtools,
                            capture_console=sc.capture_console,
                            inspect=sc.inspect,
                        )
                    )
                except Exception:
                    continue

    def list_scenarios(
        self,
        base_dir: Path | str | None = None,
        project_id: str | None = None,
        include_library: bool = True,
    ) -> list[ScenarioSummaryDTO]:
        """Lista cenários do projeto local e opcionalmente da biblioteca interna."""
        scenarios: list[ScenarioSummaryDTO] = []
        seen_ids: set[str] = set()

        catalog: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            catalog = list_registered_projects()

        # 1. Se project_id == "library", busca exclusivamente na biblioteca interna
        if project_id == "library":
            if include_library:
                self._collect_library_scenarios(scenarios, seen_ids)
            return sorted(scenarios, key=lambda s: s.title.lower())

        # 2. Se project_id for fornecido (diferente de "library"), busca no catálogo
        if project_id is not None:
            if project_id not in catalog:
                return []
            entry = catalog[project_id]
            self._collect_project_scenarios(project_id, entry, scenarios, seen_ids)
            return sorted(scenarios, key=lambda s: s.title.lower())

        # 3. Se project_id for None (ou seja, 'Todos os Projetos'):
        # Se houver projetos cadastrados no catálogo, varre cada um deles
        if catalog:
            for p_id, entry in catalog.items():
                self._collect_project_scenarios(p_id, entry, scenarios, seen_ids)
        else:
            # Se NÃO houver nenhum projeto cadastrado no catálogo:
            # Não invente projetos fictícios a partir do diretório onde o servidor foi aberto (como $HOME / ALEXANDRE).
            # Retorne lista vazia para projetos!
            pass

        # Inclui biblioteca embutida se solicitado
        if include_library:
            self._collect_library_scenarios(scenarios, seen_ids)

        return sorted(scenarios, key=lambda s: s.title.lower())

    def find_scenario_path(self, scenario_id: str, base_dir: Path | str | None) -> Path | None:
        """Localiza o caminho físico de um cenário no projeto ou na biblioteca interna."""
        try:
            self._sanitize_path_component(scenario_id)
        except PermissionError:
            return None

        clean_q = scenario_id.strip()
        if not clean_q:
            return None

        # 1. Se base_dir foi fornecido, prioriza a busca dentro do projeto ativo
        if base_dir is not None:
            base_path = Path(base_dir).resolve()
            for sdir in (
                base_path / "scenarios",
                base_path / ".uxsentinel" / "scenarios",
                base_path / "tests" / "scenarios",
                base_path,
            ):
                if not sdir.is_dir():
                    continue
                for ext in ("*.yaml", "*.yml"):
                    for candidate in sdir.glob(ext):
                        if not is_valid_scenario_file(candidate):
                            continue
                        try:
                            sc = load_scenario(str(candidate))
                            if (
                                sc.id == scenario_id
                                or candidate.stem == scenario_id
                                or candidate.name == scenario_id
                            ):
                                return candidate.resolve()
                        except Exception:
                            continue

        # 2. Busca nos projetos registrados no catálogo
        with contextlib.suppress(Exception):
            catalog = list_registered_projects()
            for p_val in catalog.values():
                for s_key, s_item in p_val.scenarios.items():
                    if (s_key == scenario_id or getattr(s_item, "id", None) == scenario_id) and (
                        s_item.path and Path(s_item.path).is_file()
                    ):
                        cand = Path(s_item.path).resolve()
                        if is_valid_scenario_file(cand):
                            return cand

                if p_val.root_path:
                    r_path = Path(p_val.root_path).resolve()
                    if r_path.is_dir():
                        for sdir in (
                            r_path / "scenarios",
                            r_path / ".uxsentinel" / "scenarios",
                            r_path / "tests" / "scenarios",
                            r_path,
                        ):
                            if not sdir.is_dir():
                                continue
                            for ext in ("*.yaml", "*.yml"):
                                for candidate in sdir.glob(ext):
                                    if not is_valid_scenario_file(candidate):
                                        continue
                                    try:
                                        sc = load_scenario(str(candidate))
                                        if (
                                            sc.id == scenario_id
                                            or candidate.stem == scenario_id
                                            or candidate.name == scenario_id
                                        ):
                                            return candidate.resolve()
                                    except Exception:
                                        continue

        # 3. Busca na biblioteca embutida do core
        lib_dir = self.get_library_dir()
        if lib_dir.is_dir():
            for ext in ("*.yaml", "*.yml"):
                for candidate in lib_dir.glob(ext):
                    if not is_valid_scenario_file(candidate):
                        continue
                    try:
                        sc = load_scenario(str(candidate))
                        if (
                            sc.id == scenario_id
                            or candidate.stem == scenario_id
                            or candidate.name == scenario_id
                        ):
                            return candidate.resolve()
                    except Exception:
                        continue

        return None

    def get_scenario(self, scenario_id: str, base_dir: Path | str | None) -> ScenarioDetailDTO:
        """Obtém detalhes de um cenário específico preservando raw_yaml original."""
        self._sanitize_path_component(scenario_id)
        target_file = self.find_scenario_path(scenario_id, base_dir)

        if not target_file or not target_file.is_file():
            raise FileNotFoundError(f"Cenário com id '{scenario_id}' não encontrado em {base_dir}")

        lib_dir = self.get_library_dir().resolve()
        source_found = "library" if str(target_file.resolve()).startswith(str(lib_dir)) else "project"

        raw_yaml = target_file.read_text(encoding="utf-8")
        sc = load_scenario(str(target_file))
        stat = target_file.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

        steps_dto = [
            StepDTO(
                index=idx + 1,
                action=step.action,
                selector=step.selector,
                value=step.value,
                description=step.description,
                url=step.url,
                name=step.name,
                expected_behavior=step.expected_behavior,
            )
            for idx, step in enumerate(sc.steps)
        ]

        return ScenarioDetailDTO(
            id=sc.id,
            filename=target_file.name,
            title=sc.title,
            profile=sc.profile,
            tags=sc.tags,
            source=source_found,
            step_count=len(sc.steps),
            modified_at=mod_time,
            raw_yaml=raw_yaml,
            steps=steps_dto,
            headless=sc.headless,
            devtools=sc.devtools,
            capture_console=sc.capture_console,
            inspect=sc.inspect,
        )

    def validate_scenario(self, yaml_content: str) -> ValidationResult:
        """Valida o conteúdo YAML de um cenário identificando erros de sintaxe e de schema."""
        errors: list[StepError] = []

        if not yaml_content or not yaml_content.strip():
            return ValidationResult(
                valid=False,
                errors=[StepError(step_index=0, field="yaml", message="Conteúdo YAML está vazio.")],
            )

        try:
            parsed = yaml.safe_load(yaml_content)
        except yaml.YAMLError as err:
            line_no = getattr(err, "problem_mark", None)
            step_idx = line_no.line + 1 if line_no else 0
            return ValidationResult(
                valid=False,
                errors=[StepError(step_index=step_idx, field="syntax", message=str(err))],
            )

        if not isinstance(parsed, dict):
            return ValidationResult(
                valid=False,
                errors=[
                    StepError(
                        step_index=0,
                        field="root",
                        message="O cenário deve ser um dicionário/objeto YAML.",
                    )
                ],
            )

        steps = parsed.get("steps")
        if not steps or not isinstance(steps, list):
            errors.append(
                StepError(
                    step_index=0,
                    field="steps",
                    message="O cenário precisa declarar uma lista 'steps'.",
                )
            )
            return ValidationResult(valid=False, errors=errors)

        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(
                    StepError(
                        step_index=idx,
                        field="step",
                        message=f"Passo {idx} deve ser um dicionário/objeto.",
                    )
                )
                continue
            action = step.get("action")
            if not action:
                errors.append(
                    StepError(
                        step_index=idx,
                        field="action",
                        message=f"Passo {idx} não possui a propriedade obrigatória 'action'.",
                    )
                )
                continue

            if action == "goto" and not step.get("url"):
                errors.append(
                    StepError(
                        step_index=idx,
                        field="url",
                        message=f"Ação 'goto' no passo {idx} requer 'url'.",
                    )
                )

            if action in ("click", "fill") and not step.get("selector") and not step.get("target"):
                errors.append(
                    StepError(
                        step_index=idx,
                        field="selector",
                        message=f"Ação '{action}' no passo {idx} requer 'selector' ou 'target'.",
                    )
                )

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def save_scenario(self, yaml_content: str, filename: str, base_dir: Path | str) -> Path:
        """Valida e salva um arquivo de cenário no diretório scenarios/ do projeto."""
        self._sanitize_path_component(filename)
        validation = self.validate_scenario(yaml_content)
        if not validation.valid:
            err_msg = "; ".join(f"Passo {e.step_index} [{e.field}]: {e.message}" for e in validation.errors)
            raise ValueError(f"YAML inválido: {err_msg}")

        base_path = Path(base_dir).resolve()
        target_dir = base_path / "scenarios"
        target_dir.mkdir(parents=True, exist_ok=True)

        if not filename.endswith((".yaml", ".yml")):
            filename = f"{filename}.yaml"

        target_file = target_dir / filename
        target_file.write_text(yaml_content, encoding="utf-8")
        return target_file

    def delete_scenario(
        self,
        scenario_id: str,
        base_dir: Path | str | None,
        project_id: str | None = None,
        delete_file: bool = False,
    ) -> bool:
        """Exclui ou desvincula um cenário pertencente ao projeto (nunca da biblioteca interna)."""
        if not scenario_id or not scenario_id.strip():
            return False

        self._sanitize_path_component(scenario_id)

        target_file = self.find_scenario_path(scenario_id, base_dir)

        # Se não encontrar fisicamente, verifica se o cenário está registrado no catálogo
        catalog_entry_found = False
        with contextlib.suppress(Exception):
            catalog = list_registered_projects()
            for p_id, p_val in catalog.items():
                if project_id and p_id != project_id:
                    continue
                if scenario_id in p_val.scenarios:
                    catalog_entry_found = True
                    break
                for s_key, s_item in p_val.scenarios.items():
                    if s_key == scenario_id or getattr(s_item, "id", None) == scenario_id:
                        catalog_entry_found = True
                        break
                if catalog_entry_found:
                    break

        # Caso não encontre nem o arquivo nem o cenário no catálogo, retorne False
        if target_file is None and not catalog_entry_found:
            return False

        # Se target_file fizer parte da biblioteca embutida do core, protege contra exclusão
        lib_dir = self.get_library_dir().resolve()
        if target_file is not None and str(target_file.resolve()).startswith(str(lib_dir)):
            return False

        # Sempre remove o vínculo do catálogo
        catalog_removed = remove_scenario_from_catalog(scenario_id, project_id=project_id)
        if target_file is not None and target_file.is_file():
            with contextlib.suppress(Exception):
                sc = load_scenario(str(target_file))
                if sc.id != scenario_id and remove_scenario_from_catalog(sc.id, project_id=project_id):
                    catalog_removed = True

        file_deleted = False
        if delete_file and target_file is not None and target_file.is_file():
            target_file.unlink()
            file_deleted = True

        if file_deleted or catalog_removed:
            return True

        return bool(not delete_file and (target_file is not None or catalog_entry_found))

    def duplicate_scenario(
        self,
        scenario_id: str,
        base_dir: Path | str | None = None,
        new_id: str | None = None,
        new_title: str | None = None,
        project_id: str | None = None,
    ) -> ScenarioDetailDTO:
        """Duplica um cenário YAML existente gerando novo ID e título, salvando no disco e registrando no catálogo."""
        self._sanitize_path_component(scenario_id)
        orig_path = self.find_scenario_path(scenario_id, base_dir)
        if not orig_path or not orig_path.is_file():
            raise FileNotFoundError(f"Cenário '{scenario_id}' não encontrado para duplicação.")

        orig_content = orig_path.read_text(encoding="utf-8")
        loaded = yaml.safe_load(orig_content)
        data: dict[str, Any] = loaded if isinstance(loaded, dict) else {}

        if not new_id or not new_id.strip():
            candidate_id = f"{scenario_id}_copia"
            candidate_path = orig_path.parent / f"{candidate_id}.yaml"
            counter = 2
            while candidate_path.exists():
                candidate_id = f"{scenario_id}_copia_{counter}"
                candidate_path = orig_path.parent / f"{candidate_id}.yaml"
                counter += 1
            new_id = candidate_id
        else:
            new_id = new_id.strip()
            if new_id.endswith((".yaml", ".yml")):
                new_id = new_id.rsplit(".", 1)[0]
            self._sanitize_path_component(new_id)

        if not new_title or not new_title.strip():
            orig_title = data.get("title") or scenario_id
            new_title = f"{orig_title} (Cópia)"
        else:
            new_title = new_title.strip()

        data["id"] = new_id
        data["title"] = new_title

        new_path = orig_path.parent / f"{new_id}.yaml"
        new_content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        new_path.write_text(new_content, encoding="utf-8")

        project_name: str | None = None
        if project_id:
            with contextlib.suppress(Exception):
                catalog = list_registered_projects()
                if project_id in catalog:
                    project_name = catalog[project_id].name

        register_project_scenario(
            scenario_path=new_path,
            scenario_data=data,
            project_name=project_name,
        )

        return self.get_scenario(new_id, base_dir=base_dir or orig_path.parent)
