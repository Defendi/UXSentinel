"""Script para compilação do Manual do Usuário do UXSentinel Studio em formato PDF.

Utiliza Playwright headless com Chromium para renderizar o manual com layout editorial A4.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

MANUAL_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>UXSentinel Studio - Manual de Uso e Padronização da Qualidade</title>
  <style>
    @page {
      size: A4;
      margin: 14mm 14mm 14mm 14mm;
    }

    * {
      box-sizing: border-box;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 9.5pt;
      line-height: 1.45;
      color: #1e293b;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }

    .manual-page {
      page-break-after: always;
      break-after: page;
      height: 269mm; /* Altura exata da área útil A4 com margens */
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
    }

    .manual-page:last-child {
      page-break-after: avoid;
      break-after: avoid;
    }

    .page-content {
      flex: 1;
    }

    /* Cabeçalhos e Títulos */
    .doc-badge {
      display: inline-block;
      background: #eff6ff;
      color: #1d4ed8;
      font-weight: 700;
      font-size: 8pt;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 3px 8px;
      border-radius: 4px;
      margin-bottom: 10px;
      border: 1px solid #bfdbfe;
    }

    h1 {
      font-size: 22pt;
      font-weight: 800;
      color: #0f172a;
      line-height: 1.2;
      margin: 0 0 6px 0;
    }

    .subtitle {
      font-size: 11pt;
      color: #475569;
      margin-bottom: 16px;
      line-height: 1.35;
    }

    h2 {
      font-size: 14pt;
      font-weight: 700;
      color: #0f172a;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 4px;
      margin-top: 14px;
      margin-bottom: 8px;
    }

    h3 {
      font-size: 11pt;
      font-weight: 700;
      color: #1e293b;
      margin-top: 10px;
      margin-bottom: 6px;
    }

    p {
      margin: 0 0 8px 0;
    }

    /* Metadados Capa */
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 14px;
    }

    .meta-item {
      font-size: 8.5pt;
    }

    .meta-label {
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      font-size: 7pt;
      letter-spacing: 0.05em;
      display: block;
      margin-bottom: 2px;
    }

    .meta-value {
      font-weight: 600;
      color: #0f172a;
    }

    /* Callouts / Boxes */
    .callout {
      background: #f0fdf4;
      border-left: 4px solid #16a34a;
      border-radius: 0 6px 6px 0;
      padding: 8px 12px;
      margin: 10px 0;
      font-size: 9pt;
    }

    .callout-title {
      font-weight: 700;
      color: #15803d;
      margin-bottom: 2px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .callout-info {
      background: #eff6ff;
      border-left-color: #2563eb;
    }
    .callout-info .callout-title {
      color: #1d4ed8;
    }

    .callout-warning {
      background: #fffbeb;
      border-left-color: #d97706;
    }
    .callout-warning .callout-title {
      color: #b45309;
    }

    .callout-security {
      background: #faf5ff;
      border-left-color: #9333ea;
    }
    .callout-security .callout-title {
      color: #7e22ce;
    }

    /* Tabelas */
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 8px 0 10px 0;
      font-size: 8.5pt;
    }

    th {
      background: #f1f5f9;
      color: #334155;
      font-weight: 700;
      text-align: left;
      padding: 6px 8px;
      border: 1px solid #cbd5e1;
      font-size: 8pt;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    td {
      padding: 5px 8px;
      border: 1px solid #e2e8f0;
      vertical-align: top;
      line-height: 1.35;
    }

    tr:nth-child(even) td {
      background: #f8fafc;
    }

    /* Badges de Severidade */
    .badge {
      display: inline-block;
      padding: 1px 6px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 7.5pt;
      text-transform: uppercase;
    }

    .badge-blocker { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
    .badge-high { background: #ffedd5; color: #9a3412; border: 1px solid #fed7aa; }
    .badge-medium { background: #fef9c3; color: #854d0e; border: 1px solid #fef08a; }
    .badge-low { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }

    /* Diagramas ASCII / Wireframes */
    .ascii-box {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
      font-size: 7pt;
      background: #0f172a;
      color: #38bdf8;
      padding: 8px 10px;
      border-radius: 6px;
      white-space: pre;
      line-height: 1.25;
      margin: 8px 0;
      overflow-x: hidden;
    }

    /* Passos numerados */
    .steps-container {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 8px 0;
    }

    .step-card {
      display: flex;
      gap: 10px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 8px 10px;
    }

    .step-number {
      flex-shrink: 0;
      width: 24px;
      height: 24px;
      background: #2563eb;
      color: #ffffff;
      font-weight: 800;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 9.5pt;
    }

    .step-body {
      flex: 1;
    }

    .step-title {
      font-weight: 700;
      color: #0f172a;
      font-size: 9.5pt;
      margin-bottom: 2px;
    }

    .step-desc {
      font-size: 8.5pt;
      color: #334155;
      margin: 0;
      line-height: 1.35;
    }

    /* Termômetro de Qualidade */
    .score-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin: 10px 0;
    }

    .score-card {
      border-radius: 6px;
      padding: 8px;
      text-align: center;
      border: 1px solid #e2e8f0;
    }

    .score-excelente { background: #f0fdf4; border-color: #86efac; color: #166534; }
    .score-bom { background: #eff6ff; border-color: #93c5fd; color: #1e40af; }
    .score-atencao { background: #fffbeb; border-color: #fde047; color: #854d0e; }
    .score-critico { background: #fef2f2; border-color: #fca5a5; color: #991b1b; }

    .score-range { font-size: 12pt; font-weight: 800; }
    .score-label { font-size: 8pt; font-weight: 700; text-transform: uppercase; margin: 2px 0; }
    .score-detail { font-size: 7.5pt; line-height: 1.25; }

    /* Rodapé e Numeração */
    .doc-footer {
      font-size: 7.5pt;
      color: #64748b;
      border-top: 1px solid #e2e8f0;
      padding-top: 6px;
      display: flex;
      justify-content: space-between;
    }

    code {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
      font-size: 8pt;
      background: #f1f5f9;
      color: #0f172a;
      padding: 1px 4px;
      border-radius: 4px;
      border: 1px solid #e2e8f0;
    }

    .pill {
      display: inline-block;
      background: #e0f2fe;
      color: #0369a1;
      padding: 1px 5px;
      border-radius: 4px;
      font-size: 7.5pt;
      font-weight: 600;
    }

    ul {
      margin: 4px 0 8px 18px;
      padding: 0;
    }

    li {
      margin-bottom: 4px;
    }
  </style>
</head>
<body>

  <!-- PÁGINA 1: CAPA E IDENTIFICAÇÃO -->
  <div class="manual-page">
    <div class="page-content">
      <div class="doc-badge">🛡️ Documento Oficial de Padronização e Qualidade</div>
      <h1>Manual de Uso do<br>UXSentinel Studio</h1>
      <div class="subtitle">Guia prático, acessível e desmistificado para controle de qualidade visual, testes automatizados e auditoria de experiência do usuário com inteligência artificial.</div>

      <div class="meta-grid">
        <div class="meta-item">
          <span class="meta-label">Produto</span>
          <span class="meta-value">UXSentinel Studio</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Versão Homologada</span>
          <span class="meta-value">0.1.8 (Core CLI 1.1.9)</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Público-Alvo</span>
          <span class="meta-value">Analistas de QA, Designers, Devs e Gestores</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Finalidade</span>
          <span class="meta-value">Padronização da Qualidade de Software</span>
        </div>
      </div>

      <div class="callout callout-info">
        <div class="callout-title">ℹ️ Licença e Governança</div>
        O <strong>UXSentinel</strong> é um projeto de código aberto, universal, neutro e independente de frameworks, distribuído sob licença MIT. Seu propósito é garantir a conformidade estética, funcional e de acessibilidade de produtos digitais sem demandar infraestruturas complexas.
      </div>

      <h2>1. Visão Geral e Propósito</h2>
      <p>O <strong>UXSentinel Studio</strong> é um ambiente visual e interativo desenvolvido para simplificar radicalmente a auditoria de interfaces web. Ele atua como um <em>"Auditor de Qualidade Digital"</em> incansável: abre as telas do seu sistema automaticamente, fotografa cada etapa, inspeciona se há elementos quebrados, textos em outro idioma, contrastes ilegíveis ou botões fora do lugar, e entrega relatórios detalhados com notas de saúde de 0 a 100.</p>

      <div class="callout">
        <div class="callout-title">💡 Para que serve na prática?</div>
        Imagine que um programador alterou uma cor ou mudou um formulário. Sem o Studio, uma pessoa teria que entrar no site, clicar em dezenas de botões no computador e no celular para ver se algo quebrou. Com o UXSentinel Studio, você apenas clica em <strong>"Executar"</strong> e ele faz essa checagem completa em segundos!
      </div>

      <h3>Os Três Pilares da Padronização da Qualidade</h3>
      <ul>
        <li><strong>Rigor Visual e Matemático:</strong> Medição precisa de pixels, distorções, tamanhos de fontes e conformidade internacional de acessibilidade (WCAG 2.2).</li>
        <li><strong>Inteligência Cognitiva:</strong> Avaliação contextual através de Visão Computacional (VLM), identificando se a tela parece profissional, desorganizada ou confusa para o usuário real.</li>
        <li><strong>Zero Falsos Positivos:</strong> O Studio utiliza árbitros de checagem cruzada e tolerância adaptativa para garantir que alarmes falsos nunca interrompam a equipe.</li>
      </ul>
    </div>

    <div class="doc-footer">
      <span>UXSentinel Studio v0.1.8 · Manual de Uso e Padronização da Qualidade</span>
      <span>Pág. 1 de 7</span>
    </div>
  </div>

  <!-- PÁGINA 2: ARQUITETURA E ESPECIFICAÇÕES TÉCNICAS -->
  <div class="manual-page">
    <div class="page-content">
      <h2>Arquitetura em 3 Colunas Produtivas (Layout Estilo A)</h2>
      <p>A interface do Studio foi ergonomicamente projetada para permitir que qualquer usuário trabalhe confortavelmente em uma única tela integrada:</p>

      <div class="ascii-box">┌────────────────────────────────────────────────────────────────────────┐
│ TOPBAR: 🛡️ UXSentinel Studio · Cenários | Config | Histórico · Status  │
├─────────────────┬───────────────────────────────┬──────────────────────┤
│ COLUNA 1        │ COLUNA 2                      │ COLUNA 3             │
│ (260px)         │ (Flexível - Centro)           │ (320px)              │
│ 📁 Catálogo     │ 📝 Editor Visual / YAML       │ 🎯 Medidor de Saúde  │
│ • Meus Cenários │ • Assistente IA em Português  │ • Falhas Detectadas  │
│ • 🕷️ Modo Crawl │ • Live Preview (Foto ao Vivo) │ • Console de Logs    │
│ • Filtros/Busca │ • Atalho Ctrl+S e Autosave    │ • Detalhes do Erro   │
│ • Projetos (➕) │ • Ações Rápidas por Step      │ • Score Ring (0-100) │
└─────────────────┴───────────────────────────────┴──────────────────────┘</div>

      <h2>2. Especificações Técnicas</h2>
      <p>Esta seção reúne os dados técnicos, parâmetros de desempenho e dimensões de engenharia que fundamentam o UXSentinel Studio, assegurando estabilidade em computadores corporativos ou esteiras de CI/CD.</p>

      <h3>Dados de Desempenho e Recursos do Sistema</h3>
      <table>
        <thead>
          <tr>
            <th>Parâmetro</th>
            <th>Especificação Homologada</th>
            <th>Impacto Prático para o Usuário</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Tempo de Inicialização</strong></td>
            <td>Inferior a 1,2 segundos</td>
            <td>O Studio sobe instantaneamente ao digitar o comando no terminal.</td>
          </tr>
          <tr>
            <td><strong>Consumo de Memória (RAM)</strong></td>
            <td>65 MB a 180 MB em pico</td>
            <td>Leve o suficiente para rodar tranquilamente em notebooks corporativos.</td>
          </tr>
          <tr>
            <td><strong>Comunicação em Tempo Real</strong></td>
            <td>Server-Sent Events (SSE) nativo</td>
            <td>Atualizações fluidas na tela sem recarregar a página e sem travar.</td>
          </tr>
          <tr>
            <td><strong>Armazenamento em Fila</strong></td>
            <td>Cap FIFO de 50 execuções</td>
            <td>Mantém o histórico recente sem risco de esgotar o disco ou a memória.</td>
          </tr>
          <tr>
            <td><strong>Conexão de Rede</strong></td>
            <td>Loopback estrito (127.0.0.1:8765)</td>
            <td>Segurança Máxima: o Studio não abre portas externas na rede pública.</td>
          </tr>
        </tbody>
      </table>

      <h3>Dimensões de Telas e Dispositivos (Multi-Viewport)</h3>
      <table>
        <thead>
          <tr>
            <th>Perfil</th>
            <th>Resolução em Pixels</th>
            <th>Proporção</th>
            <th>Objetivo de Inspeção</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Desktop Full HD</strong></td>
            <td>1920 × 1080</td>
            <td>16:9</td>
            <td>Visualização ampla em monitores de escritório, barras e menus laterais.</td>
          </tr>
          <tr>
            <td><strong>Desktop Compacto</strong></td>
            <td>1440 × 900</td>
            <td>16:10</td>
            <td>Padrão dominante em notebooks corporativos e laptops.</td>
          </tr>
          <tr>
            <td><strong>Tablet</strong></td>
            <td>768 × 1024</td>
            <td>3:4</td>
            <td>Comportamento de tabelas sem rolagem e colapso de menus para hambúrguer.</td>
          </tr>
          <tr>
            <td><strong>Mobile Standard</strong></td>
            <td>375 × 812</td>
            <td>9:19.5</td>
            <td>Inspeção crítica de quebra de texto, transbordamento horizontal e botões.</td>
          </tr>
        </tbody>
      </table>

      <div class="callout callout-security">
        <div class="callout-title">🔒 Segurança e Isolamento de Credenciais</div>
        O Studio implementa a política de <strong>Zero Vazamento</strong>. Chaves de API, senhas e tokens de integração (Jira e IA) são gravados em arquivo com permissão estrita de sistema <code>0600</code> (legível apenas pelo seu usuário). Senhas nunca aparecem em texto puro: exibem apenas o indicador seguro <span class="pill">Configurado: Sim</span>.
      </div>
    </div>

    <div class="doc-footer">
      <span>UXSentinel Studio v0.1.8 · Manual de Uso e Padronização da Qualidade</span>
      <span>Pág. 2 de 7</span>
    </div>
  </div>

  <!-- PÁGINA 3: CRITÉRIOS DE ACEITAÇÃO E SCORE RING -->
  <div class="manual-page">
    <div class="page-content">
      <h2>3. Critérios de Aceitação da Qualidade</h2>
      <p>Para que um produto digital seja considerado <strong>Conforme</strong>, ele deve satisfazer regras objetivas. O UXSentinel Studio padroniza essas regras dividindo os defeitos em quatro classes de severidade.</p>

      <h3>Matriz de Classificação de Defeitos</h3>
      <table>
        <thead>
          <tr>
            <th>Severidade</th>
            <th>O que define o defeito?</th>
            <th>Exemplo Típico</th>
            <th>Ação Requerida</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><span class="badge badge-blocker">BLOQUEANTE</span></td>
            <td>A tela não carrega, ocorrem erros HTTP 500, crash de JavaScript fatal, ou um botão de ação indispensável não responde.</td>
            <td>Tela branca (WSOD); botão "Finalizar Compra" travado; formulário que não envia.</td>
            <td><strong>Parada Imediata:</strong> impede publicação em produção até ser corrigido.</td>
          </tr>
          <tr>
            <td><span class="badge badge-high">ALTA</span></td>
            <td>Conteúdo cortado, transbordamento lateral de tela no celular, termos em idioma estrangeiro no meio do sistema.</td>
            <td>Tabela que ultrapassa a tela do celular; texto "Submit Order" em tela em português.</td>
            <td><strong>Correção obrigatória</strong> na sprint ou versão atual.</td>
          </tr>
          <tr>
            <td><span class="badge badge-medium">MÉDIA</span></td>
            <td>Contraste de cor ilegível (texto cinza claro em fundo branco), espaçamento desalinhado, campos fora de ordem.</td>
            <td>Texto ilegível sob luz solar; ícone sobreposto ao texto explicativo.</td>
            <td><strong>Ajuste recomendado</strong> para garantir conformidade legal (WCAG).</td>
          </tr>
          <tr>
            <td><span class="badge badge-low">BAIXA</span></td>
            <td>Pequenos detalhes estéticos, oportunidades de modernização de CSS, pequenas inconsistências visuais.</td>
            <td>Falta de efeito hover em botão secundário; sugestão de arredondamento de borda.</td>
            <td><strong>Melhoria estética</strong> a ser planejada conforme prioridade.</td>
          </tr>
        </tbody>
      </table>

      <div class="callout callout-warning">
        <div class="callout-title">⚠️ Detecção de Falhas Silenciosas e Regra de Recuo (Backtrack)</div>
        Erros 500, telas brancas e exceções graves de JS no console geram apontamentos de severidade inicial <strong>Alta</strong> e acionam automaticamente uma rotina de recuo de um passo (<strong>backtrack</strong>). Caso o passo de recuo falhe ou trave a navegação, o apontamento é escalonado imediatamente para <strong>Bloqueante</strong>.
      </div>

      <h3>O Termômetro de Qualidade (Score Ring de UX)</h3>
      <p>Ao final de cada inspeção, o Studio sintetiza o estado da tela em uma pontuação ponderada de 0 a 100:</p>

      <div class="score-grid">
        <div class="score-card score-excelente">
          <div class="score-range">90 a 100</div>
          <div class="score-label">Excelente</div>
          <div class="score-detail">Interface impecável, acessível e sem falhas graves. Pronta para lançamento.</div>
        </div>
        <div class="score-card score-bom">
          <div class="score-range">75 a 89</div>
          <div class="score-label">Bom</div>
          <div class="score-detail">Funcionalidade perfeita com pequenos detalhes estéticos a polir.</div>
        </div>
        <div class="score-card score-atencao">
          <div class="score-range">50 a 74</div>
          <div class="score-label">Atenção</div>
          <div class="score-detail">Existem problemas visíveis de responsividade ou tradução. Requer ajuste.</div>
        </div>
        <div class="score-card score-critico">
          <div class="score-range">0 a 49</div>
          <div class="score-label">Crítico</div>
          <div class="score-detail">Presença de falha bloqueante ou quebra estrutural severa. Não publicar.</div>
        </div>
      </div>
    </div>

    <div class="doc-footer">
      <span>UXSentinel Studio v0.1.8 · Manual de Uso e Padronização da Qualidade</span>
      <span>Pág. 3 de 7</span>
    </div>
  </div>

  <!-- PÁGINA 4: INSTRUÇÕES DE USO PASSO A PASSO -->
  <div class="manual-page">
    <div class="page-content">
      <h2>4. Instruções de Uso Passo a Passo</h2>
      <p>Siga este roteiro prático para operar o Studio com facilidade, mesmo sem conhecimento prévio de programação:</p>

      <div class="steps-container">
        <div class="step-card">
          <div class="step-number">1</div>
          <div class="step-body">
            <div class="step-title">Inicializando o Studio</div>
            <p class="step-desc">Abra o terminal e digite: <code>uxsentinel-studio</code>. O navegador abrirá automaticamente em <code>http://127.0.0.1:8765/?token=...</code> com o token de sessão configurado.</p>
          </div>
        </div>

        <div class="step-card">
          <div class="step-number">2</div>
          <div class="step-body">
            <div class="step-title">Navegando no Catálogo e Projetos (Coluna 1 · Esquerda)</div>
            <p class="step-desc">Alterne entre projetos cadastrados no Seletor de Projetos ou adicione novas pastas via <strong>➕</strong>. Os testes são agrupados em uma árvore hierárquica colapsável por projeto. Localize cenários usando a busca instantânea ou os filtros rápidos. Clique em "+ Novo Cenário" para criar um teste novo. Para excluir ou desvincular um cenário existente com agilidade, utilize o botão rápido de lixeira (<strong>🗑️</strong>) disponível no cabeçalho de cada item.</p>
          </div>
        </div>

        <div class="step-card">
          <div class="step-number">3</div>
          <div class="step-body">
            <div class="step-title">Editando e Salvando (Coluna 2 · Centro)</div>
            <p class="step-desc">Altere as etapas no editor com destaque de sintaxe. Suas alterações contam com Autosave (1s) e atalho <code>Ctrl+S</code>. Se houver erro de sintaxe, o Studio alerta antes de rodar.</p>
          </div>
        </div>

        <div class="step-card">
          <div class="step-number">4</div>
          <div class="step-body">
            <div class="step-title">Criando Testes com o Assistente de IA</div>
            <p class="step-desc">Abra a aba <strong>"🤖 Assistente IA"</strong>, descreva o teste em português (ex: <em>"Acesse o login, digite as credenciais e cheque se o menu abre em português"</em>) e clique em "Gerar Cenário".</p>
          </div>
        </div>

        <div class="step-card">
          <div class="step-number">5</div>
          <div class="step-body">
            <div class="step-title">Executando e Acompanhando ao Vivo (Live Preview)</div>
            <p class="step-desc">Clique em <strong>"▶ Executar Agora"</strong>. O modo Dual-Mode abre as capturas da tela em tempo real, mostrando o robô navegando e clicando exatamente como um usuário humano.</p>
          </div>
        </div>

        <div class="step-card">
          <div class="step-number">6</div>
          <div class="step-body">
            <div class="step-title">Examinando Falhas e Recomendações (Coluna 3 · Direita)</div>
            <p class="step-desc">Consulte o Score Geral de Saúde e a lista de defeitos. Cada cartão detalha o problema encontrado e traz uma Sugestão Prática de Correção pronta para o desenvolvedor.</p>
          </div>
        </div>
      </div>
    </div>

    <div class="doc-footer">
      <span>UXSentinel Studio v0.1.8 · Manual de Uso e Padronização da Qualidade</span>
      <span>Pág. 4 de 7</span>
    </div>
  </div>

  <!-- PÁGINA 5: MODO EXPLORATÓRIO AUTÔNOMO (CRAWLER & DESCOBERTA) -->
  <div class="manual-page">
    <div class="page-content">
      <h2>5. Modo Exploratório Autônomo (Crawler & Descoberta)</h2>
      <div class="callout callout-info">
        <div class="callout-title">🕷️ Descoberta Automatizada de Rotas e Telas (UXS-12)</div>
        O <strong>Modo Exploratório Autônomo</strong> permite auditar aplicações inteiras sem a necessidade de escrever manualmente nenhum cenário de teste prévio. O robô navega sozinho pelo sistema mapeando links, identificando telas e gerando cenários YAML completos de forma 100% autônoma.
      </div>

      <h3>Como Funciona o Crawler Autônomo</h3>
      <p>Ao fornecer uma URL inicial, o motor adota a estratégia <strong>BFS (Busca em Largura)</strong> para descobrir nós da aplicação:</p>
      <ul>
        <li><strong>Isolamento de Mesma Origem (Same-Origin Policy):</strong> O robô limita sua navegação rigorosamente ao mesmo protocolo, domínio e porta da aplicação sob teste, ignorando links externos que possam vazar a auditoria.</li>
        <li><strong>Prevenção de Loops e Deduplicação:</strong> As URLs descobertas passam por normalização de query params e fragmentos, prevenindo visitas duplicadas ou loops infinitos de navegação.</li>
        <li><strong>Evidências Visuais Automáticas:</strong> Cada página descoberta gera uma captura de tela em alta definição armazenada no diretório de saída do job.</li>
      </ul>

      <h3>🛡️ Guardrails Anti-Ações Destrutivas</h3>
      <div class="callout callout-warning">
        <div class="callout-title">Bloqueio Automático de Elementos Críticos</div>
        O robô analisa atributos de links e botões (<code>text</code>, <code>id</code>, <code>class</code>, <code>href</code>) e <strong>ignora terminantemente</strong> interações com termos perigosos como:
        <code>excluir</code>, <code>delete</code>, <code>remover</code>, <code>cancelar</code>, <code>trash</code>, <code>logout</code>, <code>sair</code> e classes como <code>.btn-danger</code>.
      </div>

      <h3>Operando o Modo Crawl no UXSentinel Studio</h3>
      <div class="steps-container">
        <div class="step-card">
          <div class="step-number">A</div>
          <div class="step-body">
            <div class="step-title">Abertura do Modal de Configuração</div>
            <p class="step-desc">Clique no botão <strong>"🕷️ Modo Crawl"</strong> na barra lateral ou catálogo. Uma janela modal dedicada será exibida.</p>
          </div>
        </div>
        <div class="step-card">
          <div class="step-number">B</div>
          <div class="step-body">
            <div class="step-title">Definição dos Parâmetros de Exploração</div>
            <p class="step-desc">Informe a <strong>URL Inicial</strong> (ex: <code>http://localhost:3000/app</code>), a <strong>Profundidade Máxima</strong> (padrão: 3) e o <strong>Limite de Páginas</strong> (padrão: 50). Marque a opção <em>"Gerar Cenários YAML Automaticamente"</em> para transformar a navegação em testes reproduzíveis.</p>
          </div>
        </div>
        <div class="step-card">
          <div class="step-number">C</div>
          <div class="step-body">
            <div class="step-title">Acompanhamento em Tempo Real e Edição Direta</div>
            <p class="step-desc">Visualize o progresso ao vivo com páginas visitadas e fila restante. Ao concluir, os cenários criados aparecem em <code>scenarios/generated/</code> com botão rápido para <strong>"Abrir Cenário Gerado no Editor"</strong> para ajuste fino imediato.</p>
          </div>
        </div>
      </div>

      <h3>Execução via Linha de Comando (CLI)</h3>
      <p>O modo exploratório também pode ser acionado diretamente no terminal ou em pipelines de CI:</p>
      <p><code>uxsentinel --crawl http://localhost:8080 --max-depth 3 --max-pages 50 --generate-scenarios</code></p>
    </div>

    <div class="doc-footer">
      <span>UXSentinel Studio v0.1.8 · Manual de Uso e Padronização da Qualidade</span>
      <span>Pág. 5 de 7</span>
    </div>
  </div>

  <!-- PÁGINA 6: CONFIGURAÇÕES E GERENCIAMENTO DE PROJETOS -->
  <div class="manual-page">
    <div class="page-content">
      <h2>6. Configurações, Projetos e Histórico</h2>

      <h3>Seletor de Projetos e Agrupamento Hierárquico no Studio</h3>
      <p>No topo da barra lateral esquerda, o Seletor de Projetos permite transitar instantaneamente entre diferentes aplicações e pastas cadastradas no catálogo global (<code>~/.config/uxsentinel/config.yaml</code>):</p>
      <ul>
        <li><strong>Dropdown de Seleção Ativa:</strong> Escolha entre visualizar <em>"🌐 Todos os Projetos"</em> de forma consolidada ou focar especificamente em uma aplicação ativa.</li>
        <li><strong>Adição Rápida de Projetos (➕):</strong> Abra o modal para cadastrar o nome e o caminho absoluto de qualquer pasta do sistema contendo cenários YAML, integrando-a ao Studio em tempo real.</li>
        <li><strong>Árvore Hierárquica Colapsável:</strong> Os cenários são agrupados visualmente por projeto com badges numéricos de contagem e pastas expansíveis/colapsáveis (▾), separando os testes do negócio da biblioteca embutida.</li>
        <li><strong>Exclusão Flexível de Cenários (🗑️):</strong> Ao acionar o botão de exclusão na barra lateral ou no editor, o QA escolhe entre:
          <ul>
            <li><strong>Apenas desvincular do catálogo:</strong> remove o registro do <code>config.yaml</code> preservando o arquivo YAML no disco para reutilização futura.</li>
            <li><strong>Excluir arquivo fisicamente do disco:</strong> apaga o arquivo YAML permanentemente da máquina e remove o vínculo do catálogo com confirmação de segurança.</li>
          </ul>
        </li>
      </ul>

      <h3>Aba "Configurações" (Topbar)</h3>
      <p>Acesse "Configurações" para personalizar o comportamento do UXSentinel e auditar o ambiente:</p>
      <ul>
        <li><strong>Localização dos Arquivos de Configuração:</strong> Mapeia os caminhos absolutos do Arquivo Ativo em Uso, da Configuração Global do Usuário (XDG em <code>~/.config/uxsentinel/config.yaml</code> com permissão restrita <code>0600</code>), da Configuração Local do Projeto (detectada no workspace), do arquivo de Variáveis de Ambiente (<code>.env</code>) e do Diretório Raiz do Projeto.</li>
        <li><strong>Modo do Navegador:</strong> Ative "Modo Headless" para testes em segundo plano, ou desative para ver a janela física abrindo durante o desenvolvimento.</li>
        <li><strong>Integração com Jira:</strong> Conecte sua conta do Jira para abertura automática de cards de bug com evidências anexadas. Valide com o botão <em>"Testar Conexão"</em>.</li>
        <li><strong>Provedores de IA:</strong> Escolha entre Google Gemini, Anthropic Claude ou OpenAI informando sua credencial com proteção de visualização.</li>
      </ul>

      <h3>Aba "Histórico de Relatórios"</h3>
      <p>Permite auditar execuções passadas com data, status, duração e link direto para o relatório navegável em HTML com galeria de fotos e gravação de vídeo/GIF da sessão.</p>
    </div>

    <div class="doc-footer">
      <span>UXSentinel Studio v0.1.8 · Manual de Uso e Padronização da Qualidade</span>
      <span>Pág. 6 de 7</span>
    </div>
  </div>

  <!-- PÁGINA 7: GLOSSÁRIO E BOAS PRÁTICAS -->
  <div class="manual-page">
    <div class="page-content">
      <h2>7. Glossário Amigável e Boas Práticas</h2>

      <h3>Glossário Amigável de Termos</h3>
      <table>
        <thead>
          <tr>
            <th>Termo</th>
            <th>Significado em Linguagem Simples</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Cenário (YAML)</strong></td>
            <td>Receita passo a passo em formato de texto limpo: "vá para a página X, clique no botão Y, tire uma foto e analise".</td>
          </tr>
          <tr>
            <td><strong>Checkpoint</strong></td>
            <td>Momento de parada onde o robô tira uma foto de alta resolução e aciona a inteligência artificial para avaliar a tela.</td>
          </tr>
          <tr>
            <td><strong>Crawler Autônomo</strong></td>
            <td>Mecanismo de exploração automática que descobre e navega por todas as telas do sistema sem intervenção humana.</td>
          </tr>
          <tr>
            <td><strong>Backtrack (Recuo)</strong></td>
            <td>Técnica em que o robô, ao se deparar com um erro grave, recua um passo na navegação para tentar caminhos alternativos antes de falhar.</td>
          </tr>
          <tr>
            <td><strong>Self-Healing (Auto-Cura)</strong></td>
            <td>Tecnologia inteligente: se um botão mudou de código mas continua visível na tela, o robô acha o botão pela visão e clica nele mesmo assim!</td>
          </tr>
          <tr>
            <td><strong>Viewport</strong></td>
            <td>O tamanho virtual da janela de visualização (ex: tamanho de tela de um computador vs. tamanho de tela de um smartphone).</td>
          </tr>
          <tr>
            <td><strong>WCAG / Acessibilidade</strong></td>
            <td>Normas internacionais para garantir que pessoas com limitações visuais ou daltonismo consigam usar o sistema sem barreiras.</td>
          </tr>
        </tbody>
      </table>

      <div class="callout callout-info">
        <div class="callout-title">✅ Boas Práticas para a Padronização da Qualidade</div>
        <ul>
          <li><strong>Inspeção Contínua:</strong> Execute os cenários antes de qualquer deploy em produção.</li>
          <li><strong>Foco nas Falhas Críticas:</strong> Priorize sempre a correção imediata de falhas classificadas como <em>Bloqueantes</em> e <em>Altas</em>.</li>
          <li><strong>Modularidade:</strong> Mantenha os cenários organizados por jornada do cliente (Ex: <em>Login</em>, <em>Compra</em>, <em>Emissão de Relatório</em>).</li>
          <li><strong>Descoberta Periódica:</strong> Execute o <em>Modo Crawl</em> periodicamente após grandes lançamentos para identificar páginas órfãs, links quebrados ou telas brancas silenciosas.</li>
        </ul>
      </div>

      <div style="margin-top: 30px; text-align: center; color: #64748b; font-size: 8pt;">
        <p><strong>UXSentinel Open Source Project</strong> · Garantindo a Excelência Digital de Ponta a Ponta</p>
        <p>Licença MIT · Documentação e Suporte: <a href="https://github.com/Defendi/UXSentinel" style="color: #2563eb; text-decoration: none;">github.com/Defendi/UXSentinel</a></p>
      </div>
    </div>

    <div class="doc-footer">
      <span>UXSentinel Studio v0.1.8 · Manual de Uso e Padronização da Qualidade</span>
      <span>Pág. 7 de 7</span>
    </div>
  </div>

</body>
</html>
"""


async def generate_pdf():
    output_path = Path("/mnt/home/alexandre/Projetos/UXSentinel/UXSentinel_Studio_Manual_do_Usuario.pdf")
    print(f"Gerando PDF em: {output_path}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Carrega o HTML com estilos embutidos
        await page.set_content(MANUAL_HTML, wait_until="networkidle")

        # Gera o PDF em A4 com cores fiéis
        await page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
        )
        await browser.close()

    print(f"Sucesso! PDF gerado ({output_path.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(generate_pdf())
