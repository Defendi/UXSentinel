import os
import re
from pathlib import Path

import yaml

from uxsentinel.core.models import Scenario, ScenarioExceptions, StepAction

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


def _normalize_string_list(val: object) -> list[str]:
    if isinstance(val, list):
        return [str(item).strip() for item in val if str(item).strip()]
    if isinstance(val, str) and val.strip():
        if "\n" in val:
            return [line.strip() for line in val.splitlines() if line.strip()]
        return [val.strip()]
    return []


def parse_scenario_exceptions(raw_data: object) -> ScenarioExceptions | None:
    """Interpreta cláusula declarativa de exceções no formato estruturado (dict) ou sintético (list/str)."""
    if not raw_data:
        return None

    allowed_texts: list[str] = []
    ignored_selectors: list[str] = []
    ignored_elements: list[str] = []
    ignored_categories: list[str] = []
    custom_rules: list[str] = []

    if isinstance(raw_data, dict):
        allowed_texts.extend(
            _normalize_string_list(raw_data.get("allowed_texts") or raw_data.get("textos_permitidos") or [])
        )
        ignored_selectors.extend(
            _normalize_string_list(
                raw_data.get("ignored_selectors") or raw_data.get("seletores_ignorados") or []
            )
        )
        ignored_elements.extend(
            _normalize_string_list(
                raw_data.get("ignored_elements") or raw_data.get("elementos_ignorados") or []
            )
        )
        ignored_categories.extend(
            _normalize_string_list(
                raw_data.get("ignored_categories") or raw_data.get("categorias_ignoradas") or []
            )
        )
        custom_rules.extend(
            _normalize_string_list(
                raw_data.get("custom_rules")
                or raw_data.get("regras_customizadas")
                or raw_data.get("regras")
                or []
            )
        )
    elif isinstance(raw_data, list):
        for item in raw_data:
            s_item = str(item).strip()
            if not s_item:
                continue
            if s_item.startswith(("#", ".", "[")) or re.match(r"^[a-z]+(\.|#|\[)", s_item):
                ignored_selectors.append(s_item)
            elif (s_item.startswith(('"', "'")) and s_item.endswith(('"', "'"))) or len(s_item.split()) <= 4:
                cleaned = s_item.strip("\"'")
                allowed_texts.append(cleaned)
            else:
                custom_rules.append(s_item)
                quoted = re.findall(r"[\"']([^\"']+)[\"']", s_item)
                for q in quoted:
                    if q.startswith(("#", ".")):
                        ignored_selectors.append(q)
                    else:
                        allowed_texts.append(q)
    elif isinstance(raw_data, str):
        custom_rules.append(raw_data.strip())
        quoted = re.findall(r"[\"']([^\"']+)[\"']", raw_data)
        for q in quoted:
            if q.startswith(("#", ".")):
                ignored_selectors.append(q)
            else:
                allowed_texts.append(q)

    res = ScenarioExceptions(
        allowed_texts=list(dict.fromkeys(allowed_texts)),
        ignored_selectors=list(dict.fromkeys(ignored_selectors)),
        ignored_elements=list(dict.fromkeys(ignored_elements)),
        ignored_categories=list(dict.fromkeys(ignored_categories)),
        custom_rules=list(dict.fromkeys(custom_rules)),
    )
    return res if not res.is_empty() else None


def _resolve_env_str(
    val: str, env_source: dict[str, str] | None = None, allow_os_environ: bool = True
) -> str:
    """Resolve uma string que contém ${VAR} ou ${VAR:-default}."""

    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        has_default = match.group(2) is not None
        default_val = match.group(2) if has_default else ""
        if env_source and var_name in env_source:
            return env_source[var_name]
        if allow_os_environ:
            return os.environ.get(var_name, default_val)
        # Fora do bloco `env:` o corpo do cenário não enxerga o ambiente do processo,
        # senão um cenário de terceiros exfiltraria segredos (ex.: chaves de API).
        return default_val if has_default else match.group(0)

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

    # 2. Interpola o corpo do YAML apenas com as variáveis declaradas no bloco 'env'
    interpolated_text = _resolve_env_str(raw_text, env_source=resolved_env, allow_os_environ=False)
    parsed_dict = yaml.safe_load(interpolated_text) or {}

    steps_raw = parsed_dict.get("steps", [])
    if not isinstance(steps_raw, list):
        raise ValueError(
            f"Cenário inválido em '{file_path}': o campo 'steps' deve ser uma lista de passos, "
            f"mas veio como {type(steps_raw).__name__}."
        )

    steps: list[StepAction] = []
    for pos, s in enumerate(steps_raw, start=1):
        if not isinstance(s, dict):
            raise ValueError(
                f"Cenário inválido em '{file_path}': o passo {pos} deve ser um mapeamento "
                f"com 'action', mas veio como {type(s).__name__} ({s!r})."
            )

        action = s.get("action", "")
        ai_click_val = s.get("ai_click")
        ai_fill_val = s.get("ai_fill")
        ai_assert_val = s.get("ai_assert")
        ai_action_val = s.get("ai_action")
        target_val = s.get("target")

        # Se a ação não foi explicitada via 'action', deduz a partir das chaves semânticas
        if not action:
            if ai_click_val is not None:
                action = "ai_click"
            elif ai_fill_val is not None:
                action = "ai_fill"
            elif ai_assert_val is not None:
                action = "ai_assert"
            elif ai_action_val is not None:
                action = "ai_action"

        # Garante que target e os campos específicos estejam sincronizados
        target = target_val
        if action == "ai_click":
            target = target or ai_click_val or s.get("selector")
            ai_click_val = ai_click_val or target
        elif action == "ai_fill":
            target = target or ai_fill_val or s.get("selector")
            ai_fill_val = ai_fill_val or target
        elif action == "ai_assert":
            target = target or ai_assert_val or s.get("expected_behavior")
            ai_assert_val = ai_assert_val or target
        elif action == "ai_action":
            target = target or ai_action_val or s.get("description")
            ai_action_val = ai_action_val or target

        skip_raw = s.get("skip", s.get("ignore", s.get("ignorar", s.get("disabled", False))))
        skip_val = False
        if isinstance(skip_raw, bool):
            skip_val = skip_raw
        elif skip_raw is not None:
            skip_val = str(skip_raw).strip().lower() in ("true", "1", "yes", "sim", "y")

        step_exceptions_raw = s.get("exceptions") or s.get("excecoes") or s.get("tolerances")
        step_exceptions = parse_scenario_exceptions(step_exceptions_raw)

        steps.append(
            StepAction(
                action=action,
                selector=s.get("selector"),
                value=s.get("value"),
                url=s.get("url"),
                timeout=s.get("timeout"),
                description=s.get("description"),
                name=s.get("name"),
                expected_behavior=s.get("expected_behavior"),
                criteria=s.get("criteria"),
                ai_click=ai_click_val,
                ai_fill=ai_fill_val,
                ai_assert=ai_assert_val,
                ai_action=ai_action_val,
                target=target,
                skip=skip_val,
                exceptions=step_exceptions,
            )
        )

    headless_raw = parsed_dict.get("headless")
    headless_val: bool | None = None
    if isinstance(headless_raw, bool):
        headless_val = headless_raw
    elif headless_raw is not None:
        normalized = str(headless_raw).strip().lower()
        if normalized in ("true", "1", "yes", "sim", "y"):
            headless_val = True
        elif normalized in ("false", "0", "no", "nao", "não", "n"):
            headless_val = False

    video_raw = parsed_dict.get("video")
    video_val: bool | None = None
    if isinstance(video_raw, bool):
        video_val = video_raw
    elif video_raw is not None:
        normalized = str(video_raw).strip().lower()
        if normalized in ("true", "1", "yes", "sim", "y"):
            video_val = True
        elif normalized in ("false", "0", "no", "nao", "não", "n"):
            video_val = False

    fail_fast_raw = (
        parsed_dict.get("fail_fast")
        if parsed_dict.get("fail_fast") is not None
        else parsed_dict.get("abort_on_error")
    )
    fail_fast_val: bool | None = None
    if isinstance(fail_fast_raw, bool):
        fail_fast_val = fail_fast_raw
    elif fail_fast_raw is not None:
        normalized = str(fail_fast_raw).strip().lower()
        if normalized in ("true", "1", "yes", "sim", "y"):
            fail_fast_val = True
        elif normalized in ("false", "0", "no", "nao", "não", "n"):
            fail_fast_val = False

    axe_raw = parsed_dict.get("axe")
    axe_val: bool | None = None
    if isinstance(axe_raw, bool):
        axe_val = axe_raw
    elif axe_raw is not None:
        normalized = str(axe_raw).strip().lower()
        if normalized in ("true", "1", "yes", "sim", "y"):
            axe_val = True
        elif normalized in ("false", "0", "no", "nao", "não", "n"):
            axe_val = False

    css_raw = parsed_dict.get("css") if parsed_dict.get("css") is not None else parsed_dict.get("css_audit")
    css_val: bool | None = None
    if isinstance(css_raw, bool):
        css_val = css_raw
    elif css_raw is not None:
        normalized = str(css_raw).strip().lower()
        if normalized in ("true", "1", "yes", "sim", "y"):
            css_val = True
        elif normalized in ("false", "0", "no", "nao", "não", "n"):
            css_val = False

    viewports_raw = parsed_dict.get("viewports")
    viewports_val: list[str] | None = None
    if isinstance(viewports_raw, list):
        viewports_val = [str(v) for v in viewports_raw]
    elif isinstance(viewports_raw, str):
        viewports_val = [s.strip() for s in viewports_raw.split(",") if s.strip()]

    scenario_exceptions_raw = (
        parsed_dict.get("exceptions") or parsed_dict.get("excecoes") or parsed_dict.get("tolerances")
    )
    scenario_exceptions = parse_scenario_exceptions(scenario_exceptions_raw)

    return Scenario(
        id=parsed_dict.get("id", path.stem),
        title=parsed_dict.get("title", path.stem),
        description=parsed_dict.get("description"),
        profile=parsed_dict.get("profile", "generic"),
        provider=parsed_dict.get("provider"),
        tags=parsed_dict.get("tags", []),
        env=resolved_env,
        headless=headless_val,
        video=video_val,
        axe=axe_val,
        css=css_val,
        fail_fast=fail_fast_val,
        viewports=viewports_val,
        exceptions=scenario_exceptions,
        steps=steps,
    )
