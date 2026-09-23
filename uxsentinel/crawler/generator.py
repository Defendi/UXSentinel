"""Gerador de cenários YAML do UXSentinel a partir de rotas descobertas pelo Crawler."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def _slugify(text: str) -> str:
    """Converte texto ou URL em um slug seguro para id e nome de arquivo."""
    cleaned = re.sub(r"https?://", "", text)
    cleaned = re.sub(r"[^\w\-_/]+", "_", cleaned)
    cleaned = re.sub(r"[/]+", "_", cleaned)
    slug = cleaned.strip("_").lower()
    return slug[:60] if slug else "pagina"


class ScenarioGenerator:
    """Converte fluxos navegados em arquivos YAML válidos do UXSentinel."""

    def __init__(self, output_dir: Path | str = "scenarios/generated", profile: str = "generic"):
        self.output_dir = Path(output_dir)
        self.profile = profile

    def generate_scenario_for_flow(
        self,
        flow_name: str,
        steps_data: list[dict[str, Any]],
        title: str | None = None,
        description: str | None = None,
    ) -> Path:
        """Gera e salva um único arquivo YAML de cenário para um fluxo percorrido."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        slug = _slugify(flow_name)
        scenario_id = f"crawl_{slug}"
        scenario_title = title or f"Exploração Autônoma: {slug}"
        scenario_desc = (
            description or f"Cenário de teste autônomo gerado pelo crawler para o fluxo {flow_name}."
        )

        scenario_steps: list[dict[str, Any]] = []

        for idx, step_info in enumerate(steps_data, start=1):
            url = step_info.get("url", "")
            action = step_info.get("action", "goto")
            checkpoint_name = step_info.get("checkpoint_name") or f"chk_{idx}_{_slugify(url)}"
            exp_behavior = (
                step_info.get("expected_behavior")
                or f"A página '{url}' deve carregar completamente sem erros de console ou layout quebrado."
            )

            if action == "goto":
                scenario_steps.append(
                    {
                        "action": "goto",
                        "url": url,
                        "description": f"Navegar até {url}",
                    }
                )
                scenario_steps.append(
                    {
                        "action": "wait_until_ready",
                        "description": "Aguardar estabilização e carregamento da página",
                    }
                )
                scenario_steps.append(
                    {
                        "action": "checkpoint",
                        "name": checkpoint_name,
                        "description": f"Validação visual da página {url}",
                        "expected_behavior": exp_behavior,
                    }
                )

        data = {
            "version": "1.0",
            "id": scenario_id,
            "title": scenario_title,
            "description": scenario_desc,
            "profile": self.profile,
            "tags": ["crawl", "exploratorio", "autonomo"],
            "steps": scenario_steps,
        }

        file_path = self.output_dir / f"{slug}.yaml"
        # Evita sobrescrita de fluxos com o mesmo nome diferenciando com sufixo numérico
        counter = 1
        while file_path.exists():
            file_path = self.output_dir / f"{slug}_{counter}.yaml"
            counter += 1

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

        return file_path

    def generate_from_crawl(
        self,
        visited_nodes: list[dict[str, Any]],
        base_url: str,
    ) -> list[Path]:
        """Converte nós visitados do crawler em cenários YAML salvos no disco."""
        if not visited_nodes:
            return []

        created_files: list[Path] = []

        # 1. Gera cenário consolidado da jornada completa se houver múltiplos nós
        if len(visited_nodes) > 1:
            consolidated_steps = [
                {
                    "url": node.get("url", ""),
                    "action": "goto",
                    "checkpoint_name": f"passo_{i}_{_slugify(node.get('url', ''))}",
                    "expected_behavior": f"Verificar integridade e layout de {node.get('url', '')}",
                }
                for i, node in enumerate(visited_nodes, start=1)
            ]
            main_path = self.generate_scenario_for_flow(
                flow_name=f"jornada_{_slugify(base_url)}",
                steps_data=consolidated_steps,
                title=f"Jornada Completa de Exploração: {base_url}",
                description=f"Jornada consolidada de {len(visited_nodes)} telas descobertas a partir de {base_url}.",
            )
            created_files.append(main_path)

        # 2. Gera cenários individuais para cada nó descoberto
        for node in visited_nodes:
            node_url = node.get("url", "")
            if not node_url:
                continue
            node_steps = [
                {
                    "url": node_url,
                    "action": "goto",
                    "checkpoint_name": f"tela_{_slugify(node_url)}",
                    "expected_behavior": f"A tela {node_url} deve ser carregada sem inconsistências visuais.",
                }
            ]
            path = self.generate_scenario_for_flow(
                flow_name=_slugify(node_url),
                steps_data=node_steps,
                title=f"Exploração da Rota: {node_url}",
            )
            created_files.append(path)

        return created_files
