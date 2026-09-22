# Cards de Engenharia: Refatorações e Correções do Backend (Studio)

- **Data:** 2026-09-22  
- **Origem:** Revisão de Código via `python-backend-reviewer`  
- **Módulos Alvo:** `studio/uxsentinel_studio/api.py`, `uxsentinel/service/scenario_service.py`  
- **Objetivo:** Sanar riscos de retenção de memória, decompor métodos com alta complexidade ciclomática, eliminar duplicações de busca de arquivos e eliminar warnings de depreciação de HTTP status.

---

## 📋 Sumário dos Cards

| Card | Chave Jira | Tipo | Prioridade | Componente | Título Resumido |
| :---: | :---: | :---: | :---: | :--- | :--- |
| **`STU-12`** | `UXS-56` | Performance / Memory | **Alta** | `studio/uxsentinel_studio/api.py` | Política de Retenção de Memória em `EXECUTIONS` (Cap de 50 runs) |
| **`STU-13`** | `UXS-57` | Refactor / Clean Code | **Alta** | `studio/uxsentinel_studio/api.py` | Decomposição Modular da Task Assíncrona `_execute_scenario_task` |
| **`STU-14`** | `UXS-58` | Refactor / DRY | **Média** | `uxsentinel/service/scenario_service.py` | Centralização de `find_scenario_path` no `ScenarioService` |
| **`STU-15`** | `UXS-59` | Compliance / Linter | **Baixa** | `studio/uxsentinel_studio/api.py` | Migração do Status 422 Deprecado para `HTTP_422_UNPROCESSABLE_CONTENT` |

---

## 🎯 Detalhamento dos Cards

---

### 🔴 Card STU-12 (UXS-56): Limitação de Retenção de Memória no Registro `EXECUTIONS`

- **Tipo:** Performance / Memory Leak Prevention
- **Prioridade:** Alta
- **Componente:** `studio/uxsentinel_studio/api.py` (L35 e L404-L440)
- **Severidade do Revisor:** Critical Issue (C-01)

#### 1. Descrição do Problema
O dicionário global `EXECUTIONS: dict[str, dict[str, Any]] = {}` é instanciado em nível de módulo e acumula indefinidamente o histórico de execuções disparadas pelo Studio. Cada execução armazena um payload contendo:
- `event_history`: todos os chunks serializados de SSE (`data: {...}\n\n`);
- `logs`: lista de strings de todos os logs da execução;
- `result`: dicionário de resultados;
- `subscribers`: referências a filas `asyncio.Queue`.

Em sessões prolongadas de desenvolvimento local ou auditorias em lote, o acúmulo contínuo de strings e objetos sem política de descarte gera consumo desnecessário de memória RAM.

#### 2. Como Corrigir
1. Definir uma constante de teto máximo:
   ```python
   MAX_RETAINED_EXECUTIONS = 50
   ```
2. Implementar uma função auxiliar encapsulada de registro com política FIFO (evict da execução mais antiga):
   ```python
   def _register_execution(run_id: str, data: dict[str, Any]) -> None:
       """Registra uma nova execução aplicando política FIFO de retenção máxima."""
       if len(EXECUTIONS) >= MAX_RETAINED_EXECUTIONS:
           oldest_id = next(iter(EXECUTIONS))
           EXECUTIONS.pop(oldest_id, None)
       EXECUTIONS[run_id] = data
   ```
3. Substituir as atribuições diretas `EXECUTIONS[run_id] = ...` no endpoint `run_execution` por chamadas a `_register_execution(run_id, ...)`.

#### 3. Critérios de Aceite
- `len(EXECUTIONS)` nunca excede `MAX_RETAINED_EXECUTIONS` (50 instâncias).
- Quando a 51ª execução for registrada, a execução mais antiga é removida sem gerar erros nos endpoints de consulta.
- Teste unitário em `studio/tests/test_api.py` validando o descarte FIFO de execuções antigas.

---

### 🟠 Card STU-13 (UXS-57): Decomposição Modular da Task Assíncrona `_execute_scenario_task`

- **Tipo:** Refactor / Clean Code & Maintainability
- **Prioridade:** Alta
- **Componente:** `studio/uxsentinel_studio/api.py` (L167-L272)
- **Severidade do Revisor:** Important Issue (I-01)

#### 1. Descrição do Problema
A função assíncrona `_execute_scenario_task(run_id: str, options: ExecutionOptions)` possui **105 linhas de extensão**, **complexidade ciclomática 12** e **4 níveis de aninhamento**. Ela acumula responsabilidades distintas:
1. Emissão de logs de inicialização e metadados de cenário;
2. Chamada ao `ExecutionService.run()`;
3. Iteração e formatação dos passos executados (`report.steps` vs `scenario.steps`);
4. Iteração e formatação dos checkpoints auditados (`report.checkpoints`);
5. Consolidação de status e emissão dos eventos terminais (`completed` ou `error`).

Isso dificulta a manutenção, a testabilidade unitária de cada etapa de formatação e viola o princípio de responsabilidade única (SRP).

#### 2. Como Corrigir
1. Extrair a lógica de emissão de steps para a função pura:
   ```python
   async def _emit_step_events(run_id: str, report: Any, scenario: Any | None) -> None:
       """Publica eventos SSE individuais para cada passo executado ou planejado."""
       steps_list = getattr(report, "steps", [])
       if steps_list:
           for idx, step in enumerate(steps_list, start=1):
               await publish_execution_event(
                   run_id,
                   "step",
                   {
                       "step_index": idx,
                       "action": getattr(step, "action", ""),
                       "description": getattr(step, "description", ""),
                       "status": "passed" if getattr(step, "success", True) else "failed",
                   },
               )
       elif scenario and getattr(scenario, "steps", None):
           for idx, step_def in enumerate(scenario.steps, start=1):
               await publish_execution_event(
                   run_id,
                   "step",
                   {
                       "step_index": idx,
                       "action": getattr(step_def, "action", ""),
                       "description": getattr(step_def, "description", ""),
                       "status": "passed" if report.success else "completed",
                   },
               )
   ```
2. Extrair a lógica de emissão de checkpoints para a função pura:
   ```python
   async def _emit_checkpoint_events(run_id: str, report: Any) -> None:
       """Publica eventos SSE individuais para cada checkpoint auditado."""
       for cp in getattr(report, "checkpoints", []):
           issues = getattr(cp, "issues", [])
           await publish_execution_event(
               run_id,
               "checkpoint",
               {
                   "name": getattr(cp, "name", ""),
                   "status": "passed" if not issues else "failed",
                   "issues_count": len(issues),
                   "expected_behavior": getattr(cp, "expected_behavior", ""),
               },
           )
   ```
3. Simplificar o corpo principal de `_execute_scenario_task` chamando os dois helpers, reduzindo a complexidade ciclomática da função principal para $\le 6$ e seu tamanho para $< 45$ linhas.

#### 3. Critérios de Aceite
- Complexidade ciclomática de `_execute_scenario_task` $\le 6$.
- Tamanho de `_execute_scenario_task` $< 50$ linhas.
- Nenhum evento SSE deixa de ser publicado; testes de streaming SSE em `studio/tests/test_api.py` continuam 100% aprovados.

---

### 🟡 Card STU-14 (UXS-58): Centralização de `find_scenario_path` no `ScenarioService`

- **Tipo:** Refactor / DRY (Don't Repeat Yourself)
- **Prioridade:** Média
- **Componente:** `uxsentinel/service/scenario_service.py` e `studio/uxsentinel_studio/api.py` (L109-L138)
- **Severidade do Revisor:** Important Issue (I-02)

#### 1. Descrição do Problema
O arquivo `studio/uxsentinel_studio/api.py` define a função privada `find_scenario_path(scenario_id: str, project_dir: Path) -> Path | None`, varrendo múltiplos diretórios (`scenarios/`, `.uxsentinel/scenarios/`, `tests/scenarios/` e `ScenarioService.get_library_dir()`).
Essa responsabilidade é inerente ao domínio de manipulação de cenários (`ScenarioService`). Manter essa lógica solta no módulo de rotas da API cria duplicação de regras de busca e impede reutilização por outros consumidores do Core.

#### 2. Como Corrigir
1. Em `uxsentinel/service/scenario_service.py`, promover a busca para um método público oficial da classe `ScenarioService`:
   ```python
   def find_scenario_path(self, scenario_id: str, base_dir: Path | str) -> Path | None:
       """Localiza o arquivo físico (.yaml/.yml) de um cenário pelo ID ou stem do nome."""
       self._sanitize_path_component(scenario_id)
       base_path = Path(base_dir).resolve()
       search_dirs = [
           base_path / "scenarios",
           base_path / ".uxsentinel" / "scenarios",
           base_path / "tests" / "scenarios",
           base_path,
           self.get_library_dir(),
       ]
       for sdir in search_dirs:
           if not sdir.is_dir():
               continue
           for ext in ("*.yaml", "*.yml"):
               for candidate in sdir.glob(ext):
                   try:
                       sc = load_scenario(str(candidate))
                       if sc.id == scenario_id or candidate.stem == scenario_id:
                           return candidate
                   except Exception:
                       continue
       return None
   ```
2. Em `uxsentinel/service/scenario_service.py`, reutilizar esse método dentro de `get_scenario()` para simplificar a busca interna.
3. Em `studio/uxsentinel_studio/api.py`, remover a função local `find_scenario_path` e substituir as chamadas por:
   ```python
   scenario_service = ScenarioService()
   scenario_path = scenario_service.find_scenario_path(req.scenario_id, project_dir)
   ```

#### 3. Critérios de Aceite
- Lógica de varredura unificada e centralizada em `ScenarioService`.
- `api.py` livre de lógica manual de I/O em disco para busca de cenários.
- 100% dos testes existentes de `ScenarioService` e da API do Studio continuam passando.

---

### 🟢 Card STU-15 (UXS-59): Atualização dos Status Codes 422 Deprecados no Starlette/FastAPI

- **Tipo:** Compliance / Deprecation Warning Fix
- **Prioridade:** Baixa
- **Componente:** `studio/uxsentinel_studio/api.py` (L333 e L353)
- **Severidade do Revisor:** Suggestion (S-01)

#### 1. Descrição do Problema
O código atual utiliza `status.HTTP_422_UNPROCESSABLE_ENTITY` nas rotas `POST /scenarios` e `PUT /scenarios/{scenario_id}`. Nas versões recentes do Starlette e FastAPI (conforme a RFC 9110), esse atributo emite o warning:
```
StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
```

#### 2. Como Corrigir
Substituir as duas ocorrências em `studio/uxsentinel_studio/api.py`:
```python
# ❌ ANTES (L333 e L353):
raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err)) from err

# ✅ DEPOIS:
raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from err
```

#### 3. Critérios de Aceite
- Eliminação completa do `StarletteDeprecationWarning` durante a execução dos testes com pytest.
- Resposta HTTP 422 preservada com exata fidelidade funcional para entradas inválidas.

---

## 🧪 Matriz de Verificação Pós-Correções

```bash
# 1. Suíte Hermética Completa (Core + Studio)
ambiente/bin/pytest tests studio/tests

# 2. Auditoria Estática e Linter
ambiente/bin/ruff check .
ambiente/bin/ruff format --check .
```
