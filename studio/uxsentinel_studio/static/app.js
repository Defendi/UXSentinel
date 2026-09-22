/**
 * UXSentinel Studio - Live Mission Control & SPA Engine (UXS-54 / STU-10)
 * Arquitetura reativa desacoplada, zero dependências externas, suporte offline integral.
 */

(() => {
    "use strict";

    // --- 1. Estado Central da Aplicação ---
    const state = {
        token: "",
        scenarios: [],
        filteredScenarios: [],
        activeScenarioId: null,
        activeScenarioData: null,
        isDirty: false,
        autosaveTimer: null,
        validationTimer: null,
        activeTab: "scenarios",
        activeInspTab: "preview",
        activeFilter: "all",
        searchQuery: "",
        currentRunId: null,
        eventSource: null,
        executionLogs: [],
        checkpointsLive: [],
    };

    // --- 2. Utilitários e Cliente HTTP Autenticado ---
    function initSessionToken() {
        // Tenta obter da URL (?token=...) ou do sessionStorage
        const urlParams = new URLSearchParams(window.location.search);
        const urlToken = urlParams.get("token");
        if (urlToken) {
            state.token = urlToken;
            sessionStorage.setItem("studio_token", urlToken);
        } else {
            state.token = sessionStorage.getItem("studio_token") || "";
        }

        const statusEl = document.getElementById("status-text");
        if (state.token) {
            const shortToken = state.token.substring(0, 8);
            if (statusEl) statusEl.textContent = `Token Ativo: ${shortToken}...`;
        } else if (statusEl) {
            statusEl.textContent = "Modo Anônimo";
        }
    }

    async function apiFetch(endpoint, options = {}) {
        const headers = options.headers || {};
        if (state.token) {
            headers["X-Studio-Token"] = state.token;
        }
        if (!headers["Content-Type"] && !(options.body instanceof FormData)) {
            headers["Content-Type"] = "application/json";
        }

        const config = {
            ...options,
            headers,
        };

        try {
            const response = await fetch(endpoint, config);
            if (response.status === 401) {
                showToast("Sessão expirada ou não autorizada. Verifique o token de acesso.", "error");
                throw new Error("Não autorizado (401)");
            }
            return response;
        } catch (err) {
            console.error(`Erro na requisição para ${endpoint}:`, err);
            throw err;
        }
    }

    function showToast(message, type = "info", duration = 3500) {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const icons = {
            success: "✓",
            error: "✕",
            warning: "⚠️",
            info: "ℹ️",
        };

        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${icons[type] || "•"}</span> <span>${escapeHtml(message)}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(30px)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function formatTime(isoString) {
        if (!isoString) return "--";
        try {
            const date = new Date(isoString);
            return date.toLocaleString("pt-BR", {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
            });
        } catch {
            return isoString;
        }
    }

    // --- 3. Carregamento e Gerenciamento de Cenários ---
    async function loadScenarios() {
        try {
            const res = await apiFetch("/api/scenarios");
            if (!res.ok) return;
            state.scenarios = await res.json();
            filterAndRenderScenarios();

            // Se nenhum cenário estiver ativo, seleciona o primeiro
            if (!state.activeScenarioId && state.scenarios.length > 0) {
                selectScenario(state.scenarios[0].id);
            }
        } catch (err) {
            console.error("Falha ao listar cenários:", err);
        }
    }

    function filterAndRenderScenarios() {
        const query = state.searchQuery.toLowerCase().trim();
        state.filteredScenarios = state.scenarios.filter((sc) => {
            const matchesQuery =
                sc.id.toLowerCase().includes(query) ||
                (sc.title && sc.title.toLowerCase().includes(query));
            if (!matchesQuery) return false;

            if (state.activeFilter === "project") return sc.source === "project";
            if (state.activeFilter === "library") return sc.source === "library";
            return true;
        });

        const projectList = document.getElementById("project-scenarios-list");
        const libraryList = document.getElementById("library-scenarios-list");
        if (!projectList || !libraryList) return;

        projectList.innerHTML = "";
        libraryList.innerHTML = "";

        let projectCount = 0;
        let libraryCount = 0;

        state.filteredScenarios.forEach((sc) => {
            const li = document.createElement("li");
            li.className = `scenario-item ${sc.id === state.activeScenarioId ? "active" : ""}`;
            li.innerHTML = `
                <div class="scenario-item-header">
                    <span class="scenario-item-title" title="${escapeHtml(sc.title || sc.id)}">${escapeHtml(sc.title || sc.id)}</span>
                    <span class="scenario-item-steps">${sc.step_count || 0} passos</span>
                </div>
                <div class="scenario-item-meta">
                    <span class="scenario-item-profile">${escapeHtml(sc.profile || "generic")}</span>
                    <span>•</span>
                    <span>${escapeHtml(sc.filename)}</span>
                </div>
            `;
            li.addEventListener("click", () => selectScenario(sc.id));

            if (sc.source === "library") {
                libraryList.appendChild(li);
                libraryCount++;
            } else {
                projectList.appendChild(li);
                projectCount++;
            }
        });

        const pCountEl = document.getElementById("project-count");
        const lCountEl = document.getElementById("library-count");
        if (pCountEl) pCountEl.textContent = projectCount;
        if (lCountEl) lCountEl.textContent = libraryCount;
    }

    async function selectScenario(scenarioId) {
        if (state.isDirty) {
            const confirmDiscard = confirm("Você tem alterações não salvas no cenário atual. Deseja descartar?");
            if (!confirmDiscard) return;
        }

        try {
            const res = await apiFetch(`/api/scenarios/${scenarioId}`);
            if (!res.ok) {
                showToast(`Cenário '${scenarioId}' não encontrado.`, "error");
                return;
            }

            const data = await res.json();
            state.activeScenarioId = scenarioId;
            state.activeScenarioData = data;
            state.isDirty = false;

            // Atualiza UI da Sidebar
            filterAndRenderScenarios();

            // Atualiza Editor
            const filenameEl = document.getElementById("current-filename");
            const sourceBadge = document.getElementById("current-source-badge");
            const profileSelect = document.getElementById("editor-profile-select");
            const codeEditor = document.getElementById("yaml-code-editor");
            const btnDelete = document.getElementById("btn-delete-scenario");

            if (filenameEl) filenameEl.textContent = data.filename;
            if (sourceBadge) {
                sourceBadge.textContent = data.source === "library" ? "Biblioteca" : "Projeto";
                sourceBadge.style.color = data.source === "library" ? "var(--accent-purple)" : "var(--accent-cyan)";
            }
            if (profileSelect) profileSelect.value = data.profile || "generic";
            if (codeEditor) {
                codeEditor.value = data.raw_yaml || "";
                updateLineNumbers();
            }

            // Biblioteca é read-only para exclusão
            if (btnDelete) {
                btnDelete.style.display = data.source === "library" ? "none" : "inline-flex";
            }

            setSaveStatus("saved");
            renderPreviewSteps(data.steps || []);
            validateYaml(codeEditor ? codeEditor.value : "");
        } catch (err) {
            console.error("Erro ao selecionar cenário:", err);
        }
    }

    // --- 4. YAML Studio Editor & Validação (STU-06) ---
    function updateLineNumbers() {
        const codeEditor = document.getElementById("yaml-code-editor");
        const lineNumbers = document.getElementById("editor-line-numbers");
        if (!codeEditor || !lineNumbers) return;

        const lines = codeEditor.value.split("\n").length;
        lineNumbers.textContent = Array.from({ length: Math.max(lines, 1) }, (_, i) => i + 1).join("\n");
    }

    function syncEditorScroll() {
        const codeEditor = document.getElementById("yaml-code-editor");
        const lineNumbers = document.getElementById("editor-line-numbers");
        if (codeEditor && lineNumbers) {
            lineNumbers.scrollTop = codeEditor.scrollTop;
        }
    }

    function setSaveStatus(status) {
        const indicator = document.getElementById("save-status-indicator");
        if (!indicator) return;

        indicator.className = `save-status ${status}`;
        if (status === "saved") {
            indicator.textContent = "● Salvo";
        } else if (status === "modified") {
            indicator.textContent = "● Modificado...";
        } else if (status === "saving") {
            indicator.textContent = "● Salvando...";
        }
    }

    async function validateYaml(yamlContent) {
        const valBar = document.getElementById("validation-feedback-bar");
        const valIcon = document.getElementById("val-icon");
        const valMsg = document.getElementById("val-message");
        if (!valBar || !valIcon || !valMsg) return;

        if (!yamlContent.trim()) {
            valBar.className = "validation-bar invalid";
            valIcon.textContent = "⚠️";
            valMsg.textContent = "Conteúdo YAML vazio.";
            return;
        }

        try {
            const res = await apiFetch("/api/scenarios/validate", {
                method: "POST",
                body: JSON.stringify({ yaml_content: yamlContent }),
            });
            if (!res.ok) return;

            const result = await res.json();
            if (result.valid) {
                valBar.className = "validation-bar valid";
                valIcon.textContent = "✓";
                valMsg.textContent = "Sintaxe YAML e semântica de passos em conformidade total.";
            } else {
                valBar.className = "validation-bar invalid";
                valIcon.textContent = "✕";
                const firstErr = result.errors[0];
                const errMsg = firstErr ? `Passo ${firstErr.step_index}: ${firstErr.message}` : "Erro de validação YAML.";
                valMsg.textContent = errMsg;
            }
        } catch {
            // Silencioso em caso de erro transitório de rede
        }
    }

    async function saveScenario() {
        if (!state.activeScenarioId || !state.activeScenarioData) return;
        if (state.activeScenarioData.source === "library") {
            showToast("Cenários da biblioteca embutida são somente leitura.", "warning");
            return;
        }

        const codeEditor = document.getElementById("yaml-code-editor");
        if (!codeEditor) return;

        setSaveStatus("saving");
        try {
            const res = await apiFetch(`/api/scenarios/${state.activeScenarioId}`, {
                method: "PUT",
                body: JSON.stringify({
                    yaml_content: codeEditor.value,
                    filename: state.activeScenarioData.filename,
                }),
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                showToast(`Falha ao salvar: ${errData.detail || "Erro de validação"}`, "error");
                setSaveStatus("modified");
                return;
            }

            state.isDirty = false;
            setSaveStatus("saved");
            showToast("Cenário salvo com sucesso!", "success", 2000);
            loadScenarios();
        } catch (err) {
            console.error("Erro ao salvar:", err);
            setSaveStatus("modified");
        }
    }

    async function deleteScenario() {
        if (!state.activeScenarioId || !state.activeScenarioData) return;
        if (state.activeScenarioData.source === "library") {
            showToast("Não é permitido excluir cenários da biblioteca interna.", "warning");
            return;
        }

        const confirmDel = confirm(`Tem certeza que deseja excluir o cenário '${state.activeScenarioData.title || state.activeScenarioId}'?`);
        if (!confirmDel) return;

        try {
            const res = await apiFetch(`/api/scenarios/${state.activeScenarioId}`, {
                method: "DELETE",
            });

            if (res.ok) {
                showToast("Cenário excluído com sucesso!", "info");
                state.activeScenarioId = null;
                state.activeScenarioData = null;
                state.isDirty = false;
                await loadScenarios();
            } else {
                showToast("Erro ao excluir cenário.", "error");
            }
        } catch (err) {
            console.error("Erro ao excluir:", err);
        }
    }

    // --- 5. Renderização do Roteiro de Passos (Preview) ---
    function renderPreviewSteps(steps) {
        const container = document.getElementById("preview-steps-list");
        const countBadge = document.getElementById("preview-step-count");
        if (!container) return;

        if (countBadge) countBadge.textContent = `${steps.length} passos`;

        if (!steps || steps.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <span class="empty-icon">📝</span>
                    <p>Nenhum passo estruturado neste cenário.</p>
                </div>
            `;
            return;
        }

        const actionIcons = {
            goto: "🌐",
            click: "🖱️",
            fill: "⌨️",
            wait: "⏳",
            wait_modal: "🪟",
            checkpoint: "📸",
            scroll: "📜",
            select: "🔽",
        };

        container.innerHTML = steps
            .map((step) => {
                const icon = actionIcons[step.action] || "⚡";
                const paramText = step.url || step.selector || step.name || "";
                return `
                <div class="step-card">
                    <div class="step-card-header">
                        <span class="step-action-badge">${icon} ${escapeHtml(step.action)}</span>
                        <span class="step-index-badge">#${step.index}</span>
                    </div>
                    ${step.description ? `<div class="step-card-desc">${escapeHtml(step.description)}</div>` : ""}
                    ${paramText ? `<div class="step-card-param">${escapeHtml(paramText)}</div>` : ""}
                    ${step.expected_behavior ? `<div class="step-card-desc" style="color: var(--accent-cyan); font-size: 0.72rem;">Esperado: ${escapeHtml(step.expected_behavior)}</div>` : ""}
                </div>
            `;
            })
            .join("");
    }

    // --- 6. Live Mission Control & Streaming SSE (STU-07) ---
    async function runScenarioExecution() {
        if (!state.activeScenarioId) {
            showToast("Selecione um cenário antes de executar.", "warning");
            return;
        }

        // Se houver alterações pendentes, salva primeiro
        if (state.isDirty) {
            await saveScenario();
        }

        // Alterna coluna 3 para aba Live
        switchInspectorTab("live");

        const liveBadge = document.getElementById("live-badge");
        const liveRunId = document.getElementById("live-run-id");
        const liveStatus = document.getElementById("live-step-status");
        const livePercentage = document.getElementById("live-percentage");
        const liveProgressFill = document.getElementById("live-progress-fill");
        const liveFooter = document.getElementById("live-footer");
        const logsWindow = document.getElementById("terminal-logs-window");
        const checkpointsList = document.getElementById("live-checkpoints-list");

        if (liveBadge) {
            liveBadge.className = "live-badge running";
            liveBadge.textContent = "EXECUTANDO";
        }
        if (liveStatus) liveStatus.textContent = "Disparando agente Playwright...";
        if (livePercentage) livePercentage.textContent = "10%";
        if (liveProgressFill) liveProgressFill.style.width = "10%";
        if (liveFooter) liveFooter.style.display = "none";
        if (logsWindow) logsWindow.innerHTML = "";
        if (checkpointsList) checkpointsList.innerHTML = "";

        appendLogLine(`[ORQUESTRAÇÃO] Disparando execução do cenário: ${state.activeScenarioId}...`, "info");

        try {
            const res = await apiFetch("/api/execution/run", {
                method: "POST",
                body: JSON.stringify({
                    scenario_id: state.activeScenarioId,
                    overrides: {},
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                showToast(`Falha ao disparar execução: ${err.detail || "Erro interno"}`, "error");
                if (liveBadge) {
                    liveBadge.className = "live-badge failed";
                    liveBadge.textContent = "FALHOU";
                }
                return;
            }

            const data = await res.json();
            state.currentRunId = data.run_id;
            if (liveRunId) liveRunId.textContent = `ID: ${data.run_id}`;
            appendLogLine(`[RUN] Sessão alocada com ID: ${data.run_id}. Conectando ao canal SSE em tempo real...`, "info");

            // Inicia streaming SSE
            connectExecutionStream(data.run_id);
        } catch (err) {
            appendLogLine(`[ERRO] Falha de comunicação com o backend: ${err.message}`, "error");
        }
    }

    function connectExecutionStream(runId) {
        if (state.eventSource) {
            state.eventSource.close();
            state.eventSource = null;
        }

        const streamUrl = `/api/execution/${runId}/stream?token=${encodeURIComponent(state.token)}`;
        const es = new EventSource(streamUrl);
        state.eventSource = es;

        es.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                handleStreamEvent(payload);
            } catch (ex) {
                console.error("Erro ao decodificar evento SSE:", ex, event.data);
            }
        };

        es.onerror = (err) => {
            console.warn("Evento de erro no stream SSE (conexão encerrada ou concluída):", err);
            es.close();
            state.eventSource = null;
        };
    }

    function handleStreamEvent(eventObj) {
        const liveBadge = document.getElementById("live-badge");
        const liveStatus = document.getElementById("live-step-status");
        const livePercentage = document.getElementById("live-percentage");
        const liveProgressFill = document.getElementById("live-progress-fill");
        const liveFooter = document.getElementById("live-footer");
        const reportLink = document.getElementById("btn-view-report-link");

        const eventType = eventObj.event;
        const data = eventObj.data;

        switch (eventType) {
            case "log": {
                const msg = data.message || (typeof data === "string" ? data : JSON.stringify(data));
                appendLogLine(msg, "info");
                break;
            }
            case "step": {
                const stepIdx = data.step_index || "?";
                const action = data.action || "";
                const desc = data.description || "";
                appendLogLine(`[PASSO ${stepIdx}] ${action.toUpperCase()} - ${desc}`, "success");
                if (liveStatus) liveStatus.textContent = `Passo ${stepIdx}: ${action} (${desc})`;
                if (liveProgressFill) liveProgressFill.style.width = "60%";
                if (livePercentage) livePercentage.textContent = "60%";
                break;
            }
            case "checkpoint": {
                appendCheckpointLive(data);
                appendLogLine(`[CHECKPOINT] ${data.name} - Status: ${data.status} (Inconformidades: ${data.issues_count})`, data.issues_count > 0 ? "error" : "success");
                break;
            }
            case "completed": {
                if (liveBadge) {
                    liveBadge.className = "live-badge completed";
                    liveBadge.textContent = "CONCLUÍDO";
                }
                if (liveStatus) liveStatus.textContent = `Auditoria finalizada. Duração: ${data.duration_seconds}s | Issues: ${data.total_issues}`;
                if (liveProgressFill) liveProgressFill.style.width = "100%";
                if (livePercentage) livePercentage.textContent = "100%";

                appendLogLine(`[FINALIZADO] Auditoria concluída com sucesso! Total de inconformidades: ${data.total_issues}`, "success");
                showToast("Execução da auditoria finalizada com sucesso!", "success");

                if (liveFooter && reportLink) {
                    liveFooter.style.display = "block";
                    reportLink.href = `/api/results/${state.activeScenarioId}/artifacts/${state.activeScenarioId}_report.html`;
                }

                if (state.eventSource) {
                    state.eventSource.close();
                    state.eventSource = null;
                }
                break;
            }
            case "error": {
                if (liveBadge) {
                    liveBadge.className = "live-badge failed";
                    liveBadge.textContent = "FALHOU";
                }
                const errText = data.error || "Erro desconhecido";
                if (liveStatus) liveStatus.textContent = `Erro na execução: ${errText}`;
                appendLogLine(`[ERRO CRÍTICO] ${errText}`, "error");
                showToast(`Execução interrompida com erro: ${errText}`, "error");

                if (state.eventSource) {
                    state.eventSource.close();
                    state.eventSource = null;
                }
                break;
            }
        }
    }

    function appendLogLine(text, styleClass = "") {
        const logsWindow = document.getElementById("terminal-logs-window");
        if (!logsWindow) return;

        const now = new Date().toTimeString().split(" ")[0];
        const line = document.createElement("div");
        line.className = `log-line ${styleClass}`;
        line.textContent = `[${now}] ${text}`;
        logsWindow.appendChild(line);

        // Autoscroll para a linha mais recente
        logsWindow.scrollTop = logsWindow.scrollHeight;
    }

    function appendCheckpointLive(cpData) {
        const container = document.getElementById("live-checkpoints-list");
        if (!container) return;

        const empty = container.querySelector(".empty-checkpoints");
        if (empty) empty.remove();

        const isPassed = cpData.status === "passed" || cpData.issues_count === 0;
        const card = document.createElement("div");
        card.className = "checkpoint-card";
        card.innerHTML = `
            <div class="checkpoint-header">
                <span class="checkpoint-name">📸 ${escapeHtml(cpData.name)}</span>
                <span class="checkpoint-status-badge ${isPassed ? "passed" : "failed"}">
                    ${isPassed ? "✓ APROVADO" : `✕ ${cpData.issues_count} ISSUES`}
                </span>
            </div>
            ${cpData.expected_behavior ? `<div style="font-size: 0.72rem; color: var(--text-muted);">${escapeHtml(cpData.expected_behavior)}</div>` : ""}
        `;
        container.appendChild(card);
    }

    // --- 7. Central de Resultados & Hub de Histórico (STU-08) ---
    async function loadHistoryResults() {
        const tbody = document.getElementById("results-table-body");
        if (!tbody) return;

        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Carregando histórico de auditorias...</td></tr>`;

        try {
            const res = await apiFetch("/api/results?limit=50");
            if (!res.ok) return;

            const results = await res.json();
            updateHistoryMetrics(results);

            if (results.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Nenhuma execução registrada no diretório report/.</td></tr>`;
                return;
            }

            tbody.innerHTML = results
                .map((r) => {
                    const statusClass = r.status === "passed" ? "passed" : r.status === "failed" ? "failed" : "error";
                    const statusLabel = r.status === "passed" ? "✓ Aprovado" : r.status === "failed" ? "✕ Falhas" : "⚠️ Erro";
                    const htmlUrl = r.report_html_url || `/api/results/${r.scenario_id}/artifacts/${r.scenario_id}_report.html`;

                    return `
                    <tr>
                        <td><span class="badge-status ${statusClass}">${statusLabel}</span></td>
                        <td>
                            <strong>${escapeHtml(r.scenario_title || r.scenario_id)}</strong>
                            <div style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono);">${escapeHtml(r.scenario_id)}</div>
                        </td>
                        <td>${formatTime(r.executed_at)}</td>
                        <td style="font-family: var(--font-mono);">${(r.duration_seconds || 0).toFixed(1)}s</td>
                        <td>
                            <span style="color: ${r.issue_count > 0 ? "var(--accent-yellow)" : "var(--accent-green)"}; font-weight: 700; font-family: var(--font-mono);">
                                ${r.issue_count || 0}
                            </span>
                            ${r.bloqueante_count ? `<span class="badge-status failed" style="font-size: 0.65rem; margin-left: 4px;">${r.bloqueante_count} B</span>` : ""}
                        </td>
                        <td>
                            <a href="${htmlUrl}" target="_blank" class="btn btn-secondary" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;">
                                <span>📄</span> Ver HTML
                            </a>
                        </td>
                    </tr>
                `;
                })
                .join("");
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Erro ao carregar histórico: ${escapeHtml(err.message)}</td></tr>`;
        }
    }

    function updateHistoryMetrics(results) {
        const totalRuns = results.length;
        const totalPassed = results.filter((r) => r.status === "passed").length;
        const successRate = totalRuns > 0 ? Math.round((totalPassed / totalRuns) * 100) : 0;
        const totalIssues = results.reduce((acc, r) => acc + (r.issue_count || 0), 0);

        const totalRunsEl = document.getElementById("metric-total-runs");
        const successRateEl = document.getElementById("metric-success-rate");
        const totalIssuesEl = document.getElementById("metric-total-issues");

        if (totalRunsEl) totalRunsEl.textContent = totalRuns;
        if (successRateEl) successRateEl.textContent = `${successRate}%`;
        if (totalIssuesEl) totalIssuesEl.textContent = totalIssues;
    }

    // --- 8. Painel de Configurações Globais (STU-09) ---
    async function loadGlobalConfig() {
        try {
            const res = await apiFetch("/api/config");
            if (!res.ok) return;

            const cfg = await res.json();

            // Provedor IA
            const provSelect = document.getElementById("cfg-active-provider");
            if (provSelect && cfg.active_provider) {
                provSelect.value = cfg.active_provider;
            }

            // Jira
            if (cfg.jira) {
                const jEnabled = document.getElementById("cfg-jira-enabled");
                const jUrl = document.getElementById("cfg-jira-url");
                const jProject = document.getElementById("cfg-jira-project");
                const jEmail = document.getElementById("cfg-jira-email");
                const jIssueType = document.getElementById("cfg-jira-issuetype");

                if (jEnabled) jEnabled.checked = Boolean(cfg.jira.enabled);
                if (jUrl) jUrl.value = cfg.jira.url || "";
                if (jProject) jProject.value = cfg.jira.project_key || "";
                if (jEmail) jEmail.value = cfg.jira.email || "";
                if (jIssueType) jIssueType.value = cfg.jira.issue_type || "Bug";
            }

            // Navegador
            if (cfg.browser) {
                const bHeadless = document.getElementById("cfg-browser-headless");
                const bAxe = document.getElementById("cfg-browser-axe");
                const bFailFast = document.getElementById("cfg-browser-failfast");
                const bSlowMo = document.getElementById("cfg-browser-slowmo");
                const bWidth = document.getElementById("cfg-browser-width");
                const bHeight = document.getElementById("cfg-browser-height");

                if (bHeadless) bHeadless.checked = Boolean(cfg.browser.headless);
                if (bAxe) bAxe.checked = Boolean(cfg.browser.enable_axe);
                if (bFailFast) bFailFast.checked = Boolean(cfg.browser.fail_fast);
                if (bSlowMo) bSlowMo.value = cfg.browser.slow_mo_ms || 0;
                if (bWidth) bWidth.value = cfg.browser.viewport_width || 1280;
                if (bHeight) bHeight.value = cfg.browser.viewport_height || 800;
            }
        } catch (err) {
            console.error("Erro ao carregar configurações:", err);
        }
    }

    async function saveGlobalConfig() {
        const payload = {
            active_provider: document.getElementById("cfg-active-provider")?.value,
            browser: {
                headless: document.getElementById("cfg-browser-headless")?.checked,
                enable_axe: document.getElementById("cfg-browser-axe")?.checked,
                fail_fast: document.getElementById("cfg-browser-failfast")?.checked,
                slow_mo_ms: Number(document.getElementById("cfg-browser-slowmo")?.value || 0),
                viewport_width: Number(document.getElementById("cfg-browser-width")?.value || 1280),
                viewport_height: Number(document.getElementById("cfg-browser-height")?.value || 800),
            },
            jira: {
                enabled: document.getElementById("cfg-jira-enabled")?.checked,
                url: document.getElementById("cfg-jira-url")?.value,
                project_key: document.getElementById("cfg-jira-project")?.value,
                email: document.getElementById("cfg-jira-email")?.value,
                issue_type: document.getElementById("cfg-jira-issuetype")?.value || "Bug",
            },
        };

        const tokenVal = document.getElementById("cfg-jira-token")?.value.trim();
        if (tokenVal) {
            payload.jira.api_token = tokenVal;
        }

        try {
            const res = await apiFetch("/api/config", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            if (res.ok) {
                showToast("Configurações atualizadas com sucesso!", "success");
            } else {
                showToast("Erro ao persistir configurações.", "error");
            }
        } catch (err) {
            showToast(`Falha de comunicação: ${err.message}`, "error");
        }
    }

    async function testAIConnection() {
        const provider = document.getElementById("cfg-active-provider")?.value || "gemini_sso";
        const feedbackBox = document.getElementById("ai-test-feedback");
        const btn = document.getElementById("btn-test-ai");

        if (btn) btn.disabled = true;
        if (feedbackBox) {
            feedbackBox.style.display = "block";
            feedbackBox.className = "connection-feedback-box";
            feedbackBox.textContent = `Conectando ao modelo de visão (${provider})...`;
        }

        try {
            const res = await apiFetch("/api/config/test-ai", {
                method: "POST",
                body: JSON.stringify({ provider }),
            });
            const data = await res.json();

            if (data.valid) {
                feedbackBox.className = "connection-feedback-box success";
                feedbackBox.textContent = `✓ ${data.message} (Latência: ${data.latency_ms}ms)`;
                showToast("Conexão com IA validada com sucesso!", "success");
            } else {
                feedbackBox.className = "connection-feedback-box error";
                feedbackBox.textContent = `✕ Falha: ${data.message}`;
                showToast(`Falha de conexão com IA: ${data.message}`, "error");
            }
        } catch (err) {
            if (feedbackBox) {
                feedbackBox.className = "connection-feedback-box error";
                feedbackBox.textContent = `✕ Erro: ${err.message}`;
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async function testJiraConnection() {
        const url = document.getElementById("cfg-jira-url")?.value.trim();
        const email = document.getElementById("cfg-jira-email")?.value.trim();
        const token = document.getElementById("cfg-jira-token")?.value.trim();
        const feedbackBox = document.getElementById("jira-test-feedback");
        const btn = document.getElementById("btn-test-jira");

        if (!url || !email || !token) {
            showToast("Informe URL, E-mail e Token para testar a conexão com o Jira.", "warning");
            return;
        }

        if (btn) btn.disabled = true;
        if (feedbackBox) {
            feedbackBox.style.display = "block";
            feedbackBox.className = "connection-feedback-box";
            feedbackBox.textContent = "Testando autenticação na API v3 do Atlassian Jira Cloud...";
        }

        try {
            const res = await apiFetch("/api/config/test-jira", {
                method: "POST",
                body: JSON.stringify({ url, email, token }),
            });
            const data = await res.json();

            if (data.valid) {
                feedbackBox.className = "connection-feedback-box success";
                feedbackBox.textContent = `✓ ${data.message} (Latência: ${data.latency_ms}ms)`;
                showToast("Conexão com Jira validada com sucesso!", "success");
            } else {
                feedbackBox.className = "connection-feedback-box error";
                feedbackBox.textContent = `✕ Falha: ${data.message}`;
                showToast(`Falha Jira: ${data.message}`, "error");
            }
        } catch (err) {
            if (feedbackBox) {
                feedbackBox.className = "connection-feedback-box error";
                feedbackBox.textContent = `✕ Erro: ${err.message}`;
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    // --- 9. Assistente de IA de Autoria (/generate-scenario) ---
    async function submitAiPrompt() {
        const promptInput = document.getElementById("ai-prompt-input");
        const previewBox = document.getElementById("ai-preview-box");
        const yamlCode = document.getElementById("ai-generated-yaml");
        const btnApply = document.getElementById("btn-apply-ai-yaml");
        const btnSubmit = document.getElementById("btn-submit-ai-prompt");

        const promptText = promptInput ? promptInput.value.trim() : "";
        if (!promptText) {
            showToast("Descreva o objetivo da auditoria para a IA.", "warning");
            return;
        }

        if (btnSubmit) btnSubmit.disabled = true;
        showToast("Gerando estrutura do cenário com IA Multimodal...", "info");

        try {
            const res = await apiFetch("/api/generate-scenario", {
                method: "POST",
                body: JSON.stringify({ prompt: promptText }),
            });

            if (!res.ok) {
                showToast("Erro ao gerar cenário com IA.", "error");
                return;
            }

            const data = await res.json();
            if (previewBox && yamlCode && btnApply) {
                yamlCode.textContent = data.yaml_content;
                previewBox.style.display = "flex";
                btnApply.style.display = "inline-flex";
            }
            showToast("Cenário gerado com sucesso! Clique em 'Inserir no Editor'.", "success");
        } catch (err) {
            showToast(`Falha na IA: ${err.message}`, "error");
        } finally {
            if (btnSubmit) btnSubmit.disabled = false;
        }
    }

    function applyAiGeneratedYaml() {
        const yamlCode = document.getElementById("ai-generated-yaml");
        const codeEditor = document.getElementById("yaml-code-editor");
        if (yamlCode && codeEditor) {
            codeEditor.value = yamlCode.textContent;
            updateLineNumbers();
            state.isDirty = true;
            setSaveStatus("modified");
            validateYaml(codeEditor.value);
            closeModals();
            showToast("Estrutura inserida no editor! Salve com Ctrl+S.", "success");
        }
    }

    // --- 10. Novo Cenário ---
    async function confirmCreateScenario() {
        let filename = document.getElementById("new-scenario-filename")?.value.trim();
        const id = document.getElementById("new-scenario-id")?.value.trim();
        const title = document.getElementById("new-scenario-title")?.value.trim();
        const url = document.getElementById("new-scenario-url")?.value.trim() || "https://exemplo.com.br";

        if (!filename || !id || !title) {
            showToast("Preencha todos os campos obrigatórios.", "warning");
            return;
        }

        if (!filename.endsWith(".yaml") && !filename.endsWith(".yml")) {
            filename += ".yaml";
        }

        const template = `id: ${id}
title: "${title}"
profile: "generic"
tags:
  - "projeto"
steps:
  - action: goto
    url: "${url}"
    description: "Navegação inicial"
  - action: checkpoint
    name: "visao_geral"
    expected_behavior: "A tela deve carregar perfeitamente"
`;

        try {
            const res = await apiFetch("/api/scenarios", {
                method: "POST",
                body: JSON.stringify({
                    filename,
                    yaml_content: template,
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                showToast(`Erro ao criar: ${err.detail || "Conflito de arquivo"}`, "error");
                return;
            }

            closeModals();
            showToast(`Cenário '${filename}' criado com sucesso!`, "success");
            await loadScenarios();
            selectScenario(id);
        } catch (err) {
            showToast(`Falha ao criar: ${err.message}`, "error");
        }
    }

    // --- 11. Alternância de Abas e Modais ---
    function switchMainTab(tabName) {
        state.activeTab = tabName;
        document.querySelectorAll(".nav-tab").forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.tab === tabName);
        });

        document.getElementById("view-editor")?.classList.toggle("active", tabName === "scenarios");
        document.getElementById("view-history")?.classList.toggle("active", tabName === "history");
        document.getElementById("view-settings")?.classList.toggle("active", tabName === "settings");

        if (tabName === "history") loadHistoryResults();
        if (tabName === "settings") loadGlobalConfig();
    }

    function switchInspectorTab(inspTabName) {
        state.activeInspTab = inspTabName;
        document.querySelectorAll(".insp-tab").forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.inspTab === inspTabName);
        });

        document.getElementById("insp-panel-preview")?.classList.toggle("active", inspTabName === "preview");
        document.getElementById("insp-panel-live")?.classList.toggle("active", inspTabName === "live");
    }

    function openModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) modal.classList.add("active");
    }

    function closeModals() {
        document.querySelectorAll(".modal-overlay").forEach((m) => m.classList.remove("active"));
    }

    // --- 12. Inicialização e Event Listeners Globais ---
    function initEventListeners() {
        // Topbar Nav Tabs
        document.querySelectorAll(".nav-tab").forEach((tab) => {
            tab.addEventListener("click", () => switchMainTab(tab.dataset.tab));
        });

        // Inspector Tabs
        document.querySelectorAll(".insp-tab").forEach((tab) => {
            tab.addEventListener("click", () => switchInspectorTab(tab.dataset.inspTab));
        });

        // Busca e Filtros
        document.getElementById("scenario-search")?.addEventListener("input", (e) => {
            state.searchQuery = e.target.value;
            filterAndRenderScenarios();
        });

        document.querySelectorAll(".tag-pill").forEach((pill) => {
            pill.addEventListener("click", () => {
                document.querySelectorAll(".tag-pill").forEach((p) => p.classList.remove("active"));
                pill.classList.add("active");
                state.activeFilter = pill.dataset.filter;
                filterAndRenderScenarios();
            });
        });

        // Editor YAML
        const codeEditor = document.getElementById("yaml-code-editor");
        if (codeEditor) {
            codeEditor.addEventListener("input", () => {
                state.isDirty = true;
                setSaveStatus("modified");
                updateLineNumbers();

                // Debounce de Validação em Linha (300ms)
                clearTimeout(state.validationTimer);
                state.validationTimer = setTimeout(() => validateYaml(codeEditor.value), 300);

                // Debounce de Autosave (1000ms)
                clearTimeout(state.autosaveTimer);
                state.autosaveTimer = setTimeout(() => {
                    if (state.isDirty) saveScenario();
                }, 1000);
            });

            codeEditor.addEventListener("scroll", syncEditorScroll);

            // Suporte a indentação com Tab
            codeEditor.addEventListener("keydown", (e) => {
                if (e.key === "Tab") {
                    e.preventDefault();
                    const start = codeEditor.selectionStart;
                    const end = codeEditor.selectionEnd;
                    codeEditor.value = codeEditor.value.substring(0, start) + "  " + codeEditor.value.substring(end);
                    codeEditor.selectionStart = codeEditor.selectionEnd = start + 2;
                    codeEditor.dispatchEvent(new Event("input"));
                }
            });
        }

        // Atalho Global Ctrl+S / Cmd+S
        window.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                e.preventDefault();
                saveScenario();
            }
        });

        // Botões do Editor
        document.getElementById("btn-run-scenario")?.addEventListener("click", runScenarioExecution);
        document.getElementById("btn-save-scenario")?.addEventListener("click", saveScenario);
        document.getElementById("btn-delete-scenario")?.addEventListener("click", deleteScenario);

        // Modais de Criação e IA
        document.getElementById("btn-open-create-modal")?.addEventListener("click", () => openModal("modal-create-scenario"));
        document.getElementById("btn-open-ai-modal")?.addEventListener("click", () => openModal("modal-ai-assistant"));
        document.getElementById("btn-confirm-create-scenario")?.addEventListener("click", confirmCreateScenario);
        document.getElementById("btn-submit-ai-prompt")?.addEventListener("click", submitAiPrompt);
        document.getElementById("btn-apply-ai-yaml")?.addEventListener("click", applyAiGeneratedYaml);

        document.querySelectorAll("[data-close-modal]").forEach((btn) => {
            btn.addEventListener("click", closeModals);
        });

        // Histórico
        document.getElementById("btn-refresh-history")?.addEventListener("click", loadHistoryResults);

        // Configurações
        document.getElementById("btn-save-config")?.addEventListener("click", saveGlobalConfig);
        document.getElementById("btn-test-ai")?.addEventListener("click", testAIConnection);
        document.getElementById("btn-test-jira")?.addEventListener("click", testJiraConnection);

        // Terminal
        document.getElementById("btn-clear-logs")?.addEventListener("click", () => {
            const logs = document.getElementById("terminal-logs-window");
            if (logs) logs.innerHTML = '<div class="log-line system">[TERMINAL LIMPO]</div>';
        });
    }

    // --- 13. Boot da Aplicação ---
    async function loadVersionStatus() {
        try {
            const res = await apiFetch("/api/status");
            if (res.ok) {
                const data = await res.json();
                const v = data.studio_version || data.core_version;
                if (v) {
                    const el = document.getElementById("version-display");
                    if (el) el.textContent = `v${v}`;
                }
            }
        } catch (_) {}
    }

    async function initApp() {
        initSessionToken();
        initEventListeners();
        loadVersionStatus();
        await loadScenarios();
    }

    document.addEventListener("DOMContentLoaded", initApp);
})();
