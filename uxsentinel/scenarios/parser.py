import os
import re
from pathlib import Path

import yaml

from uxsentinel.core.models import Scenario, StepAction

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


def _resolve_env_str(val: str, env_source: dict[str, str] | None = None) -> str:
    """Resolve uma string que contém ${VAR} ou ${VAR:-default}."""

    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        if env_source and var_name in env_source:
            return env_source[var_name]
        return os.environ.get(var_name, default_val)

    # Executa até 3 passes para resolver referências em cascata
    current = val
    for _ in range(3):
        new_val = ENV_VAR_PATTERN.sub(_replacer, current)
        if new_val == current:
            break
        current = new_val
    return current


def load_scenario(file_path: str) -> Scenario:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de cenário não encontrado: {file_path}")

    raw_text = path.read_text(encoding="utf-8")
    parsed_raw = yaml.safe_load(raw_text) or {}

    # 1. Resolve o dicionário de variáveis do bloco 'env' contra as variáveis do SO
    custom_env_raw = parsed_raw.get("env", {})
    resolved_env: dict[str, str] = {}
    for k, v in custom_env_raw.items():
        if isinstance(v, str):
            resolved_env[k] = _resolve_env_str(v)
        else:
            resolved_env[k] = str(v)

    # 2. Agora interpola o texto inteiro do YAML usando resolved_env + os.environ
    interpolated_text = _resolve_env_str(raw_text, env_source=resolved_env)
    parsed_dict = yaml.safe_load(interpolated_text) or {}

    steps_raw = parsed_dict.get("steps", [])
    steps: list[StepAction] = []
    for s in steps_raw:
        steps.append(
            StepAction(
                action=s.get("action", ""),
                selector=s.get("selector"),
                value=s.get("value"),
                url=s.get("url"),
                timeout=s.get("timeout"),
                description=s.get("description"),
                name=s.get("name"),
                expected_behavior=s.get("expected_behavior"),
                criteria=s.get("criteria"),
            )
        )

    return Scenario(
        id=parsed_dict.get("id", path.stem),
        title=parsed_dict.get("title", path.stem),
        description=parsed_dict.get("description"),
        profile=parsed_dict.get("profile", "generic"),
        provider=parsed_dict.get("provider"),
        tags=parsed_dict.get("tags", []),
        env=resolved_env,
        steps=steps,
    )
