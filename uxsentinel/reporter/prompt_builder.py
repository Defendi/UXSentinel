"""Gerador de documento de prompt Markdown para correção de problemas detectados pelo UXSentinel."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from uxsentinel.core.models import Issue, IssueSeverity, TestReport

SEVERITY_ORDER = [
    IssueSeverity.BLOQUEANTE,
    IssueSeverity.ALTA,
    IssueSeverity.MEDIA,
    IssueSeverity.BAIXA,
]

SEVERITY_BADGES = {
    IssueSeverity.BLOQUEANTE: "🔴 BLOQUEANTE (Crítico)",
    IssueSeverity.ALTA: "🟠 ALTA (Prioritário)",
    IssueSeverity.MEDIA: "🟡 MÉDIA (Importante)",
    IssueSeverity.BAIXA: "🔵 BAIXA (Melhoria)",
}


def build_fix_prompt(report: TestReport) -> str:
    """Gera um documento Markdown estruturado formatado como prompt para agentes de código ou desenvolvedores."""
    all_issues: list[tuple[str, str, Issue]] = []

    for cp in report.checkpoints:
        for issue in cp.issues:
            all_issues.append((cp.name, cp.expected_behavior, issue))

    if not all_issues and not report.healed_steps:
        return (
            f"# 🛠️ Relatório de Auditoria UXSentinel - {report.scenario_title}\n\n"
            f"> **Status:** Todos os checkpoints foram aprovados sem inconformidades!\n"
            f"> **Data:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            "Nenhum problema de UX, acessibilidade, tradução ou layout foi detectado durante a execução dos testes. "
            "Nenhuma correção técnica é necessária no momento.\n"
        )

    # Ordena issues por severidade
    def get_sort_key(item: tuple[str, str, Issue]) -> int:
        sev = item[2].severidade
        return SEVERITY_ORDER.index(sev) if sev in SEVERITY_ORDER else 99

    sorted_issues = sorted(all_issues, key=get_sort_key)

    total_bloqueantes = sum(1 for _, _, i in all_issues if i.severidade == IssueSeverity.BLOQUEANTE)
    total_altas = sum(1 for _, _, i in all_issues if i.severidade == IssueSeverity.ALTA)
    total_medias = sum(1 for _, _, i in all_issues if i.severidade == IssueSeverity.MEDIA)
    total_baixas = sum(1 for _, _, i in all_issues if i.severidade == IssueSeverity.BAIXA)

    lines: list[str] = []
    lines.append(f"# 🛠️ Prompt Técnico de Correção de UI/UX - {report.scenario_title}")
    lines.append("")
    lines.append(
        "> 🤖 **Instrução para o Agente de IA / Engenheiro de Software (Claude Code, Cursor, Copilot):**"
    )
    lines.append(
        "> Atue como um Engenheiro Frontend Sênior e Especialista em UI/UX e Acessibilidade. "
        "Abaixo está a lista detalhada de falhas visuais, termos não traduzidos e violações de regras de negócio "
        f"detectados pelo **UXSentinel** no cenário `{report.scenario_id}` (Perfil: `{report.profile}`).\n"
        "> Corrija cada um dos itens apontados diretamente no código-fonte da aplicação, garantindo integridade "
        "e padrão visual consistente."
    )
    lines.append("")
    lines.append("## 📌 Contexto da Auditoria")
    lines.append(f"- **Cenário:** `{report.scenario_id}` ({report.scenario_title})")
    lines.append(f"- **Perfil do Framework:** `{report.profile}`")
    lines.append(f"- **Provedor de Visão IA:** `{report.provider_used}`")
    lines.append(f"- **Data da Execução:** {report.started_at.strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append(f"- **Duração:** {report.duration_seconds:.2f}s")
    lines.append(f"- **Total de Inconformidades:** {len(all_issues)}")
    lines.append(
        f"  - 🔴 Bloqueantes: **{total_bloqueantes}** | 🟠 Altas: **{total_altas}** | "
        f"🟡 Médias: **{total_medias}** | 🔵 Baixas: **{total_baixas}**"
    )
    if report.healed_steps:
        lines.append(f"- **⚡ Seletores Auto-Curados (Self-Healing):** {len(report.healed_steps)}")
    lines.append("")

    if report.healed_steps:
        lines.append("---")
        lines.append("")
        lines.append("## ⚡ Sugestões de Correção de Seletores YAML (Self-Healing)")
        lines.append(
            "Durante a execução, os seguintes seletores sofreram timeout e foram recuperados automaticamente. "
            "Recomenda-se atualizar o arquivo de cenário YAML com as sugestões abaixo:"
        )
        lines.append("")
        for h_idx, step in enumerate(report.healed_steps, start=1):
            target = step.recovered_selector or f"coords {step.coordinates}"
            lines.append(f"### #{h_idx:02d} Ação `{step.action}` no Passo {step.step_index or 'N/A'}")
            lines.append(f"- **Seletor Original:** `{step.original_selector}`")
            lines.append(f"- **Estratégia de Recuperação:** `{step.strategy}`")
            lines.append(f"- **Destino Recuperado:** `{target}`")
            if step.yaml_fix_suggestion:
                lines.append(f"- **Sugestão para o YAML:** `{step.yaml_fix_suggestion}`")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 📋 Regras de Ouro para a Resolução")
    lines.append(
        "1. **Tradução (i18n):** Toda a interface do usuário deve estar 100% em Português do Brasil (pt-BR)."
    )
    lines.append(
        "2. **Sem Vazamento Técnico:** Nunca exiba nomes técnicos de colunas (snake_case) ou IDs brutos para o usuário final."
    )
    lines.append(
        "3. **Layout & Modais:** Modais devem caber na viewport sem barras de rolagem horizontais e com botões de ação sempre acessíveis."
    )
    lines.append(
        "4. **Design System:** Preserve as classes CSS, componentes semânticos e paleta de cores do projeto."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🛠️ Inconformidades a Corrigir (Ordenadas por Prioridade)")
    lines.append("")

    for idx, (cp_name, expected, issue) in enumerate(sorted_issues, start=1):
        badge = SEVERITY_BADGES.get(issue.severidade, str(issue.severidade).upper())
        cat_badge = str(issue.categoria).upper()

        lines.append(f"### #{idx:02d} [{cat_badge}] {issue.descricao}")
        lines.append(f"- **Severidade:** {badge}")
        lines.append(f"- **Categoria:** `{issue.categoria}`")
        if issue.evaluator:
            lines.append(f"- **Avaliador:** `{issue.evaluator}`")
        lines.append(f"- **CHECKPOINT:** `{cp_name}`")
        lines.append(f"- **Comportamento Esperado:** {expected}")
        if issue.elemento_alvo:
            lines.append(f"- **Elemento / Seletor:** `{issue.elemento_alvo}`")
        if issue.trecho_codigo:
            lines.append(f"- **Trecho Detectado:** `{issue.trecho_codigo}`")
        lines.append("")
        lines.append(f"**Descrição Detalhada:**\n{issue.descricao.strip()}")
        lines.append("")
        if issue.sugestao_correcao:
            lines.append(f"**Sugestão Técnica de Correção:**\n{issue.sugestao_correcao.strip()}")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## ✅ Checklist de Verificação Pós-Correção")
    lines.append("1. [ ] Implementar as alterações nos arquivos e templates correspondentes.")
    lines.append(
        "2. [ ] Atualizar seletores obsoletos nos cenários YAML com base nas sugestões de Self-Healing."
    )
    lines.append("3. [ ] Testar localmente a renderização no navegador.")
    lines.append("4. [ ] Re-executar o UXSentinel para validar a aprovação completa:")
    lines.append(f"   ```bash\n   uxsentinel -s scenarios/{report.scenario_id}.yaml\n   ```")
    lines.append("")

    return "\n".join(lines)


def save_fix_prompt(report: TestReport, output_dir: str | Path) -> Path:
    """Gera e salva o arquivo Markdown com o prompt de correção técnica."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    prompt_file = out_path / f"{report.scenario_id}_fix_prompt.md"

    content = build_fix_prompt(report)
    prompt_file.write_text(content, encoding="utf-8")
    return prompt_file
