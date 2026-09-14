"""Integração com Atlassian Jira para abertura automática de cards (issues) pós-auditoria."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from rich.console import Console

if TYPE_CHECKING:
    from uxsentinel.core.config import JiraSettings
    from uxsentinel.core.models import Issue, TestReport

logger = logging.getLogger("uxsentinel.integrations.jira")
console = Console()


class JiraClient:
    """Cliente para criação de issues/cards no Jira a partir de relatórios do UXSentinel."""

    def __init__(self, settings: JiraSettings):
        self.settings = settings
        self.url = (settings.url or os.environ.get("JIRA_URL", "")).rstrip("/")
        self.email = (settings.email or os.environ.get("JIRA_EMAIL", "")).strip()
        self.api_token = (settings.api_token or os.environ.get("JIRA_API_TOKEN", "")).strip()
        self.project_key = (settings.project_key or os.environ.get("JIRA_PROJECT_KEY", "")).strip().upper()
        self.issue_type = settings.issue_type or "Bug"
        self.labels = settings.labels or ["uxsentinel", "qa-audit"]

    def is_configured(self) -> bool:
        """Verifica se as credenciais mínimas para envio ao Jira estão presentes."""
        return bool(self.url and self.api_token and self.project_key)

    def _get_auth_headers_and_client_kwargs(self) -> dict[str, Any]:
        """Prepara autenticação HTTP (Basic para Atlassian Cloud ou Bearer Token)."""
        kwargs: dict[str, Any] = {
            "timeout": 30.0,
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        }

        # Se houver email + token -> Atlassian Cloud Basic Auth
        if self.email and self.api_token:
            kwargs["auth"] = (self.email, self.api_token)
        elif self.api_token:
            # Bearer token (PAT - Personal Access Token / Jira Data Center)
            kwargs["headers"]["Authorization"] = f"Bearer {self.api_token}"

        return kwargs

    async def test_connection(self) -> tuple[bool, str]:
        """Valida a conexão com o Jira e a existência do projeto alvo."""
        if not self.is_configured():
            missing = []
            if not self.url:
                missing.append("JIRA_URL")
            if not self.api_token:
                missing.append("JIRA_API_TOKEN")
            if not self.project_key:
                missing.append("JIRA_PROJECT_KEY")
            return False, f"Configurações do Jira incompletas. Faltando: {', '.join(missing)}"

        kwargs = self._get_auth_headers_and_client_kwargs()
        check_url = f"{self.url}/rest/api/2/project/{self.project_key}"

        try:
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(check_url)
                if resp.status_code == 200:
                    pdata = resp.json()
                    pname = pdata.get("name", self.project_key)
                    return (
                        True,
                        f"Conexão com o Jira validada com sucesso no projeto '{pname}' ({self.project_key}).",
                    )
                elif resp.status_code in (401, 403):
                    return (
                        False,
                        f"Autenticação no Jira recusada (HTTP {resp.status_code}). Verifique seu email e API Token.",
                    )
                elif resp.status_code == 404:
                    return False, f"Projeto '{self.project_key}' não encontrado no Jira ({self.url})."
                else:
                    return False, f"Erro ao consultar o Jira (HTTP {resp.status_code}): {resp.text[:200]}"
        except Exception as exc:
            return False, f"Falha de conexão com o Jira ({self.url}): {exc}"

    def _format_description(
        self,
        scenario_id: str,
        scenario_title: str,
        checkpoint_name: str,
        expected_behavior: str,
        issue: Issue,
        screenshot_path: str | None = None,
        viewport: str | None = None,
    ) -> str:
        """Formata a descrição detalhada para o card do Jira em sintaxe Jira Wiki/Confluence."""
        vp_val = issue.viewport or viewport
        lines = [
            "h2. 🛡️ Inconformidade Detectada pelo UXSentinel",
            f"*Cenário:* {scenario_id} ({scenario_title})",
            f"*Checkpoint:* {checkpoint_name}",
        ]
        if vp_val:
            lines.append(f"*Dispositivo / Resolução:* {vp_val}")

        lines.extend(
            [
                f"*Comportamento Esperado:* {expected_behavior}",
                f"*Categoria:* {issue.categoria.value.upper()}",
                f"*Severidade:* *{issue.severidade.value.upper()}*",
            ]
        )
        if issue.evaluator:
            lines.append(f"*Avaliador Responsável:* {issue.evaluator}")
        lines.extend(
            [
                "",
                "h3. 📝 Descrição da Falha",
                issue.descricao.strip(),
                "",
            ]
        )

        if vp_val:
            lines.extend(
                [
                    "h3. 📱 Resolução / Dispositivo Afetado",
                    f"*Viewport:* {vp_val}",
                    "Esta inconformidade foi observada especificamente sob esta resolução/dispositivo.",
                    "",
                ]
            )

        if issue.elemento_alvo:
            lines.extend(
                [
                    "h3. 🎯 Elemento / Seletor",
                    f"{{noformat}}{issue.elemento_alvo}{{noformat}}",
                    "",
                ]
            )

        if issue.trecho_codigo:
            lines.extend(
                [
                    "h3. 💻 Trecho de Código / DOM",
                    f"{{code:html}}{issue.trecho_codigo}{{code}}",
                    "",
                ]
            )

        if issue.sugestao_correcao:
            lines.extend(
                [
                    "h3. 💡 Sugestão Técnica de Correção",
                    issue.sugestao_correcao.strip(),
                    "",
                ]
            )

        if screenshot_path:
            lines.extend(
                [
                    "h3. 📸 Evidência Visual",
                    f"Screenshot: {{color:#64748b}}{screenshot_path}{{color}}",
                    "",
                ]
            )

        lines.extend(
            [
                "----",
                "_Card gerado automaticamente pelo UXSentinel QA Agent._",
            ]
        )

        return "\n".join(lines)

    async def create_issues_from_report(self, report: TestReport) -> list[str]:
        """Cria cards no Jira para todas as issues identificadas no relatório."""
        if not self.is_configured():
            console.print(
                "[yellow]⚠️ Integração com Jira habilitada, mas variáveis/configurações (URL, API Token ou Projeto) estão incompletas.[/yellow]"
            )
            return []

        all_items: list[tuple[str, str, Issue, str | None, str | None]] = []
        for cp in report.checkpoints:
            for issue in cp.issues:
                vp = issue.viewport or cp.viewport
                all_items.append((cp.name, cp.expected_behavior, issue, cp.screenshot_path, vp))

        if not all_items:
            console.print(
                "[dim]Nenhuma inconformidade encontrada no relatório. Nenhum card do Jira precisa ser criado.[/dim]"
            )
            return []

        console.print(
            f"\n[bold cyan]🎫 Enviando {len(all_items)} inconformidade(s) para o Jira ([bold yellow]{self.project_key}[/bold yellow])...[/bold cyan]"
        )

        kwargs = self._get_auth_headers_and_client_kwargs()
        endpoint = f"{self.url}/rest/api/2/issue"
        created_card_urls: list[str] = []

        async with httpx.AsyncClient(**kwargs) as client:
            for cp_name, expected, issue, screenshot_path, vp in all_items:
                vp_prefix = ""
                if vp:
                    short_name = vp.split()[0].upper()
                    vp_prefix = f"[{short_name}]"

                summary = f"[UXSentinel]{vp_prefix}[{issue.categoria.value.upper()}][{issue.severidade.value.upper()}] {issue.descricao}"
                if len(summary) > 250:
                    summary = summary[:247] + "..."

                description = self._format_description(
                    scenario_id=report.scenario_id,
                    scenario_title=report.scenario_title,
                    checkpoint_name=cp_name,
                    expected_behavior=expected,
                    issue=issue,
                    screenshot_path=screenshot_path,
                    viewport=vp,
                )

                extra_labels = [f"viewport-{vp.split()[0].lower()}"] if vp else []
                issue_labels = list(
                    set(
                        self.labels
                        + ["uxsentinel", issue.categoria.value.lower(), issue.severidade.value.lower()]
                        + extra_labels
                    )
                )

                payload = {
                    "fields": {
                        "project": {"key": self.project_key},
                        "summary": summary,
                        "description": description,
                        "issuetype": {"name": self.issue_type},
                        "labels": issue_labels,
                    }
                }

                try:
                    resp = await client.post(endpoint, json=payload)
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        key = data.get("key", "")
                        issue_url = f"{self.url}/browse/{key}"
                        created_card_urls.append(issue_url)
                        console.print(
                            f"  [bold green]✓ Card criado:[/bold green] [bold yellow]{key}[/bold yellow] - "
                            f"[underline cyan]{issue_url}[/underline cyan] ({issue.descricao[:45]})"
                        )
                        # Anexa evidências relevantes (screenshots, GIF animado e vídeo)
                        if screenshot_path and Path(screenshot_path).is_file():
                            await self.attach_file_to_issue(key, screenshot_path)
                        if report.gif_path and Path(report.gif_path).is_file():
                            await self.attach_file_to_issue(key, report.gif_path)
                        if report.video_path and Path(report.video_path).is_file():
                            await self.attach_file_to_issue(key, report.video_path)
                    else:
                        console.print(
                            f"  [bold red]✗ Falha ao criar card no Jira ({resp.status_code}):[/bold red] {resp.text[:180]}"
                        )
                except Exception as err:
                    console.print(f"  [bold red]✗ Erro de rede ao comunicar com Jira:[/bold red] {err}")

        if created_card_urls:
            console.print(
                f"[bold green]✨ {len(created_card_urls)} card(s) criado(s) com sucesso no Jira![/bold green]\n"
            )

        return created_card_urls

    async def attach_file_to_issue(self, issue_key: str, file_path: str | Path) -> bool:
        """Anexa um arquivo (vídeo, GIF, imagem) a uma issue existente no Jira via API de anexos."""
        p = Path(file_path)
        if not p.is_file() or not self.is_configured():
            return False

        endpoint = f"{self.url}/rest/api/2/issue/{issue_key}/attachments"
        auth_kwargs = self._get_auth_headers_and_client_kwargs()
        headers = dict(auth_kwargs.get("headers", {}))
        headers.pop("Content-Type", None)
        headers["X-Atlassian-Token"] = "no-check"
        auth_kwargs["headers"] = headers

        try:
            async with httpx.AsyncClient(**auth_kwargs) as client:
                with p.open("rb") as f:
                    files = {"file": (p.name, f)}
                    resp = await client.post(endpoint, files=files)
                    if resp.status_code in (200, 201):
                        console.print(f"    [dim]📎 Evidência '{p.name}' anexada à issue {issue_key}.[/dim]")
                        return True
                    else:
                        logger.warning(
                            "Falha ao anexar arquivo %s à issue %s: HTTP %s - %s",
                            p.name,
                            issue_key,
                            resp.status_code,
                            resp.text[:200],
                        )
                        return False
        except Exception as exc:
            logger.warning("Erro ao anexar arquivo %s à issue %s: %s", p.name, issue_key, exc)
            return False
