---
prd_number: "001"
status: rascunho
priority: alta
created: 2026-10-01
issue: "UXS-91"
depends_on: []
references:
  - "docs/2026-10-01-uxs91-modo-assistido-design.md"
  - "docs/uxs91_modo_assistido_planejamento.md"
  - "https://mygotryx.atlassian.net/browse/UXS-91"
---

# PRD 001: Modo Assistido de Criação de Cenários de Teste

## 1. Contexto

- **Produto/área:** UXSentinel — criação de cenários de QA automatizado.
- **Estado atual:** Para criar um cenário de teste, o usuário precisa escrever manualmente um arquivo YAML descrevendo cada passo: URL de acesso, seletores de elementos, ações (fill, click, assert), checkpoints e validações. Isso exige conhecimento da estrutura YAML do UXSentinel, dos comandos disponíveis e de como identificar elementos da interface (seletores CSS, XPath, roles ARIA).
- **Problema:** A barreira técnica do YAML exclui do processo qualquer pessoa que conheça o processo de negócio mas não domine Playwright ou automação de testes. Analistas de negócio, QAs funcionais e product owners não conseguem criar cenários sem depender de um desenvolvedor — o que cria gargalo, aumenta o tempo entre identificação do processo e criação do teste, e reduz a cobertura de cenários de negócio da ferramenta.

## 2. Solução Proposta

### Visão de produto

- O usuário navega pela aplicação alvo como faria normalmente, enquanto o UXSentinel Studio captura suas interações em tempo real e as exibe como uma lista de passos legíveis em um painel lateral.
- Ao final da gravação, o sistema gera automaticamente um arquivo `workflow.yaml` compatível com o executor existente — sem que o usuário precise escrever ou editar YAML.
- Durante e após a gravação, o usuário pode revisar, editar, reordenar e remover ações capturadas, além de adicionar validações explícitas.
- Quando uma ação capturada for ambígua, o sistema consulta a IA configurada e apresenta uma sugestão com justificativa para o usuário aceitar ou rejeitar — o comportamento original nunca é alterado silenciosamente.
- O workflow gerado pelo modo assistido é idêntico em formato e comportamento a um workflow criado manualmente, podendo ser executado pelo mesmo agente, sem nenhuma alteração no executor.

### Decisões de produto

1. **Uma sessão de gravação ativa por vez** — evita estado inconsistente e simplifica o controle de sessão; múltiplas sessões simultâneas são melhoria futura.
2. **Fechar o browser encerra e salva a gravação** — o sistema salva o YAML automaticamente ao detectar o fechamento; não há rascunho persistente no MVP, pois isso introduziria estado complexo sem entregar valor imediato ao usuário. A retomada de sessão é melhoria futura.
3. **A IA atua apenas como auxiliar de decisão, não como autor** — o usuário é sempre o autor do workflow; a IA sugere, o usuário decide. Isso garante rastreabilidade e confiança no cenário gerado.
4. **Validações podem ser adicionadas durante e após a gravação** — o usuário não precisa interromper a navegação para adicionar um ponto de validação; pode fazê-lo inline pelo painel ou no editor pós-gravação.
5. **O contrato YAML não muda** — o executor existente não é alterado; o modo assistido é uma entrada alternativa para o mesmo pipeline.

### Fora do escopo

- Retomada de sessão de gravação após fechar o browser *(melhoria futura — backlog)*
- Múltiplas sessões de gravação simultâneas *(melhoria futura — backlog)*
- Importar um workflow YAML existente para edição no modo assistido *(melhoria futura — backlog)*
- Gravação em browsers que não sejam Chromium no MVP *(premissa — confirme ou corrija)*
- Geração automática de dados de teste (valores de campos) pela IA — a IA auxilia na classificação de ações, não na geração de conteúdo de dados *(premissa — confirme ou corrija)*

## 3. Funcionalidades

### US01: Iniciar uma sessão de gravação

Como analista de QA ou de negócio, quero iniciar uma gravação informando o nome do workflow, a URL de entrada e o objetivo do teste, para que o sistema abra a aplicação e comece a capturar minhas interações.

**Rules:**
- O sistema exige no mínimo: nome do workflow e URL de entrada. O objetivo é opcional.
- A URL deve ser acessível pelo navegador do servidor onde o Studio está rodando; o sistema valida o formato antes de iniciar.
- Ao iniciar, o sistema abre um novo contexto de navegador isolado (headed), separado de qualquer execução de cenário em andamento.
- Apenas uma sessão de gravação pode estar ativa por vez; tentativa de iniciar nova sessão enquanto há uma ativa deve exibir mensagem clara indicando que existe uma sessão em andamento e oferecer a opção de encerrá-la.
- O painel lateral do Studio deve indicar visualmente que a gravação está ativa (ex.: indicador vermelho "Gravando").

**Edge cases:**
- URL inválida ou mal-formada → sistema rejeita antes de abrir o browser e exibe mensagem de erro específica.
- URL válida mas inacessível (timeout de rede) → sistema exibe erro após tentativa, sem abrir sessão parcial.
- Tentativa de segunda sessão simultânea → `HTTP 409` + mensagem no Studio indicando a sessão ativa.
- Studio reiniciado enquanto há sessão ativa no processo anterior → sessão anterior é considerada encerrada; estado é destruído no restart. *(premissa — confirme ou corrija)*

---

### US02: Capturar interações durante a gravação

Como analista de QA ou de negócio, quero navegar pela aplicação normalmente enquanto o sistema captura automaticamente minhas interações, para que eu não precise memorizar ou anotar cada passo.

**Rules:**
- O sistema captura, no mínimo, as seguintes ações: clicar em elementos, preencher campos de texto, selecionar opções em dropdowns, navegar para uma URL e submeter formulários.
- Cada ação capturada é imediatamente exibida no painel lateral do Studio como um item da timeline, em linguagem legível (ex.: "Preencher → E-mail → joao@email.com").
- Para cada elemento interagido, o sistema determina automaticamente o seletor mais estável disponível, seguindo a hierarquia: `data-testid` → `role + nome acessível` → `label` → `texto visível` → `CSS` → `XPath`.
- Quando uma ação é ambígua (ex.: eventos DOM que podem representar `fill` ou `hover`), o sistema consulta a IA configurada e exibe a sugestão com justificativa para o usuário aceitar ou rejeitar antes de confirmar o passo. *(premissa: limiar de confiança ≥ 0.85 para sugestão automática; abaixo disso, pede intervenção manual — confirme ou corrija)*
- Se nenhum provedor de IA estiver configurado, ações ambíguas são marcadas para revisão manual, sem bloquear a gravação.
- Screenshots da tela podem ser associados às ações capturadas quando disponíveis.

**Edge cases:**
- Elemento sem nenhum seletor identificável (DOM corrompido ou iframe cross-origin) → ação é marcada para revisão manual com indicação do problema; gravação não é interrompida.
- IA consultada mas indisponível (timeout ou erro) → ação ambígua vai para revisão manual; nenhuma sugestão é apresentada; gravação continua.
- Usuário navega muito rapidamente, gerando burst de eventos → sistema agrupa e deduplica eventos antes de exibir; nenhum passo duplicado deve aparecer na timeline. *(premissa — confirme ou corrija)*
- Ação sobre elemento em iframe → *(premissa: captura de interações em iframes não é suportada no MVP; elemento é marcado para revisão manual — confirme ou corrija)*

---

### US03: Controlar a sessão durante a gravação

Como analista de QA ou de negócio, quero pausar, retomar e encerrar a gravação a qualquer momento, para ter controle sobre o que é capturado.

**Rules:**
- Pausar a gravação suspende a captura de eventos; o navegador permanece aberto e o usuário pode continuar interagindo com a aplicação sem gerar passos no workflow.
- Retomar a gravação reinicia a captura a partir do estado atual da página.
- Encerrar a gravação pelo Studio ou fechar o browser dispara o mesmo fluxo: o sistema serializa os passos confirmados para `workflow.yaml`, valida o arquivo gerado e encerra a sessão.
- O status da sessão (gravando / pausada / encerrando) deve ser visível no painel lateral em tempo real.
- Após encerrar, o Studio exibe o caminho do arquivo salvo e oferece atalho para abrir o cenário no editor.

**Edge cases:**
- Usuário fecha o browser sem encerrar pelo Studio → evento de fechamento do browser dispara o fluxo de encerramento automático; YAML é salvo e sessão é destruída.
- Encerramento com zero passos confirmados → sistema avisa que nenhum passo foi capturado e pergunta se deseja salvar um arquivo vazio ou descartar. *(premissa — confirme ou corrija)*
- Falha ao salvar o YAML (ex.: disco cheio, permissão negada) → sistema exibe erro detalhado; sessão não é destruída, permitindo nova tentativa de export.
- Pausa seguida de navegação a URL diferente → ao retomar, a URL atual é registrada como passo de navegação para manter a reprodutibilidade. *(premissa — confirme ou corrija)*

---

### US04: Revisar e editar ações capturadas

Como analista de QA ou de negócio, quero editar, remover e reordenar as ações capturadas no painel lateral, para corrigir capturas erradas ou adicionar contexto antes de salvar o workflow.

**Rules:**
- O usuário pode editar qualquer campo de uma ação capturada: tipo de ação, seletor, valor e descrição.
- O usuário pode remover qualquer ação da timeline.
- O usuário pode reordenar ações por arrastar-e-soltar ou por controles de mover para cima/baixo. *(premissa — confirme ou corrija a forma de interação)*
- Edições e remoções são aplicadas imediatamente ao modelo interno; não afetam o estado do navegador.
- Ações sugeridas pela IA (status `sugerido`) devem ser visivelmente distintas das ações confirmadas, com botões claros de "Aceitar" e "Rejeitar".
- Ações pendentes de revisão manual devem destacar o motivo (ex.: "seletor não resolvido", "ação ambígua").

**Edge cases:**
- Usuário edita o seletor para um valor que não será encontrado na aplicação → o sistema não valida o seletor em tempo real durante a edição (isso só ocorre no replay); a edição é aceita com aviso de que a validade do seletor é verificada apenas na execução. *(premissa — confirme ou corrija)*
- Usuário remove todos os passos → timeline fica vazia; o export é permitido, mas exibe aviso antes de salvar.
- Usuário tenta salvar com passos em status `pendente de revisão` → sistema exibe alerta listando os passos pendentes e pergunta se deseja salvar assim mesmo ou resolver antes. *(premissa — confirme ou corrija)*

---

### US05: Adicionar validações ao workflow

Como analista de QA ou de negócio, quero adicionar pontos de validação explícitos durante ou após a gravação, para que o agente verifique condições específicas ao reproduzir o teste.

**Rules:**
- O usuário pode adicionar uma validação a qualquer momento: durante a gravação (via botão no painel) ou após encerrar (via editor da timeline).
- Ao adicionar uma validação, o usuário informa em linguagem natural o que deve ser verificado (ex.: "Deve aparecer a mensagem 'Salvo com sucesso'").
- A validação é inserida imediatamente após o passo atual da timeline, como um passo do tipo `assert`.
- O sistema suporta, no mínimo, validações de: texto visível na tela, elemento presente, elemento ausente, URL atual e título da página.
- Quando a IA está disponível, o sistema pode sugerir pontos óbvios de validação após certas ações (ex.: após clicar em "Salvar"), apresentando como sugestão com aceitar/rejeitar. *(premissa — confirme ou corrija se essa sugestão proativa é desejada)*

**Edge cases:**
- Usuário descreve validação ambígua (ex.: "tudo certo") → sistema não aceita; exige descrição objetiva do que deve ser verificado ou qual elemento deve estar visível. *(premissa — confirme ou corrija)*
- Validação adicionada em posição errada na timeline → usuário pode reordenar conforme US04.
- IA sugere validação mas usuário rejeita → passo não é adicionado; comportamento capturado não é alterado.

---

### US06: Exportar o workflow como arquivo YAML

Como analista de QA ou de negócio, quero exportar o workflow gravado como um arquivo `workflow.yaml` que possa ser executado imediatamente pelo agente UXSentinel, sem precisar editar o arquivo manualmente.

**Rules:**
- O arquivo gerado deve ser válido segundo o schema do executor existente (`parser.py`); o sistema valida antes de salvar.
- Somente passos com status `confirmado` ou `sugerido e aceito` são incluídos no arquivo; passos rejeitados e pendentes de revisão não são exportados.
- O nome do arquivo é sugerido automaticamente a partir do nome informado ao criar a sessão, em formato kebab-case. O usuário pode alterar antes de salvar.
- O arquivo é salvo no diretório de cenários do projeto ativo no Studio.
- Após salvar, o workflow aparece imediatamente na lista de cenários do projeto e pode ser executado sem nenhuma etapa adicional.

**Edge cases:**
- YAML gerado não passa na validação do parser → sistema exibe quais passos geraram o erro e não salva; sessão permanece ativa para correção.
- Nome de arquivo informado pelo usuário já existe no projeto → sistema pergunta se deseja sobrescrever ou escolher outro nome. *(premissa — confirme ou corrija)*
- Projeto ativo não tem diretório de cenários configurado → sistema informa e oferece opção de configurar antes de exportar. *(premissa — confirme ou corrija)*
- Workflow exportado executado com sucesso pelo agente → resultado é idêntico ao de um workflow criado manualmente com os mesmos passos.

---

## 4. Fluxo de Negócio

```
Usuário inicia gravação (nome + URL)
         │
         ▼
Sistema abre browser headed e inicia captura
         │
         ▼
Usuário navega pela aplicação
         │
         ├── Ação clara ──────────────────────────────▶ Passo adicionado à timeline (confirmado)
         │                                                        │
         ├── Ação ambígua + IA disponível ──▶ IA consultada      │
         │         └── confiança alta ──▶ Sugestão (aceitar/rejeitar)  │
         │         └── confiança baixa ──▶ Pendente de revisão   │
         │                                                        │
         ├── Ação ambígua + IA indisponível ──────────▶ Pendente de revisão
         │                                                        │
         ├── Usuário adiciona validação manual ────────▶ Passo assert inserido
         │                                                        │
         └── Usuário pausa/retoma ─────────────────────▶ Captura suspensa/retomada
         │
         ▼
Usuário encerra gravação (ou fecha browser)
         │
         ▼
Usuário revisa e edita timeline (opcional)
         │
         ▼
Exportar → validação do YAML
         │
         ├── válido ──▶ Arquivo salvo no projeto ──▶ Disponível para execução
         └── inválido ──▶ Erro exibido; sessão mantida para correção
```

## 5. Critérios de Aceite

### 5a. Critérios de aceite da feature

| Critério | Razão de negócio | Como verificar |
|---|---|---|
| Workflow gravado executado pelo agente sem erros | O modo assistido só tem valor se o output for executável | Executar o YAML gerado com o executor existente e verificar que não há erro de parse nem falha de execução causada pelo formato |
| Passo capturado aparece no painel lateral em até 2 segundos após a interação | Acima disso o usuário perde a noção de que a ação foi registrada e refaz, gerando duplicatas | Medir tempo entre evento DOM e exibição do passo no painel via SSE |
| Seletor gerado é do tipo mais estável disponível (`data-testid` > `role` > `label` > `text` > `css` > `xpath`) | Seletores frágeis quebram o workflow em mudanças de frontend, esvaziando o valor do modo assistido | Inspecionar o YAML gerado para uma aplicação com `data-testid` e verificar que o seletor usa `testid`, não CSS |
| Sugestão da IA nunca altera silenciosamente um passo confirmado | Confiança e auditabilidade do workflow pelo usuário não-técnico | Simular sugestão da IA e verificar que o passo só muda após `accept` explícito do usuário |
| Fechar o browser salva o YAML automaticamente | Usuário não perde a gravação por erro de operação | Fechar o browser sem encerrar pelo Studio e verificar arquivo salvo no projeto |
| Workflow gerado é idêntico em formato ao criado manualmente | Garantia de compatibilidade com o executor sem manutenção extra | Comparar o schema do YAML gerado com o do `parser.py` usando o próprio `load_scenario()` |
| Export bloqueado se YAML gerado for inválido | Evitar salvar arquivo quebrado que cause erro silencioso na execução | Forçar um passo inválido e verificar que o sistema bloqueia o export com mensagem de erro específica |

### 5b. Métricas de sucesso

| Métrica | Baseline (fonte) | Meta | Prazo | Mín. aceitável | Responsável |
|---|---|---|---|---|---|
| Tempo médio para criar um cenário básico (5 passos) | A levantar — não há dado atual para criação manual | Reduzir em 60% vs. criação manual medida no baseline | 30 dias após lançamento do MVP | Redução de 40% | Product Owner |
| Taxa de workflows gravados que executam sem erro de formato | 0% (feature inexistente) | 95% dos workflows exportados passam no `load_scenario()` | Desde o lançamento | 90% | QA |
| Taxa de adoção por usuários não-técnicos | 0% (feature inexistente) | 30% dos novos workflows criados via modo assistido em 60 dias | 60 dias após lançamento | 15% | Product Owner |

## 6. Milestones

### Milestone 1: Gravar e Exportar Workflow Básico

**Por que é um marco:** O usuário consegue, pela primeira vez, navegar em uma aplicação e obter um `workflow.yaml` executável sem escrever uma linha de YAML. Este é o valor central da feature e pode ser validado end-to-end.

**Funcionalidades:** US01, US02, US03, US06

**Checklist de aceite** (marcado pelo Aprovador após a implementação):
- [ ] Sessão de gravação inicia, captura ações básicas (click, fill, navigate) e encerra
- [ ] Browser fechado pelo usuário salva o YAML automaticamente
- [ ] YAML exportado passa no `load_scenario()` sem erros
- [ ] Workflow gerado pode ser executado pelo agente e reproduz o fluxo gravado
- [ ] Passo capturado aparece no painel em até 2 segundos

**Aprovador:** Product Owner

---

### Milestone 2: Editar, Validar e Refinar o Workflow

**Por que é um marco:** O usuário passa a ter controle editorial completo sobre o que foi capturado — pode corrigir erros de captura, adicionar validações e entregar um cenário auditado, não apenas gravado.

**Funcionalidades:** US04, US05

**Checklist de aceite** (marcado pelo Aprovador após a implementação):
- [ ] Usuário edita, remove e reordena passos no painel
- [ ] Usuário adiciona validação durante a gravação e ela aparece como passo `assert` no YAML
- [ ] Usuário adiciona validação após encerrar a gravação
- [ ] Passos com status `pendente de revisão` são destacados visualmente
- [ ] Export bloqueado com aviso quando há passos pendentes de revisão

**Aprovador:** Product Owner

---

### Milestone 3: Assistência da IA para Decisões Ambíguas

**Por que é um marco:** O sistema passa a agir como co-autor inteligente — identificando ambiguidades que o usuário não perceberia e sugerindo a interpretação mais adequada com justificativa. Isso aumenta a qualidade dos workflows sem aumentar a carga cognitiva do usuário.

**Funcionalidades:** US02 (fluxo de IA), US05 (sugestão proativa de validação)

**Checklist de aceite** (marcado pelo Aprovador após a implementação):
- [ ] Ação ambígua gera sugestão da IA com justificativa visível no painel
- [ ] Sugestão com confiança alta aparece como draft (aceitar/rejeitar)
- [ ] Sugestão com confiança baixa exige intervenção manual
- [ ] Sem IA configurada, ações ambíguas vão para revisão manual sem erro
- [ ] Sugestão da IA nunca altera passo confirmado sem aceite explícito

**Aprovador:** Product Owner

---

## 7. Riscos e Dependências

| Risco | Impacto | Mitigação | Status |
|---|---|---|---|
| Normalização de eventos DOM gera passos duplicados ou perde ações relevantes | Alto — workflow gerado não reproduz o fluxo real | Validar com aplicações reais em múltiplos cenários; testes herméticos de normalização | Pendente |
| Seletores gerados são frágeis para aplicações sem `data-testid` ou ARIA | Médio — workflow quebra em mudanças mínimas de frontend | Hierarquia de fallback com múltiplos candidatos; usuário pode editar o seletor manualmente | Pendente |
| Usuário não-técnico não entende os status de passo (confirmado / sugerido / pendente) | Médio — baixa adoção por causa de confusão de UI | UX clara com labels, cores e tooltips explicativos; testes de usabilidade com usuários reais | Pendente |
| IA indisponível impacta a experiência para ações ambíguas | Baixo — o sistema degrada graciosamente para revisão manual | `RecorderAdvisor` é opcional; comportamento sem IA é validado em testes | Monitorando |

**Dependências:**

| Dependência | Tipo | Status | Impacto se bloqueado |
|---|---|---|---|
| Provedor de IA configurado no UXSentinel (Milestone 3) | Interna | Disponível — configuração existente no produto | Milestone 3 depende de IA configurada; Milestones 1 e 2 são independentes |
| Studio com suporte a SSE (streaming de eventos) | Interna | Disponível — padrão já implementado para execuções | Nenhum impacto — reutilização direta |

## 8. Referências

- [Design Spec UXS-91 — Modo Assistido](docs/2026-10-01-uxs91-modo-assistido-design.md) — especificação técnica completa com arquitetura, modelos de dados e API
- [Análise de Planejamento UXS-91](docs/uxs91_modo_assistido_planejamento.md) — análise inicial do épico com mapeamento de riscos e decisões de escopo
- [UXS-91 no Jira](https://mygotryx.atlassian.net/browse/UXS-91) — épico original com história completa e critérios de aceite
- [Especificação de Cenários YAML](docs/04_especificacao_cenarios_yaml.md) — contrato do executor; o YAML gerado deve ser compatível com este schema

## 9. Registro de Decisões

- **2026-10-01:** Uma sessão de gravação ativa por vez. Motivo: simplifica o controle de estado no MVP; múltiplas sessões são melhoria futura com valor de caso de uso ainda não validado.
- **2026-10-01:** Fechar o browser encerra e salva automaticamente, sem rascunho persistente. Motivo: rascunho persistente exige reconciliação de estado entre sessões, com custo de implementação alto e valor não validado para o MVP.
- **2026-10-01:** IA atua somente como auxiliar de decisão com aceite explícito do usuário. Motivo: confiança e auditabilidade são críticas para usuários não-técnicos que precisam entender e aprovar o que o agente vai executar.
- **2026-10-01:** Validações podem ser adicionadas durante e após a gravação. Motivo: fluxos reais de teste têm pontos de validação que o usuário identifica naturalmente durante a navegação, sem precisar planejar com antecedência.
- **2026-10-01:** O contrato YAML não muda; o executor existente não é alterado. Motivo: isola o risco da nova feature e garante compatibilidade total com workflows existentes.
