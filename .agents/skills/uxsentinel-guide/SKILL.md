---
name: uxsentinel-guide
description: Espelho compacto do roteiro operacional canônico do UXSentinel.
---

# UXSentinel — espelho operacional

> Fonte canônica: [`.agents/skills/uxsentinel-guide/SKILL.md`](../../../.agents/skills/uxsentinel-guide/SKILL.md). Em caso de divergência, a fonte canônica prevalece. Esta cópia existe para clientes que não carregam a referência.

## Essencial

- O UXSentinel audita QA visual, UX e regras de negócio em aplicações web, com perfil `generic` e perfis adaptativos; clientes externos são apenas alvos.
- `core` orquestra; `scenarios` controla YAML; `browser` executa Playwright; `vision` analisa imagens sem conhecer Playwright; `reporter` apenas apresenta. Studio e integrações permanecem periféricos.
- Leia [`AGENTS.md`](../../../AGENTS.md) antes de agir. Alterações seguem Especificação → Implementação → Testes → Publicação → Finalização, sem pular autorizações.
- Use Português do Brasil, menor privilégio, escopo mínimo, sem segredos e com testes herméticos, rápidos e determinísticos.
- O contrato YAML está em [docs/04](../../../docs/04_especificacao_cenarios_yaml.md); não duplique o dicionário de ações.

## Fase 3

Após autorização expressa, execute da raiz:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests studio/tests -v
```

Relate falhas, erros e ignorados; não afirme cobertura sem ferramenta autorizada. Consulte o [checklist canônico](../../../.agents/skills/uxsentinel-qa-tester/SKILL.md).

## Referências

- [Arquitetura](../../../docs/01_visao_e_arquitetura.md)
- [Heurísticas](../../../docs/02_heuristicas_de_inspecao.md)
- [Navegação e visão](../../../docs/03_agente_navegador_e_visao.md)
- [Provedores](../../../docs/05_configuracao_llm_e_provedores.md)
- [Perfis](../../../docs/06_plugins_e_perfis_frameworks.md)
- [Publicação](../../../docs/07_guia_de_publicacao_e_releases.md)

Publicação é fase separada: exige suíte completa, qualidade aprovada e autorização explícita. Nenhuma operação Git ou de publicação pode ser inferida de uma autorização de implementação.
