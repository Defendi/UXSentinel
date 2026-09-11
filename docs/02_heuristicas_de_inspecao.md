# Heurísticas Universais de Inspeção de QA e UX

O **UXSentinel** utiliza um conjunto abrangente de heurísticas cognitivas de inspeção visual, aplicáveis a qualquer interface gráfica web (SaaS, e-commerces, CRMs, ERPs como Odoo, painéis administrativos e portais de autoatendimento).

---

## 1. As 5 Dimensões de Auditoria Visual

### 1.1 Internacionalização e Localização (i18n / L10n)
Identifica discrepâncias linguísticas que quebram a imersão do usuário:
- **Textos Não Traduzidos**: Termos em inglês (ou outro idioma de origem da biblioteca/framework) em interfaces voltadas ao público brasileiro (ex: botões *"Submit"*, *"Save"*, *"Discard"*, *"Filter"*, links *"Back to top"*, abas de formulário).
- **Inconsistência de Tradução**: Uso simultâneo de sinônimos conflitantes para o mesmo conceito na mesma tela (ex: em um lugar *"Descartar"* e em outro *"Cancelar"*).
- **Formatação de Dados Locais**: Datas no formato `MM/DD/YYYY` ao invés de `DD/MM/YYYY`, moedas sem símbolo `R$` ou pontuação decimal invertida (vírgula versus ponto).
- **Textos Cortados por Expansão de Idioma**: Quando a tradução em português é mais longa que o termo original e o container trunca o texto sem reticências ou com quebra feia.

### 1.2 Vazamento de Jargões e Termos Técnicos
Garante que a complexidade interna do código não atinja o usuário leigo:
- **Identificadores de Banco de Dados**: Rótulos e colunas exibindo nomes de campos em `snake_case` (ex: `client_tax_id`, `created_at`, `is_active`) ao invés de nomes naturais (*"CPF/CNPJ"*, *"Data de Criação"*, *"Ativo"*).
- **Prefixos de Frameworks e Ferramentas**: Variáveis como `x_studio_...` (Odoo), referências a classes de CSS ou tags React no texto renderizado.
- **IDs Crus e Chaves Estrangeiras**: Exibição de números inteiros de ID de banco sem contexto humano.
- **Stacktraces e Mensagens de Erro Crítico**: Erros de servidor (500, JSON-RPC, GraphQL errors) exibidos diretamente na tela ao invés de mensagens de erro amigáveis e instrucionais.

### 1.3 Geometria e Disposição de Modais e Diálogos (`Overlays`)
Modais, gavetas laterais (*drawers*) e popups são campeões em problemas de usabilidade:
- **Centralização e Viewport**: O modal deve respeitar os limites verticais e horizontais da tela, sem estourar a viewport nem forçar rolagem horizontal.
- **Visibilidade de Ações Principais**: Os botões de confirmação e cancelamento (normalmente localizados no rodapé do modal) devem estar sempre visíveis na primeira renderização, sem exigir que o usuário role para descobrir onde confirmar.
- **Sobreposição e Isolamento de Backdrop**: O fundo escurecido (*backdrop*) deve impedir cliques acidentais em elementos da tela anterior. Não pode haver vazamento de elementos com z-index inadequado atravessando o modal.
- **Fechamento Intuitivo**: Presença clara de botão de fechar (ícone `X`) no canto superior e fechamento funcional por tecla `Esc` ou clique fora.

### 1.4 Aderência a Regras de Negócio e Estados da Aplicação
Avalia se o fluxo atende aos requisitos declarados para a jornada:
- **Indicação de Obrigatoriedade**: Campos obrigatórios devem estar visualmente destacados (asterisco vermelho ou badge) e impedir avanço se estiverem vazios.
- **Feedback Imediato de Validação**: Validação em tempo real (inline) em campos numéricos, e-mails, CPFs e telefones com mensagens explicativas.
- **Barra de Progresso / Estados**: Statusbars (ex: *Rascunho* -> *Em Análise* -> *Aprovado*) devem refletir visualmente a fase atual do registro com contraste claro sobre as fases passadas e futuras.
- **Desabilitação Apropriada**: Botões que dependem de condições prévias devem estar claramente desabilitados (`disabled`), com tooltip explicando o motivo quando o usuário passar o mouse.

### 1.5 Ergonomia Visual e Acessibilidade Básica
- **Contraste de Cores**: Texto legível contra o fundo (conforme padrões WCAG AA).
- **Hierarquia Tipográfica**: Títulos, subtítulos e textos de apoio com distinção clara de tamanho e peso.
- **Alinhamento de Formulários**: Rótulos e campos alinhados de forma consistente, sem quebras irregulares de coluna.

---

## 2. Classificação de Severidade de Defeitos

| Nível de Severidade | Impacto no Usuário | Critério de Decisão |
| :--- | :--- | :--- |
| **🔴 Bloqueante (Critical)** | O usuário não consegue concluir a tarefa principal da tela ou ocorre quebra irreversível da aplicação. | Botão de confirmar cortado ou inacessível; tela branca (*crash*); modal preso sem opção de fechamento; erro 500 exposto. |
| **🟠 Alta (High)** | O usuário consegue contornar, mas há risco de erro de negócio, violação de regra ou grave confusão. | Campo obrigatório não sinalizado que causa falha silenciosa; texto de ação ambíguo ou invertido; campo com valor monetário errado. |
| **🟡 Média (Medium)** | Problema visual ou de linguagem evidente que afeta o profissionalismo e a experiência. | Palavra ou botão em inglês em tela brasileira; nome técnico do banco visível (`snake_case`); modal desalinhado ou com scroll feio. |
| **🟢 Baixa (Low)** | Detalhe cosmético ou oportunidade de melhoria visual leve. | Margem inferior um pouco menor que o padrão; espaçamento sutil entre ícone e texto; sugestão de contraste mais nítido. |
