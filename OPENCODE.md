# Adaptador OpenCode

Siga e obedeça estritamente ao [`AGENTS.md`](./AGENTS.md) na raiz do repositório, que é a fonte única da verdade para a governança, arquitetura e processos do UXSentinel.

## ⚠️ PROTOCOLO MANDATÓRIO DE ABERTURA DE SESSÃO (PASSO ZERO INEGOCIÁVEL)

Ao iniciar qualquer sessão ou receber qualquer demanda envolvendo cards, alterações ou código:

1. **Validação de Conexão MCP Atlassian:** Validar a conexão e autenticação com o MCP do Atlassian imediatamente (`atlassianUserInfo` ou `getAccessibleAtlassianResources`). Se falhar, interrompa o fluxo e avise o usuário.
2. **Leitura Ativa Mandatória de Governança:** Carregar ativamente via ferramenta de leitura os arquivos [`AGENTS.md`](./AGENTS.md) e [`.agents/rules/jira-card-lifecycle.md`](./.agents/rules/jira-card-lifecycle.md) antes de qualquer ação.
3. **Gate Estrito de Papéis (Orquestrador vs. Subagentes):**
   - O **agente principal atua EXCLUSIVAMENTE como coordenador**, despachante de subagentes e gestor de status e comentários no Jira.
   - O agente principal é **ESTRITAMENTE PROIBIDO de inspecionar código para desenvolver ou implementar alterações diretamente**.
   - Toda e qualquer implementação e testes unitários **DEVEM ser delegados imediatamente ao subagente `uxsentinel-python-senior`**.
   - Todo Code Review **DEVE ser delegado ao subagente `uxsentinel-review-agent`**.
   - Toda etapa de Qualidade e Testes Herméticos **DEVE ser delegada ao subagente `uxsentinel-qa-tester`**.
4. **Fluxo Contínuo como um Relógio:** O ciclo opera de ponta a ponta sem interrupções artificiais ou solicitações manuais de permissão, atualizando o card do Jira com comentários detalhados a cada transição de fase conforme o ciclo oficial.

- **Governança Canônica**: Toda diretriz de escopo, fluxo de execução contínuo, convenções técnicas e hermeticidade reside em [`AGENTS.md`](./AGENTS.md).
- **Skills sob Demanda**: Carregue a skill oficial [`.agents/skills/uxsentinel-guide/SKILL.md`](./.agents/skills/uxsentinel-guide/SKILL.md) apenas quando a tarefa exigir seus detalhes operacionais.
- **Precedência**: Não duplique, reinterprete nem crie regras divergentes neste arquivo. Em qualquer caso de ambiguidade ou conflito, [`AGENTS.md`](./AGENTS.md) prevalece absolutamente.
