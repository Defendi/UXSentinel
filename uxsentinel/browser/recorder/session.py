"""Gerenciador de ciclo de vida da sessão de gravação (RecorderSession).

Controla o ciclo de vida do navegador em modo headed via Playwright,
exposição de bindings para captura de eventos DOM, pause, resume e
persistência automática de cenários gravados.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from uxsentinel.browser.recorder.models import (
    RecordedStep,
    RecordedTarget,
    RecordedWorkflow,
    SelectorCandidate,
    SelectorStrategy,
    StepStatus,
)
from uxsentinel.browser.recorder.resolver import ElementResolver

RECORD_INIT_SCRIPT = """(() => {
  if (window.__uxs_recorder_injected__) return;
  window.__uxs_recorder_injected__ = true;

  function extractElementInfo(el) {
    if (!el || !(el instanceof Element)) return null;
    return {
      tagName: el.tagName ? el.tagName.toLowerCase() : null,
      id: el.id || null,
      name: el.getAttribute('name') || null,
      type: el.getAttribute('type') || null,
      testId: el.getAttribute('data-testid') || el.getAttribute('data-test') || null,
      role: el.getAttribute('role') || null,
      ariaLabel: el.getAttribute('aria-label') || null,
      innerText: el.innerText ? el.innerText.trim().slice(0, 100) : null,
      value: 'value' in el ? String(el.value) : null,
      className: typeof el.className === 'string' ? el.className : null,
      outerHtml: el.outerHTML ? el.outerHTML.slice(0, 500) : null,
    };
  }

  document.addEventListener('click', (event) => {
    if (!event.isTrusted) return;
    if (window.__uxs_record__) {
      window.__uxs_record__({
        action: 'click',
        target: extractElementInfo(event.target),
        url: window.location.href,
        timestamp: Date.now(),
      });
    }
  }, true);

  document.addEventListener('change', (event) => {
    if (!event.isTrusted) return;
    const target = extractElementInfo(event.target);
    if (window.__uxs_record__) {
      window.__uxs_record__({
        action: 'change',
        value: target ? target.value : null,
        target: target,
        url: window.location.href,
        timestamp: Date.now(),
      });
    }
  }, true);

  document.addEventListener('input', (event) => {
    if (!event.isTrusted) return;
    const target = extractElementInfo(event.target);
    if (window.__uxs_record__) {
      window.__uxs_record__({
        action: 'input',
        value: target ? target.value : null,
        target: target,
        url: window.location.href,
        timestamp: Date.now(),
      });
    }
  }, true);

  document.addEventListener('submit', (event) => {
    if (!event.isTrusted) return;
    const target = extractElementInfo(event.target);
    if (window.__uxs_record__) {
      window.__uxs_record__({
        action: 'submit',
        target: target,
        url: window.location.href,
        timestamp: Date.now(),
      });
    }
  }, true);
})();
"""


class _AwaitableResult:
    """Invólucro polimórfico compatível com chamadas síncronas e assíncronas."""

    def __init__(self, value: Any = None) -> None:
        self._value = value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: Any) -> bool:
        return self._value == other

    def __repr__(self) -> str:
        return repr(self._value)

    def __await__(self) -> Any:
        async def _wrapper() -> Any:
            return self._value

        return _wrapper().__await__()


class RecorderSession:
    """Sessão de gravação interativa de cenários (Modo Assistido)."""

    def __init__(
        self,
        session_id: str,
        name: str,
        url: str,
        objective: str | None = None,
        scenario_output_dir: str | Path | None = None,
        resolver: ElementResolver | None = None,
        normalizer: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.name = name
        self.url = url
        self.objective = objective
        self.scenario_output_dir = (
            Path(scenario_output_dir) if scenario_output_dir is not None else Path.cwd() / "scenarios"
        )
        self.resolver = resolver or ElementResolver()
        self.normalizer = normalizer

        self.workflow = RecordedWorkflow(
            session_id=session_id,
            name=name,
            url=url,
            objective=objective,
            created_at=datetime.now(UTC).isoformat(),
            steps=[],
            paused=False,
        )

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

        self._pause_url: str | None = None
        self._stopped: bool = False
        self._stop_lock = asyncio.Lock()
        self._last_stop_result: dict[str, Any] | None = None
        self._close_task: asyncio.Task[Any] | None = None

    @staticmethod
    def _validate_url(url: str) -> None:
        """Valida que a URL possui esquema http ou https e host válido."""
        if not url or not isinstance(url, str):
            raise ValueError(f"URL inválida ou mal-formada: '{url}'. Deve ser uma string não vazia.")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"URL inválida ou mal-formada: '{url}'. Deve possuir esquema http ou https e host válido."
            )

    async def start(self) -> None:
        """Inicia a sessão de gravação no navegador Chromium em modo headed.

        Valida a URL inicial antes de invocar o Playwright (CA01b).
        Registra bindings para eventos DOM, listeners de navegação e auto-save no close.
        """
        self._validate_url(self.url)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        await self._page.expose_binding("__uxs_record__", self._handle_dom_event)
        await self._page.add_init_script(RECORD_INIT_SCRIPT)

        self._page.on("framenavigated", self._on_navigate)
        self._page.on("popup", self._on_popup)
        self._context.on("close", self._on_context_close)

        await self._page.goto(self.url)

    def pause(self) -> _AwaitableResult:
        """Pausa a captura de eventos da gravação e memoriza a URL atual."""
        self.workflow.paused = True
        if self._page:
            self._pause_url = getattr(self._page, "url", None)
        else:
            self._pause_url = None
        return _AwaitableResult(None)

    def resume(self) -> _AwaitableResult:
        """Retoma a captura de eventos da gravação.

        Se a URL atual for diferente da URL no momento da pausa,
        injeta imediatamente um RecordedStep(action="navigate", url=page.url) (CA14).
        """
        self.workflow.paused = False
        navigate_injected = False
        if self._page and self._pause_url is not None:
            current_url = getattr(self._page, "url", None)
            if current_url and current_url != self._pause_url:
                step = RecordedStep(
                    index=len(self.workflow.steps),
                    action="navigate",
                    url=current_url,
                    status=StepStatus.CONFIRMED,
                )
                self.workflow.steps.append(step)
                navigate_injected = True
        self._pause_url = None
        return _AwaitableResult(navigate_injected)

    async def stop(self) -> dict[str, Any]:
        """Encerra a sessão de gravação de forma idempotente e segura.

        Filtra passos confirmados e aceitos. Se não houver passos válidos,
        retorna `{"saved": False, "reason": "no_steps"}` sem salvar arquivo.
        Caso contrário, salva o arquivo YAML em `scenario_output_dir` e
        retorna `{"saved": True, "path": str(filepath)}`.
        """
        async with self._stop_lock:
            if self._stopped:
                return self._last_stop_result or {"saved": False, "reason": "already_stopped"}
            self._stopped = True

            if self.normalizer and hasattr(self.normalizer, "flush"):
                res = self.normalizer.flush()
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    flushed_steps = await res
                else:
                    flushed_steps = res
                for step in flushed_steps:
                    step_copy = step.model_copy(update={"index": len(self.workflow.steps)})
                    self.workflow.steps.append(step_copy)

            valid_steps = [
                step
                for step in self.workflow.steps
                if step.status in (StepStatus.CONFIRMED, StepStatus.ACCEPTED)
            ]

            result: dict[str, Any]
            if not valid_steps:
                result = {"saved": False, "reason": "no_steps"}
            else:
                filepath = self._save_scenario(valid_steps)
                result = {"saved": True, "path": str(filepath)}

            self._last_stop_result = result
            await self._cleanup_browser()
            return result

    def _on_context_close(self, *args: Any) -> None:
        """Dispara a finalização e persistência automática caso o contexto seja fechado (CA11)."""
        if not self._stopped:
            try:
                loop = asyncio.get_running_loop()
                self._close_task = loop.create_task(self.stop())
            except RuntimeError:
                pass

    async def _on_navigate(self, frame: Any) -> None:
        """Trata evento de navegação do frame principal."""
        if self.workflow.paused or self._stopped:
            return

        is_main_frame = getattr(frame, "parent_frame", None) is None
        if not is_main_frame:
            return

        url = getattr(frame, "url", None)
        if not url or url.startswith("about:blank") or url.startswith("chrome-error://"):
            return

        if (
            self.workflow.steps
            and self.workflow.steps[-1].action == "navigate"
            and self.workflow.steps[-1].url == url
        ):
            return

        step = RecordedStep(
            index=len(self.workflow.steps),
            action="navigate",
            url=url,
            status=StepStatus.CONFIRMED,
        )
        self.workflow.steps.append(step)

    async def _on_popup(self, popup_page: Any) -> None:
        """Configura listeners de captura em novas abas ou janelas abertas."""
        if self._stopped:
            return
        with contextlib.suppress(Exception):
            await popup_page.expose_binding("__uxs_record__", self._handle_dom_event)
            await popup_page.add_init_script(RECORD_INIT_SCRIPT)
            popup_page.on("framenavigated", self._on_navigate)

    async def _handle_dom_event(self, source: Any, event_data: dict[str, Any]) -> None:
        """Recebe eventos DOM brutos capturados via script injetado."""
        if self.workflow.paused or self._stopped:
            return

        if self.normalizer:
            step = None
            if hasattr(self.normalizer, "ingest_event"):
                res = self.normalizer.ingest_event(event_data)
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    step = await res
                else:
                    step = res
            elif hasattr(self.normalizer, "process_event"):
                res = self.normalizer.process_event(source, event_data)
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    step = await res
                else:
                    step = res

            if step:
                step_copy = step.model_copy(update={"index": len(self.workflow.steps)})
                self.workflow.steps.append(step_copy)

            if hasattr(self.normalizer, "pop_pending_steps"):
                for pending in self.normalizer.pop_pending_steps():
                    pending_copy = pending.model_copy(update={"index": len(self.workflow.steps)})
                    self.workflow.steps.append(pending_copy)
        else:
            raw_action = event_data.get("action", "")
            action_map = {
                "click": "click",
                "input": "fill",
                "change": "fill",
                "submit": "click",
            }
            action = action_map.get(raw_action, raw_action)
            target_info = event_data.get("target") or {}

            primary_candidate = None
            if target_info.get("testId"):
                primary_candidate = SelectorCandidate(
                    strategy=SelectorStrategy.TESTID,
                    value=target_info["testId"],
                )
            elif target_info.get("role"):
                primary_candidate = SelectorCandidate(
                    strategy=SelectorStrategy.ROLE,
                    value=target_info["role"],
                    name=target_info.get("ariaLabel") or target_info.get("innerText"),
                )
            elif target_info.get("id"):
                primary_candidate = SelectorCandidate(
                    strategy=SelectorStrategy.CSS,
                    value=f"#{target_info['id']}",
                )

            target = (
                RecordedTarget(
                    primary=primary_candidate,
                    raw_html_snippet=target_info.get("outerHtml"),
                )
                if primary_candidate or target_info.get("outerHtml")
                else None
            )

            step = RecordedStep(
                index=len(self.workflow.steps),
                action=action,
                target=target,
                value=event_data.get("value"),
                url=event_data.get("url"),
                status=StepStatus.CONFIRMED,
            )
            self.workflow.steps.append(step)

    async def _cleanup_browser(self) -> None:
        """Limpa recursos do Playwright com segurança."""
        if self._context:
            with contextlib.suppress(Exception):
                await self._context.close()
            self._context = None

        if self._browser:
            with contextlib.suppress(Exception):
                await self._browser.close()
            self._browser = None

        if self._playwright:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None

    def _save_scenario(self, valid_steps: list[RecordedStep]) -> Path:
        """Serializa os passos válidos para YAML estruturado e grava no disco."""
        self.scenario_output_dir.mkdir(parents=True, exist_ok=True)
        slug = self._to_kebab_case(self.workflow.name)
        filepath = self.scenario_output_dir / f"{slug}.yaml"

        scenario_dict = {
            "version": "1.0",
            "id": slug.replace("-", "_"),
            "title": self.workflow.name,
            "description": self.workflow.objective or f"Cenário gravado: {self.workflow.name}",
            "steps": [self._serialize_step(s) for s in valid_steps],
        }

        yaml_text = yaml.dump(scenario_dict, allow_unicode=True, sort_keys=False)
        filepath.write_text(yaml_text, encoding="utf-8")
        return filepath

    def _serialize_step(self, step: RecordedStep) -> dict[str, Any]:
        """Mapeia um RecordedStep para o schema de StepAction do UXSentinel."""
        step_dict: dict[str, Any] = {}
        action = step.action.lower().strip()

        if action in ("navigate", "goto"):
            step_dict["action"] = "goto"
            step_dict["url"] = step.url
            step_dict["description"] = f"Acessa a URL {step.url}"
        elif action == "click":
            step_dict["action"] = "click"
            selector = self._extract_selector(step.target)
            if selector:
                step_dict["selector"] = selector
            if step.value:
                step_dict["value"] = step.value
        elif action in ("fill", "input", "change"):
            step_dict["action"] = "fill"
            selector = self._extract_selector(step.target)
            if selector:
                step_dict["selector"] = selector
            if step.value is not None:
                step_dict["value"] = step.value
        elif action == "assert":
            step_dict["action"] = "assert"
            selector = self._extract_selector(step.target)
            if selector:
                step_dict["selector"] = selector
            step_dict["expected_behavior"] = step.value or "Validação de interface"
        else:
            step_dict["action"] = action
            selector = self._extract_selector(step.target)
            if selector:
                step_dict["selector"] = selector
            if step.value is not None:
                step_dict["value"] = step.value
            if step.url is not None:
                step_dict["url"] = step.url

        return step_dict

    @staticmethod
    def _extract_selector(target: RecordedTarget | None) -> str | None:
        """Determina a string de seletor a partir do seletor primário do elemento gravado."""
        if not target or not target.primary:
            return None
        primary = target.primary
        if primary.strategy == SelectorStrategy.TESTID:
            return f"[data-testid='{primary.value}']"
        if primary.strategy == SelectorStrategy.ROLE:
            if primary.name:
                return f"role={primary.value}[name='{primary.name}']"
            return f"role={primary.value}"
        if primary.strategy == SelectorStrategy.LABEL:
            return f"label={primary.value}"
        if primary.strategy == SelectorStrategy.TEXT:
            return f"text={primary.value}"
        return primary.value

    @staticmethod
    def _to_kebab_case(name: str) -> str:
        """Converte uma string arbitrária para slug em kebab-case."""
        normalized = unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
        return slug or "scenario"
