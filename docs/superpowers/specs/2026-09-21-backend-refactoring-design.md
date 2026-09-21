# Especificação de Design: Refatoração Arquitetural e Desacoplamento dos Hotspots (UXSentinel)

- **Data:** 2026-09-21
- **Status:** Aprovado / Em Planejamento
- **Origem:** Análise do `python-backend-reviewer`

---

## 1. Visão Geral e Objetivos

Eliminar os hotspots de complexidade ciclomática, anti-patterns e potenciais riscos de concorrência identificados na análise técnica sênior, mantendo 100% de retrocompatibilidade e a aprovação de todos os 200 testes herméticos existentes.

### Métricas-Alvo
1. `Agent._execute_step`: Reduzir complexidade ciclomática de 126 para $\le 15$ e tamanho de 406 para $< 50$ linhas.
2. `Agent.run_scenario`: Eliminar mutação concorrente de `self.last_execution_result`.
3. `build_markdown_report`: Reduzir complexidade de 46 para $\le 12$ dividindo em renderers modulares.
4. `cli.py` (`async_main`): Extrair orquestração de execução para `core/runner.py`.

---

## 2. Divisão Detalhada de Tarefas e Bugs (Cards de Ação)

### 🔴 Bloco 1: Caminho Crítico & Dispatcher do Agente

#### Card 1 (BUG / Refactor): Eliminar Mutação de Estado Concorrente em `Agent.run_scenario`
- **Tipo:** Bug / Concurrency
- **Prioridade:** Alta
- **Componente:** `uxsentinel/core/agent.py`
- **Descrição:** O método assíncrono `run_scenario` muta diretamente `self.last_execution_result = report`. Em cenários de execuções concorrentes ou agentes reutilizados, isso gera race conditions.
- **Critérios de Aceite:**
  - `run_scenario` retorna o `TestReport` sem depender ou mutar estado mutável na instância do `Agent`.
  - Atualizar chamadas dependentes para receber o relatório como retorno explícito.

#### Card 2 (Task): Criar Estrutura de `ActionContext` e Handlers Especializados
- **Tipo:** Task / Architecture
- **Prioridade:** Alta
- **Componente:** `uxsentinel/browser/actions/`
- **Descrição:** Criar o pacote e contratos para os executores de ações semânticas:
  - `ActionContext`: Dataclass agrupando dependências de execução (driver, scenario, report, out_dir, etc.).
  - `BaseActionHandler`: Interface abstrata base.
  - Registro central de handlers (`ActionRegistry`).

#### Card 3 (Task): Implementar Handlers de Navegação, Formulários e Asserções
- **Tipo:** Task / Feature
- **Prioridade:** Alta
- **Componente:** `uxsentinel/browser/actions/`
- **Descrição:** Mover e isolar a lógica de:
  - `NavigationHandler`: `goto`, `set_viewport`, `scroll`, `hover`, etc.
  - `FormHandler`: `click`, `fill`, `type`, `clear`, `select`, `upload_file`.
  - `AssertionHandler`: `assert_required`, `assert_readonly`, `assert_options`.
  - `AiActionHandler`: Delegação para Set-of-Marks e `ScreenInspector`.

#### Card 4 (Task): Refatorar `Agent._execute_step` para Usar o `ActionRegistry`
- **Tipo:** Task / Refactor
- **Prioridade:** Alta
- **Componente:** `uxsentinel/core/agent.py`
- **Descrição:** Substituir a cadeia `if/elif` de 400 linhas por dispatch dinâmico através do `ActionRegistry`.
- **Critérios de Aceite:**
  - Complexidade ciclomática de `Agent._execute_step` $\le 15$.
  - 100% dos testes herméticos passando sem alteração de comportamento.

---

### 🟡 Bloco 2: Componentização do Reporter Markdown

#### Card 5 (Task): Modularizar Renderização em `uxsentinel/reporter/sections/`
- **Tipo:** Task / Maintainability
- **Prioridade:** Média
- **Componente:** `uxsentinel/reporter/`
- **Descrição:** Quebrar a função `build_markdown_report` (352 linhas, complexidade 46) em submódulos com responsabilidade única:
  - `render_header_summary(report: TestReport) -> str`
  - `render_axe_violations(a11y_data: AxeReport) -> str`
  - `render_visual_discrepancies(diffs: list[VisualDiffResult]) -> str`
  - `render_timeline_steps(steps: list[StepResult]) -> str`

#### Card 6 (Task): Compor `build_markdown_report` via Pipeline Modular
- **Tipo:** Task / Refactor
- **Prioridade:** Média
- **Componente:** `uxsentinel/reporter/markdown_builder.py`
- **Descrição:** Reestruturar a função principal para concatenar as seções produzidas pelos módulos puros.

---

### 🟢 Bloco 3: Desacoplamento da Orquestração do CLI

#### Card 7 (Task): Criar `ScenarioRunnerService`
- **Tipo:** Task / Architecture
- **Prioridade:** Média
- **Componente:** `uxsentinel/core/runner.py`
- **Descrição:** Isolar a lógica de coordenação multi-viewport, paralelismo, coleta de telemetria e arquivamento que atualmente está acoplada dentro do `cli.py:async_main`.

#### Card 8 (Task): Simplificar `cli.py` (`async_main`)
- **Tipo:** Task / Refactor
- **Prioridade:** Média
- **Componente:** `uxsentinel/cli.py`
- **Descrição:** Reduzir `async_main` de 594 linhas para menos de 100 linhas, mantendo nele estritamente o parsing de flags Typer/Click, logging visual no console e conversão para exit codes.

---

## 3. Plano de Verificação

- `uv run pytest` (Garantir 200 testes aprovados a cada card concluído)
- `uv run ruff check .` e `uv run ruff format --check .` (Manter código limpo)
