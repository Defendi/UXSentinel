/**
 * UXSentinel Studio - Live Mission Control & SPA Engine (UXS-54 / STU-10)
 * Arquitetura reativa desacoplada, zero dependências externas, suporte offline integral.
 */

(() => {
    "use strict";

    // --- 1. Estado Central da Aplicação ---
    const state = {
        token: "",
        projects: [],
        activeProjectId: "",
        scenarios: [],
        filteredScenarios: [],
        collapsedGroups: {},
        activeScenarioId: null,
        activeScenarioData: null,
        pendingDeleteScenarioId: null,
        pendingDeleteScenarioTitle: null,
        isDirty: false,
        autosaveTimer: null,
        validationTimer: null,
        activeTab: "scenarios",
        activeInspTab: "live",
        editorViewMode: "visual",
        activeFilter: "all",
        searchQuery: "",
        currentRunId: null,
        eventSource: null,
        executionLogs: [],
        checkpointsLive: [],
        aiConnected: null,
        globalConfig: null,
        pipelineSteps: [],
        metadataModalTags: [],
        editingStepIndex: null,
        draggedStepIndex: null,
        congruenceWarnings: {},
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

    function withAuthToken(url) {
        if (!url || !state.token) return url;
        if (url.includes("token=")) return url;
        const separator = url.includes("?") ? "&" : "?";
        return `${url}${separator}token=${encodeURIComponent(state.token)}`;
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

    // --- 3. Carregamento e Gerenciamento de Projetos e Cenários ---
    async function loadProjects() {
        try {
            const res = await apiFetch("/api/projects");
            if (!res.ok) return;
            state.projects = await res.json();
            renderProjectsDropdown();
        } catch (err) {
            console.error("Falha ao carregar catálogo de projetos:", err);
        }
    }

    function renderProjectsDropdown() {
        const selectEl = document.getElementById("select-active-project");
        if (!selectEl) return;

        if (!state.projects || state.projects.length === 0) {
            selectEl.innerHTML = '<option value="" disabled selected>Nenhum projeto cadastrado</option>';
            state.activeProjectId = "";
            updateDeleteProjectButtonVisibility();
            return;
        }

        selectEl.innerHTML = '<option value="">🌐 Todos os Projetos</option>';

        let foundActive = false;
        state.projects.forEach((p) => {
            const opt = document.createElement("option");
            opt.value = p.id;
            opt.textContent = `📁 ${p.name} (${p.scenarios_count})`;
            if (state.activeProjectId && p.id === state.activeProjectId) {
                opt.selected = true;
                foundActive = true;
            } else if (!state.activeProjectId && p.is_active && !foundActive) {
                opt.selected = true;
                state.activeProjectId = p.id;
                foundActive = true;
            }
            selectEl.appendChild(opt);
        });

        if (foundActive && selectEl.value !== state.activeProjectId) {
            selectEl.value = state.activeProjectId;
        }

        updateDeleteProjectButtonVisibility();
    }

    function updateDeleteProjectButtonVisibility() {
        const btnDelete = document.getElementById("btn-open-delete-project-modal");
        if (!btnDelete) return;
        if (state.projects && state.projects.length > 0 && state.activeProjectId) {
            btnDelete.style.display = "inline-flex";
        } else {
            btnDelete.style.display = "none";
        }
    }

    function clearEditor() {
        state.activeScenarioId = null;
        state.activeScenarioData = null;
        state.isDirty = false;

        const filenameEl = document.getElementById("current-filename");
        const sourceBadge = document.getElementById("current-source-badge");
        const codeEditor = document.getElementById("yaml-code-editor");
        const btnDelete = document.getElementById("btn-delete-scenario");

        if (filenameEl) filenameEl.textContent = "Nenhum cenário selecionado";
        if (sourceBadge) sourceBadge.textContent = "-";
        if (codeEditor) {
            codeEditor.value = "";
            updateLineNumbers();
        }
        if (btnDelete) btnDelete.style.display = "none";
        renderPreviewSteps([]);
        setSaveStatus("saved");

        const browserCfg = state.globalConfig?.browser || {};
        const headlessToggle = document.getElementById("editor-execution-headless");
        const devtoolsToggle = document.getElementById("editor-execution-devtools");
        const consoleToggle = document.getElementById("editor-execution-console");
        const inspectToggle = document.getElementById("editor-execution-inspect");

        if (headlessToggle) headlessToggle.checked = Boolean(browserCfg.headless);
        if (devtoolsToggle) devtoolsToggle.checked = Boolean(browserCfg.devtools);
        if (consoleToggle) consoleToggle.checked = browserCfg.capture_console !== undefined ? Boolean(browserCfg.capture_console) : true;
        if (inspectToggle) inspectToggle.checked = Boolean(browserCfg.inspect);

        if (devtoolsToggle?.checked && headlessToggle) {
            headlessToggle.checked = false;
        }
        updateExecutionFlagsUI();
    }

    async function loadScenarios() {
        try {
            const url = state.activeProjectId
                ? `/api/scenarios?project_id=${encodeURIComponent(state.activeProjectId)}`
                : "/api/scenarios";
            const res = await apiFetch(url);
            if (!res.ok) return;
            state.scenarios = await res.json();
            filterAndRenderScenarios();

            // Se nenhum cenário estiver ativo, seleciona o primeiro
            if (!state.activeScenarioId && state.scenarios.length > 0) {
                selectScenario(state.scenarios[0].id);
            } else if (state.scenarios.length === 0 || !state.scenarios.some((s) => s.id === state.activeScenarioId)) {
                clearEditor();
            }
        } catch (err) {
            console.error("Falha ao listar cenários:", err);
        }
    }

    async function duplicateScenario(scenarioId) {
        try {
            const res = await apiFetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/duplicate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                showToast(errData.detail || "Falha ao duplicar cenário.", "error");
                return;
            }
            const data = await res.json();
            showToast("Cenário duplicado com sucesso!", "success");
            await loadScenarios();
            if (data && data.id) {
                selectScenario(data.id);
            }
        } catch (err) {
            console.error("Erro ao duplicar cenário:", err);
            showToast("Erro de comunicação ao duplicar cenário.", "error");
        }
    }

    function createScenarioItemElement(sc) {
        const li = document.createElement("li");
        li.className = `scenario-item ${sc.id === state.activeScenarioId ? "active" : ""}`;
        li.innerHTML = `
            <div class="scenario-item-header">
                <span class="scenario-item-title" title="${escapeHtml(sc.title || sc.id)}">${escapeHtml(sc.title || sc.id)}</span>
                <div class="scenario-item-actions scenario-actions">
                    <span class="scenario-item-steps">${sc.step_count || 0} passos</span>
                    <button class="btn-scenario-duplicate" data-duplicate-id="${escapeHtml(sc.id)}" title="Duplicar Cenário">📋</button>
                    <button class="btn-delete-scenario-item btn-scenario-delete" title="Excluir cenário" data-scenario-id="${escapeHtml(sc.id)}">🗑️</button>
                </div>
            </div>
            <div class="scenario-item-meta">
                <span class="scenario-item-profile">${escapeHtml(sc.profile || "generic")}</span>
                <span>•</span>
                <span>${escapeHtml(sc.filename)}</span>
            </div>
        `;

        const duplicateBtn = li.querySelector(".btn-scenario-duplicate");
        if (duplicateBtn) {
            duplicateBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                duplicateScenario(sc.id);
            });
        }

        const deleteBtn = li.querySelector(".btn-delete-scenario-item");
        if (deleteBtn) {
            deleteBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                openDeleteScenarioModal(sc.id, sc.title || sc.id);
            });
        }

        li.addEventListener("click", () => selectScenario(sc.id));
        return li;
    }

    function filterAndRenderScenarios() {
        const query = state.searchQuery.toLowerCase().trim();
        state.filteredScenarios = state.scenarios.filter((sc) => {
            const matchesQuery =
                sc.id.toLowerCase().includes(query) ||
                (sc.title && sc.title.toLowerCase().includes(query)) ||
                (sc.project_name && sc.project_name.toLowerCase().includes(query)) ||
                (sc.project_id && sc.project_id.toLowerCase().includes(query));
            if (!matchesQuery) return false;

            // Se um projeto específico estiver selecionado no dropdown, restringe todos os cenários
            if (state.activeProjectId && sc.project_id !== state.activeProjectId) {
                return false;
            }

            return true;
        });

        const treeContainer = document.getElementById("project-scenarios-tree");
        if (!treeContainer) return;

        treeContainer.innerHTML = "";

        if (!state.projects || state.projects.length === 0) {
            treeContainer.innerHTML = `
                <div class="empty-state" style="padding: 24px 16px; text-align: center; color: var(--color-text-muted); font-size: 13px;">
                    <span style="font-size: 28px; display: block; margin-bottom: 8px;">📂</span>
                    Nenhum cenário cadastrado.<br>
                    <span style="font-size: 12px; color: var(--color-text-dim);">Adicione uma pasta de projeto no botão ➕ abaixo.</span>
                </div>
            `;
            clearEditor();
            return;
        }

        if (state.filteredScenarios.length === 0) {
            treeContainer.innerHTML = `
                <div class="empty-state" style="padding: 24px 16px; text-align: center; color: var(--color-text-muted); font-size: 13px;">
                    <span style="font-size: 28px; display: block; margin-bottom: 8px;">📂</span>
                    Nenhum cenário cadastrado.<br>
                    <span style="font-size: 12px; color: var(--color-text-dim);">Adicione uma pasta de projeto no botão ➕ abaixo.</span>
                </div>
            `;
            clearEditor();
            return;
        }

        // Agrupa cenários por nome de projeto
        const projectGroups = {};
        state.filteredScenarios.forEach((sc) => {
            const grpKey = sc.project_name || sc.project_id || "Projeto Atual";
            if (!projectGroups[grpKey]) {
                projectGroups[grpKey] = [];
            }
            projectGroups[grpKey].push(sc);
        });

        // Renderiza cada grupo de projeto
        const sortedGroupKeys = Object.keys(projectGroups).sort((a, b) => a.localeCompare(b));
        sortedGroupKeys.forEach((grpName) => {
            const scenariosInGroup = projectGroups[grpName];
            const isCollapsed = !!state.collapsedGroups[grpName];

            const groupDiv = document.createElement("div");
            groupDiv.className = `scenario-group ${isCollapsed ? "collapsed" : ""}`;

            const titleDiv = document.createElement("div");
            titleDiv.className = "group-title group-collapsible";
            titleDiv.innerHTML = `
                <span><span class="group-arrow">▾</span>📁 ${escapeHtml(grpName)}</span>
                <span class="group-count">${scenariosInGroup.length}</span>
            `;

            titleDiv.addEventListener("click", () => {
                state.collapsedGroups[grpName] = !state.collapsedGroups[grpName];
                groupDiv.classList.toggle("collapsed", state.collapsedGroups[grpName]);
            });

            const ul = document.createElement("ul");
            ul.className = "scenario-list";

            scenariosInGroup.forEach((sc) => {
                const li = createScenarioItemElement(sc);
                ul.appendChild(li);
            });

            groupDiv.appendChild(titleDiv);
            groupDiv.appendChild(ul);
            treeContainer.appendChild(groupDiv);
        });
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
                sourceBadge.textContent = "Projeto";
                sourceBadge.style.color = "var(--accent-cyan)";
            }
            if (profileSelect) profileSelect.value = data.profile || "generic";
            if (codeEditor) {
                codeEditor.value = data.raw_yaml || "";
                updateLineNumbers();
            }

            if (btnDelete) {
                btnDelete.style.display = "inline-flex";
            }

            setSaveStatus("saved");
            state.pipelineSteps = (data.steps || []).map((s, idx) => ({ ...s, index: idx + 1 }));
            if (state.pipelineSteps.length === 0 && data.raw_yaml) {
                const parsed = parseScenarioYaml(data.raw_yaml);
                if (parsed.steps && parsed.steps.length > 0) {
                    state.pipelineSteps = parsed.steps;
                }
            }
            renderPipelineCards();
            validatePipelineCongruence(state.pipelineSteps);
            validateYaml(codeEditor ? codeEditor.value : "");

            // Sincroniza os toggles de execução com o cenário ou com a configuração global (UXS-76)
            const scenarioFlags = extractScenarioFlags(data);
            const browserCfg = state.globalConfig?.browser || {};

            const headlessToggle = document.getElementById("editor-execution-headless");
            const devtoolsToggle = document.getElementById("editor-execution-devtools");
            const consoleToggle = document.getElementById("editor-execution-console");
            const inspectToggle = document.getElementById("editor-execution-inspect");

            if (headlessToggle) {
                headlessToggle.checked = scenarioFlags.headless !== null
                    ? scenarioFlags.headless
                    : Boolean(browserCfg.headless);
            }
            if (devtoolsToggle) {
                devtoolsToggle.checked = scenarioFlags.devtools !== null
                    ? scenarioFlags.devtools
                    : Boolean(browserCfg.devtools);
            }
            if (consoleToggle) {
                consoleToggle.checked = scenarioFlags.capture_console !== null
                    ? scenarioFlags.capture_console
                    : (browserCfg.capture_console !== undefined ? Boolean(browserCfg.capture_console) : true);
            }
            if (inspectToggle) {
                inspectToggle.checked = scenarioFlags.inspect !== null
                    ? scenarioFlags.inspect
                    : Boolean(browserCfg.inspect);
            }

            if (devtoolsToggle?.checked && headlessToggle) {
                headlessToggle.checked = false;
            }

            updateExecutionFlagsUI();
        } catch (err) {
            console.error("Erro ao selecionar cenário:", err);
        }
    }

    // --- 4. YAML Studio Editor & Alternância de Visão (UXS-82 / STU-06) ---
    function switchEditorViewMode(mode) {
        state.editorViewMode = mode;
        const visualContainer = document.getElementById("visual-container");
        const editorContainer = document.getElementById("editor-container");
        const btnVisual = document.getElementById("btn-view-mode-visual");
        const btnCode = document.getElementById("btn-view-mode-code");

        if (mode === "visual") {
            visualContainer?.classList.remove("hidden");
            editorContainer?.classList.add("hidden");
            btnVisual?.classList.add("active");
            btnCode?.classList.remove("active");
        } else if (mode === "code") {
            editorContainer?.classList.remove("hidden");
            visualContainer?.classList.add("hidden");
            btnCode?.classList.add("active");
            btnVisual?.classList.remove("active");
            updateLineNumbers();
        }
    }

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
                if (Object.keys(state.congruenceWarnings || {}).length > 0) {
                    const firstWarn = Object.values(state.congruenceWarnings)[0];
                    valBar.className = "validation-bar warning";
                    valIcon.textContent = "⚠️";
                    valMsg.textContent = `Aviso de Congruência: ${firstWarn}`;
                } else {
                    valBar.className = "validation-bar valid";
                    valIcon.textContent = "✓";
                    valMsg.textContent = "Sintaxe YAML e sequência determinística em conformidade total.";
                }
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

        const codeEditor = document.getElementById("yaml-code-editor");
        if (!codeEditor) return;

        setSaveStatus("saving");
        try {
            const res = await apiFetch(`/api/scenarios/${encodeURIComponent(state.activeScenarioId)}`, {
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

    function openDeleteScenarioModal(scenarioId, scenarioTitle) {
        if (!scenarioId) return;
        state.pendingDeleteScenarioId = scenarioId;
        state.pendingDeleteScenarioTitle = scenarioTitle || scenarioId;

        const titleEl = document.getElementById("delete-scenario-title");
        if (titleEl) {
            titleEl.textContent = state.pendingDeleteScenarioTitle;
        }

        const linkRadio = document.querySelector('input[name="delete-scenario-mode"][value="link"]');
        if (linkRadio) {
            linkRadio.checked = true;
        }

        const warningEl = document.getElementById("delete-scenario-file-warning");
        if (warningEl) {
            warningEl.style.display = "none";
        }

        openModal("modal-delete-scenario");
    }

    // --- 5. Motor do Pipeline Visual de Cenários (UXS-83) ---

    // Parser Tolerante de YAML para Cenários do UXSentinel (Zero dependências externas)
    function parseScenarioYaml(yamlText) {
        const result = {
            id: "",
            title: "",
            description: "",
            profile: "generic",
            tags: [],
            env: {},
            steps: [],
            headless: null,
            devtools: null,
            capture_console: null,
            inspect: null,
        };

        if (!yamlText || !yamlText.trim()) return result;

        const lines = yamlText.split("\n");
        let currentSection = null;
        let currentStep = null;
        let currentListKey = null;

        // Estado para rastrear blocos escalares multilinhas (> ou |)
        let inMultilineScalar = false;
        let multilineType = ">";
        let multilineIndent = 0;
        let multilineLines = [];
        let multilineTarget = null;
        let multilineKey = "";

        function finalizeMultilineScalar() {
            if (inMultilineScalar && multilineTarget && multilineKey) {
                if (multilineType === ">") {
                    multilineTarget[multilineKey] = multilineLines.map((l) => l.trim()).filter(Boolean).join(" ");
                } else {
                    multilineTarget[multilineKey] = multilineLines.join("\n").trimEnd();
                }
            }
            inMultilineScalar = false;
            multilineTarget = null;
            multilineLines = [];
            multilineKey = "";
        }

        for (let i = 0; i < lines.length; i++) {
            const rawLine = lines[i];
            const trimmed = rawLine.trim();
            const lineIndent = rawLine.search(/\S/);

            // 1. Processamento de Bloco Escalar Multilinha ativo
            if (inMultilineScalar) {
                if (!trimmed) {
                    multilineLines.push("");
                    continue;
                }
                if (lineIndent > multilineIndent) {
                    multilineLines.push(rawLine.trim());
                    continue;
                }
                // Indentação menor ou igual à chave pai -> o bloco escalar encerrou!
                finalizeMultilineScalar();
            }

            // 2. Linhas vazias e comentários puros (#) são solenemente ignorados e NUNCA criam steps
            if (!trimmed || trimmed.startsWith("#")) continue;

            const isIndent0 = lineIndent === 0;

            if (isIndent0) {
                if (currentStep) {
                    result.steps.push(currentStep);
                    currentStep = null;
                }
                currentListKey = null;

                const colonIdx = trimmed.indexOf(":");
                if (colonIdx > 0) {
                    const key = trimmed.substring(0, colonIdx).trim();
                    let val = trimmed.substring(colonIdx + 1).trim();

                    if (val === ">" || val === "|" || val === ">-" || val === "|-") {
                        inMultilineScalar = true;
                        multilineType = val.startsWith("|") ? "|" : ">";
                        multilineIndent = lineIndent;
                        multilineTarget = result;
                        multilineKey = key;
                        multilineLines = [];
                        currentSection = null;
                        continue;
                    }

                    val = val.replace(/^["']|["']$/g, "");

                    if (key === "tags") {
                        currentSection = "tags";
                    } else if (key === "env") {
                        currentSection = "env";
                    } else if (key === "steps") {
                        currentSection = "steps";
                    } else {
                        currentSection = null;
                        if (key === "id") result.id = val;
                        else if (key === "title") result.title = val;
                        else if (key === "description") result.description = val;
                        else if (key === "profile") result.profile = val || "generic";
                        else if (key === "headless") result.headless = val === "true";
                        else if (key === "devtools") result.devtools = val === "true";
                        else if (key === "capture_console") result.capture_console = val === "true";
                        else if (key === "inspect") result.inspect = val === "true";
                    }
                }
                continue;
            }

            if (currentSection === "tags") {
                if (trimmed.startsWith("- ")) {
                    const tagVal = trimmed.substring(2).trim().replace(/^["']|["']$/g, "");
                    if (tagVal) result.tags.push(tagVal);
                }
            } else if (currentSection === "env") {
                const colonIdx = trimmed.indexOf(":");
                if (colonIdx > 0) {
                    const envKey = trimmed.substring(0, colonIdx).trim();
                    const envVal = trimmed.substring(colonIdx + 1).trim().replace(/^["']|["']$/g, "");
                    if (envKey) result.env[envKey] = envVal;
                }
            } else if (currentSection === "steps") {
                // Um passo de steps: só deve ser iniciado se a linha começar exatamente indentada como item da lista steps ('  - ' ou indentação 2 com '- ')
                const isStepStart = rawLine.startsWith("  - ") || (lineIndent === 2 && trimmed.startsWith("- "));

                if (isStepStart) {
                    if (currentStep) {
                        result.steps.push(currentStep);
                    }
                    currentStep = {
                        index: result.steps.length + 1,
                        action: "goto",
                    };
                    currentListKey = null;

                    const rest = trimmed.substring(2).trim();
                    if (rest) {
                        const colonIdx = rest.indexOf(":");
                        if (colonIdx > 0) {
                            const k = rest.substring(0, colonIdx).trim();
                            let v = rest.substring(colonIdx + 1).trim();

                            if (v === ">" || v === "|" || v === ">-" || v === "|-") {
                                inMultilineScalar = true;
                                multilineType = v.startsWith("|") ? "|" : ">";
                                multilineIndent = lineIndent;
                                multilineTarget = currentStep;
                                multilineKey = k;
                                multilineLines = [];
                            } else {
                                v = v.replace(/^["']|["']$/g, "");
                                currentStep[k] = v;
                            }
                        }
                    }
                } else if (currentStep) {
                    // Sub-lista dentro do passo (ex: criteria de checkpoint)
                    const isSubListItem = trimmed.startsWith("- ") && lineIndent > 2;

                    if (isSubListItem) {
                        if (currentListKey) {
                            if (!Array.isArray(currentStep[currentListKey])) {
                                currentStep[currentListKey] = [];
                            }
                            const itemVal = trimmed.substring(2).trim().replace(/^["']|["']$/g, "");
                            if (itemVal) currentStep[currentListKey].push(itemVal);
                        }
                    } else {
                        const colonIdx = trimmed.indexOf(":");
                        if (colonIdx > 0) {
                            const k = trimmed.substring(0, colonIdx).trim();
                            let v = trimmed.substring(colonIdx + 1).trim();

                            if (v === "" || v === "[]") {
                                currentListKey = k;
                                currentStep[k] = [];
                                continue;
                            }

                            if (v === ">" || v === "|" || v === ">-" || v === "|-") {
                                inMultilineScalar = true;
                                multilineType = v.startsWith("|") ? "|" : ">";
                                multilineIndent = lineIndent;
                                multilineTarget = currentStep;
                                multilineKey = k;
                                multilineLines = [];
                                currentListKey = null;
                                continue;
                            }

                            currentListKey = null;
                            v = v.replace(/^["']|["']$/g, "");
                            if (k === "timeout" || k === "ms") {
                                const parsedNum = parseInt(v, 10);
                                if (!isNaN(parsedNum)) v = parsedNum;
                            } else if (v === "true") {
                                v = true;
                            } else if (v === "false") {
                                v = false;
                            }
                            currentStep[k] = v;
                        }
                    }
                }
            }
        }

        finalizeMultilineScalar();

        if (currentStep) {
            result.steps.push(currentStep);
        }

        // Filtro estrito: apenas itens válidos com action, url, selector ou name
        result.steps = (result.steps || [])
            .filter((s) => s && typeof s === "object" && (s.action || s.url || s.selector || s.name))
            .map((s, idx) => ({ ...s, index: idx + 1 }));

        return result;
    }

    // Serializador Limpo e Determinístico de Cenários para YAML
    function serializeScenarioYaml(meta, steps) {
        const out = [];
        if (meta.id) out.push(`id: "${meta.id}"`);
        if (meta.title) out.push(`title: "${meta.title}"`);
        if (meta.description) {
            if (meta.description.includes("\n")) {
                out.push(`description: >`);
                meta.description.split("\n").forEach((l) => {
                    const tl = l.trim();
                    if (tl) out.push(`  ${tl}`);
                });
            } else {
                out.push(`description: "${meta.description.replace(/"/g, '\\"')}"`);
            }
        }
        out.push(`profile: "${meta.profile || "generic"}"`);

        if (meta.tags && meta.tags.length > 0) {
            out.push("tags:");
            meta.tags.forEach((t) => out.push(`  - "${t}"`));
        }

        if (meta.env && Object.keys(meta.env).length > 0) {
            out.push("env:");
            for (const [k, v] of Object.entries(meta.env)) {
                out.push(`  ${k}: "${v}"`);
            }
        }

        if (meta.headless !== null && meta.headless !== undefined) out.push(`headless: ${Boolean(meta.headless)}`);
        if (meta.devtools !== null && meta.devtools !== undefined) out.push(`devtools: ${Boolean(meta.devtools)}`);
        if (meta.capture_console !== null && meta.capture_console !== undefined) out.push(`capture_console: ${Boolean(meta.capture_console)}`);
        if (meta.inspect !== null && meta.inspect !== undefined) out.push(`inspect: ${Boolean(meta.inspect)}`);

        out.push("steps:");
        (steps || []).forEach((step) => {
            out.push(`  - action: "${step.action || "goto"}"`);
            if (step.description) out.push(`    description: "${step.description.replace(/"/g, '\\"')}"`);
            if (step.url) out.push(`    url: "${step.url}"`);
            if (step.selector) out.push(`    selector: "${step.selector.replace(/"/g, '\\"')}"`);
            if (step.value !== undefined && step.value !== null && step.value !== "") {
                out.push(`    value: "${String(step.value).replace(/"/g, '\\"')}"`);
            }
            if (step.name) out.push(`    name: "${step.name.replace(/"/g, '\\"')}"`);
            if (step.expected_behavior) {
                if (typeof step.expected_behavior === "string" && step.expected_behavior.includes("\n")) {
                    out.push(`    expected_behavior: >`);
                    step.expected_behavior.split("\n").forEach((line) => {
                        const tl = line.trim();
                        if (tl) out.push(`      ${tl}`);
                    });
                } else {
                    out.push(`    expected_behavior: "${String(step.expected_behavior).replace(/"/g, '\\"')}"`);
                }
            }
            if (step.criteria && Array.isArray(step.criteria) && step.criteria.length > 0) {
                out.push(`    criteria:`);
                step.criteria.forEach((crit) => {
                    out.push(`      - "${String(crit).replace(/"/g, '\\"')}"`);
                });
            }
            if (step.timeout) out.push(`    timeout: ${parseInt(step.timeout, 10)}`);
            if (step.key) out.push(`    key: "${step.key}"`);
            if (step.option) out.push(`    option: "${step.option}"`);
            if (step.direction) out.push(`    direction: "${step.direction}"`);
            if (step.target) out.push(`    target: "${step.target}"`);
            if (step.wait_visible !== undefined && step.wait_visible !== null && !step.wait_visible) {
                out.push(`    wait_visible: false`);
            }
            if (step.clear !== undefined && step.clear !== null && !step.clear) {
                out.push(`    clear: false`);
            }
            if (step.focus) out.push(`    focus: "${step.focus}"`);
        });

        return out.join("\n") + "\n";
    }

    // Sincronização Bidirecional: Pipeline -> YAML
    function syncPipelineToYaml() {
        const codeEditor = document.getElementById("yaml-code-editor");
        if (!codeEditor) return;

        const currentMeta = state.activeScenarioData || {};
        const parsed = parseScenarioYaml(codeEditor.value);

        const metaToUse = {
            id: currentMeta.id || parsed.id || "cenario_sem_id",
            title: currentMeta.title || parsed.title || "Cenário de Auditoria",
            description: currentMeta.description !== undefined ? currentMeta.description : parsed.description,
            profile: currentMeta.profile || parsed.profile || "generic",
            tags: currentMeta.tags || parsed.tags || [],
            env: currentMeta.env || parsed.env || {},
            headless: currentMeta.headless !== undefined ? currentMeta.headless : parsed.headless,
            devtools: currentMeta.devtools !== undefined ? currentMeta.devtools : parsed.devtools,
            capture_console: currentMeta.capture_console !== undefined ? currentMeta.capture_console : parsed.capture_console,
            inspect: currentMeta.inspect !== undefined ? currentMeta.inspect : parsed.inspect,
        };

        const newYaml = serializeScenarioYaml(metaToUse, state.pipelineSteps);
        codeEditor.value = newYaml;
        updateLineNumbers();

        state.isDirty = true;
        setSaveStatus("modified");

        clearTimeout(state.validationTimer);
        state.validationTimer = setTimeout(() => validateYaml(newYaml), 300);
    }

    // Sincronização Bidirecional: YAML -> Pipeline
    function syncYamlToPipeline() {
        const codeEditor = document.getElementById("yaml-code-editor");
        if (!codeEditor) return;

        const parsed = parseScenarioYaml(codeEditor.value);
        if (parsed.steps) {
            state.pipelineSteps = parsed.steps;
            if (state.activeScenarioData) {
                if (parsed.id) state.activeScenarioData.id = parsed.id;
                if (parsed.title) state.activeScenarioData.title = parsed.title;
                if (parsed.description !== undefined) state.activeScenarioData.description = parsed.description;
                if (parsed.profile) state.activeScenarioData.profile = parsed.profile;
                if (parsed.tags) state.activeScenarioData.tags = parsed.tags;
                if (parsed.env) state.activeScenarioData.env = parsed.env;
            }
            renderPipelineCards();
            validatePipelineCongruence(state.pipelineSteps);
        }
    }

    // Verificador Determinístico de Congruência (UXS-83)
    function validatePipelineCongruence(steps) {
        state.congruenceWarnings = {};
        const valBar = document.getElementById("validation-feedback-bar");
        const valIcon = document.getElementById("val-icon");
        const valMsg = document.getElementById("val-message");

        if (!steps || steps.length === 0) {
            return true;
        }

        let firstWarning = null;
        let hasNavigation = false;

        const interactiveActions = ["click", "fill", "hover", "press", "scroll", "select"];

        for (let idx = 0; idx < steps.length; idx++) {
            const step = steps[idx];
            const action = (step.action || "").toLowerCase();

            // 1. Regra de Navegação: interação antes de goto
            if (action === "goto") {
                hasNavigation = true;
            } else if (interactiveActions.includes(action) && !hasNavigation) {
                const msg = `Passo #${idx + 1} (${action}): Ação interativa posicionada antes de uma navegação 'goto' inicial!`;
                state.congruenceWarnings[idx] = msg;
                if (!firstWarning) firstWarning = msg;
            }

            // 2. Regra de Checkpoints Consecutivos ou Vazios
            if (action === "checkpoint") {
                if (!step.name && !step.expected_behavior && !step.description) {
                    const msg = `Passo #${idx + 1} (checkpoint): Critérios de auditoria e nome do ponto estão vazios.`;
                    state.congruenceWarnings[idx] = msg;
                    if (!firstWarning) firstWarning = msg;
                } else if (idx > 0 && steps[idx - 1].action === "checkpoint") {
                    const prev = steps[idx - 1];
                    if (prev.name && prev.name === step.name) {
                        const msg = `Passo #${idx + 1} (checkpoint): Checkpoint redundante consecutivo com mesmo nome do passo anterior.`;
                        state.congruenceWarnings[idx] = msg;
                        if (!firstWarning) firstWarning = msg;
                    }
                }
            }

            // 3. Regra de Campos Obrigatórios
            if (action === "goto" && (!step.url || !step.url.trim())) {
                const msg = `Passo #${idx + 1} (goto): URL de destino é obrigatória.`;
                state.congruenceWarnings[idx] = msg;
                if (!firstWarning) firstWarning = msg;
            } else if ((action === "click" || action === "hover") && (!step.selector || !step.selector.trim())) {
                const msg = `Passo #${idx + 1} (${action}): Seletor do elemento alvo é obrigatório.`;
                state.congruenceWarnings[idx] = msg;
                if (!firstWarning) firstWarning = msg;
            } else if (action === "fill") {
                if (!step.selector || !step.selector.trim()) {
                    const msg = `Passo #${idx + 1} (fill): Seletor do elemento é obrigatório.`;
                    state.congruenceWarnings[idx] = msg;
                    if (!firstWarning) firstWarning = msg;
                }
            } else if (action === "press" && (!step.key || !step.key.trim())) {
                const msg = `Passo #${idx + 1} (press): Tecla a ser pressionada é obrigatória.`;
                state.congruenceWarnings[idx] = msg;
                if (!firstWarning) firstWarning = msg;
            } else if (action === "select" && (!step.selector || !step.selector.trim())) {
                const msg = `Passo #${idx + 1} (select): Seletor do dropdown é obrigatório.`;
                state.congruenceWarnings[idx] = msg;
                if (!firstWarning) firstWarning = msg;
            }
        }

        // Atualiza a barra de feedback caso haja avisos de congruência
        if (firstWarning && valBar && valIcon && valMsg) {
            valBar.className = "validation-bar warning";
            valIcon.textContent = "⚠️";
            valMsg.textContent = `Aviso de Congruência: ${firstWarning}`;
            return false;
        }

        return true;
    }

    // Renderização dos Cards do Pipeline Visual
    function renderPipelineCards() {
        const container = document.getElementById("preview-steps-list");
        const countBadge = document.getElementById("preview-step-count");
        if (!container) return;

        const rawSteps = state.pipelineSteps || [];
        const steps = rawSteps.filter((s) => s && typeof s === "object" && (s.action || s.url || s.selector || s.name));
        state.pipelineSteps = steps.map((s, idx) => ({ ...s, index: idx + 1 }));

        if (countBadge) countBadge.textContent = `${steps.length} passo${steps.length === 1 ? "" : "s"}`;

        if (steps.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <span class="empty-icon">📝</span>
                    <p>Nenhum passo estruturado neste cenário.</p>
                    <p style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">Clique no botão abaixo para adicionar a primeira ação.</p>
                </div>
            `;
            return;
        }

        const actionIcons = {
            goto: "🌐",
            click: "🖱️",
            fill: "⌨️",
            checkpoint: "📸",
            wait: "⏳",
            hover: "👆",
            press: "⚡",
            scroll: "📜",
            select: "🔽",
        };

        container.innerHTML = steps
            .map((step, idx) => {
                const action = (step.action || "goto").toLowerCase();
                const icon = actionIcons[action] || "⚡";
                const badgeClass = `step-badge badge-${action}`;
                const warningMsg = state.congruenceWarnings[idx];
                const cardWarningClass = warningMsg ? " has-congruence-warning" : "";
                const isCheckpoint = action === "checkpoint";
                const checkpointClass = isCheckpoint ? " checkpoint-card" : "";

                // Formatação de resumo
                let paramSummary = "";
                let mainTitle = step.description || "";

                if (action === "goto") {
                    paramSummary = step.url || "";
                    if (!mainTitle) mainTitle = "Navegar para URL";
                } else if (action === "fill") {
                    paramSummary = `${step.selector || ""} ➔ "${step.value || ""}"`;
                    if (!mainTitle) mainTitle = `Preencher ${step.selector || "campo"}`;
                } else if (action === "click") {
                    paramSummary = step.selector || "";
                    if (!mainTitle) mainTitle = `Clicar em ${step.selector || "elemento"}`;
                } else if (action === "hover") {
                    paramSummary = step.selector || "";
                    if (!mainTitle) mainTitle = `Passar mouse sobre ${step.selector || "elemento"}`;
                } else if (action === "press") {
                    paramSummary = `${step.key || ""}${step.selector ? ` em ${step.selector}` : ""}`;
                    if (!mainTitle) mainTitle = `Pressionar tecla ${step.key || ""}`;
                } else if (action === "select") {
                    paramSummary = `${step.selector || ""} ➔ "${step.option || step.value || ""}"`;
                    if (!mainTitle) mainTitle = `Selecionar opção em ${step.selector || "dropdown"}`;
                } else if (action === "checkpoint") {
                    mainTitle = step.name || step.description || "Auditoria Visual (Checkpoint)";
                    paramSummary = step.expected_behavior || step.instructions || step.focus || "Validação visual";
                } else if (action === "wait") {
                    paramSummary = step.timeout || step.ms ? `${step.timeout || step.ms}ms` : (step.selector || "Aguardar condição");
                    if (!mainTitle) mainTitle = "Pausa temporizada / Espera";
                } else if (action === "scroll") {
                    paramSummary = step.direction || step.target || "down";
                    if (!mainTitle) mainTitle = "Rolar página";
                }

                return `
                <div class="card-step-pipeline${checkpointClass}${cardWarningClass}"
                     draggable="true"
                     data-step-index="${idx}"
                     title="Clique para editar parâmetros do passo #${idx + 1}">
                    <div class="step-card-left">
                        <span class="drag-handle" title="Arraste para reordenar" data-drag-handle>⠿</span>
                        <div class="step-card-details">
                            <div class="step-card-meta-row">
                                <span class="${badgeClass}">${icon} ${escapeHtml(action)}</span>
                                <span class="step-summary-title">${escapeHtml(mainTitle)}</span>
                                <span class="step-number-tag">#${idx + 1}</span>
                                ${warningMsg ? `<span class="step-warning-icon" title="${escapeHtml(warningMsg)}">⚠️</span>` : ""}
                            </div>
                            ${paramSummary ? `<div class="step-param-text">${escapeHtml(paramSummary)}</div>` : ""}
                            ${step.description && mainTitle !== step.description ? `<div class="step-comment-text">💬 ${escapeHtml(step.description)}</div>` : ""}
                        </div>
                    </div>
                    <div class="step-card-actions">
                        <button type="button" class="btn-step-quick btn-step-dup" data-dup-index="${idx}" title="Duplicar Passo">📋</button>
                        <button type="button" class="btn-step-quick btn-step-del" data-del-index="${idx}" title="Excluir Passo">🗑️</button>
                    </div>
                </div>
            `;
            })
            .join("");

        // Registra listeners de Drag and Drop e Ações Rápidas nos cards
        attachPipelineCardsEvents(container);
    }

    function renderPreviewSteps(steps) {
        if (steps) {
            state.pipelineSteps = steps.map((s, idx) => ({ ...s, index: idx + 1 }));
        }
        renderPipelineCards();
    }

    function attachPipelineCardsEvents(container) {
        const cards = container.querySelectorAll(".card-step-pipeline");

        cards.forEach((card) => {
            const idx = parseInt(card.dataset.stepIndex, 10);

            // Clique no card abre o modal de edição de passos
            card.addEventListener("click", (e) => {
                if (e.target.closest(".btn-step-quick")) return;
                openStepModal(idx);
            });

            // Botão Duplicar
            card.querySelector(".btn-step-dup")?.addEventListener("click", (e) => {
                e.stopPropagation();
                duplicatePipelineStep(idx);
            });

            // Botão Excluir
            card.querySelector(".btn-step-del")?.addEventListener("click", (e) => {
                e.stopPropagation();
                deletePipelineStep(idx);
            });

            // Drag and Drop nativo HTML5
            card.addEventListener("dragstart", (e) => {
                state.draggedStepIndex = idx;
                card.classList.add("dragging");
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", String(idx));
            });

            card.addEventListener("dragover", (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                card.classList.add("drag-over");
            });

            card.addEventListener("dragleave", () => {
                card.classList.remove("drag-over");
            });

            card.addEventListener("drop", (e) => {
                e.preventDefault();
                card.classList.remove("drag-over");
                document.querySelectorAll(".card-step-pipeline").forEach((c) => c.classList.remove("dragging", "drag-over"));

                const targetIdx = idx;
                const sourceIdx = state.draggedStepIndex !== null ? state.draggedStepIndex : parseInt(e.dataTransfer.getData("text/plain"), 10);

                if (isNaN(sourceIdx) || sourceIdx === targetIdx) return;

                // Reordena o array de passos
                const movedItem = state.pipelineSteps.splice(sourceIdx, 1)[0];
                state.pipelineSteps.splice(targetIdx, 0, movedItem);

                // Reindexa
                state.pipelineSteps = state.pipelineSteps.map((s, i) => ({ ...s, index: i + 1 }));

                // Sincroniza em tempo real com o YAML
                syncPipelineToYaml();
                renderPipelineCards();
                validatePipelineCongruence(state.pipelineSteps);
                showToast(`Passo #${sourceIdx + 1} reposicionado para #${targetIdx + 1}`, "info");
            });

            card.addEventListener("dragend", () => {
                state.draggedStepIndex = null;
                document.querySelectorAll(".card-step-pipeline").forEach((c) => c.classList.remove("dragging", "drag-over"));
            });
        });
    }

    function duplicatePipelineStep(idx) {
        if (idx < 0 || idx >= state.pipelineSteps.length) return;
        const original = state.pipelineSteps[idx];
        const cloned = JSON.parse(JSON.stringify(original));
        if (cloned.name) cloned.name = `${cloned.name} (Cópia)`;
        if (cloned.description) cloned.description = `${cloned.description} (Cópia)`;

        state.pipelineSteps.splice(idx + 1, 0, cloned);
        state.pipelineSteps = state.pipelineSteps.map((s, i) => ({ ...s, index: i + 1 }));

        syncPipelineToYaml();
        renderPipelineCards();
        validatePipelineCongruence(state.pipelineSteps);
        showToast(`Passo #${idx + 1} duplicado com sucesso!`, "success");
    }

    function deletePipelineStep(idx) {
        if (idx < 0 || idx >= state.pipelineSteps.length) return;
        state.pipelineSteps.splice(idx, 1);
        state.pipelineSteps = state.pipelineSteps.map((s, i) => ({ ...s, index: i + 1 }));

        syncPipelineToYaml();
        renderPipelineCards();
        validatePipelineCongruence(state.pipelineSteps);
        showToast(`Passo #${idx + 1} removido da pipeline.`, "info");
    }

    // Modal de Metadados Iniciais do Cenário (UXS-83 / UXS-84)
    function openScenarioMetadataModal() {
        console.log("Abrindo modal de metadados do cenário");
        const codeEditor = document.getElementById("yaml-code-editor");
        let parsed = {};
        try {
            parsed = codeEditor && codeEditor.value ? parseScenarioYaml(codeEditor.value) : {};
        } catch (err) {
            console.warn("Aviso ao analisar YAML atual para metadados:", err);
            parsed = {};
        }

        const meta = state.activeScenarioData || {};

        const idField = document.getElementById("scenario-meta-id");
        const titleField = document.getElementById("scenario-meta-title");
        const descField = document.getElementById("scenario-meta-description");
        const profileField = document.getElementById("scenario-meta-profile");

        if (idField) idField.value = meta.id || parsed.id || "";
        if (titleField) titleField.value = meta.title || parsed.title || "";
        if (descField) descField.value = (meta.description !== undefined && meta.description !== null) ? meta.description : (parsed.description || "");
        if (profileField) profileField.value = meta.profile || parsed.profile || "generic";

        const rawTags = Array.isArray(meta.tags) ? meta.tags : (Array.isArray(parsed.tags) ? parsed.tags : []);
        state.metadataModalTags = [...rawTags];
        renderMetadataTags();

        const envObj = (meta.env && typeof meta.env === "object" && !Array.isArray(meta.env))
            ? meta.env
            : ((parsed.env && typeof parsed.env === "object" && !Array.isArray(parsed.env)) ? parsed.env : {});
        renderMetadataEnvRows(envObj);

        openModal("modal-scenario-metadata");
    }

    function renderMetadataTags() {
        const container = document.getElementById("scenario-meta-tags-container");
        if (!container) return;

        container.innerHTML = state.metadataModalTags
            .map((tag, idx) => `
                <span class="tag-pill">
                    ${escapeHtml(tag)}
                    <button type="button" class="tag-pill-remove" data-tag-remove="${idx}" title="Remover etiqueta">✕</button>
                </span>
            `)
            .join("");

        container.querySelectorAll(".tag-pill-remove").forEach((btn) => {
            btn.addEventListener("click", () => {
                const idx = parseInt(btn.dataset.tagRemove, 10);
                state.metadataModalTags.splice(idx, 1);
                renderMetadataTags();
            });
        });
    }

    function addMetadataTag() {
        const input = document.getElementById("scenario-meta-tag-input");
        if (!input) return;
        const val = input.value.trim();
        if (val && !state.metadataModalTags.includes(val)) {
            state.metadataModalTags.push(val);
            renderMetadataTags();
            input.value = "";
        }
    }

    function renderMetadataEnvRows(envObj) {
        const container = document.getElementById("scenario-meta-env-container");
        if (!container) return;
        container.innerHTML = "";

        const entries = Object.entries(envObj || {});
        if (entries.length === 0) {
            addMetadataEnvRow("", "");
            return;
        }

        for (const [k, v] of entries) {
            addMetadataEnvRow(k, v);
        }
    }

    function addMetadataEnvRow(key = "", val = "") {
        const container = document.getElementById("scenario-meta-env-container");
        if (!container) return;

        const row = document.createElement("div");
        row.className = "env-row";
        row.innerHTML = `
            <input type="text" placeholder="CHAVE_VAR" class="env-key-input" value="${escapeHtml(key)}">
            <span class="env-equal-sign">=</span>
            <input type="text" placeholder="valor" class="env-val-input" value="${escapeHtml(val)}">
            <button type="button" class="btn-remove-env" title="Excluir Variável">🗑️</button>
        `;

        row.querySelector(".btn-remove-env").addEventListener("click", () => {
            row.remove();
        });

        container.appendChild(row);
    }

    function saveScenarioMetadataModal() {
        const idField = document.getElementById("scenario-meta-id");
        const titleField = document.getElementById("scenario-meta-title");
        const descField = document.getElementById("scenario-meta-description");
        const profileField = document.getElementById("scenario-meta-profile");

        const newId = idField ? idField.value.trim() : "";
        const newTitle = titleField ? titleField.value.trim() : "";
        const newDesc = descField ? descField.value.trim() : "";
        const newProfile = profileField ? profileField.value : "generic";

        if (!newId) {
            showToast("O identificador único (ID) do cenário é obrigatório.", "warning");
            return;
        }

        const envObj = {};
        const rows = document.querySelectorAll("#scenario-meta-env-container .env-row");
        rows.forEach((r) => {
            const k = r.querySelector(".env-key-input")?.value.trim();
            const v = r.querySelector(".env-val-input")?.value.trim() || "";
            if (k) envObj[k] = v;
        });

        if (!state.activeScenarioData) {
            state.activeScenarioData = {};
        }

        state.activeScenarioData.id = newId;
        state.activeScenarioData.title = newTitle || newId;
        state.activeScenarioData.description = newDesc;
        state.activeScenarioData.profile = newProfile;
        state.activeScenarioData.tags = [...state.metadataModalTags];
        state.activeScenarioData.env = envObj;

        const profileSelect = document.getElementById("editor-profile-select");
        if (profileSelect) profileSelect.value = newProfile;

        syncPipelineToYaml();

        closeModal("modal-scenario-metadata");
        showToast("Metadados do cenário atualizados!", "success");
    }

    // Modal de Edição de Passos / Ações (UXS-83 / UXS-84)
    function openStepModal(stepIdx) {
        const step = (state.pipelineSteps && state.pipelineSteps[stepIdx]) ? state.pipelineSteps[stepIdx] : {};
        console.log("Abrindo modal do passo", stepIdx, step);

        state.editingStepIndex = stepIdx;
        const modal = document.getElementById("modal-step-editor");
        if (!modal) {
            console.error("Elemento modal-step-editor não encontrado!");
            return;
        }

        const titleEl = document.getElementById("step-modal-title");
        const numInput = document.getElementById("step-modal-number");
        const actionSelect = document.getElementById("step-modal-action");
        const delBtn = document.getElementById("btn-step-modal-delete");
        const commentInput = document.getElementById("step-modal-comment");

        if (titleEl) titleEl.innerHTML = "<span>✏️</span> Editar Parâmetros da Ação";
        if (delBtn) delBtn.style.display = "inline-flex";

        if (numInput) numInput.value = stepIdx + 1;
        if (actionSelect) actionSelect.value = step.action || "goto";
        if (commentInput) commentInput.value = step.description || "";

        populateStepModalFields(step);
        updateStepModalFieldVisibility();
        openModal("modal-step-editor");
    }

    function openNewStepModal() {
        console.log("Abrindo modal para novo passo no pipeline");
        clearStepModalFields();
        state.editingStepIndex = null;

        const titleEl = document.getElementById("step-modal-title");
        const numInput = document.getElementById("step-modal-number");
        const actionSelect = document.getElementById("step-modal-action");
        const delBtn = document.getElementById("btn-step-modal-delete");
        const commentInput = document.getElementById("step-modal-comment");

        if (titleEl) titleEl.innerHTML = "<span>➕</span> Adicionar Passo à Pipeline";
        if (delBtn) delBtn.style.display = "none";

        const newIndex = (state.pipelineSteps ? state.pipelineSteps.length : 0) + 1;
        if (numInput) numInput.value = newIndex;
        if (actionSelect) actionSelect.value = "goto";
        if (commentInput) commentInput.value = "";

        updateStepModalFieldVisibility();
        openModal("modal-step-editor");
    }

    function clearStepModalFields() {
        const setVal = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.value = v;
        };
        const setChk = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.checked = v;
        };

        setVal("step-field-url", "");
        setVal("step-field-timeout-goto", "");
        setVal("step-field-selector-click", "");
        setChk("step-field-wait-visible-click", true);
        setVal("step-field-timeout-click", "");
        setVal("step-field-selector-fill", "");
        setVal("step-field-value-fill", "");
        setChk("step-field-clear-fill", true);
        setVal("step-field-selector-press", "");
        setVal("step-field-key-press", "");
        setVal("step-field-selector-select", "");
        setVal("step-field-option-select", "");
        setVal("step-field-checkpoint-name", "");
        setVal("step-field-checkpoint-instructions", "");
        setVal("step-field-checkpoint-focus", "");
        setVal("step-field-wait-ms", "");
        setVal("step-field-wait-selector", "");
        setVal("step-field-scroll-direction", "");
        setVal("step-field-scroll-target", "");
    }

    function populateStepModalFields(step) {
        clearStepModalFields();
        const action = (step.action || "").toLowerCase();
        const setVal = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.value = v;
        };
        const setChk = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.checked = v;
        };

        if (action === "goto") {
            setVal("step-field-url", step.url || "");
            setVal("step-field-timeout-goto", step.timeout || "");
        } else if (action === "click" || action === "hover") {
            setVal("step-field-selector-click", step.selector || "");
            setChk("step-field-wait-visible-click", step.wait_visible !== false);
            setVal("step-field-timeout-click", step.timeout || "");
        } else if (action === "fill") {
            setVal("step-field-selector-fill", step.selector || "");
            setVal("step-field-value-fill", step.value !== undefined ? step.value : "");
            setChk("step-field-clear-fill", step.clear !== false);
        } else if (action === "press") {
            setVal("step-field-selector-press", step.selector || "");
            setVal("step-field-key-press", step.key || "");
        } else if (action === "select") {
            setVal("step-field-selector-select", step.selector || "");
            setVal("step-field-option-select", step.option || step.value || "");
        } else if (action === "checkpoint") {
            setVal("step-field-checkpoint-name", step.name || "");
            setVal("step-field-checkpoint-instructions", step.expected_behavior || step.instructions || "");
            setVal("step-field-checkpoint-focus", step.focus || step.target || "");
        } else if (action === "wait") {
            setVal("step-field-wait-ms", step.timeout || step.ms || "");
            setVal("step-field-wait-selector", step.selector || "");
        } else if (action === "scroll") {
            setVal("step-field-scroll-direction", step.direction || "");
            setVal("step-field-scroll-target", step.target || "");
        }
    }

    function updateStepModalFieldVisibility() {
        const actionSelect = document.getElementById("step-modal-action");
        if (!actionSelect) return;
        const action = actionSelect.value;

        document.querySelectorAll(".step-conditional-group").forEach((g) => g.classList.add("hidden"));

        if (action === "goto") {
            document.getElementById("step-group-goto")?.classList.remove("hidden");
        } else if (action === "click" || action === "hover") {
            document.getElementById("step-group-click-hover")?.classList.remove("hidden");
        } else if (action === "fill") {
            document.getElementById("step-group-fill")?.classList.remove("hidden");
        } else if (action === "press") {
            document.getElementById("step-group-press")?.classList.remove("hidden");
        } else if (action === "select") {
            document.getElementById("step-group-select")?.classList.remove("hidden");
        } else if (action === "checkpoint") {
            document.getElementById("step-group-checkpoint")?.classList.remove("hidden");
        } else if (action === "wait") {
            document.getElementById("step-group-wait")?.classList.remove("hidden");
        } else if (action === "scroll") {
            document.getElementById("step-group-scroll")?.classList.remove("hidden");
        }
    }

    function saveStepModal() {
        const actionSelect = document.getElementById("step-modal-action");
        const numInput = document.getElementById("step-modal-number");
        const commentInput = document.getElementById("step-modal-comment");

        const action = actionSelect ? actionSelect.value : "goto";
        const comment = commentInput ? commentInput.value.trim() : "";
        const targetNumber = numInput ? parseInt(numInput.value, 10) : 1;

        const stepData = {
            action: action,
        };
        if (comment) stepData.description = comment;

        if (action === "goto") {
            stepData.url = document.getElementById("step-field-url")?.value.trim() || "";
            const to = document.getElementById("step-field-timeout-goto")?.value.trim();
            if (to) stepData.timeout = parseInt(to, 10);
        } else if (action === "click" || action === "hover") {
            stepData.selector = document.getElementById("step-field-selector-click")?.value.trim() || "";
            const wv = document.getElementById("step-field-wait-visible-click")?.checked;
            if (!wv) stepData.wait_visible = false;
            const to = document.getElementById("step-field-timeout-click")?.value.trim();
            if (to) stepData.timeout = parseInt(to, 10);
        } else if (action === "fill") {
            stepData.selector = document.getElementById("step-field-selector-fill")?.value.trim() || "";
            stepData.value = document.getElementById("step-field-value-fill")?.value || "";
            const clr = document.getElementById("step-field-clear-fill")?.checked;
            if (!clr) stepData.clear = false;
        } else if (action === "press") {
            const sel = document.getElementById("step-field-selector-press")?.value.trim();
            if (sel) stepData.selector = sel;
            stepData.key = document.getElementById("step-field-key-press")?.value.trim() || "";
        } else if (action === "select") {
            stepData.selector = document.getElementById("step-field-selector-select")?.value.trim() || "";
            stepData.option = document.getElementById("step-field-option-select")?.value.trim() || "";
        } else if (action === "checkpoint") {
            stepData.name = document.getElementById("step-field-checkpoint-name")?.value.trim() || "";
            const instructions = document.getElementById("step-field-checkpoint-instructions")?.value.trim();
            if (instructions) stepData.expected_behavior = instructions;
            const focus = document.getElementById("step-field-checkpoint-focus")?.value.trim();
            if (focus) stepData.focus = focus;
        } else if (action === "wait") {
            const ms = document.getElementById("step-field-wait-ms")?.value.trim();
            if (ms) stepData.timeout = parseInt(ms, 10);
            const sel = document.getElementById("step-field-wait-selector")?.value.trim();
            if (sel) stepData.selector = sel;
        } else if (action === "scroll") {
            const dir = document.getElementById("step-field-scroll-direction")?.value.trim();
            if (dir) stepData.direction = dir;
            const tgt = document.getElementById("step-field-scroll-target")?.value.trim();
            if (tgt) stepData.target = tgt;
        }

        if (state.editingStepIndex === null) {
            let insertPos = isNaN(targetNumber) ? state.pipelineSteps.length : Math.max(0, targetNumber - 1);
            if (insertPos > state.pipelineSteps.length) insertPos = state.pipelineSteps.length;
            state.pipelineSteps.splice(insertPos, 0, stepData);
            showToast(`Novo passo adicionado à posição #${insertPos + 1}!`, "success");
        } else {
            const oldIdx = state.editingStepIndex;
            const newPos = isNaN(targetNumber) ? oldIdx : Math.max(0, Math.min(state.pipelineSteps.length - 1, targetNumber - 1));

            if (newPos === oldIdx) {
                state.pipelineSteps[oldIdx] = stepData;
            } else {
                state.pipelineSteps.splice(oldIdx, 1);
                state.pipelineSteps.splice(newPos, 0, stepData);
            }
            showToast(`Passo #${newPos + 1} atualizado com sucesso!`, "success");
        }

        state.pipelineSteps = state.pipelineSteps.map((s, i) => ({ ...s, index: i + 1 }));

        syncPipelineToYaml();
        renderPipelineCards();
        validatePipelineCongruence(state.pipelineSteps);
        closeModal("modal-step-editor");
    }

    function deleteStepFromModal() {
        if (state.editingStepIndex === null) return;
        const idx = state.editingStepIndex;
        deletePipelineStep(idx);
        closeModal("modal-step-editor");
    }

    // --- 5.1. Sincronização de Flags de Execução da Toolbar (UXS-74 / UXS-76) ---
    function updateExecutionFlagsUI() {
        const headlessToggle = document.getElementById("editor-execution-headless");
        const headlessLabel = document.getElementById("editor-execution-headless-label");
        const headlessContainer = document.getElementById("toggle-container-headless") || headlessToggle?.closest(".toolbar-headless-toggle");

        if (headlessToggle && headlessLabel) {
            const isHeadless = headlessToggle.checked;
            if (isHeadless) {
                headlessLabel.textContent = "Headless";
                if (headlessContainer) {
                    headlessContainer.classList.remove("headed-active");
                    headlessContainer.title = "Alternar entre modo invisível (background) e janela do navegador visível na tela";
                }
            } else {
                headlessLabel.textContent = "🖥️ Visível";
                if (headlessContainer) {
                    headlessContainer.classList.add("headed-active");
                    headlessContainer.title = "Navegador Gráfico Visível na tela (Headed). Clique para rodar em segundo plano (Headless).";
                }
            }
        }

        const devtoolsToggle = document.getElementById("editor-execution-devtools");
        const devtoolsContainer = document.getElementById("toggle-container-devtools");
        if (devtoolsToggle && devtoolsContainer) {
            if (devtoolsToggle.checked) {
                devtoolsContainer.classList.add("active");
            } else {
                devtoolsContainer.classList.remove("active");
            }
        }

        const consoleToggle = document.getElementById("editor-execution-console");
        const consoleContainer = document.getElementById("toggle-container-console");
        if (consoleToggle && consoleContainer) {
            if (consoleToggle.checked) {
                consoleContainer.classList.add("active");
            } else {
                consoleContainer.classList.remove("active");
            }
        }

        const inspectToggle = document.getElementById("editor-execution-inspect");
        const inspectContainer = document.getElementById("toggle-container-inspect");
        if (inspectToggle && inspectContainer) {
            if (inspectToggle.checked) {
                inspectContainer.classList.add("active");
            } else {
                inspectContainer.classList.remove("active");
            }
        }
    }

    function updateHeadlessToggleUI() {
        updateExecutionFlagsUI();
    }

    async function syncExecutionFlagsFromConfig(cachedConfig = null) {
        try {
            let cfg = cachedConfig || state.globalConfig;
            if (!cfg) {
                const res = await apiFetch("/api/config");
                if (res.ok) {
                    cfg = await res.json();
                    state.globalConfig = cfg;
                }
            }
            if (cfg && cfg.browser) {
                const headlessVal = Boolean(cfg.browser.headless);
                const devtoolsVal = Boolean(cfg.browser.devtools);
                const consoleVal = cfg.browser.capture_console !== undefined ? Boolean(cfg.browser.capture_console) : true;
                const inspectVal = Boolean(cfg.browser.inspect);

                const headlessCheckbox = document.getElementById("editor-execution-headless");
                const devtoolsCheckbox = document.getElementById("editor-execution-devtools");
                const consoleCheckbox = document.getElementById("editor-execution-console");
                const inspectCheckbox = document.getElementById("editor-execution-inspect");

                if (headlessCheckbox) headlessCheckbox.checked = headlessVal;
                if (devtoolsCheckbox) devtoolsCheckbox.checked = devtoolsVal;
                if (consoleCheckbox) consoleCheckbox.checked = consoleVal;
                if (inspectCheckbox) inspectCheckbox.checked = inspectVal;

                // Se o DevTools estiver ativo por padrão, Chromium exige headed
                if (devtoolsVal && headlessCheckbox) {
                    headlessCheckbox.checked = false;
                }

                updateExecutionFlagsUI();
            }
        } catch (err) {
            console.error("Erro ao sincronizar flags de execução da configuração:", err);
        }
    }

    async function syncHeadlessToggleFromConfig(cachedConfig = null) {
        return await syncExecutionFlagsFromConfig(cachedConfig);
    }

    function extractScenarioFlags(scenarioData) {
        const flags = {
            headless: null,
            devtools: null,
            capture_console: null,
            inspect: null,
        };
        if (!scenarioData) return flags;

        if (typeof scenarioData.headless === "boolean") flags.headless = scenarioData.headless;
        if (typeof scenarioData.devtools === "boolean") flags.devtools = scenarioData.devtools;
        if (typeof scenarioData.capture_console === "boolean") flags.capture_console = scenarioData.capture_console;
        else if (typeof scenarioData.console === "boolean") flags.capture_console = scenarioData.console;
        if (typeof scenarioData.inspect === "boolean") flags.inspect = scenarioData.inspect;

        if (scenarioData.raw_yaml) {
            const lines = scenarioData.raw_yaml.split("\n");
            for (const line of lines) {
                const hMatch = line.match(/^headless\s*:\s*(true|false|yes|no|1|0|on|off)\s*$/i);
                if (hMatch && flags.headless === null) {
                    const val = hMatch[1].toLowerCase();
                    flags.headless = val === "true" || val === "yes" || val === "1" || val === "on";
                }
                const dMatch = line.match(/^devtools\s*:\s*(true|false|yes|no|1|0|on|off)\s*$/i);
                if (dMatch && flags.devtools === null) {
                    const val = dMatch[1].toLowerCase();
                    flags.devtools = val === "true" || val === "yes" || val === "1" || val === "on";
                }
                const cMatch = line.match(/^(?:capture_console|console)\s*:\s*(true|false|yes|no|1|0|on|off)\s*$/i);
                if (cMatch && flags.capture_console === null) {
                    const val = cMatch[1].toLowerCase();
                    flags.capture_console = val === "true" || val === "yes" || val === "1" || val === "on";
                }
                const iMatch = line.match(/^inspect\s*:\s*(true|false|yes|no|1|0|on|off)\s*$/i);
                if (iMatch && flags.inspect === null) {
                    const val = iMatch[1].toLowerCase();
                    flags.inspect = val === "true" || val === "yes" || val === "1" || val === "on";
                }
            }
        }
        return flags;
    }

    function extractScenarioHeadless(scenarioData) {
        return extractScenarioFlags(scenarioData).headless;
    }

    // --- 6. Live Mission Control & Streaming SSE (STU-07) ---
    async function runScenarioExecution() {
        if (!state.activeScenarioId) {
            showToast("Selecione um cenário antes de executar.", "warning");
            return;
        }

        if (state.aiConnected === false) {
            showToast("⚠️ IA não conectada! Configure o provedor de IA antes de executar.", "warning");
            switchMainTab("settings");
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

        const isHeadless = document.getElementById("editor-execution-headless")?.checked ?? true;
        const isDevtools = document.getElementById("editor-execution-devtools")?.checked ?? false;
        const isConsole = document.getElementById("editor-execution-console")?.checked ?? true;
        const isInspect = document.getElementById("editor-execution-inspect")?.checked ?? false;

        appendLogLine(`[CONFIG] Modo de exibição: ${isHeadless ? "Headless (Background)" : "Navegador Gráfico Visível (Headed)"}`, "info");
        appendLogLine(`[CONFIG] Flags de depuração: DevTools=${isDevtools}, Console=${isConsole}, Inspect=${isInspect}`, "info");
        appendLogLine(`[ORQUESTRAÇÃO] Disparando execução do cenário: ${state.activeScenarioId}...`, "info");

        try {
            const res = await apiFetch("/api/execution/run", {
                method: "POST",
                body: JSON.stringify({
                    scenario_id: state.activeScenarioId,
                    overrides: {
                        headless: isHeadless,
                        devtools: isDevtools,
                        capture_console: isConsole,
                        inspect: isInspect,
                        slowmo: isHeadless ? 200 : 450,
                    },
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
        const data = eventObj.data || {};

        switch (eventType) {
            case "log": {
                const msg = data.message || (typeof data === "string" ? data : JSON.stringify(data));
                appendLogLine(msg, "info");
                break;
            }
            case "step": {
                const stepIdx = data.step_index || "?";
                const totalSteps = data.total_steps || 0;
                const action = data.action || "";
                const desc = data.description || action;
                const status = data.status || "running";

                if (liveStatus) {
                    liveStatus.textContent = desc || `Executando passo ${stepIdx}: ${action}`;
                }

                if (totalSteps > 0 && typeof data.step_index === "number") {
                    const pct = Math.min(90, Math.round(10 + (data.step_index / totalSteps) * 80));
                    if (liveProgressFill) liveProgressFill.style.width = `${pct}%`;
                    if (livePercentage) livePercentage.textContent = `${pct}%`;
                }

                if (status === "failed") {
                    appendLogLine(`[PASSO ${stepIdx}] ❌ FALHA: ${data.error || desc}`, "error");
                }
                break;
            }
            case "checkpoint": {
                appendCheckpointLive(data);
                appendLogLine(
                    `[CHECKPOINT] ${data.name || "Auditoria"} - Status: ${data.status} (Inconformidades: ${data.issues_count || 0})`,
                    (data.issues_count > 0 || data.status === "failed") ? "error" : "success"
                );
                break;
            }
            case "completed": {
                if (liveBadge) {
                    liveBadge.className = "live-badge completed";
                    liveBadge.textContent = "CONCLUÍDO";
                }
                if (liveStatus) {
                    liveStatus.textContent = `Auditoria finalizada. Duração: ${data.duration_seconds || 0}s | Issues: ${data.total_issues || 0}`;
                }
                if (liveProgressFill) liveProgressFill.style.width = "100%";
                if (livePercentage) livePercentage.textContent = "100%";

                appendLogLine(`[FINALIZADO] Auditoria concluída com sucesso! Total de inconformidades: ${data.total_issues || 0}`, "success");
                showToast("Execução da auditoria finalizada com sucesso!", "success");

                if (liveFooter && reportLink) {
                    liveFooter.style.display = "block";
                    const reportUrl = `/api/results/${state.activeScenarioId}/artifacts/${state.activeScenarioId}_report.html`;
                    reportLink.href = withAuthToken(reportUrl);
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
                const errText = data.error || (typeof data === "string" ? data : "Erro na execução");
                if (liveStatus) {
                    liveStatus.textContent = `Erro na execução: ${errText}`;
                }
                appendLogLine(`[ERRO NA EXECUÇÃO] ${errText}`, "error");
                showToast(`Erro na execução: ${errText}`, "error");

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
                    const rawHtmlUrl = r.report_html_url || `/api/results/${r.scenario_id}/artifacts/${r.scenario_id}_report.html`;
                    const htmlUrl = withAuthToken(rawHtmlUrl);

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
            state.globalConfig = cfg;

            // Localização dos Arquivos de Configuração
            if (cfg.config_files) {
                const files = cfg.config_files;

                // Arquivo Ativo
                const elActive = document.getElementById("cfg-file-active");
                if (elActive) elActive.textContent = files.active_config_path || "--";

                // Config Usuário Global
                const elUser = document.getElementById("cfg-file-user");
                const badgeUser = document.getElementById("cfg-badge-user");
                if (elUser) elUser.textContent = files.user_config_path || "--";
                if (badgeUser) {
                    badgeUser.textContent = files.user_config_exists ? "Existe (0600)" : "Padrão (Auto)";
                    badgeUser.className = `badge ${files.user_config_exists ? "badge-success" : "badge-muted"}`;
                }

                // Config Projeto
                const elProject = document.getElementById("cfg-file-project");
                const badgeProject = document.getElementById("cfg-badge-project");
                if (elProject) elProject.textContent = files.project_config_path || "Nenhum arquivo detectado";
                if (badgeProject) {
                    badgeProject.textContent = files.project_config_exists ? "Detectado" : "Não presente";
                    badgeProject.className = `badge ${files.project_config_exists ? "badge-success" : "badge-muted"}`;
                }

                // Arquivo .env
                const elEnv = document.getElementById("cfg-file-env");
                const badgeEnv = document.getElementById("cfg-badge-env");
                if (elEnv) elEnv.textContent = files.env_path || "Nenhum .env detectado";
                if (badgeEnv) {
                    badgeEnv.textContent = files.env_exists ? "Presente" : "Não presente";
                    badgeEnv.className = `badge ${files.env_exists ? "badge-success" : "badge-muted"}`;
                }

                // Diretório Raiz do Projeto
                const elProjDir = document.getElementById("cfg-file-project-dir");
                if (elProjDir) elProjDir.textContent = files.project_dir || "--";
            }

            // Provedor IA
            const provSelect = document.getElementById("cfg-active-provider");
            if (provSelect && cfg.active_provider) {
                provSelect.value = cfg.active_provider;
            }
            updateSSOButtonVisibility();

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

        const bHeadlessInput = document.getElementById("cfg-browser-headless");
        const newHeadless = bHeadlessInput ? bHeadlessInput.checked : undefined;

        try {
            const res = await apiFetch("/api/config", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            if (res.ok) {
                showToast("Configurações atualizadas com sucesso!", "success");
                if (newHeadless !== undefined) {
                    if (state.globalConfig && state.globalConfig.browser) {
                        state.globalConfig.browser.headless = newHeadless;
                    }
                    const editorHeadless = document.getElementById("editor-execution-headless");
                    if (editorHeadless) {
                        editorHeadless.checked = Boolean(newHeadless);
                        updateHeadlessToggleUI();
                    }
                }
                await checkAIStatus();
            } else {
                showToast("Erro ao persistir configurações.", "error");
            }
        } catch (err) {
            showToast(`Falha de comunicação: ${err.message}`, "error");
        }
    }

    function updateSSOButtonVisibility() {
        const provider = document.getElementById("cfg-active-provider")?.value || "";
        const ssoBtn = document.getElementById("btn-login-sso");
        if (!ssoBtn) return;
        if (provider === "claude_sso" || provider === "gemini_sso") {
            ssoBtn.style.display = "inline-flex";
        } else {
            ssoBtn.style.display = "none";
        }
    }

    async function loginSSO() {
        const provider = document.getElementById("cfg-active-provider")?.value || "claude_sso";
        const feedbackBox = document.getElementById("ai-test-feedback");
        const btn = document.getElementById("btn-login-sso");

        if (btn) btn.disabled = true;
        if (feedbackBox) {
            feedbackBox.style.display = "block";
            feedbackBox.className = "connection-feedback-box";
            feedbackBox.textContent = `Iniciando autenticação SSO (${provider}) no navegador...`;
        }

        try {
            const res = await apiFetch("/api/config/login-sso", {
                method: "POST",
                body: JSON.stringify({ provider }),
            });
            const data = await res.json();

            if (res.ok && data.success) {
                if (feedbackBox) {
                    feedbackBox.className = "connection-feedback-box success";
                    feedbackBox.textContent = `ℹ️ ${data.message}`;
                }
                showToast(data.message, "info");
                setTimeout(async () => {
                    await checkAIStatus();
                }, 1500);
            } else {
                const errMsg = data.detail || data.message || "Erro ao iniciar login SSO.";
                if (feedbackBox) {
                    feedbackBox.className = "connection-feedback-box error";
                    feedbackBox.textContent = `✕ Falha: ${errMsg}`;
                }
                showToast(`Falha no login SSO: ${errMsg}`, "error");
            }
        } catch (err) {
            if (feedbackBox) {
                feedbackBox.className = "connection-feedback-box error";
                feedbackBox.textContent = `✕ Erro: ${err.message}`;
            }
            showToast(`Erro ao conectar com servidor: ${err.message}`, "error");
        } finally {
            if (btn) btn.disabled = false;
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
                await checkAIStatus();
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

    // --- 10.5. Modo Exploratório Autônomo (Crawler - UXS-12) ---
    let crawlPollInterval = null;
    let activeCrawlJobId = null;

    async function startCrawl() {
        const urlInput = document.getElementById("crawl-url-input");
        const url = urlInput ? urlInput.value.trim() : "";
        if (!url) {
            showToast("Informe a URL inicial para iniciar a exploração.", "warning");
            return;
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            showToast("A URL inicial deve começar com http:// ou https://", "warning");
            return;
        }

        const maxDepth = parseInt(document.getElementById("crawl-max-depth")?.value, 10) || 3;
        const maxPages = parseInt(document.getElementById("crawl-max-pages")?.value, 10) || 50;
        const generateScenarios = document.getElementById("crawl-generate-scenarios")?.checked ?? true;
        const headless = document.getElementById("crawl-headless")?.checked ?? true;

        try {
            const res = await apiFetch("/api/crawl/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    url,
                    max_depth: maxDepth,
                    max_pages: maxPages,
                    generate_scenarios: generateScenarios,
                    headless,
                }),
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                showToast(`Falha ao iniciar crawl: ${errData.detail || "Erro no servidor"}`, "error");
                return;
            }

            const data = await res.json();
            activeCrawlJobId = data.job_id;

            // UI: Alterna para painel de progresso
            document.getElementById("crawl-progress-section").style.display = "block";
            document.getElementById("btn-start-crawl").style.display = "none";
            document.getElementById("btn-cancel-crawl").style.display = "inline-flex";

            // Limpa dados anteriores
            document.getElementById("crawl-visited-count").textContent = "0";
            document.getElementById("crawl-queued-count").textContent = "0";
            document.getElementById("crawl-errors-count").textContent = "0";
            document.getElementById("crawl-scenarios-count").textContent = "0";
            document.getElementById("crawl-current-url").textContent = url;
            document.getElementById("crawl-errors-box").style.display = "none";
            document.getElementById("crawl-errors-list").innerHTML = "";
            document.getElementById("crawl-results-box").style.display = "none";
            document.getElementById("crawl-scenarios-list").innerHTML = "";

            if (crawlPollInterval) clearInterval(crawlPollInterval);
            crawlPollInterval = setInterval(pollCrawlStatus, 1500);
            showToast("Exploração autônoma iniciada com sucesso!", "info");
        } catch (err) {
            showToast(`Erro na comunicação: ${err.message}`, "error");
        }
    }

    async function pollCrawlStatus() {
        if (!activeCrawlJobId) return;

        try {
            const res = await apiFetch(`/api/crawl/status/${encodeURIComponent(activeCrawlJobId)}`);
            if (!res.ok) return;

            const st = await res.json();

            // Atualiza contadores
            document.getElementById("crawl-visited-count").textContent = String(st.visited_count || 0);
            document.getElementById("crawl-queued-count").textContent = String(st.queued_count || 0);
            document.getElementById("crawl-errors-count").textContent = String((st.errors || []).length);
            document.getElementById("crawl-scenarios-count").textContent = String((st.generated_scenarios || []).length);
            if (st.current_url) {
                document.getElementById("crawl-current-url").textContent = `(Prof. ${st.current_depth}) ${st.current_url}`;
            }

            // Exibe erros detectados
            if (st.errors && st.errors.length > 0) {
                const errBox = document.getElementById("crawl-errors-box");
                const errList = document.getElementById("crawl-errors-list");
                if (errBox && errList) {
                    errBox.style.display = "block";
                    errList.innerHTML = st.errors
                        .map((err) => {
                            const isBlock = err.severity === "bloqueante";
                            const badgeColor = isBlock ? "#e63946" : "#f4a261";
                            const btText = err.backtrack_success ? "Recuo OK" : "Recuo Falhou";
                            return `<div style="padding: 4px 0; border-bottom: 1px solid #222;">
                                <span style="background: ${badgeColor}; color: #fff; font-size: 0.65rem; padding: 2px 5px; border-radius: 3px; font-weight: bold;">
                                    ${err.severity.toUpperCase()}
                                </span>
                                <span style="color: #aaa; margin-left: 6px;">[${err.error_type} - ${btText}]</span>
                                <div style="color: #eee; margin-top: 2px;">${err.url}: ${err.message}</div>
                            </div>`;
                        })
                        .join("");
                }
            }

            // Exibe cenários gerados
            if (st.generated_scenarios && st.generated_scenarios.length > 0) {
                const resBox = document.getElementById("crawl-results-box");
                const resList = document.getElementById("crawl-scenarios-list");
                if (resBox && resList) {
                    resBox.style.display = "block";
                    resList.innerHTML = st.generated_scenarios
                        .map((scPath) => {
                            const parts = scPath.split("/");
                            const filename = parts[parts.length - 1];
                            const scenarioId = filename.replace(/\.ya?ml$/, "");
                            return `<div style="display: flex; align-items: center; justify-content: space-between; background: var(--bg-card, #1c1c1c); padding: 6px 10px; border-radius: 4px; border: 1px solid var(--border-color, #333);">
                                <span style="font-size: 0.8rem; color: var(--text-color, #eee); font-family: monospace;">${filename}</span>
                                <button class="btn btn-sm btn-primary btn-open-crawl-scenario" data-scenario-id="${scenarioId}" style="padding: 3px 8px; font-size: 0.75rem;">
                                    Abrir no Editor
                                </button>
                            </div>`;
                        })
                        .join("");

                    // Adiciona listeners para abrir cenários
                    resList.querySelectorAll(".btn-open-crawl-scenario").forEach((btn) => {
                        btn.addEventListener("click", async (e) => {
                            const scId = e.currentTarget.dataset.scenarioId;
                            closeModals();
                            await loadScenarios();
                            selectScenario(scId);
                        });
                    });
                }
            }

            // Conclusão ou cancelamento
            if (st.status === "completed" || st.status === "cancelled" || st.status === "failed") {
                if (crawlPollInterval) {
                    clearInterval(crawlPollInterval);
                    crawlPollInterval = null;
                }
                document.getElementById("btn-start-crawl").style.display = "inline-flex";
                document.getElementById("btn-start-crawl").textContent = "🚀 Reiniciar Crawl";
                document.getElementById("btn-cancel-crawl").style.display = "none";
                await loadScenarios();

                if (st.status === "completed") {
                    showToast("Crawling autônomo concluído!", "success");
                } else if (st.status === "cancelled") {
                    showToast("Crawling cancelado pelo usuário.", "warning");
                } else {
                    showToast("Crawling encerrado com falhas.", "error");
                }
            }
        } catch (err) {
            console.error("Erro no polling do crawl:", err);
        }
    }

    async function cancelCrawl() {
        if (!activeCrawlJobId) return;
        try {
            const res = await apiFetch(`/api/crawl/cancel/${encodeURIComponent(activeCrawlJobId)}`, {
                method: "POST",
            });
            if (res.ok) {
                showToast("Solicitação de cancelamento enviada.", "info");
            }
        } catch (err) {
            showToast(`Falha ao cancelar: ${err.message}`, "error");
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

    function switchGlobalTab(tabName) {
        switchMainTab(tabName);
    }

    async function checkAIStatus() {
        const banner = document.getElementById("ai-status-banner");
        const bannerText = document.getElementById("ai-banner-text");
        try {
            const res = await apiFetch("/api/config/ai-status");
            if (res.ok) {
                const data = await res.json();
                state.aiConnected = Boolean(data.connected);
                if (!data.connected) {
                    if (banner) {
                        banner.style.display = "flex";
                        banner.classList.add("warning");
                    }
                    if (bannerText && data.message) bannerText.textContent = data.message;
                } else {
                    if (banner) {
                        banner.style.display = "none";
                        banner.classList.remove("warning");
                    }
                }
            } else {
                state.aiConnected = false;
                if (banner) {
                    banner.style.display = "flex";
                    banner.classList.add("warning");
                }
                if (bannerText) bannerText.textContent = "Não foi possível verificar a conectividade com a IA.";
            }
        } catch (err) {
            console.error("Erro ao verificar status da IA:", err);
            state.aiConnected = false;
            if (banner) {
                banner.style.display = "flex";
                banner.classList.add("warning");
            }
            if (bannerText) bannerText.textContent = "Erro ao conectar com o serviço de validação de IA.";
        }
    }

    function switchInspectorTab(inspTabName) {
        state.activeInspTab = inspTabName;
        document.querySelectorAll(".insp-tab").forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.inspTab === inspTabName);
        });

        document.getElementById("insp-panel-live")?.classList.toggle("active", inspTabName === "live");
    }

    function openModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add("active");
        } else {
            console.warn(`Modal com id '${modalId}' não encontrado no DOM.`);
        }
    }

    function closeModal(modalId) {
        if (modalId) {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.classList.remove("active");
                return;
            }
        }
        closeModals();
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

        // Container de Cenários: duplicação via botão da lista
        document.getElementById("project-scenarios-tree")?.addEventListener("click", (e) => {
            const dupBtn = e.target.closest(".btn-scenario-duplicate");
            if (dupBtn) {
                e.stopPropagation();
                const dupId = dupBtn.dataset.duplicateId;
                if (dupId) {
                    duplicateScenario(dupId);
                }
            }
        });

        // Editor YAML
        const codeEditor = document.getElementById("yaml-code-editor");
        if (codeEditor) {
            codeEditor.addEventListener("input", () => {
                state.isDirty = true;
                setSaveStatus("modified");
                updateLineNumbers();

                // Debounce de Sincronização YAML -> Pipeline e Validação em Linha (300ms)
                clearTimeout(state.validationTimer);
                state.validationTimer = setTimeout(() => {
                    syncYamlToPipeline();
                    validateYaml(codeEditor.value);
                }, 300);

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

        // Toggles de Execução da Toolbar (UXS-74 / UXS-76)
        const headlessToggle = document.getElementById("editor-execution-headless");
        const devtoolsToggle = document.getElementById("editor-execution-devtools");
        const consoleToggle = document.getElementById("editor-execution-console");
        const inspectToggle = document.getElementById("editor-execution-inspect");

        headlessToggle?.addEventListener("change", () => {
            if (headlessToggle.checked && devtoolsToggle?.checked) {
                devtoolsToggle.checked = false;
            }
            updateExecutionFlagsUI();
        });

        devtoolsToggle?.addEventListener("change", () => {
            if (devtoolsToggle.checked && headlessToggle) {
                // DevTools do Chromium exige modo headed (navegador visível)
                headlessToggle.checked = false;
            }
            updateExecutionFlagsUI();
        });

        consoleToggle?.addEventListener("change", updateExecutionFlagsUI);
        inspectToggle?.addEventListener("change", updateExecutionFlagsUI);

        updateExecutionFlagsUI();

        // Alternador de Visão: Visual vs Código YAML (UXS-82)
        document.getElementById("btn-view-mode-visual")?.addEventListener("click", () => switchEditorViewMode("visual"));
        document.getElementById("btn-view-mode-code")?.addEventListener("click", () => switchEditorViewMode("code"));

        document.getElementById("btn-run-scenario")?.addEventListener("click", runScenarioExecution);
        document.getElementById("btn-save-scenario")?.addEventListener("click", saveScenario);
        document.getElementById("btn-delete-scenario")?.addEventListener("click", () => {
            if (!state.activeScenarioId) return;
            const title = state.activeScenarioData?.title || state.activeScenarioId;
            openDeleteScenarioModal(state.activeScenarioId, title);
        });

        // UXS-83: Editor Visual de Pipeline e Modais
        document.getElementById("btn-edit-scenario-metadata")?.addEventListener("click", openScenarioMetadataModal);
        document.getElementById("btn-save-scenario-metadata")?.addEventListener("click", saveScenarioMetadataModal);
        document.getElementById("btn-add-tag")?.addEventListener("click", addMetadataTag);
        document.getElementById("scenario-meta-tag-input")?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                addMetadataTag();
            }
        });
        document.getElementById("btn-add-env-var")?.addEventListener("click", () => addMetadataEnvRow("", ""));

        // Delegação de evento para os cards de steps do pipeline (UXS-84)
        const previewList = document.getElementById("preview-steps-list");
        if (previewList) {
            previewList.addEventListener("click", (e) => {
                if (e.target.closest(".btn-step-quick")) return;
                const card = e.target.closest(".card-step-pipeline");
                if (card && card.dataset.stepIndex !== undefined) {
                    const idx = parseInt(card.dataset.stepIndex, 10);
                    if (!isNaN(idx)) {
                        openStepModal(idx);
                    }
                }
            });
        }

        document.getElementById("btn-add-step-footer")?.addEventListener("click", openNewStepModal);
        document.getElementById("step-modal-action")?.addEventListener("change", updateStepModalFieldVisibility);
        document.getElementById("btn-step-modal-save")?.addEventListener("click", saveStepModal);
        document.getElementById("btn-step-modal-delete")?.addEventListener("click", deleteStepFromModal);

        document.getElementById("editor-profile-select")?.addEventListener("change", (e) => {
            if (state.activeScenarioData) {
                state.activeScenarioData.profile = e.target.value;
                syncPipelineToYaml();
            }
        });

        // Seletor de Projetos
        document.getElementById("select-active-project")?.addEventListener("change", async (e) => {
            const selectedId = e.target.value;
            state.activeProjectId = selectedId;
            updateDeleteProjectButtonVisibility();
            if (selectedId) {
                try {
                    const res = await apiFetch("/api/projects/select", {
                        method: "POST",
                        body: JSON.stringify({ project_id: selectedId }),
                    });
                    if (res.ok) {
                        const data = await res.json();
                        showToast(`Projeto ativo alterado para '${data.project_name}'.`, "success");
                    }
                } catch (err) {
                    console.error("Falha ao selecionar projeto:", err);
                }
            }
            await loadScenarios();
            await checkAIStatus();
        });

        // Modal: Adicionar Projeto
        document.getElementById("btn-open-add-project-modal")?.addEventListener("click", () => {
            openModal("modal-add-project");
            document.getElementById("new-project-name")?.focus();
        });

        document.getElementById("btn-confirm-add-project")?.addEventListener("click", async () => {
            const name = document.getElementById("new-project-name")?.value.trim() || "";
            const path = document.getElementById("new-project-path")?.value.trim() || "";

            if (!path) {
                showToast("Informe o caminho absoluto da pasta do projeto.", "warning");
                return;
            }

            try {
                const res = await apiFetch("/api/projects", {
                    method: "POST",
                    body: JSON.stringify({ name, path }),
                });

                if (!res.ok) {
                    const err = await res.json();
                    showToast(err.detail || "Erro ao adicionar pasta de projeto.", "error");
                    return;
                }

                const data = await res.json();
                closeModals();
                const nameInput = document.getElementById("new-project-name");
                const pathInput = document.getElementById("new-project-path");
                if (nameInput) nameInput.value = "";
                if (pathInput) pathInput.value = "";
                showToast(`Projeto '${data.project_name}' cadastrado com sucesso!`, "success");

                await loadProjects();
                await loadScenarios();
            } catch (err) {
                showToast(`Falha de comunicação: ${err.message}`, "error");
            }
        });

        // Modal: Excluir Projeto
        document.getElementById("btn-open-delete-project-modal")?.addEventListener("click", () => {
            if (!state.activeProjectId) return;
            const currentProj = state.projects.find((p) => p.id === state.activeProjectId);
            const nameEl = document.getElementById("delete-project-name");
            if (nameEl) {
                nameEl.textContent = currentProj ? currentProj.name : state.activeProjectId;
            }
            openModal("modal-delete-project");
        });

        document.getElementById("btn-confirm-delete-project")?.addEventListener("click", async () => {
            if (!state.activeProjectId) return;
            const projIdToDelete = state.activeProjectId;

            try {
                const res = await apiFetch(`/api/projects/${encodeURIComponent(projIdToDelete)}`, {
                    method: "DELETE",
                });

                if (!res.ok) {
                    const err = await res.json();
                    showToast(err.detail || "Erro ao remover projeto do catálogo.", "error");
                    return;
                }

                const data = await res.json();
                closeModals();
                showToast(data.message || "Projeto removido com sucesso!", "success");

                state.activeProjectId = data.active_project_id || "";
                clearEditor();
                await loadProjects();
                await loadScenarios();
            } catch (err) {
                showToast(`Falha de comunicação: ${err.message}`, "error");
            }
        });

        // Modais de Criação e IA
        document.getElementById("btn-open-create-modal")?.addEventListener("click", () => openModal("modal-create-scenario"));
        document.getElementById("btn-open-ai-modal")?.addEventListener("click", () => openModal("modal-ai-assistant"));
        document.getElementById("btn-confirm-create-scenario")?.addEventListener("click", confirmCreateScenario);
        document.getElementById("btn-submit-ai-prompt")?.addEventListener("click", submitAiPrompt);
        document.getElementById("btn-apply-ai-yaml")?.addEventListener("click", applyAiGeneratedYaml);

        // Modal de Crawling Autônomo (UXS-12)
        document.getElementById("btn-open-crawl-modal")?.addEventListener("click", () => openModal("modal-crawler"));
        document.getElementById("btn-start-crawl")?.addEventListener("click", startCrawl);
        document.getElementById("btn-cancel-crawl")?.addEventListener("click", cancelCrawl);

        // Modal de Exclusão de Cenário
        document.querySelectorAll('input[name="delete-scenario-mode"]').forEach((radio) => {
            radio.addEventListener("change", (e) => {
                const warningEl = document.getElementById("delete-scenario-file-warning");
                if (warningEl) {
                    warningEl.style.display = e.target.value === "file" ? "block" : "none";
                }
            });
        });

        document.getElementById("btn-confirm-delete-scenario")?.addEventListener("click", async () => {
            if (!state.pendingDeleteScenarioId) return;

            const modeInput = document.querySelector('input[name="delete-scenario-mode"]:checked');
            const mode = modeInput ? modeInput.value : "link";
            const deleteFile = mode === "file";

            try {
                const res = await apiFetch(
                    `/api/scenarios/${encodeURIComponent(state.pendingDeleteScenarioId)}?delete_file=${deleteFile}`,
                    { method: "DELETE" }
                );

                if (res.ok) {
                    closeModals();
                    const wasActive = state.activeScenarioId === state.pendingDeleteScenarioId;
                    if (wasActive) {
                        clearEditor();
                    }
                    await loadScenarios();
                    if (deleteFile) {
                        showToast("Cenário excluído permanentemente do disco!", "info");
                    } else {
                        showToast("Cenário desvinculado do catálogo com sucesso!", "info");
                    }
                } else {
                    const errData = await res.json().catch(() => ({}));
                    showToast(errData.detail || "Erro ao excluir cenário.", "error");
                }
            } catch (err) {
                console.error("Erro ao excluir cenário:", err);
                showToast("Falha de comunicação ao excluir cenário.", "error");
            } finally {
                state.pendingDeleteScenarioId = null;
                state.pendingDeleteScenarioTitle = null;
            }
        });

        document.querySelectorAll("[data-close-modal]").forEach((btn) => {
            btn.addEventListener("click", closeModals);
        });

        // Histórico
        document.getElementById("btn-refresh-history")?.addEventListener("click", loadHistoryResults);

        // Configurações
        document.getElementById("btn-save-config")?.addEventListener("click", saveGlobalConfig);
        document.getElementById("btn-test-ai")?.addEventListener("click", testAIConnection);
        document.getElementById("btn-login-sso")?.addEventListener("click", loginSSO);
        document.getElementById("cfg-active-provider")?.addEventListener("change", updateSSOButtonVisibility);
        document.getElementById("btn-test-jira")?.addEventListener("click", testJiraConnection);
        document.getElementById("btn-banner-configure-ai")?.addEventListener("click", () => switchGlobalTab("settings"));

        // Terminal
        document.getElementById("btn-clear-logs")?.addEventListener("click", () => {
            const logs = document.getElementById("terminal-logs-window");
            if (logs) logs.innerHTML = '<div class="log-line system">[TERMINAL LIMPO]</div>';
        });

        // Splitter Redimensionável (Coluna 2 / Coluna 3) - UXS-76
        initColumnSplitter();
    }

    // Splitter Redimensionável (Coluna 2 / Coluna 3) - UXS-76
    function initColumnSplitter() {
        const splitter = document.getElementById("splitter-col2-col3");
        if (!splitter) return;

        // Recupera largura salva previamente no localStorage
        try {
            const savedWidth = localStorage.getItem("studio_inspector_width");
            if (savedWidth) {
                const parsed = parseInt(savedWidth, 10);
                if (!isNaN(parsed) && parsed >= 260 && parsed <= 700) {
                    document.documentElement.style.setProperty("--inspector-width", `${parsed}px`);
                }
            }
        } catch (_) {}

        const onMouseMove = (e) => {
            const newWidth = window.innerWidth - e.clientX;
            const maxAllowed = Math.min(700, Math.floor(window.innerWidth - 350));
            const clampedWidth = Math.max(260, Math.min(newWidth, Math.max(260, maxAllowed)));
            document.documentElement.style.setProperty("--inspector-width", `${clampedWidth}px`);
            try {
                localStorage.setItem("studio_inspector_width", String(clampedWidth));
            } catch (_) {}
        };

        const onMouseUp = () => {
            document.body.classList.remove("is-resizing");
            splitter.classList.remove("active");
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };

        splitter.addEventListener("mousedown", (e) => {
            e.preventDefault();
            document.body.classList.add("is-resizing");
            splitter.classList.add("active");
            window.addEventListener("mousemove", onMouseMove);
            window.addEventListener("mouseup", onMouseUp);
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
        await checkAIStatus();
        await syncExecutionFlagsFromConfig();
        await loadProjects();
        await loadScenarios();
    }

    document.addEventListener("DOMContentLoaded", initApp);
})();
