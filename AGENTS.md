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

- **Auditoria somente leitura:** inspeção, análise ou revisão sem alteração de arquivos, cards, versões ou infraestrutura. Não exige card, implementação ou aprovação das fases; deve apenas relatar evidências e recomendações.
- **Alteração:** qualquer mudança em código, testes, Studio, documentação, configuração ou harness. Mesmo uma alteração pequena passa por todos os gates aplicáveis.
- **Release:** alteração de versão, tag, commit de publicação, GitHub ou PyPI. É uma etapa separada e nunca pode ser inferida de uma autorização de implementação.
- Uma auditoria somente leitura que resulte em mudança proposta continua sendo uma tarefa de alteração quando for executada.

## 3. Gates de aprovação

Toda alteração deve seguir esta ordem, sem avançar por omissão:

1. **Especificação:** registrar o objetivo, comportamento, restrições e critérios de aceitação no card do Jira do UXS; auditorias somente leitura são a exceção.
2. **Implementação:** aguardar aprovação explícita da especificação e executar a mudança aprovada por subagente especializado.
3. **Testes:** aguardar autorização para testar; executar a suíte completa, verificações de qualidade e todos os testes herméticos aplicáveis.
4. **Publicação:** aguardar autorização expressa após apresentar os resultados; somente então versionar, criar tag, publicar ou acionar o PyPI.
5. **Finalização:** aguardar autorização após a publicação para atualizar documentação, manual aplicável, Jira e estado final do trabalho.

- A aprovação deve ser explícita e por escrito; a falta de resposta não constitute autorização.
- Antes de iniciar qualquer tarefa, valide a conexão e a autenticação do MCP do Atlassian; se falhar, bloqueie o fluxo e avise o usuário.
- O fluxo pode ser adaptado ou excepcionado somente quando o usuário pedir explicitamente uma mudança de política.

## 4. Subagentes e implementação

- O agente principal coordena; implementações de código e mudanças técnicas devem ser delegadas a subagentes especializados.
- O subagente deve seguir a especificação aprovada, a skill oficial e as convenções existentes; não amplie o escopo nem invente dependências.
- Toda mudança relevante deve incluir cobertura de testes aplicável; mudanças de CLI/YAML/Studio devem manter a paridade entre esses componentes e atualizar o manual oficial conforme a documentação quando houver interface.
- A skill [uxsentinel-qa-tester](.agents/skills/uxsentinel-qa-tester/SKILL.md) define a execução de qualidade e hermeticidade quando essa etapa for autorizada.

## 5. Hermeticidade e segurança

- Testes devem ser rápidos, determinísticos e 100% herméticos: sem rede externa real, produção, credenciais reais ou dados sensíveis.
- Nunca comite, registre ou exponha segredos, tokens, chaves, `.env` ou configurações locais de agentes.
- Preserve `.claude/`, `.gemini/`, `.superpowers/`, worktrees, caches e artefatos locais fora do versionamento, salvo uma exceção canônica explícita.
- Use o menor privilégio necessário e confirme o destino de operações destrutivas, remotas ou irreversíveis antes de executá-las.

## 6. Release e manutenção

- Não altere versões, crie tags, publique releases, faça push de publicação ou dispare PyPI de forma autônoma.
- A versão só pode ser alterada depois da suíte completa, das verificações de qualidade e da autorização humana explícita.
- Após essa autorização, siga o fluxo único de bump, commit semântico, tag, push, release e pipeline definido na [skill oficial](.agents/skills/uxsentinel-guide/SKILL.md) e no [guia de releases](docs/07_guia_de_publicacao_e_releases.md).
- Uma tarefa de reorganização do harness não autoriza bump, commit, tag, release ou publicação.

## 7. Precedência das fontes

1. `AGENTS.md` é a política canônica deste repositório.
2. A skill oficial é a referência operacional detalhada e deve ser carregada apenas sob demanda.
3. `CLAUDE.md` e `GEMINI.md` são adaptadores mínimos que remetem a este arquivo, sem criar regras próprias.
4. A documentação técnica explica domínios e processos, mas não substitui esta governança.
5. Uma instrução explícita do usuário pode mudar a política somente para a tarefa e somente quando isso for declarado; as proteções de segurança e os gates não são presumidos removidos.
6. Em caso de conflito entre adaptadores, skills ou referências, prevalece `AGENTS.md`; nunca mantenha uma cópia divergente da política.
