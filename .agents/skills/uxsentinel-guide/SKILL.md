---
name: uxsentinel-guide
description: Índice operacional canônico do UXSentinel para arquitetura, YAML, qualidade, segurança e publicação.
---

# UXSentinel — roteiro operacional

## 1. Identidade e fronteiras

O UXSentinel é um agente universal de QA visual, auditoria de UX e proteção de regras de negócio. Ele combina roteiros YAML determinísticos, exploração autônoma, Playwright com acompanhamento visual e visão multimodal independente do provedor.

Aplicações externas são apenas alvos de auditoria. Regras, convenções e dependências de clientes não pertencem ao produto; o perfil `generic` permanece no núcleo e particularidades ficam em perfis adaptativos.

Fronteiras estáveis:

- `uxsentinel/cli.py`: ponto de composição e interface de linha de comando.
- `uxsentinel/core/`: domínio, modelos, configuração e orquestração.
- `uxsentinel/browser/`: Playwright, sessão, estabilização, marcadores visuais e perfis; não chama `vision` nem `reporter` diretamente.
- `uxsentinel/scenarios/`: contrato, leitura e validação de YAML.
- `uxsentinel/vision/`: análise multimodal de imagens e texto, sem conhecer Playwright.
- `uxsentinel/reporter/`: apresentação de resultados, sem alterar a execução.
- `integrations/`, `crawler/`, `mcp/`, `css/` e `service/`: capacidades periféricas acessadas por interfaces.
- `studio/`: aplicação separada; não deve introduzir dependências ou regras no motor.

O fluxo principal é cenário → orquestrador → navegador → visão → relatório. Consulte a [arquitetura canônica](../../../docs/01_visao_e_arquitetura.md) e os [perfis de framework](../../../docs/06_plugins_e_perfis_frameworks.md) antes de alterar fronteiras.

## 2. Regras de trabalho

1. Leia e aplique a [governança do repositório](../../../AGENTS.md); este roteiro não a substitui.
2. Inspecione o código e as convenções atuais antes de decidir; faça a menor mudança que satisfaça a especificação.
3. Toda alteração começa com especificação no Jira da UXS, salvo exceção explícita, e segue Especificação → Implementação → Testes → Publicação → Finalização. Nenhuma fase avança sem a autorização exigida.
4. Toda comunicação, documentação e interface nova fica em Português do Brasil.
5. Use Python 3.12, `pathlib`, tipagem moderna, Pydantic v2 e Playwright assíncrono conforme o código existente. Não introduza dependências, scripts ou abstrações sem necessidade aprovada.
6. Mantenha o produto universal e os módulos desacoplados. Regras de projeto cliente não entram no UXSentinel.
7. Alterações de CLI ou YAML devem manter a cobertura aplicável no Studio e nos testes.
8. Testes devem ser rápidos, determinísticos e herméticos: sem rede externa real, produção, credenciais reais, dados sensíveis, estado global ou arquivos fora de áreas temporárias.
9. Aplique menor privilégio. Nunca crie, registre ou versione segredos, tokens, `.env`, diretórios locais de agentes, caches, relatórios ou worktrees.
10. Não faça commit, push, tag, release, bump ou publicação sem solicitação explícita; publicação é fase separada.

## 3. Contrato YAML

O contrato canônico é a [especificação de cenários YAML](../../../docs/04_especificacao_cenarios_yaml.md). Use-a como referência para estrutura, ações, checkpoints, exceções, variáveis e perfis; não mantenha cópia local do dicionário.

Cenários de auditoria pertencem a `scenarios/` no projeto-alvo. A biblioteca interna em `uxsentinel/scenarios/library/` guarda apenas linha de base reutilizável. Escreva `expected_behavior` em Português do Brasil e deixe a especificação funcional determinar o resultado esperado.

## 4. Validação da Fase 3

Somente após autorização expressa para testes, execute da raiz exatamente esta tríade:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests studio/tests -v
```

Registre sucesso, falhas, erros e testes ignorados. Não declare percentual de cobertura sem ferramenta configurada e execução autorizada. O checklist completo está em [`uxsentinel-qa-tester`](../uxsentinel-qa-tester/SKILL.md).

## 5. Publicação

Alteração de versão, tag, commit de publicação, release e PyPI exigem suíte completa, qualidade aprovada e nova autorização humana. Uma autorização de implementação ou de harness não autoriza publicação. Siga exclusivamente o [guia de publicação e releases](../../../docs/07_guia_de_publicacao_e_releases.md) e mantenha credenciais apenas em mecanismos seguros.

## 6. Referências canônicas

- [Índice técnico](../../../docs/README.md)
- [Heurísticas de QA e UX](../../../docs/02_heuristicas_de_inspecao.md)
- [Navegação, visão e telemetria](../../../docs/03_agente_navegador_e_visao.md)
- [Configuração de provedores](../../../docs/05_configuracao_llm_e_provedores.md)
