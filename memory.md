# UXSentinel — índice de contexto do harness

> Documento de índice não normativo. Serve para localizar contexto útil e decisões estáveis; não substitui o código executável, os testes, a configuração efetiva, as regras do repositório ou a skill oficial. Em caso de divergência, valide o comportamento no código e nos testes.

## Finalidade

O UXSentinel é um agente de QA visual, auditoria de UX, acessibilidade e proteção de regras de negócio para aplicações web. A proposta é universal e neutra em relação ao framework auditado: `generic` é o perfil padrão e `odoo` é um adaptador especializado.

## Decisões arquiteturais estáveis

- A solução é organizada em camadas de entrada, orquestração, navegador, avaliação e geração de artefatos.
- Cenários YAML combinam passos determinísticos e ações semânticas orientadas por intenção.
- Cada checkpoint produz evidência observável da tela e pode combinar DOM, telemetria, acessibilidade, baseline e avaliação visual.
- A configuração segue a precedência: argumento explícito da CLI, campo equivalente no cenário, configuração global do usuário e fallback do código.
- A integração com provedores de visão é abstraída para permitir serviços cloud, locais e gateways, com fallback controlado.
- Testes devem ser herméticos, sem rede real, credenciais de produção ou dependência de sistemas externos.
- Segredos e dados pessoais não devem ser gravados no repositório; integrações externas são opcionais.
- Quando presente, o UXSentinel Studio é um subprojeto separado, sem transformar a interface web em dependência do núcleo do agente.

## Fontes canônicas

| Necessidade | Fonte |
| --- | --- |
| Contexto inicial | [Janela de contexto do projeto](docs/00_contexto_do_projeto.md) |
| Visão e arquitetura | [Visão e arquitetura](docs/01_visao_e_arquitetura.md) |
| Heurísticas e severidades | [Heurísticas de inspeção](docs/02_heuristicas_de_inspecao.md) |
| Navegador, visão e telemetria | [Agente navegador e visão](docs/03_agente_navegador_e_visao.md) |
| Contrato de cenários YAML | [Especificação de cenários](docs/04_especificacao_cenarios_yaml.md) |
| Provedores e configuração de IA | [Configuração de LLMs](docs/05_configuracao_llm_e_provedores.md) |
| Perfis de framework | [Plugins e perfis](docs/06_plugins_e_perfis_frameworks.md) |
| Uso e operação | [README](README.md) |
| Configuração de referência | [Exemplo de configuração](config/config.example.yaml) |
| Metadados e dependências | [pyproject.toml](pyproject.toml) e [uv.lock](uv.lock) |
| Regras operacionais | [AGENTS.md](AGENTS.md) |
| Skill oficial | [`.agents/skills/uxsentinel-guide`](.agents/skills/uxsentinel-guide/SKILL.md) |
| Análise histórica | [Análise da memória compactada](docs/09_analise_memoria_compactada.md) |
| Inventário detalhado, quando necessário | [Estado atual, inventário e riscos](docs/10_estado_atual_inventario_e_riscos.md) |

## Regras de recuperação de contexto

1. Comece por este índice e pela janela de contexto; abra apenas o documento relacionado à tarefa.
2. Para saber o que o produto faz hoje, consulte a implementação correspondente, os testes e a configuração de referência.
3. Use a documentação técnica para entender contratos e intenção; não a transforme em inventário de estado sem verificação.
4. Consulte a skill oficial antes de qualquer trabalho técnico ou operacional.
5. Trate este arquivo e a análise histórica como pistas não normativas; eles não autorizam alterações nem descrevem necessariamente o estado atual.
6. Recupere versões, datas, contagens, estados de tarefas, resultados de validação e artefatos de release diretamente das fontes operacionais no momento da tarefa.
7. Se uma informação não estiver em uma fonte canônica, registre-a como desconhecida em vez de inferi-la.

## Limites de contexto

Este índice não contém caminhos de máquina, URLs absolutas, credenciais, estado volátil nem histórico de releases. Projetos externos são apenas alhos de teste circunstanciais; o foco documental continua sendo o UXSentinel.
