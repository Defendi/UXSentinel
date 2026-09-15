# Especificação Declarativa de Cenários (YAML)

O **UXSentinel** utiliza arquivos **YAML** declarativos para descrever cenários de teste, fluxos de navegação e regras de negócio a serem protegidas contra regressões visuais e funcionais.

---

## 1. Estrutura Canônica de um Cenário

```yaml
version: "1.0"
id: "fluxo_cadastro_cliente"
title: "Cadastro de Novo Cliente e Verificação de Modal"
description: >
  Navega até o módulo de cadastros, abre o modal de criação de parceiro/cliente,
  valida o comportamento visual dos campos obrigatórios e confirma o layout do modal.

# Perfil do framework da aplicação alvo (opcional: 'generic', 'odoo', 'react_spa')
profile: "generic"

# Provedor de IA opcional para o cenário (ex: gemini_sso, claude_sso, ollama_local)
provider: "gemini_sso"

# Controle de visualização e ferramentas de inspeção
headless: false
devtools: false        # 'true' para abrir com o painel DevTools/Console acoplado
video: false           # 'true' para gravar vídeo da sessão
markdown: true         # 'true' para gerar relatório em Markdown para MarkText/Obsidian
archive: true          # 'true' para compactar a análise anterior em .zip antes da nova execução
archive_dir: "scenarios/report/archive" # Diretório opcional para armazenar os zips históricos

# Viewports para auditoria de responsividade (presets ou dimensões LARGURAxALTURA)
viewports:
  - "desktop"
  - "tablet"
  - "mobile"

# Tags para execução seletiva via CLI (--tags smoke,clientes)
tags:
  - "smoke"
  - "clientes"
  - "modais"

# Variáveis do ambiente com fallback para variáveis do sistema operacional
env:
  base_url: "${APP_BASE_URL:-http://localhost:8000}"
  usuario: "${QA_USER:-admin}"
  senha: "${QA_PASSWORD:-admin}"

# Sequência ordenada de passos
steps:
  - action: "goto"
    url: "/login"
    description: "Acessa a página de autenticação"

  - action: "fill"
    selector: "input[name='username'], input#login"
    value: "${usuario}"

  - action: "fill"
    selector: "input[name='password'], input#password"
    value: "${senha}"

  - action: "click"
    selector: "button[type='submit']"
    description: "Submete o login"

  - action: "wait_navigation"
    description: "Aguarda carregamento da dashboard"

  - action: "click"
    selector: "a[href*='/customers'], button#btn-novocliente"
    description: "Clica para abrir novo cliente"

  - action: "wait_modal"
    timeout: 8000
    description: "Aguarda a renderização completa da janela modal"

  # Checkpoint de Auditoria Visual e de Negócio
  - action: "checkpoint"
    name: "modal_novo_cliente"
    description: "Inspeção visual e semântica do modal aberto"
    expected_behavior: >
      O modal de criação de cliente deve estar perfeitamente centralizado na viewport.
      Os campos 'Nome Completo', 'CPF/CNPJ' e 'E-mail' devem estar visíveis e com indicação
      de obrigatoriedade. Os botões 'Salvar' e 'Cancelar' devem estar totalmente visíveis no rodapé.
      Nenhum texto em inglês (como 'Save', 'Close', 'Cancel') deve estar presente.
      Nenhum nome técnico interno de banco de dados (ex: 'snake_case') deve ser exibido.
    criteria:
      - "i18n_pt_br"
      - "no_technical_jargon"
      - "modal_geometry"
      - "business_rules"

  - action: "click"
    selector: "button.btn-cancel, button[data-dismiss='modal']"
    description: "Descarta e fecha o modal"

  - action: "wait_modal_close"
    description: "Verifica se o modal e backdrop desapareceram adequadamente"
```

---

## 2. Dicionário Completo de Ações Suportadas

| Ação | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `goto` | `url` | Navega para URL relativa ou absoluta. |
| `click` | `selector`, `timeout` | Clica em um elemento com feedback visual na tela. |
| `fill` | `selector`, `value` | Insere texto diretamente em um campo de formulário (input ou textarea). |
| `type` / `digitar` | `selector`, `value` | Digita caractere por caractere com ritmo humano (ideal para inputs com máscaras como CPF, telefone, CEP ou autocompletes). |
| `clear` / `limpar` | `selector` | Limpa o conteúdo preenchido em um campo de formulário. |
| `select` / `dropdown` | `selector`, `value` | Seleciona item em `<select>` nativo ou em dropdowns customizados de frameworks (Bootstrap, Odoo OWL, React, Tailwind, Shadcn). |
| `assert_required` | `selector` ou `criteria` | Valida deterministicamente se o campo está marcado como obrigatório (atributo `required`, `aria-required="true"`, classe `.required` ou asterisco `*` no label). |
| `assert_invalid` | `selector` | Confirma se o campo está em estado de erro/invalidação (`:invalid`, `aria-invalid="true"`, `.is-invalid` ou mensagem de erro visível). |
| `check` | `selector` | Marca checkbox ou radio button. |
| `press` | `key` | Dispara tecla do teclado (ex: `Enter`, `Escape`, `Tab`). |
| `hover` | `selector` | Passa o mouse sobre o elemento (útil para tooltips e menus suspensos). |
| `scroll` | `direction` (`up`/`down`), `amount` | Executa rolagem na tela ou em container específico. |
| `wait_selector` | `selector`, `timeout` | Aguarda um seletor ficar visível no DOM. |
| `wait_navigation` | `timeout` | Aguarda que a rede e a página assentem após navegação. |
| `wait_modal` | `timeout` | Aguarda que uma janela modal ou diálogo termine de abrir. |
| `wait_modal_close` | `timeout` | Confirma o fechamento completo do modal e remoção do backdrop. |
| `pause` | `duration` (segundos) | Pausa programada para permitir acompanhamento visual ao vivo. |
| `checkpoint` | `name`, `expected_behavior`, `criteria` | Congela o estado, captura evidências e dispara auditoria da IA. |
| `ai_click` | `target`, `timeout` | Clique inteligente resolvido em linguagem natural via acessibilidade e visão computacional (ex: `"botão azul de salvar"`). |
| `ai_fill` | `target`, `value` | Localiza o campo em linguagem natural e preenche o valor indicado. |
| `ai_assert` | `assertion` | Asserção declarativa cognitiva avaliada diretamente pelo modelo de visão multimodal. |
| `ai_action` | `instruction` | Executa ação autônoma em linguagem natural guiada por raciocínio multimodal. |

---

## 3. Filosofia dos Checkpoints

O `checkpoint` não é uma asserção rígida de igualdade de texto (*string matching*). Ele é uma **instrução cognitiva para a IA Multimodal**:
- A IA analisa a imagem renderizada com os olhos de um usuário experiente.
- Ela lê o que você declarou em `expected_behavior` como o gabarito de conformidade da sua empresa.
- Caso a tela viole alguma regra (ex: um campo não coube, um texto em inglês apareceu, o botão sumiu na rolagem), ela emite uma `Issue` detalhada com severidade, localização e print anotado.

---

## 4. Resolução e Execução de Cenários na CLI

O UXSentinel implementa um mecanismo determinístico de resolução de arquivos de cenário para garantir previsibilidade nas esteiras de automação e na linha de comando:

1. **Passagem Explícita de Cenário**:
   - Por flag: `uxsentinel -s scenarios/meu_fluxo.yaml`
   - Por argumento posicional: `uxsentinel scenarios/meu_fluxo.yaml`
2. **Execução Sem Informar Cenário (`uxsentinel`)**:
   - O agente busca automaticamente a pasta `./scenarios/` no diretório atual de trabalho.
   - ❌ **Pasta inexistente ou vazia**: Retorna erro claro (`FileNotFoundError`) informando que nenhum cenário foi passado e a pasta `scenarios/` não foi localizada.
   - ❌ **Múltiplos cenários detectados na pasta**: Retorna erro (`ValueError`) alertando que existem múltiplos cenários disponíveis e que o parâmetro `-s` / `--scenario` é obrigatório para evitar ambiguidades.
   - ✅ **Exatamente 1 cenário presente**: Executa automaticamente o único cenário sem necessidade de parâmetros adicionais.
3. **Listagem de Cenários**:
   - Execute `uxsentinel --list-scenarios` para visualizar todos os cenários disponíveis no projeto local e na biblioteca interna integrada.

---

## 5. Cláusula Declarativa de Exceções (`exceptions` / `excecoes`)

O **UXSentinel** permite homologar regras de tolerância e exceções diretamente no arquivo de cenário YAML. Isso impede que a IA reporte falsos positivos em elementos conhecidos ou marcas permitidas e possibilita suspender temporariamente testes em botões ou trechos da interface.

### 5.1 Formato Estruturado (Completo)

Você pode declarar o bloco `exceptions:` (ou `excecoes:`) na raiz do cenário:

```yaml
version: "1.0"
id: "auditoria_painel"
title: "Auditoria com Exceções Homologadas"

# Cláusula de Exceções do Cenário
exceptions:
  # Frases e marcas em inglês ou jargões autorizados (não reportar como erro de i18n ou vazamento)
  allowed_texts:
    - "By Gotryx"
    - "Powered by"
    - "Copyright 2026"
    - "All rights reserved"

  # Seletores CSS de elementos a serem ignorados nas auditorias de layout/acessibilidade
  ignored_selectors:
    - "#btn-feedback-experimental"
    - "button.badge-legado"

  # Nomes ou textos de elementos a desconsiderar
  ignored_elements:
    - "o botão x"
    - "banner de cookies"

  # Categorias de inconsistências a serem toleradas/desconsideradas
  ignored_categories:
    - "cosmetico"

  # Diretrizes livres em linguagem natural para o Mixture of Evaluators e Devil's Advocate
  custom_rules:
    - "Manter a frase 'By Gotryx' no rodapé sem apontar inconformidade de idioma"
    - "Não testar nem reportar inconsistências no botão experimental do canto inferior direito"

steps:
  # 1. Pular um passo específico temporariamente (skip: true ou ignore: true)
  - action: "click"
    selector: "#btn-feedback-experimental"
    skip: true
    description: "Não testar o botão x neste ciclo"

  # 2. Checkpoint com herança das exceções globais e suporte a exceções específicas locais
  - action: "checkpoint"
    name: "visao_geral"
    expected_behavior: "Tela principal renderizada sem erros visuais."
    exceptions:
      allowed_texts:
        - "Status: Beta"
```

### 5.2 Formato Sintético (Lista Direta)

Para cenários rápidos, você também pode declarar a cláusula como uma lista direta de regras ou termos entre aspas:

```yaml
exceptions:
  - '"By Gotryx"'
  - "#btn-x"
  - "Não testar o botão x e manter frase 'Powered by'"
```
O parser inteligente do UXSentinel extrai automaticamente os seletores iniciados em `#` ou `.`, textos entre aspas para a lista de termos autorizados e regras completas para o prompt dos avaliadores cognitivos.

