"""Motor de Crawling Autônomo e Exploratório do UXSentinel (UXS-12)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Response

from uxsentinel.crawler.generator import ScenarioGenerator, _slugify

logger = logging.getLogger("uxsentinel.crawler")

# Guardrails anti-ações destrutivas
DESTRUCTIVE_KEYWORDS: tuple[str, ...] = (
    "excluir",
    "delete",
    "remover",
    "cancelar",
    "trash",
    "logout",
    "sair",
    "desconectar",
    "signout",
    "apagar",
    "drop",
)

DESTRUCTIVE_CLASSES: tuple[str, ...] = (
    "btn-danger",
    ".btn-danger",
    "destructive",
    "btn-delete",
    "btn-remove",
)


def is_same_origin(url_a: str, url_b: str) -> bool:
    """Verifica se duas URLs pertencem à mesma origem (Same-Origin Policy: scheme + host + port)."""
    try:
        pa = urlsplit(url_a)
        pb = urlsplit(url_b)
        if not pa.scheme or not pb.scheme:
            return False
        if pa.scheme.lower() != pb.scheme.lower():
            return False
        port_a = pa.port or (
            443 if pa.scheme.lower() == "https" else (80 if pa.scheme.lower() == "http" else None)
        )
        port_b = pb.port or (
            443 if pb.scheme.lower() == "https" else (80 if pb.scheme.lower() == "http" else None)
        )
        host_a = pa.hostname.lower() if pa.hostname else ""
        host_b = pb.hostname.lower() if pb.hostname else ""
        return host_a == host_b and port_a == port_b
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """Normaliza uma URL removendo âncoras/fragmentos e padronizando trailing slashes."""
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path
        if path and len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        return urlunsplit((scheme, netloc, path, parsed.query, ""))
    except Exception:
        return url


def is_destructive_element(
    text: str = "",
    classes: str = "",
    href: str = "",
    aria_label: str = "",
    elem_id: str = "",
) -> bool:
    """Avalia se um elemento HTML pode disparar ações destrutivas ou encerramento de sessão."""
    combined_text = f"{text} {classes} {href} {aria_label} {elem_id}".lower()

    for kw in DESTRUCTIVE_KEYWORDS:
        if kw in combined_text:
            return True

    return any(cls.lower() in classes.lower() or cls.lower() in combined_text for cls in DESTRUCTIVE_CLASSES)


@dataclass
class CrawlIssue:
    """Representação estruturada de falha detectada durante o crawling."""

    url: str
    error_type: str  # http_500, blank_page, console_error, navigation_error
    message: str
    severity: str  # "alta" ou "bloqueante"
    backtrack_attempted: bool = False
    backtrack_success: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrawlNode:
    """Nó estruturado descoberto no grafo da aplicação."""

    url: str
    depth: int
    title: str = ""
    status_code: int | None = None
    screenshot_path: str | None = None
    parent_url: str | None = None
    discovered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrawlOptions:
    """Parâmetros de configuração do modo exploratório."""

    start_url: str
    max_depth: int = 3
    max_pages: int = 50
    generate_scenarios: bool = True
    output_dir: str = "scenarios/generated"
    headless: bool = True
    screenshot_evidence: bool = True
    timeout_ms: int = 15000
    profile: str = "generic"


class Crawler:
    """Motor BFS autônomo para exploração de superfícies web e descoberta de rotas."""

    def __init__(self, options: CrawlOptions):
        self.options = options
        self.start_url = normalize_url(options.start_url)
        self.output_dir = Path(options.output_dir)
        self.screenshots_dir = self.output_dir / "screenshots"

        # Estado do Crawl
        self.visited_urls: set[str] = set()
        self.screen_fingerprints: set[str] = set()
        self.discovered_nodes: list[CrawlNode] = []
        self.queue: deque[tuple[str, int, list[str]]] = deque()
        self.errors: list[CrawlIssue] = []
        self.generated_scenarios: list[str] = []

        # Controle de ciclo de vida
        self.is_running: bool = False
        self.is_cancelled: bool = False
        self.current_url: str | None = None
        self.current_depth: int = 0
        self.started_at: str | None = None
        self.finished_at: str | None = None

    def cancel(self) -> None:
        """Sinaliza interrupção imediata e graciosa do crawling."""
        self.is_cancelled = True

    def get_status(self) -> dict[str, Any]:
        """Retorna snapshot detalhado do progresso atual."""
        status_str = "idle"
        if self.is_running:
            status_str = "running"
        elif self.is_cancelled:
            status_str = "cancelled"
        elif self.finished_at:
            status_str = "completed"

        queued_urls = [item[0] for item in list(self.queue)]
        return {
            "status": status_str,
            "start_url": self.start_url,
            "current_url": self.current_url,
            "current_depth": self.current_depth,
            "visited_count": len(self.visited_urls),
            "queued_count": len(self.queue),
            "visited_pages": list(self.visited_urls),
            "queued_pages": queued_urls,
            "errors": [e.to_dict() for e in self.errors],
            "generated_scenarios": self.generated_scenarios,
            "nodes_count": len(self.discovered_nodes),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    async def _capture_screenshot(self, page: Page, url: str) -> str | None:
        """Captura screenshot de evidência visual do nó explorado."""
        if not self.options.screenshot_evidence:
            return None
        try:
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            slug = _slugify(url)
            shot_file = self.screenshots_dir / f"{slug}_{len(self.discovered_nodes) + 1}.png"
            await page.screenshot(path=str(shot_file), full_page=False)
            return str(shot_file)
        except Exception as e:
            logger.warning("Falha ao capturar screenshot de %s: %s", url, e)
            return None

    async def _check_page_health(self, page: Page, status_code: int | None) -> tuple[bool, str, str]:
        """Verifica integridade da página (HTTP 500, tela branca / corpo vazio)."""
        # 1. Falha HTTP 500+
        if status_code is not None and status_code >= 500:
            return False, "http_500", f"A página retornou código de erro HTTP {status_code}"

        # 2. Tela branca / corpo vazio
        try:
            body_text_len = await page.evaluate(
                "() => document.body ? (document.body.innerText || '').trim().length : 0"
            )
            if body_text_len == 0:
                # Checa se há iframes ou elementos visuais alternativos antes de cravar tela branca
                elem_count = await page.evaluate("() => document.body ? document.body.children.length : 0")
                if elem_count == 0:
                    return (
                        False,
                        "blank_page",
                        "Tela branca / corpo da página vazio sem elementos renderizados",
                    )
        except Exception:
            # Erro de avaliação no DOM indica falha na página
            return False, "blank_page", "Falha de renderização ao acessar DOM da página"

        return True, "", ""

    async def _handle_backtrack(self, page: Page, path_history: list[str]) -> bool:
        """Executa rotina de recuo (backtrack de 1 passo) após falha grave."""
        logger.info("Acionando rotina de recuo (backtrack) para recuperar estado da navegação...")
        try:
            # 1. Tenta retorno no histórico do navegador
            resp = await page.go_back(wait_until="domcontentloaded", timeout=5000)
            if resp is not None:
                return True
        except Exception as err:
            logger.debug("Tentativa de page.go_back falhou: %s", err)

        # 2. Se go_back não funcionou, tenta navegar explicitamente para o nó anterior no histórico
        if len(path_history) >= 2:
            prev_url = path_history[-2]
            try:
                await page.goto(prev_url, wait_until="domcontentloaded", timeout=5000)
                return True
            except Exception as err:
                logger.warning("Recuo para URL anterior (%s) falhou: %s", prev_url, err)
                return False

        return False

    async def _extract_safe_links(self, page: Page, current_url: str) -> list[str]:
        """Extrai links navegáveis na mesma origem aplicando os guardrails anti-destruição."""
        valid_links: list[str] = []
        try:
            # Coleta atributos relevantes de todas as tags 'a[href]'
            links_data: list[dict[str, str]] = await page.evaluate(
                """() => {
                const results = [];
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                for (const a of anchors) {
                    results.push({
                        href: a.getAttribute('href') || '',
                        text: (a.innerText || a.textContent || '').trim(),
                        className: a.className || '',
                        ariaLabel: a.getAttribute('aria-label') || '',
                        id: a.id || ''
                    });
                }
                return results;
            }"""
            )
        except Exception as e:
            logger.warning("Não foi possível extrair links de %s: %s", current_url, e)
            return []

        if not isinstance(links_data, list):
            return []

        for item in links_data:
            if not isinstance(item, dict):
                continue
            raw_href = item.get("href", "").strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            # Avalia Guardrails anti-ações destrutivas
            if is_destructive_element(
                text=item.get("text", ""),
                classes=item.get("className", ""),
                href=raw_href,
                aria_label=item.get("ariaLabel", ""),
                elem_id=item.get("id", ""),
            ):
                logger.debug("Link destrutivo descartado pelo guardrail: %s (%s)", raw_href, item.get("text"))
                continue

            # Converte em URL absoluta e normaliza
            abs_url = normalize_url(urljoin(current_url, raw_href))

            # Valida Same-Origin Policy
            if not is_same_origin(abs_url, self.start_url):
                continue

            # Evita links externos ou inválidos
            parsed = urlsplit(abs_url)
            if parsed.scheme not in ("http", "https"):
                continue

            if abs_url not in valid_links and abs_url not in self.visited_urls:
                valid_links.append(abs_url)

        return valid_links

    async def run(self, page: Page | None = None) -> dict[str, Any]:
        """Inicia a execução do loop BFS de crawling."""
        self.is_running = True
        self.started_at = datetime.now(UTC).isoformat()
        logger.info("Iniciando crawl exploratório em: %s", self.start_url)

        own_session = False
        browser_session_obj = None

        try:
            if page is None:
                # Inicia sessão própria do Playwright via uxsentinel
                from uxsentinel.browser.session import open_browser_session
                from uxsentinel.core.config import BrowserSettings

                b_settings = BrowserSettings(
                    headless=self.options.headless,
                    timeout=self.options.timeout_ms,
                )
                session_gen = open_browser_session(
                    settings=b_settings,
                    headless=self.options.headless,
                    capture_console=True,
                )
                driver = await session_gen.__aenter__()
                page = driver.page
                browser_session_obj = session_gen
                own_session = True

            # Registra listeners para capturar erros graves de JS no console da página
            console_errors: list[str] = []

            def on_page_error(exc: Any) -> None:
                console_errors.append(str(exc))

            def on_console_msg(msg: Any) -> None:
                if getattr(msg, "type", None) == "error":
                    console_errors.append(str(getattr(msg, "text", msg)))

            if hasattr(page, "on") and callable(page.on):
                r1 = page.on("pageerror", on_page_error)
                if asyncio.iscoroutine(r1):
                    await r1
                r2 = page.on("console", on_console_msg)
                if asyncio.iscoroutine(r2):
                    await r2

            # Inicializa a fila BFS com a start_url (profundidade 0)
            self.queue.append((self.start_url, 0, [self.start_url]))

            while self.queue and len(self.visited_urls) < self.options.max_pages:
                if self.is_cancelled:
                    logger.info("Crawling interrompido por cancelamento.")
                    break

                target_url, depth, history = self.queue.popleft()

                if target_url in self.visited_urls:
                    continue

                if depth > self.options.max_depth:
                    continue

                self.current_url = target_url
                self.current_depth = depth
                console_errors.clear()

                logger.info(
                    "[%d/%d] Explorando (Profundidade %d): %s",
                    len(self.visited_urls) + 1,
                    self.options.max_pages,
                    depth,
                    target_url,
                )

                response: Response | None = None
                nav_error: str | None = None

                try:
                    response = await page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=self.options.timeout_ms,
                    )
                    # Pequena tolerância para hidratação de SPA
                    await asyncio.sleep(0.3)
                except (PlaywrightError, Exception) as err:
                    nav_error = str(err)
                    logger.warning("Falha na navegação para %s: %s", target_url, err)

                self.visited_urls.add(target_url)
                status_code = response.status if response else None

                # 1. Verifica falha de navegação inicial
                if nav_error:
                    severity = "alta"
                    backtrack_ok = await self._handle_backtrack(page, history)
                    if not backtrack_ok:
                        severity = "bloqueante"

                    self.errors.append(
                        CrawlIssue(
                            url=target_url,
                            error_type="navigation_error",
                            message=nav_error,
                            severity=severity,
                            backtrack_attempted=True,
                            backtrack_success=backtrack_ok,
                        )
                    )
                    continue

                # 2. Verifica saúde da página (HTTP 500 / Tela Branca)
                healthy, err_type, err_msg = await self._check_page_health(page, status_code)
                if not healthy:
                    severity = "alta"
                    backtrack_ok = await self._handle_backtrack(page, history)
                    if not backtrack_ok:
                        severity = "bloqueante"

                    self.errors.append(
                        CrawlIssue(
                            url=target_url,
                            error_type=err_type,
                            message=err_msg,
                            severity=severity,
                            backtrack_attempted=True,
                            backtrack_success=backtrack_ok,
                        )
                    )
                    continue

                # 3. Verifica erros graves de console JavaScript
                if console_errors:
                    err_summary = "; ".join(console_errors[:3])
                    severity = "alta"
                    backtrack_ok = await self._handle_backtrack(page, history)
                    if not backtrack_ok:
                        severity = "bloqueante"

                    self.errors.append(
                        CrawlIssue(
                            url=target_url,
                            error_type="console_error",
                            message=f"Erros de console JS detectados: {err_summary}",
                            severity=severity,
                            backtrack_attempted=True,
                            backtrack_success=backtrack_ok,
                        )
                    )
                    # Não interrompe se o backtrack recuperou, mas registra o erro

                # Deduplicação por impressão de tela (fingerprint)
                page_title = ""
                with contextlib.suppress(Exception):
                    page_title = await page.title()

                shot_path = await self._capture_screenshot(page, target_url)

                parent = history[-2] if len(history) >= 2 else None
                node = CrawlNode(
                    url=target_url,
                    depth=depth,
                    title=page_title,
                    status_code=status_code,
                    screenshot_path=shot_path,
                    parent_url=parent,
                )
                self.discovered_nodes.append(node)

                # Se ainda não atingiu max_depth, descobre novos links navegáveis
                if depth < self.options.max_depth:
                    safe_links = await self._extract_safe_links(page, target_url)
                    for next_link in safe_links:
                        if next_link not in self.visited_urls:
                            self.queue.append((next_link, depth + 1, history + [next_link]))

            # Geração de cenários YAML pós-crawling
            if self.options.generate_scenarios and self.discovered_nodes:
                generator = ScenarioGenerator(
                    output_dir=self.output_dir,
                    profile=self.options.profile,
                )
                nodes_dicts = [n.to_dict() for n in self.discovered_nodes]
                created_paths = generator.generate_from_crawl(
                    visited_nodes=nodes_dicts,
                    base_url=self.start_url,
                )
                self.generated_scenarios = [str(p) for p in created_paths]
                logger.info("Cenários gerados com sucesso: %d arquivos", len(created_paths))

        finally:
            self.is_running = False
            self.finished_at = datetime.now(UTC).isoformat()
            if own_session and browser_session_obj is not None:
                await browser_session_obj.__aexit__(None, None, None)

        return self.get_status()
