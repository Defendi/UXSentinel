# UXS-91 — Design Spec: Modo Assistido de Criação de Cenários

**Data:** 2026-10-01
**Épico:** UXS-91
**PRD de referência:** [PRD 001 — Modo Assistido de Criação de Cenários](prds/001-modo-assistido-criacao-cenarios.md)
**Status:** Planejamento concluído — aguardando revisão antes do plano de implementação
**Abordagem escolhida:** A — Playwright codegen como base + LLM auxiliar de decisão

---

## 1. Visão e Objetivo

O usuário **demonstra** o teste navegando pela aplicação; o sistema **aprende** e escreve o YAML.

O YAML deixa de ser a interface de entrada e passa a ser o artefato de saída. Qualquer pessoa que conheça o processo de negócio — sem conhecer Playwright, seletores CSS ou a sintaxe YAML — passa a ser capaz de criar cenários de teste no UXSentinel.

O executor existente (`runner.py`, `parser.py`) **não é alterado**. O modo assistido é uma entrada alternativa para o mesmo pipeline.

---

## 2. Arquitetura e Fronteiras de Módulo

### Localização do código novo

```
uxsentinel/
└── browser/
    └── recorder/
        ├── __init__.py
        ├── session.py         ← RecorderSession: ciclo de vida, BrowserContext headed
        ├── normalizer.py      ← EventNormalizer: codegen events → RecordedStep
        ├── resolver.py        ← ElementResolver: ElementHandle → seletor robusto
        ├── advisor.py         ← RecorderAdvisor: LLM consultada para decisões ambíguas
        └── models.py          ← RecordedWorkflow, RecordedStep, RecordedTarget

uxsentinel/
└── scenarios/
    └── generators.py          ← estender com RecordedWorkflowSerializer (já existe)

studio/uxsentinel_studio/
└── api.py                     ← novos routers /recorder/* + SSE + RECORDING_SESSION
```

### Fronteiras explícitas

| Módulo | Responsabilidade | Proibições |
|---|---|---|
| `recorder/session.py` | Gerencia `BrowserContext` headed; registra listeners; expõe `pause/resume/stop` | Não conhece YAML nem Studio |
| `recorder/normalizer.py` | Transforma eventos Playwright em `RecordedStep`; consulta `RecorderAdvisor` quando ambíguo | Não resolve seletores diretamente |
| `recorder/resolver.py` | Dado um `ElementHandle`, retorna o melhor seletor pela hierarquia de prioridade | Não conhece o fluxo de gravação |
| `recorder/advisor.py` | Consulta a LLM para decisões específicas; retorna sugestão + confiança; nunca altera o modelo diretamente | Não captura eventos; não serializa YAML |
| `recorder/models.py` | Dataclasses Pydantic do modelo intermediário | Não serializa para YAML |
| `scenarios/generators.py` | Serializa `RecordedWorkflow` → `workflow.yaml` | Não captura eventos |
| `studio/api.py` | Endpoints REST + SSE; singleton `RECORDING_SESSION` | Não instancia `BrowserContext` diretamente |

---

## 3. Fluxo de Dados

### Caminho feliz (ação clara)

```
Playwright codegen event (ex: click, fill, navigate)
         ↓
  EventNormalizer
         ↓ ação clara
  ElementResolver  →  SelectorCandidate (data-testid / role+name / label / css / xpath)
         ↓
  RecordedStep (status: confirmed)
         ↓
  RecordedWorkflow.append(step)
         ↓
  SSE → Studio (painel lateral atualiza em tempo real)
```

### Caminho com LLM auxiliar (ação ambígua)

```
Playwright codegen event (grupo ambíguo de eventos)
         ↓
  EventNormalizer detecta ambiguidade
         ↓
  RecorderAdvisor.consult(events, context)
         │
         ├── confiança alta (≥ 0.85)
         │       ↓
         │   RecordedStep (status: suggested, justificativa da LLM)
         │       ↓
         │   SSE → Studio apresenta como draft (accept / reject)
         │
         └── confiança baixa (< 0.85)
                 ↓
             RecordedStep (status: pending_review)
                 ↓
             SSE → Studio solicita intervenção manual
```

### Pontos de decisão onde a LLM é consultada

A LLM não participa do fluxo principal. É chamada somente em três situações:

| Situação | Pergunta que a LLM responde |
|---|---|
| **Ação ambígua** | "Este grupo de eventos (`focus → input → blur` sem `change`) é um `fill` ou apenas um `hover`?" |
| **Seletor disputado** | "Entre estes dois seletores igualmente estáveis, qual é mais legível e resistente a mudanças?" |
| **Validação inferida** | "Após esta sequência de ações, há um ponto óbvio de validação que o usuário provavelmente quer capturar?" |

O `RecorderAdvisor` sempre retorna `(sugestão: RecordedStep, confiança: float, justificativa: str)`. O Studio exibe a justificativa ao lado do draft para que o usuário tome a decisão final. O comportamento capturado **nunca é alterado silenciosamente**.

---

## 4. Modelos de Dados (`recorder/models.py`)

```python
from enum import StrEnum
from pydantic import BaseModel, Field


class StepStatus(StrEnum):
    CONFIRMED = "confirmed"  # capturado e normalizado com certeza
    SUGGESTED = "suggested"  # LLM sugeriu; aguarda accept/reject do usuário
    ACCEPTED = "accepted"  # sugestão da LLM aceita explicitamente pelo usuário
    PENDING_REVIEW = "pending_review"  # confiança baixa; aguarda intervenção manual
    REJECTED = "rejected"  # usuário rejeitou a sugestão


class SelectorStrategy(StrEnum):
    TESTID = "data-testid"
    ROLE = "role"
    LABEL = "label"
    TEXT = "text"
    CSS = "css"
    XPATH = "xpath"


class SelectorCandidate(BaseModel):
    strategy: SelectorStrategy
    value: str
    name: str | None = None  # para role+name


class RecordedTarget(BaseModel):
    """Identificação do elemento alvo da ação."""

    primary: SelectorCandidate  # seletor preferido
    fallbacks: list[SelectorCandidate] = Field(default_factory=list)
    raw_html_snippet: str | None = None  # para depuração


class RecordedStep(BaseModel):
    index: int
    action: str  # fill, click, navigate, assert, select, hover…
    target: RecordedTarget | None = None
    value: str | None = None
    url: str | None = None
    screenshot_path: str | None = None
    status: StepStatus = StepStatus.CONFIRMED
    advisor_justification: str | None = None  # preenchido pelo RecorderAdvisor
    advisor_confidence: float | None = None


class RecordedWorkflow(BaseModel):
    """Modelo intermediário independente de YAML."""

    session_id: str
    name: str
    url: str
    objective: str | None = None
    steps: list[RecordedStep] = Field(default_factory=list)
    created_at: str
    paused: bool = False
```

> **Invariante:** `RecordedWorkflow` nunca é serializado para YAML diretamente.
> Ele é passado ao `RecordedWorkflowSerializer` (em `generators.py`) que produz o YAML compatível com o `parser.py` existente.

---

## 5. Componentes em Detalhe

### 5.1 `RecorderSession` (`session.py`)

Responsável por:
- Lançar um novo `BrowserContext` headed com `playwright.chromium.launch(headless=False)`
- Registrar os listeners do Playwright que alimentam o `EventNormalizer`
- Expor `pause()`, `resume()`, `stop()` — `stop()` aciona o serializer e destrói o estado
- Registrar `browsercontext.on("close")` para auto-salvar se o usuário fechar o browser

**Ciclo de vida:**

```
__init__ → start() → [recording] → pause()/resume()* → stop()
                                                           ↓
                                                   RecordedWorkflowSerializer
                                                           ↓
                                                   workflow.yaml salvo
                                                           ↓
                                                   RECORDING_SESSION = None
```

**Listeners registrados no BrowserContext:**

```python
page.on("framenavigated", self._on_navigate)
page.on("popup", self._on_popup)
# Injeção via add_init_script: captura click, fill, select via
# window.__uxs_recorder_event__ exposto por page.expose_binding
```

A abordagem A usa `page.expose_binding("__uxs_record__", handler)` + `add_init_script` que escuta eventos DOM de alto nível e despacha via binding para o Python, aproveitando a normalização que o Playwright já faz internamente no `codegen`.

### 5.2 `EventNormalizer` (`normalizer.py`)

Recebe eventos brutos do binding e:
1. Agrupa eventos relacionados (ex: `focus + keydown* + change + blur` → `fill`)
2. Descarta ruído (`mousemove`, `scroll` sem semântica de ação)
3. Para ações claras: chama `ElementResolver` e cria `RecordedStep(status=CONFIRMED)`
4. Para ações ambíguas: chama `RecorderAdvisor.consult()` e cria `RecordedStep` com status adequado

**Ações suportadas no MVP:**

| Ação capturada | YAML gerado |
|---|---|
| Click em elemento | `action: click` |
| Fill em input | `action: fill` |
| Navegação de URL | `action: navigate` |
| Select dropdown | `action: select` |
| Checkpoint manual | `action: checkpoint` |
| Assert (validação) | `action: assert` |

### 5.3 `ElementResolver` (`resolver.py`)

Hierarquia de prioridade para seletores (da mais para a menos robusta):

```
1. data-testid          → SelectorStrategy.TESTID
2. aria-role + name     → SelectorStrategy.ROLE
3. label associado      → SelectorStrategy.LABEL
4. texto visível        → SelectorStrategy.TEXT
5. CSS estável          → SelectorStrategy.CSS
6. XPath                → SelectorStrategy.XPATH  (último recurso)
```

Retorna `RecordedTarget` com `primary` + lista de `fallbacks` para o serializer escolher a representação YAML mais expressiva.

### 5.4 `RecorderAdvisor` (`advisor.py`)

Wrapper fino sobre `UnifiedVisionClient` (já existente em `vision/client.py`):

```python
class RecorderAdvisor:
    def __init__(self, vision_client: UnifiedVisionClient) -> None: ...

    async def consult(
        self,
        events: list[RawEvent],
        context: str,
        question: AdvisorQuestion,
    ) -> AdvisorResponse: ...
```

```python
class AdvisorQuestion(StrEnum):
    AMBIGUOUS_ACTION = "ambiguous_action"
    DISPUTED_SELECTOR = "disputed_selector"
    INFER_ASSERTION = "infer_assertion"


class AdvisorResponse(BaseModel):
    suggested_step: RecordedStep
    confidence: float  # 0.0 – 1.0
    justification: str  # exibida no Studio ao lado do draft
```

O `RecorderAdvisor` é opcional: se nenhum provedor de IA estiver configurado, ações ambíguas vão direto para `status=PENDING_REVIEW` sem consulta.

### 5.5 `RecordedWorkflowSerializer` (em `scenarios/generators.py`)

Novo método público que converte `RecordedWorkflow` → `dict` compatível com o schema do `parser.py`:

```python
def serialize_recorded_workflow(workflow: RecordedWorkflow) -> str:
    """Serializa RecordedWorkflow para YAML compatível com o executor."""
    ...
```

Regras de serialização:
- Somente `steps` com `status in (CONFIRMED, ACCEPTED)` são incluídos — `SUGGESTED` sem aceite explícito, `REJECTED` e `PENDING_REVIEW` são excluídos
- `RecordedTarget.primary` determina o bloco `target:` do YAML
- `fallbacks` são descartados (não fazem parte do schema atual)
- O YAML gerado é validado pelo `load_scenario()` existente antes de salvar — se inválido, levanta `ValueError` com detalhes dos passos problemáticos

---

## 6. API do Studio (`studio/api.py`)

### Singleton de sessão

```python
# Singleton global — uma sessão ativa por vez
RECORDING_SESSION: dict[str, Any] | None = None
```

Tentativa de iniciar nova sessão com sessão ativa retorna `HTTP 409 Conflict`.

### Endpoints

```
POST   /api/recorder/sessions
       Body: { name, url, objective?, provider? }
       Validações antes de abrir browser:
         - name: não vazio
         - url: formato válido (regex); se inválida → 422 com mensagem específica
       → 201 Created: { session_id, status: "recording" }
       → 409 se já existe sessão ativa:
         { detail: "Sessão ativa em andamento", active_session_id: "...",
           hint: "Encerre a sessão ativa antes de iniciar uma nova." }

DELETE /api/recorder/sessions/{session_id}
       Se zero passos confirmados/aceitos → 200 com warning: { saved: false, reason: "no_steps" }
         (cliente exibe diálogo: salvar arquivo vazio ou descartar)
       Caso contrário → serializa, valida, salva, destrói estado
       → 200: { path: "caminho/do/workflow.yaml" }

PATCH  /api/recorder/sessions/{session_id}/pause
PATCH  /api/recorder/sessions/{session_id}/resume
       Ao retomar após pausa: se URL atual differ da URL no momento da pausa
       → injeta RecordedStep(action="navigate", url=<url_atual>) automaticamente

GET    /api/recorder/sessions/{session_id}/stream
       → text/event-stream (SSE)
       Eventos: step_added | step_suggested | step_pending | step_accepted |
                step_rejected | session_paused | session_resumed | session_closed | error

GET    /api/recorder/sessions/{session_id}/workflow
       → RecordedWorkflow (JSON) — estado atual para renderizar o painel

PUT    /api/recorder/sessions/{session_id}/steps/{index}
       Body: RecordedStep parcial (edit inline)

DELETE /api/recorder/sessions/{session_id}/steps/{index}

PATCH  /api/recorder/sessions/{session_id}/steps/{index}/accept
       → muda status SUGGESTED → ACCEPTED

PATCH  /api/recorder/sessions/{session_id}/steps/{index}/reject
       → muda status SUGGESTED | PENDING_REVIEW → REJECTED

POST   /api/recorder/sessions/{session_id}/steps
       Body: RecordedStep manual (usuário adiciona validação/assert)

POST   /api/recorder/sessions/{session_id}/export
       Body: { filename }
       Se filename já existir no projeto:
         → 409 com { detail: "Arquivo já existe", existing_path: "..." }
           (cliente pergunta sobrescrever ou renomear)
       Body alternativo: { filename, overwrite: true } → sobrescreve sem confirmação
       → 200: { path: "..." }; sessão destruída após export bem-sucedido
```

### Eventos SSE

```json
{ "event": "step_added",    "data": { "step": { ...RecordedStep } } }
{ "event": "step_suggested","data": { "step": { ...RecordedStep }, "justification": "..." } }
{ "event": "step_pending",  "data": { "step": { ...RecordedStep } } }
{ "event": "step_accepted", "data": { "step_index": 3 } }
{ "event": "step_rejected", "data": { "step_index": 3 } }
{ "event": "session_paused","data": { "current_url": "https://..." } }
{ "event": "session_resumed","data": { "current_url": "https://...", "navigate_injected": true } }
{ "event": "session_closed","data": { "path": "caminho/do/workflow.yaml" } }
{ "event": "error",         "data": { "message": "..." } }
```

---

## 7. Tratamento de Erros

| Situação | Comportamento |
|---|---|
| URL inválida ou mal-formada ao iniciar sessão | `HTTP 422` antes de abrir o browser; mensagem específica no Studio |
| URL válida mas inacessível (timeout) | Browser abre, timeout é detectado, sessão encerrada com erro; RECORDING_SESSION destruído |
| Browser fechado pelo usuário | `browsercontext.on("close")` dispara `stop()` → salva YAML automaticamente |
| Zero passos ao encerrar | `DELETE` retorna `{ saved: false, reason: "no_steps" }`; cliente exibe diálogo (salvar vazio ou descartar) |
| Pausa + navegação para nova URL ao retomar | `resume()` injeta `RecordedStep(action="navigate")` automaticamente; evento `session_resumed` com `navigate_injected: true` |
| LLM indisponível | `RecorderAdvisor` desabilitado silenciosamente; ações ambíguas → `PENDING_REVIEW` |
| YAML gerado inválido | `serialize_recorded_workflow` levanta `ValueError` com detalhes dos passos problemáticos; Studio exibe erro; sessão não é destruída |
| Segunda sessão tentada | `HTTP 409 Conflict` com `active_session_id` e hint de encerramento |
| Arquivo já existente no export | `HTTP 409` com `existing_path`; cliente pergunta sobrescrever (`overwrite: true`) ou renomear |
| Projeto sem diretório de cenários | `HTTP 400` com instrução de configurar antes de exportar |
| Seletor não resolvido | `ElementResolver` usa XPath como fallback; nunca falha silenciosamente |
| Elemento sem seletor possível | `RecordedTarget.primary = None` → step vai para `PENDING_REVIEW` com motivo "seletor não resolvido" |
| Studio reiniciado com sessão ativa no processo anterior | `RECORDING_SESSION = None` no startup do servidor; sessão anterior considerada encerrada; sem YAML salvo (dados perdidos) |
| `INFER_ASSERTION` sugerida após ação trigger (ex: submit, click em "Salvar") | `RecorderAdvisor` consultado com `AdvisorQuestion.INFER_ASSERTION`; se confiança ≥ 0.85, evento `step_suggested` enviado via SSE com tipo `assert`; usuário aceita ou rejeita |

---

## 8. Decisões de Escopo (MVP)

| # | Decisão |
|---|---|
| 1 | Novo `BrowserContext` Playwright, headed, isolado do executor |
| 2 | Uma sessão de gravação ativa por vez (singleton) |
| 3 | Fechar browser → salva YAML e destrói estado; sem persistência de rascunho |
| 4 | LLM entra no MVP como auxiliar de decisão (`RecorderAdvisor`), opcional |
| 5 | Validações podem ser adicionadas durante e depois da gravação |
| 6 | Retomada de sessão após salvar → melhoria futura (backlog) |

### Fora do escopo do MVP (backlog)
- Continuidade de sessão após fechar e reabrir
- Sessões múltiplas simultâneas
- Import de YAML existente para modo de edição assistida

---

## 9. Estratégia de Testes

Todos os testes devem ser **herméticos**: sem rede real, sem browser real, sem LLM real.

| Camada | O que testar | Como |
|---|---|---|
| `recorder/models.py` | Serialização/deserialização Pydantic; invariantes dos enums incluindo `ACCEPTED` | `pytest` puro |
| `recorder/resolver.py` | Hierarquia de seletores; fallback para XPath; `primary=None` para elemento sem seletor | Mocks de `ElementHandle` |
| `recorder/normalizer.py` | Agrupamento de eventos → `RecordedStep`; casos ambíguos identificados; deduplicação de eventos em burst | Fixtures de eventos DOM falsos |
| `recorder/advisor.py` | Interface com LLM; limiar `≥ 0.85` para `SUGGESTED` vs `PENDING_REVIEW`; fallback sem LLM; `INFER_ASSERTION` após ações trigger | Mock de `UnifiedVisionClient` |
| `recorder/session.py` | Ciclo de vida (start/pause/resume/stop); auto-save no close; injeção de `navigate` ao retomar após pausa com URL diferente | Mock de `BrowserContext` |
| `scenarios/generators.py` | YAML gerado válido segundo `load_scenario()`; somente `CONFIRMED` e `ACCEPTED` exportados; `SUGGESTED`, `REJECTED`, `PENDING_REVIEW` excluídos | `RecordedWorkflow` de fixture |
| `studio/api.py` | 422 para URL inválida; 409 com `active_session_id` para segunda sessão; zero passos retorna `saved: false`; 409 para arquivo existente no export; `RECORDING_SESSION = None` no startup | `TestClient` FastAPI + mocks |

---

## 10. Decomposição em Histórias Filhas

Ordem de implementação baseada nas dependências:

| Ordem | História | Entrega verificável | Dependência |
|---|---|---|---|
| 1 | **H1 — WorkflowModel** | `recorder/models.py` com testes unitários passando | — |
| 2 | **H2 — RecorderSession** | Sessão headed abre, grava e fecha; YAML vazio gerado | H1 |
| 3 | **H4 — ElementResolver** | Dado mock de `ElementHandle`, retorna seletor correto pela hierarquia | H1 |
| 4 | **H3 — EventNormalizer** | Grupo de eventos → `RecordedStep` correto; ambíguos identificados | H2, H4 |
| 5 | **H4b — RecorderAdvisor** | LLM consultada em casos ambíguos; fallback sem LLM | H3 |
| 6 | **H5 — YAML Serializer** | `RecordedWorkflow` → YAML válido segundo `load_scenario()` | H1, H3, H4 |
| 7 | **H6 — API + Studio UI** | Endpoints REST + SSE + painel lateral com timeline e editor | H5 |

> **Spike de risco (H1 + H2 + H4):** uma vez que o Recorder grava e o Serializer exporta um YAML executável — mesmo via CLI — o restante é iteração incremental de baixo risco.

---

## 11. Pontos de Reuso do Código Existente

| O que reusar | Arquivo | Como |
|---|---|---|
| SSE streaming | `studio/api.py` — `StreamingResponse` | Padrão idêntico ao de execuções |
| Geração de YAML | `scenarios/generators.py` | Novo método `serialize_recorded_workflow` |
| Parser/validação | `scenarios/parser.py` — `load_scenario()` | Validar YAML antes de salvar |
| Cliente de visão | `vision/client.py` — `UnifiedVisionClient` | Injetado no `RecorderAdvisor` |
| EventBus | `core/events.py` | Opcional: comunicar eventos entre `RecorderSession` e API |
| Modelos Pydantic | `core/models.py` | Referência de estilo e padrão |

---

## 12. Checklist de Critérios de Aceite

| CA | Descrição | Coberto por |
|---|---|---|
| CA01 | Iniciar gravação com URL válida abre sessão Playwright headed | H2 |
| CA01b | URL inválida rejeitada com 422 antes de abrir browser | H2 + API |
| CA02 | Ações suportadas capturadas na ordem correta | H2 + H3 |
| CA02b | Burst de eventos não gera passos duplicados na timeline | H3 (EventNormalizer) |
| CA03 | YAML gerado é válido e compatível com o executor | H5 |
| CA03b | Somente `CONFIRMED` e `ACCEPTED` exportados; demais excluídos | H5 |
| CA04 | Usuário cria workflow sem editar YAML manualmente | H6 |
| CA05 | Editar, remover e reordenar ações antes de salvar | H6 (editor) |
| CA06 | Seletores priorizados pela hierarquia robusta | H4 |
| CA07 | Validações adicionáveis durante e após a gravação como passo `assert` | H6 + H5 |
| CA07b | IA sugere validação após ação trigger; usuário aceita ou rejeita | H4b + H6 |
| CA08 | Workflow gerado executável pelo executor existente | H5 |
| CA09 | Formato idêntico ao workflow manual | H5 (usa mesmo parser) |
| CA10 | Screenshots associados às etapas quando disponíveis | H2 + H5 |
| CA11 | Fechar browser salva YAML automaticamente | H2 (session.py on_close) |
| CA12 | Zero passos: sistema avisa e não salva sem confirmação | API + H6 |
| CA13 | Arquivo existente no export: sistema pergunta sobrescrever | API + H6 |
| CA14 | Pausa + navegação: passo `navigate` injetado ao retomar | H2 (session.py resume) |
| CA15 | Sugestão da IA nunca altera passo confirmado sem aceite explícito | H4b + H3 |
