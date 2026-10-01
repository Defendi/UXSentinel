# UXS-91 — Análise do Épico: Modo Assistido de Criação de Cenários

> [!IMPORTANT]
> Esta é uma análise **somente leitura** (fase de planejamento). Nenhuma alteração de código, arquivo ou card foi realizada.

---

## 1. Identidade do Card

| Campo | Valor |
|---|---|
| **Chave** | UXS-91 |
| **Tipo** | Epic |
| **Status** | Backlog |
| **Prioridade** | Medium |
| **Projeto** | UXSentinel Tarefas |
| **Título** | Adicionar o modo assistido de criação de cenários |

---

## 2. A ideia central em uma frase

> O usuário **demonstra** o teste ao agente navegando pela aplicação; o sistema **aprende** e escreve o YAML.

Essa inversão é o coração do épico: o YAML deixa de ser o ponto de entrada e passa a ser o artefato de saída. Quem conhece o processo de negócio mas não conhece Playwright passa a ser cidadão de primeira classe no UXSentinel.

---

## 3. Mapeamento arquitetural — onde a feature vive

A tabela abaixo cruza os componentes propostos no card com a estrutura atual do repositório:

| Componente proposto (card) | Localização atual ou candidata | Situação |
|---|---|---|
| **Recorder** (captura Playwright) | `uxsentinel/browser/` — new subdir `recorder/` | ❌ Não existe |
| **Event Normalizer** | `uxsentinel/browser/recorder/normalizer.py` | ❌ Não existe |
| **Element Resolver** | Parcialmente em `uxsentinel/browser/healing.py` e `semantic_actions.py` | ⚠️ Existe, mas incompleto para o caso de uso |
| **Workflow Model** | `uxsentinel/core/models.py` tem modelos similares para execução | ⚠️ Existe para execução; precisa de variante para gravação |
| **YAML Serializer** | `uxsentinel/scenarios/generators.py` | ⚠️ Existe para geração de YAML, mas não a partir de modelo de gravação |
| **Workflow Editor (UI)** | `studio/uxsentinel_studio/` — new frontend feature | ❌ Não existe no frontend |
| **API endpoints de gravação** | `studio/uxsentinel_studio/api.py` — novos routers | ❌ Não existe |

### Fluxo de dados na arquitetura existente (contexto)

```
cenário YAML → parser → scenario model → runner/agent → browser/session → vision → reporter
```

### Fluxo proposto para o modo assistido

```
usuário interage no browser (Playwright headed)
         ↓
     Recorder (novo)
         ↓
  Event Normalizer (novo)
         ↓
   Workflow Model (adaptado de models.py)
         ↓
   ┌─────────────────────┐
   │                     │
   ▼                     ▼
UI Editor (Studio)   YAML Serializer
   (novo)            (adapta generators.py)
                         ↓
                    workflow.yaml
                         ↓
               executor existente (runner)
```

> [!NOTE]
> O executor existente (`uxsentinel/core/runner.py`) **não precisa ser alterado**. O contrato YAML é o mesmo. Isso é uma vantagem arquitetural fundamental: o modo assistido é uma **entrada alternativa** para o mesmo pipeline.

---

## 4. Análise de riscos e complexidades

### 🔴 Alta complexidade

#### R1 — Normalização de eventos Playwright
Playwright em modo `record` captura eventos brutos. A camada de normalização que transforma `focus → keydown → input → change → blur` em `fill: "E-mail" = "joao@email.com"` é o problema mais difícil do épico.

**Risco:** lógica de normalização frágil que gera YAML ruidoso ou perde ações relevantes.

**Mitigação sugerida:** usar a API `page.on("request")`, `page.on("console")` e os hooks do `BrowserContext` combinados com escuta de eventos via `page.evaluate`. O Playwright já oferece `codegen` como referência; podemos estudar como ele resolve esse problema.

#### R2 — Element Resolver robusto
O arquivo `uxsentinel/browser/healing.py` e `semantic_actions.py` já possuem lógica de seletor, mas foi desenvolvida para **execução** (self-healing). Para **gravação**, a direção é oposta: dado um elemento interagido, **inferir o melhor seletor** antes de gravar.

**Risco:** seletores gerados frágeis que quebram o workflow no replay.

**Mitigação sugerida:** reutilizar e estender a hierarquia já definida (`data-testid → role+name → label → css → xpath`), mas com orientação de gravação.

#### R3 — Sessão singleton (Studio + gravação + execução)
O Studio hoje usa `api.py` com sessões de execução em memória (`EXECUTIONS dict`). A gravação exige uma nova categoria de sessão: **sessão de gravação ativa**, com estado singleton (pausa, retomada, edição inline).

**Risco:** colisão entre sessões de execução e gravação, vazamento de estado.

**Mitigação:** criar `RECORDING_SESSION: dict | None` separado do `EXECUTIONS`, com ciclo de vida independente. Retorna `HTTP 409 Conflict` se já houver sessão ativa.

---

### 🟡 Média complexidade

#### R4 — Sincronia da UI em tempo real
O usuário navega em uma janela Playwright headed enquanto o painel lateral do Studio mostra ações sendo capturadas em tempo real. Isso exige SSE ou WebSocket do backend para o frontend — padrão **já existente** no Studio (veja `StreamingResponse` em `api.py`).

**Oportunidade:** reaproveitar a infraestrutura de SSE já implementada para execuções.

#### R5 — Integração com LLM (análise assistida)
A LLM age como **pós-processador opcional** após cada grupo de ações capturadas, sugerindo refinamentos antes de gravar no `WorkflowModel`. Toda sugestão é apresentada como `draft` com `accept/reject` explícito — o comportamento capturado pelo usuário nunca é sobrescrito silenciosamente.

---

### 🟢 Baixa complexidade (comparativamente)

#### R6 — YAML Serializer
O arquivo `uxsentinel/scenarios/generators.py` já tem lógica para gerar YAML de cenários. O serializer do modo assistido é uma extensão direta dele, partindo de um `WorkflowModel` em vez de gerar a partir de prompts.

#### R7 — Compatibilidade com executor
O card é explícito: o YAML gerado deve ser compatível com o executor atual. O `uxsentinel/scenarios/parser.py` já define o contrato. Enquanto o serializer respeitar esse parser, o replay funciona sem mudança no executor.

---

## 5. Decomposição em histórias filhas (breakdown)

O épico se decompõe em seis histórias de entrega incremental:

| # | Título | Entrega | Dependência |
|---|---|---|---|
| H1 | WorkflowModel — modelo intermediário de gravação | Dataclasses Pydantic para `RecordedWorkflow`, `RecordedStep`, `RecordedTarget` | Nenhuma |
| H2 | Recorder — captura de eventos via Playwright | Sessão headed com hooks de evento; endpoint `POST /recorder/sessions` | H1 |
| H3 | Event Normalizer — eventos → ações semânticas | Lógica de consolidação e deduplicação de eventos brutos | H2 |
| H4 | Element Resolver — inferência de seletores | Estratégia de prioridade de seletores orientada à gravação | H2 |
| H5 | YAML Serializer — modelo → `workflow.yaml` | Extensão de `generators.py` partindo do `RecordedWorkflow` | H1, H3, H4 |
| H6 | UI do Modo Assistido no Studio | Painel lateral com timeline, edição inline, botões de controle | H5 |

---

## 6. Contrato de interface (API sketch — planejamento)

Endpoints que a feature precisará expor no Studio:

```
POST   /api/recorder/sessions                          → Inicia sessão de gravação
DELETE /api/recorder/sessions/{id}                     → Encerra sessão (salva YAML + destrói estado)
PATCH  /api/recorder/sessions/{id}/pause
PATCH  /api/recorder/sessions/{id}/resume
GET    /api/recorder/sessions/{id}/stream              → SSE de ações em tempo real
GET    /api/recorder/sessions/{id}/workflow            → Estado atual do WorkflowModel
PUT    /api/recorder/sessions/{id}/steps/{step_index}  → Editar ação
DELETE /api/recorder/sessions/{id}/steps/{step_index}  → Remover ação
POST   /api/recorder/sessions/{id}/export              → Serializa para YAML e salva
```

---

## 7. Pontos de reuso do código existente

| O que reusar | Arquivo | Como |
|---|---|---|
| SSE streaming de eventos | `api.py` — `StreamingResponse` | Reaproveitar padrão para `stream` da sessão de gravação |
| Seletores semânticos | `browser/semantic_actions.py`, `browser/healing.py` | Extrair lógica de resolução de seletor para `Element Resolver` |
| Geração de YAML | `scenarios/generators.py` | Estender para serializar `RecordedWorkflow` |
| Parser de cenários | `scenarios/parser.py` | Usar como validação do YAML gerado |
| Modelos Pydantic | `core/models.py` | Referência de padrão para `WorkflowModel` |
| EventBus | `core/events.py` | Comunicar eventos de gravação entre camadas |

---

## 8. Critérios de aceite — análise de cobertura

O card define 10 CAs. Mapeamento de cobertura por história:

| CA | Descrição resumida | Coberto por |
|---|---|---|
| CA01 | Iniciar gravação com URL válida | H2 |
| CA02 | Capturar ações suportadas na ordem correta | H2 + H3 |
| CA03 | Gerar YAML válido e compatível | H5 |
| CA04 | Criar workflow sem editar YAML manualmente | H6 |
| CA05 | Editar ou remover ações antes de salvar | H6 (editor) |
| CA06 | Priorizar seletores estáveis e semânticos | H4 |
| CA07 | Adicionar validações durante/após a gravação | H6 + H5 |
| CA08 | Replay pelo executor existente | H5 (YAML compatível) |
| CA09 | Mesmo formato de workflow manual | H5 (usa mesmo parser) |
| CA10 | Associar screenshots/evidências às etapas | H2 + H5 |

---

## 9. Decisões de planejamento ✅

Perguntas respondidas e registradas como definições de escopo para o MVP.

| # | Pergunta | Decisão |
|---|---|---|
| 1 | Modo de sessão do navegador | **Novo contexto Playwright** — isolado, headed obrigatório |
| 2 | Sessões simultâneas | **Uma sessão ativa por vez** — singleton de gravação |
| 3 | Fechamento de sessão | **Salva o YAML e destrói o estado** — sem persistência de rascunho no MVP; continuidade após salvar é melhoria futura (backlog) |
| 4 | Integração LLM | **Entra no MVP** — sugestão assistida de ações com confirmação do usuário |
| 5 | Validações | **Durante e depois** da gravação — ambos os momentos são suportados |
| 6 | Retomada de gravação | **Melhoria futura (backlog)** — alinhado com a decisão 3 |

---

### Impacto das decisões na arquitetura

#### Decisão 1 → Novo contexto
O `RecorderSession` instancia um `BrowserContext` Playwright novo, independente de qualquer contexto de execução existente. Isso isola cookies, storage e estado de rede da gravação.

```
BrowserContext (recorder) ← novo, headed, isolado
BrowserContext (executor) ← existente, headless por padrão
```

#### Decisão 2 → Singleton de gravação
`RECORDING_SESSION: dict | None = None` em memória (singleton simples, análogo ao padrão `EXECUTIONS`). Tentativa de iniciar uma segunda sessão retorna `HTTP 409 Conflict` com mensagem clara.

#### Decisão 3 → Salvar e destruir
Ciclo de vida da sessão:

```
start → recording → [pause/resume]* → stop
                                          ↓
                                   YAML Serializer
                                          ↓
                                   salva workflow.yaml
                                          ↓
                                   destrói RECORDING_SESSION
```

Ao fechar o browser headed, o evento `browsercontext.on("close")` do Playwright dispara automaticamente o mesmo fluxo de `stop`.

#### Decisão 4 → LLM no MVP
A LLM age como **pós-processador opcional** após cada grupo de ações capturadas, sugerindo refinamentos antes de gravar no `WorkflowModel`. Toda sugestão é apresentada como `draft` com `accept/reject` explícito — o comportamento capturado pelo usuário nunca é sobrescrito silenciosamente.

#### Decisão 5 → Validações durante e depois
Durante a gravação: o painel lateral expõe botão "Adicionar validação" que injeta um `RecordedStep` do tipo `assert` na posição atual da timeline.
Após encerrar: o editor de workflow permite inserir, editar e reordenar passos `assert` antes do export.

#### Decisão 6 → Retomada como melhoria futura
A retomada de sessão após salvar não faz parte do MVP. O card de melhoria será criado no backlog oportunamente.

---

## 10. Visão de valor de produto

```
Antes do UXS-91:
  QA analista → escreve YAML → testa → ajusta → executa agente

Depois do UXS-91:
  QA analista → navega na aplicação → revisa ações capturadas → executa agente
```

**O impacto real:** eliminar a curva de aprendizado do YAML como barreira de adoção. Qualquer pessoa que conheça o processo de negócio passa a ser capaz de criar cenários de teste, sem precisar conhecer Playwright, seletores CSS ou a estrutura YAML do UXSentinel.

Isso potencialmente multiplica a base de usuários do produto, pois move o público-alvo de "QA técnico" para "analista de negócio com acesso à aplicação".

---

## 11. Próximos passos — planejamento concluído ✅

As decisões de escopo estão fechadas. O planejamento está pronto para avançar para a **Fase 1: Especificação** das histórias filhas.

### Ação imediata: criar histórias filhas no Jira

| Ordem | História | Prioridade |
|---|---|---|
| 1 | **H1 — WorkflowModel** — `RecordedWorkflow`, `RecordedStep`, `RecordedTarget` (Pydantic) | 🔴 Alta — fundação de tudo |
| 2 | **H2 — Recorder** — sessão headed, novo `BrowserContext`, hooks de evento, SSE | 🔴 Alta — maior risco técnico |
| 3 | **H4 — Element Resolver** — inferência de seletor orientada à gravação | 🔴 Alta — desbloqueia H3 |
| 4 | **H3 — Event Normalizer** — eventos brutos → ações semânticas, deduplicação | 🟡 Média |
| 5 | **H5 — YAML Serializer** — `RecordedWorkflow` → `workflow.yaml` compatível | 🟡 Média |
| 6 | **H6 — UI Modo Assistido** — painel Studio, timeline, editor, export | 🟢 Depende de H5 |

> [!TIP]
> H1 + H2 + H4 são o **spike de risco** do épico — devem ser especificadas e implementadas antes de qualquer UI. Uma vez que o Recorder grava e o Serializer exporta um YAML executável (mesmo que em CLI), o restante é iteração.

### Cards de melhoria futura (backlog separado)
- **Continuidade de sessão** — retomar gravação de onde parou após salvar o YAML
- **Sessões múltiplas** — gravação em paralelo para equipes
- **Import de workflow existente** — editar um YAML já criado no modo assistido
