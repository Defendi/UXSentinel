"""Serviço de gerenciamento, CRUD e validação segura de cenários YAML."""

import contextlib
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from uxsentinel.core.config import (
    infer_project_metadata,
    list_registered_projects,
    remove_scenario_from_catalog,
)
from uxsentinel.scenarios.parser import load_scenario


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

    def list_scenarios(
        self,
        base_dir: Path | str | None = None,
        project_id: str | None = None,
        include_library: bool = True,
    ) -> list[ScenarioSummaryDTO]:
        """Lista cenários do projeto local e opcionalmente da biblioteca interna."""
        scenarios: list[ScenarioSummaryDTO] = []
        seen_ids: set[str] = set()

        search_dirs: list[tuple[Path, str]] = []
        if base_dir is not None:
            base_path = Path(base_dir).resolve()
            search_dirs.extend(
                [
                    (base_path / "scenarios", "project"),
                    (base_path / ".uxsentinel" / "scenarios", "project"),
                    (base_path / "tests" / "scenarios", "project"),
                    (base_path, "project"),
                ]
            )
        if include_library:
            search_dirs.append((self.get_library_dir(), "library"))

        if not search_dirs:
            return scenarios

        catalog = {}
        with contextlib.suppress(Exception):
            catalog = list_registered_projects()

        for sdir, source in search_dirs:
            if not sdir.is_dir():
                continue
            for ext in ("*.yaml", "*.yml"):
                for yml in sdir.glob(ext):
                    if yml.name in (
                        "config.yaml",
                        "config.example.yaml",
                        "uxsentinel.yaml",
                        ".uxsentinel.yaml",
                    ):
                        continue
                    try:
                        sc = load_scenario(str(yml))
                        if sc.id in seen_ids:
                            continue
                        seen_ids.add(sc.id)
                        stat = yml.stat()
                        mod_time = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                        yml_resolved = yml.resolve()

                        p_id: str | None = None
                        p_name: str | None = None

                        # 1. Se o caminho do YAML estiver explicitamente registrado em p_val.scenarios de algum projeto do catálogo
                        for cat_p_id, p_val in catalog.items():
                            for _s_id, s_item in p_val.scenarios.items():
                                if s_item.path:
                                    with contextlib.suppress(Exception):
                                        if Path(s_item.path).resolve() == yml_resolved:
                                            p_id = cat_p_id
                                            p_name = p_val.name
                                            break
                            if p_id is not None:
                                break

                        # 2. Se o caminho do YAML estiver sob o root_path de algum projeto do catálogo (para cenários do projeto)
                        if p_id is None and source != "library":
                            for cat_p_id, p_val in catalog.items():
                                if p_val.root_path:
                                    with contextlib.suppress(Exception):
                                        cat_root = Path(p_val.root_path).resolve()
                                        if yml_resolved == cat_root or cat_root in yml_resolved.parents:
                                            p_id = cat_p_id
                                            p_name = p_val.name
                                            break

                        # 3. Caso contrário, use infer_project_metadata(yml)
                        # 4. Se for da biblioteca padrão e não pertencer a nenhum projeto cadastrado nem ao projeto do base_dir,
                        # atribua p_id = "library" e p_name = "Biblioteca Embutida"
                        if p_id is None:
                            if source == "library":
                                p_id = "library"
                                p_name = "Biblioteca Embutida"
                            else:
                                inf_id, inf_name, _ = infer_project_metadata(yml)
                                p_id = inf_id
                                p_name = inf_name
                                if p_id in catalog:
                                    p_name = catalog[p_id].name

                        # Se filtragem por project_id foi solicitada, ignora se não corresponder
                        if project_id is not None and p_id != project_id:
                            continue

                        scenarios.append(
                            ScenarioSummaryDTO(
                                id=sc.id,
                                filename=yml.name,
                                title=sc.title,
                                profile=sc.profile,
                                tags=sc.tags,
                                source=source,
                                step_count=len(sc.steps),
                                modified_at=mod_time,
                                project_id=p_id,
                                project_name=p_name,
                            )
                        )
                    except Exception:
                        continue

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

        search_dirs: list[Path] = []
        if base_dir is not None:
            base_path = Path(base_dir).resolve()
            search_dirs.extend(
                [
                    base_path / "scenarios",
                    base_path / ".uxsentinel" / "scenarios",
                    base_path / "tests" / "scenarios",
                    base_path,
                ]
            )
        search_dirs.append(self.get_library_dir())

        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for ext in ("*.yaml", "*.yml"):
                for candidate in sdir.glob(ext):
                    if candidate.name in (
                        "config.yaml",
                        "config.example.yaml",
                        "uxsentinel.yaml",
                        ".uxsentinel.yaml",
                    ):
                        continue
                    try:
                        sc = load_scenario(str(candidate))
                        if sc.id == scenario_id or candidate.stem == scenario_id:
                            return candidate
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
    ) -> bool:
        """Exclui um cenário pertencente ao projeto (nunca da biblioteca interna)."""
        if base_dir is None:
            return False

        self._sanitize_path_component(scenario_id)
        base_path = Path(base_dir).resolve()
        target_dir = base_path / "scenarios"

        if not target_dir.is_dir():
            return False

        for ext in ("*.yaml", "*.yml"):
            for candidate in target_dir.glob(ext):
                try:
                    sc = load_scenario(str(candidate))
                    if sc.id == scenario_id or candidate.stem == scenario_id or candidate.name == scenario_id:
                        candidate.unlink()
                        remove_scenario_from_catalog(scenario_id, project_id=project_id)
                        if sc.id != scenario_id:
                            remove_scenario_from_catalog(sc.id, project_id=project_id)
                        return True
                except Exception:
                    continue

        return False
