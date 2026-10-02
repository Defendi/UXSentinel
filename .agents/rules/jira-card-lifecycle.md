# Regras de Movimentação e Ciclo de Vida dos Cards no Jira

Este documento define as regras estritas e automáticas de movimentação de status dos cards no Jira do projeto UXSentinel (`UXS`), orientando todos os agentes, subagentes e desenvolvedores.

---

## 1. Mapeamento de Status e Transições

O ciclo de vida de qualquer card obedece rigorosamente à seguinte sequência:

```mermaid
flowchart TD
    Backlog["Backlog\n(Criação / Planejamento)"] -->|Planejamento Finalizado| AFazer["A Fazer\n(Aguardando Dev)"]
    AFazer -->|Início do Dev| EmAndamento["Em Andamento\n(Desenvolvimento e Testes Unitários)"]
    EmAndamento -->|Fim do Dev| ProntoParaReview["Pronto para Review"]
    ProntoParaReview -->|Início do Review| Review["Review\n(Code Reviewer)"]
    Review -->|Com Apontamentos\n(Diversos Comentários)| AFazer
    Review -->|Aprovado 100%\n(Sugestões -> Backlog)| ProntoParaTestar["Pronto Para Testar"]
    ProntoParaTestar -->|Início do QA| Testando["Testando\n(QA Tester)"]
    Testando -->|Com Apontamentos\n(Diversos Comentários)| AFazer
    Testando -->|Aprovado 100%\n(Sugestões -> Backlog)| Concluido["Concluído\n(Commit e Fechamento)"]
```

| Status no Jira         | ID do Status | Transição ID | Responsável                | Condição e Ação                                                            |
|:---------------------- |:------------ |:------------ |:-------------------------- |:-------------------------------------------------------------------------- |
| **Backlog**            | `10096`      | `5`          | Agente / Humano            | Card criado; mantido aqui durante todo o **planejamento/especificação**.   |
| **A Fazer**            | `10046`      | `21`         | Agente / Humano            | Finalização do planejamento sinalizada. Aguarda início do desenvolvimento. |
| **Em Andamento**       | `10048`      | `2`          | `uxsentinel-python-senior` | Início do desenvolvimento sinalizado.                                      |
| **Pronto para Review** | `10097`      | `6`          | `uxsentinel-python-senior` | Toda a implementação e testes unitários concluídos.                        |
| **Review**             | `10098`      | `7`          | `uxsentinel-review-agent`  | Início da revisão de código sinalizado.                                    |
| **Pronto Para Testar** | `10049`      | `3`          | `uxsentinel-review-agent`  | Review aprovado 100%. Sugestões viram novos cards em Backlog.              |
| **Testando**           | `10050`      | `4`          | `uxsentinel-qa-tester`     | Início das atividades de QA sinalizado.                                    |
| **Concluído**          | `10047`      | `41`         | QA / Revisor               | Testes herméticos 100% aprovados. Commit semântico realizado.              |

---

## 2. Regras Operacionais de Movimentação

### 2.1 Criação e Planejamento (`Backlog`)

- Enquanto os agentes criarem um card e esse card estiver sendo planejado, **deve-se manter o card em `Backlog`**.
- Todo o detalhamento de escopo, especificação e critérios de aceite ocorre nesta fase.
- Nenhum agente pode mudar o estado para "A Fazer" nessa fase sem autorização.

### 2.2 Conclusão do Planejamento (`A Fazer`)

- Assim que for sinalizada a **finalização do planejamento** (por definição de um agente ou pelo humano), **deve-se mover o card para `A Fazer`**.
- O card aguarda em `A Fazer` até o momento efetivo de início do desenvolvimento.

### 2.3 Desenvolvimento e Testes Unitários (`Em Andamento` → `Pronto para Review`)

- Assim que for sinalizado o **início do desenvolvimento**, **deve-se mudar o card para `Em Andamento`**.
- O desenvolvedor executa toda a implementação técnica, incluindo preparação de ambiente, código, tipagem defensiva e testes unitários.
- Assim que finalizada toda a implementação, **deve-se mudar o card para `Pronto para Review`**.

### 2.4 Code Review (`Review` → `A Fazer` ou `Pronto Para Testar`)

- Assim que sinalizado o **início do Review** pelo agente (`uxsentinel-review-agent`), **deve-se mudar o card para `Review`** (status `Revisar`).
- O agente executa o planejamento obrigatório via skill `brainstorming` antes da inspeção detalhada.
- **Tratamento de Resultados do Review:**
  - **Se houver qualquer tipo de apontamento:** deve-se anotar ponto a ponto em **diversos comentários** separados no card e mover o card para **`A Fazer`** para recomeçar o processo de desenvolvimento.
  - **Se passar 100% com apenas algumas sugestões:** deve-se mover o card para **`Pronto Para Testar`**. As sugestões apontadas no review **devem ser criadas como novos cards em `Backlog`**.

### 2.5 Testes de QA (`Testando` → `A Fazer` ou `Concluído`)

- Assim que for sinalizado pelo testador QA (`uxsentinel-qa-tester`) o **início da atividade**, **mova o card para `Testando`**.
- O testador executa a tríade hermética completa (`ruff check`, `ruff format --check`, `pytest`).
- **Tratamento de Resultados do QA:**
  - **Se houver qualquer tipo de apontamento / falha:** deve-se anotar ponto a ponto em **diversos comentários** separados no card e mover o card para **`A Fazer`** para recomeçar o processo.
  - **Se passar 100% com apenas algumas sugestões:** move-se o card para **`Concluído`** (com commit semântico realizado). As sugestões apontadas no teste **devem ser criadas como novos cards em `Backlog`**.

---

## 3. Diretrizes de Comentários e Novos Cards

1. **Comentários Pontuais e Diversos:** Em caso de rejeição (seja no Review ou no QA), cada inconsistência ou apontamento deve ser registrado em um comentário individual no card, com contexto exato (arquivo, linha, causa raiz e recomendação).
2. **Desdobramento de Sugestões:** Sugestões e melhorias não bloqueantes nunca atrasam o card em andamento; são convertidas imediatamente em novos cards em `Backlog` com referência ao card de origem.
