# Janela de contexto do projeto — UXSentinel

> Janela curta para agentes e desenvolvedores. Este resumo orienta a navegação pelo repositório; não é uma fonte normativa nem um inventário do estado atual. Para decidir o comportamento vigente, o código executável, os testes e a configuração de referência têm precedência.

## Objetivo

O UXSentinel é um agente de QA visual, auditoria de UX, acessibilidade e regras de negócio para aplicações web. Ele combina automação Playwright, inspeção do DOM, Axe-Core, telemetria e avaliação visual. O produto permanece neutro em relação ao framework auditado: `generic` é o perfil padrão e `odoo` é um adaptador especializado.

## Arquitetura estável

1. A CLI resolve opções, cenário e configuração efetiva.
2. O núcleo coordena a execução, a matriz de viewports, checkpoints, resiliência e artefatos.
3. A camada de navegador executa ações determinísticas e semânticas por meio dos drivers.
4. Um checkpoint captura evidência, valida o estado observado e pode combinar regras determinísticas com avaliação visual.
5. A camada de relatórios serializa JSON, HTML, Markdown e evidências de mídia; integrações externas são opcionais.
6. O UXSentinel Studio, quando utilizado, é um subprojeto separado da interface de operação do agente.

## Precedência de configuração

Para as opções suportadas pelo agente, a ordem geral é:

1. Override explícito da CLI.
2. Campo equivalente no cenário YAML.
3. Configuração global carregada pelo usuário.
4. Fallback definido no código.

A configuração efetiva deve ser observada em tempo de execução; este documento não registra credenciais, endpoints pessoais ou valores sensíveis.

## Contratos essenciais

- O cenário YAML declara identificação, perfil, ambiente controlado, passos e checkpoints.
- Ações semânticas e checkpoints devem preservar o comportamento esperado, a localização da evidência e as regras de negócio relevantes.
- A avaliação visual pode ser complementada por validações determinísticas de acessibilidade, layout, DOM, baseline e telemetria.
- Severidades são `bloqueante`, `alta`, `media` e `baixa`; relatórios e integrações devem preservar essa classificação.
- Testes do repositório devem ser herméticos e não devem depender de rede real ou credenciais de produção.

## Comandos canônicos

```bash
uv run pytest tests studio/tests -v
uv run ruff check .
uv run ruff format --check .
```

A suíte de testes e os dois comandos do Ruff são gates de qualidade; este contexto apenas os registra e não representa resultados de execução.

## Onde buscar detalhes

- [Visão e arquitetura](01_visao_e_arquitetura.md)
- [Heurísticas e severidades](02_heuristicas_de_inspecao.md)
- [Navegador, visão e telemetria](03_agente_navegador_e_visao.md)
- [Especificação de cenários YAML](04_especificacao_cenarios_yaml.md)
- [Configuração de LLMs e provedores](05_configuracao_llm_e_provedores.md)
- [Plugins e perfis de frameworks](06_plugins_e_perfis_frameworks.md)
- [Exemplo de configuração](../config/config.example.yaml)
- [README](../README.md)
- [Análise histórica da memória](09_analise_memoria_compactada.md)
- [Skill oficial do agente](../.agents/skills/uxsentinel-guide/SKILL.md)

## Regras de recuperação

1. Leia esta janela e somente os documentos necessários à tarefa.
2. Confirme comportamento atual no código, nos testes e na configuração de referência.
3. Não trate roadmap, inventário, análise histórica ou memórias anteriores como estado vigente.
4. Recupere dados mutáveis diretamente das fontes operacionais; não os promova para este resumo.
5. Consulte a skill oficial e as regras do repositório antes de alterar qualquer artefato técnico.
