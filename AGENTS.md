# Governança do UXSentinel

Este arquivo é a fonte única de verdade para agentes, subagentes e desenvolvedores do repositório. As instruções específicas de uma tarefa só podem alterar esta política quando o usuário as declarar expressamente.

## 1. Idioma, escopo e neutralidade

- Toda comunicação, documentação, artefato e mensagem operacional deve estar em Português do Brasil.
- A atuação deste workspace é exclusiva do UXSentinel: arquitetura, código, testes, Studio e evolução do produto.
- Sistemas, aplicações e repositórios externos são apenas alvos circunstanciais de auditoria ou teste; não geram dependências ou regras de negócio.
- O produto é universal e neutro em relação a frameworks e clientes. Não acople o UXSentinel a regras de um projeto específico.
- Não use skills, convenções ou regras de projetos externos para conduzir o trabalho neste repositório.
- Git, auditorias e operações devem permanecer concentrados neste repositório, salvo solicitação expressa em contrário.
- Consulte a [documentação técnica](docs/README.md) e a [skill oficial](.agents/skills/uxsentinel-guide/SKILL.md) para detalhes operacionais; para tarefas técnicas, a skill oficial é obrigatória, mas deve ser carregada sob demanda; não duplique regras aqui.

## 2. Classificação de tarefas

- **Auditoria somente leitura:** inspeção, análise ou revisão sem alteração de arquivos, cards, versões ou infraestrutura. Não exige card nem implementação; deve apenas relatar evidências e recomendações.
- **Alteração:** qualquer mudança em código, testes, Studio, documentação, configuração ou harness. Segue o fluxo contínuo de ponta a ponta.
- **Release:** alteração de versão, tag, commit de publicação, GitHub ou PyPI. É executada de ponta a ponta quando a tarefa for de release.
- Uma auditoria somente leitura que resulte em mudança proposta continua sendo uma tarefa de alteração quando for executada.

## 3. Fluxo de execução contínuo e status no Jira

Toda alteração deve seguir este ciclo de forma autônoma e contínua, de ponta a ponta, sem travas ou pausas para aguardar confirmações manuais intermediárias, acompanhando a evolução dos status no Jira:

1. **Especificação (`A Fazer` / `Backlog`):** registrar objetivo, comportamento, restrições e critérios de aceitação no card do Jira do UXS; auditorias somente leitura são a exceção.
2. **Implementação (`Em Andamento`):** transicionar o card para `Em Andamento` e executar a mudança via subagente especializado (`uxsentinel-python-senior`) com base no escopo e nas convenções existentes. Ao concluir o código, transicionar para `Pronto Para Testar`.
3. **Testes Herméticos (`Testando`):** transicionar o card para `Testando` e executar a suíte completa, verificações de qualidade e todos os testes herméticos aplicáveis via `uxsentinel-qa-tester`. Ao obter 100% de sucesso, transicionar para `Pronto para Review`.
4. **Code Review (`Revisar`):** o subagente especializado em revisão (`uxsentinel-review-agent`) assume o card, transiciona para `Revisar`, executa a etapa mandatória de planejamento com `brainstorming`, analisa qualidade, ausência de sobre-engenharia de IA e conformidade arquitetural, registrando o parecer em comentário. Se aprovado, avança para finalização; se rejeitado, retorna o card para `Em Andamento` com apontamentos.
5. **Finalização (`Concluído`):** realizar o commit semântico da alteração, atualizar a documentação se aplicável e transicionar o card do Jira para `Concluído`.

- Antes de iniciar qualquer tarefa, valide a conexão e a autenticação do MCP do Atlassian; se falhar, bloqueie o fluxo e avise o usuário.
- O fluxo opera de ponta a ponta sem interrupções artificiais ou solicitações de permissão entre etapas para o usuário.
- Cada transição de fase relevante deve manter o card do Jira documentado com comentários resumindo o progresso.

## 4. Subagentes e implementação

- O agente principal coordena; implementações de código são delegadas a `uxsentinel-python-senior` e o code review a `uxsentinel-review-agent`.
- O subagente deve seguir a especificação, a skill oficial e as convenções existentes; não amplie o escopo nem invente dependências.
- Toda mudança relevante deve incluir cobertura de testes aplicável; mudanças de CLI/YAML/Studio devem manter a paridade entre esses componentes e atualizar o manual oficial conforme a documentação quando houver interface.
- A skill [uxsentinel-qa-tester](.agents/skills/uxsentinel-qa-tester/SKILL.md) define a execução de qualidade e hermeticidade realizada durante a etapa de testes.

## 5. Hermeticidade e segurança

- Testes devem ser rápidos, determinísticos e 100% herméticos: sem rede externa real, produção, credenciais reais ou dados sensíveis.
- Nunca comite, registre ou exponha segredos, tokens, chaves, `.env` ou configurações locais de agentes.
- Preserve `.claude/`, `.gemini/`, `.superpowers/`, worktrees, caches e artefatos locais fora do versionamento, salvo uma exceção canônica explícita.
- Use o menor privilégio necessário e confirme o destino de operações destrutivas, remotas ou irreversíveis antes de executá-las.

## 6. Release e manutenção

- Siga o fluxo de bump, commit semântico, tag, push, release e pipeline definido na [skill oficial](.agents/skills/uxsentinel-guide/SKILL.md) e no [guia de releases](docs/07_guia_de_publicacao_e_releases.md) quando a tarefa for de release.
- A alteração de versão deve sempre passar pela suíte completa e verificações de qualidade antes de ser concluída.
- Uma tarefa de reorganização de harness por si só não efetua bump ou release a menos que especificado.

## 7. Precedência das fontes

1. `AGENTS.md` é a política canônica deste repositório.
2. A skill oficial é a referência operacional detalhada e deve ser carregada apenas sob demanda.
3. `CLAUDE.md` e `GEMINI.md` são adaptadores mínimos que remetem a este arquivo, sem criar regras próprias.
4. A documentação técnica explica domínios e processos, mas não substitui esta governança.
5. Uma instrução explícita do usuário pode mudar a política somente para a tarefa e somente quando isso for declarado; as proteções de segurança e os gates não são presumidos removidos.
6. Em caso de conflito entre adaptadores, skills ou referências, prevalece `AGENTS.md`; nunca mantenha uma cópia divergente da política.
