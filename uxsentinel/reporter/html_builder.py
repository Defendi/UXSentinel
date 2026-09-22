import base64
from pathlib import Path

from jinja2 import Environment

from uxsentinel.core.models import TestReport

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório UXSentinel - {{ report.scenario_title }}</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-alt: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #06b6d4;
            --border: #334155;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 2rem;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header {
            background: var(--surface);
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
            border: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }
        .title-area { display: flex; align-items: center; gap: 1.25rem; }
        .header-logo {
            height: 60px;
            width: auto;
            border-radius: 8px;
            object-fit: contain;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
            background: rgba(255, 255, 255, 0.05);
            padding: 4px;
            border: 1px solid var(--border);
        }
        .title-area h1 { font-size: 1.8rem; margin-bottom: 0.3rem; display: flex; align-items: center; gap: 0.5rem; }
        .meta-info { color: var(--text-muted); font-size: 0.9rem; }
        .badge {
            display: inline-block;
            padding: 0.35rem 0.8rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge-success { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
        .badge-danger { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
        .badge-warning { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
        .badge-info { background: rgba(6, 182, 212, 0.2); color: #38bdf8; border: 1px solid rgba(6, 182, 212, 0.4); }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .metric-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1.2rem;
            text-align: center;
        }
        .metric-val { font-size: 2rem; font-weight: 700; margin-bottom: 0.2rem; }
        .metric-label { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; }

        .checkpoint-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        .checkpoint-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.75rem;
        }
        .checkpoint-title { font-size: 1.3rem; font-weight: 600; }
        .expected-box {
            background: rgba(59, 130, 246, 0.1);
            border-left: 4px solid var(--primary);
            padding: 1rem;
            border-radius: 4px;
            margin-bottom: 1.5rem;
            font-size: 0.95rem;
        }
        .checkpoint-body {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }
        @media (max-width: 900px) {
            .checkpoint-body { grid-template-columns: 1fr; }
        }
        .screenshot-box img {
            width: 100%;
            height: auto;
            border-radius: 8px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            cursor: pointer;
            transition: transform 0.2s;
        }
        .screenshot-box img:hover { transform: scale(1.01); }

        .issues-list { display: flex; flex-direction: column; gap: 1rem; }
        .issue-item {
            background: var(--surface-alt);
            border-radius: 8px;
            padding: 1rem;
            border-left: 4px solid var(--border);
        }
        .issue-item.bloqueante { border-left-color: var(--danger); }
        .issue-item.alta { border-left-color: #f97316; }
        .issue-item.media { border-left-color: var(--warning); }
        .issue-item.baixa { border-left-color: var(--info); }
        .issue-top { display: flex; justify-content: space-between; margin-bottom: 0.5rem; }
        .issue-desc { font-weight: 500; margin-bottom: 0.5rem; }
        .issue-fix {
            font-size: 0.85rem;
            color: #cbd5e1;
            background: rgba(0,0,0,0.2);
            padding: 0.5rem;
            border-radius: 4px;
        }
        .no-issues {
            color: #34d399;
            background: rgba(16, 185, 129, 0.1);
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
            font-weight: 500;
        }
        .viewport-filter-btn {
            background: var(--surface-alt);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.45rem 1rem;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.2s ease;
        }
        .viewport-filter-btn:hover {
            border-color: var(--primary);
            background: rgba(59, 130, 246, 0.15);
        }
        .viewport-filter-btn.active {
            background: var(--primary);
            border-color: var(--primary);
            color: #fff;
            font-weight: 600;
            box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
        }

        /* Slider Comparativo Visual (Antes vs Depois) */
        .slider-wrapper {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        .slider-view-tabs {
            display: flex;
            gap: 0.4rem;
            flex-wrap: wrap;
        }
        .slider-tab-btn {
            background: var(--surface-alt);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.35rem 0.7rem;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.8rem;
            font-weight: 500;
            transition: all 0.2s ease;
        }
        .slider-tab-btn:hover {
            border-color: var(--primary);
        }
        .slider-tab-btn.active {
            background: var(--primary);
            border-color: var(--primary);
            color: #fff;
            font-weight: 600;
        }
        .visual-slider-box {
            position: relative;
            width: 100%;
            overflow: hidden;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: #000;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
            user-select: none;
            --slider-pos: 50%;
        }
        .slider-baseline-img {
            display: block;
            width: 100%;
            height: auto;
            pointer-events: none;
        }
        .slider-current-wrap {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            clip-path: inset(0 0 0 var(--slider-pos));
            overflow: hidden;
            pointer-events: none;
        }
        .slider-current-img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: contain;
            pointer-events: none;
        }
        .slider-divider {
            position: absolute;
            top: 0;
            bottom: 0;
            left: var(--slider-pos);
            width: 3px;
            background: #e11d48;
            transform: translateX(-50%);
            pointer-events: none;
            box-shadow: 0 0 10px rgba(225, 29, 72, 0.85);
            z-index: 5;
        }
        .slider-handle-btn {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 34px;
            height: 34px;
            background: #e11d48;
            color: #fff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: bold;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.7);
            border: 2px solid #fff;
        }
        .slider-input-range {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            margin: 0;
            opacity: 0;
            cursor: ew-resize;
            z-index: 10;
            -webkit-appearance: none;
        }
        .slider-floating-badge {
            position: absolute;
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            z-index: 6;
            pointer-events: none;
            box-shadow: 0 2px 6px rgba(0,0,0,0.6);
        }
        .badge-before {
            top: 12px;
            left: 12px;
            background: rgba(15, 23, 42, 0.88);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.5);
        }
        .badge-after {
            top: 12px;
            right: 12px;
            background: rgba(225, 29, 72, 0.88);
            color: #fff;
            border: 1px solid rgba(225, 29, 72, 0.6);
        }
        .diff-view-panel {
            width: 100%;
            display: none;
        }
        .diff-view-panel img {
            width: 100%;
            height: auto;
            border-radius: 8px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-area">
                {% if logo_base64 %}
                    <img src="{{ logo_base64 }}" alt="UXSentinel" class="header-logo">
                {% endif %}
                <div>
                    <h1>🛡️ UXSentinel QA Report</h1>
                    <div class="meta-info">
                        Cenário: <strong>{{ report.scenario_title }}</strong> (ID: {{ report.scenario_id }}) |
                        Perfil: <strong>{{ report.profile }}</strong> |
                        Provedor IA: <strong>{{ report.provider_used }}</strong> |
                        Duração: <strong>{{ "%.1f"|format(report.duration_seconds) }}s</strong>
                        {% if report.viewports_tested %} | Viewports: <strong>{{ report.viewports_tested|join(', ') }}</strong>{% endif %}
                    </div>
                </div>
            </div>
            <div>
                {% if report.success %}
                    <span class="badge badge-success">✓ Aprovado</span>
                {% else %}
                    <span class="badge badge-danger">✗ Problemas Encontrados</span>
                {% endif %}
            </div>
        </header>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-val">{{ report.total_issues }}</div>
                <div class="metric-label">Total de Issues</div>
            </div>
            <div class="metric-card" style="color: #f87171;">
                <div class="metric-val">{{ report.total_bloqueantes }}</div>
                <div class="metric-label">Bloqueantes</div>
            </div>
            <div class="metric-card" style="color: #fb923c;">
                <div class="metric-val">{{ report.total_altas }}</div>
                <div class="metric-label">Alta Severidade</div>
            </div>
            <div class="metric-card" style="color: #fde047;">
                <div class="metric-val">{{ report.total_medias }}</div>
                <div class="metric-label">Média Severidade</div>
            </div>
            <div class="metric-card" style="color: #38bdf8;">
                <div class="metric-val">{{ report.total_baixas }}</div>
                <div class="metric-label">Baixa Severidade</div>
            </div>
            {% if report.a11y_score is not none %}
            <div class="metric-card" style="color: {% if report.a11y_score >= 90 %}#34d399{% elif report.a11y_score >= 70 %}#fbbf24{% else %}#f87171{% endif %}; border: 1px solid {% if report.a11y_score >= 90 %}rgba(52, 211, 153, 0.3){% elif report.a11y_score >= 70 %}rgba(251, 191, 36, 0.3){% else %}rgba(248, 113, 113, 0.3){% endif %};">
                <div class="metric-val">{{ "%.1f"|format(report.a11y_score) }}%</div>
                <div class="metric-label">A11y Score (WCAG 2.2)</div>
                <div style="background: rgba(255,255,255,0.1); border-radius: 999px; height: 6px; width: 80%; margin: 0.4rem auto 0; overflow: hidden;">
                    <div style="width: {{ report.a11y_score }}%; height: 100%; background: {% if report.a11y_score >= 90 %}#10b981{% elif report.a11y_score >= 70 %}#f59e0b{% else %}#ef4444{% endif %}; border-radius: 999px;"></div>
                </div>
            </div>
            {% endif %}
            {% if report.css_audit %}
            <div class="metric-card" style="color: {% if report.css_audit.score >= 90 %}#34d399{% elif report.css_audit.score >= 70 %}#fbbf24{% else %}#f87171{% endif %}; border: 1px solid {% if report.css_audit.score >= 90 %}rgba(52, 211, 153, 0.3){% elif report.css_audit.score >= 70 %}rgba(251, 191, 36, 0.3){% else %}rgba(248, 113, 113, 0.3){% endif %};">
                <div class="metric-val">{{ "%.1f"|format(report.css_audit.score) }}</div>
                <div class="metric-label">CSS Score (UXS-47)</div>
                <div style="background: rgba(255,255,255,0.1); border-radius: 999px; height: 6px; width: 80%; margin: 0.4rem auto 0; overflow: hidden;">
                    <div style="width: {{ report.css_audit.score }}%; height: 100%; background: {% if report.css_audit.score >= 90 %}#10b981{% elif report.css_audit.score >= 70 %}#f59e0b{% else %}#ef4444{% endif %}; border-radius: 999px;"></div>
                </div>
            </div>
            {% endif %}
            {% if report.healed_steps %}
            <div class="metric-card" style="color: #fbbf24;">
                <div class="metric-val">{{ report.healed_steps|length }}</div>
                <div class="metric-label">Auto-Curados (Self-Healing)</div>
            </div>
            {% endif %}
            {% if report.semantic_steps %}
            <div class="metric-card" style="color: #a855f7; border: 1px solid rgba(168, 85, 247, 0.3);">
                <div class="metric-val">{{ report.semantic_steps|length }}</div>
                <div class="metric-label">Ações Semânticas (IA)</div>
            </div>
            {% endif %}
            {% if report.total_console_errors > 0 %}
            <div class="metric-card" style="color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3);">
                <div class="metric-val">{{ report.total_console_errors }}</div>
                <div class="metric-label">Erros Console (JS)</div>
            </div>
            {% endif %}
            {% if report.total_console_warnings > 0 %}
            <div class="metric-card" style="color: #fbbf24;">
                <div class="metric-val">{{ report.total_console_warnings }}</div>
                <div class="metric-label">Avisos Console (JS)</div>
            </div>
            {% endif %}
            {% if report.performance_metrics and report.performance_metrics.load_time_ms > 0 %}
            <div class="metric-card" style="color: #38bdf8;">
                <div class="metric-val">{{ "%.0f"|format(report.performance_metrics.load_time_ms) }}ms</div>
                <div class="metric-label">Load (TTFB {{ "%.0f"|format(report.performance_metrics.ttfb_ms) }}ms)</div>
            </div>
            {% endif %}
        </div>

        {% if video_rel_path or gif_rel_path %}
        <div class="checkpoint-card" style="border-left: 4px solid var(--primary);">
            <div class="checkpoint-header">
                <div class="checkpoint-title">🎬 Gravação de Sessão e Evidência Dinâmica</div>
                <div style="display: flex; gap: 0.5rem;">
                    {% if video_rel_path %}
                        <a href="{{ video_rel_path }}" target="_blank" class="badge badge-info" style="text-decoration: none;">⬇️ Baixar Vídeo</a>
                    {% endif %}
                    {% if gif_rel_path %}
                        <a href="{{ gif_rel_path }}" target="_blank" class="badge badge-warning" style="text-decoration: none;">⬇️ Baixar GIF</a>
                    {% endif %}
                </div>
            </div>
            <div style="display: grid; grid-template-columns: {% if video_rel_path and gif_rel_path %}1fr 1fr{% else %}1fr{% endif %}; gap: 1.5rem; padding-top: 0.5rem;">
                {% if video_rel_path %}
                <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                    <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-muted);">🎥 Player de Vídeo HTML5:</div>
                    <video controls preload="metadata" style="width: 100%; border-radius: 8px; border: 1px solid var(--border); background: #000; max-height: 460px;">
                        <source src="{{ video_rel_path }}" type="video/webm">
                        <source src="{{ video_rel_path }}" type="video/mp4">
                        Seu navegador não suporta reprodução de vídeo nativa.
                    </video>
                </div>
                {% endif %}
                {% if gif_rel_path %}
                <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                    <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-muted);">🎞️ Resumo Animado (GIF):</div>
                    <a href="{{ gif_rel_path }}" target="_blank" title="Clique para abrir GIF em nova aba">
                        <img src="{{ gif_rel_path }}" alt="Resumo Animado da Sessão" style="width: 100%; border-radius: 8px; border: 1px solid var(--border); max-height: 460px; object-fit: contain; background: rgba(0,0,0,0.3);">
                    </a>
                </div>
                {% endif %}
            </div>
        </div>
        {% endif %}

        {% if report.healed_steps %}
        <div class="checkpoint-card" style="border-left: 4px solid #f59e0b;">
            <div class="checkpoint-header">
                <div class="checkpoint-title">⚡ Seletores Recuperados Dinamicamente (Self-Healing)</div>
                <div><span class="badge badge-warning">{{ report.healed_steps|length }} Auto-Curas</span></div>
            </div>
            <div style="padding: 1rem 0;">
                <p style="color: var(--text-muted); margin-bottom: 1rem;">
                    Os seletores abaixo sofreram TimeoutError durante a execução e foram recuperados com sucesso pelas camadas de Acessibilidade ou Visão LMM.
                </p>
                <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                    {% for step in report.healed_steps %}
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 8px; padding: 1rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <strong>Passo {{ step.step_index or 'N/A' }}: <code>{{ step.action }}</code></strong>
                            <span class="badge badge-info">{{ step.strategy }}</span>
                        </div>
                        <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 0.25rem;">
                            Seletor Original: <code style="color: #f87171; text-decoration: line-through;">{{ step.original_selector }}</code>
                        </div>
                        <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 0.25rem;">
                            Destino Recuperado: <code style="color: #34d399;">{{ step.recovered_selector or step.coordinates }}</code>
                        </div>
                        {% if step.yaml_fix_suggestion %}
                        <div style="font-size: 0.85rem; background: rgba(0,0,0,0.3); padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; font-family: monospace; color: #fbbf24;">
                            Sugestão YAML: {{ step.yaml_fix_suggestion }}
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        {% endif %}

        {% if report.semantic_steps %}
        <div class="checkpoint-card" style="border-left: 4px solid #a855f7;">
            <div class="checkpoint-header">
                <div class="checkpoint-title">🤖 Ações Semânticas em Linguagem Natural (ai_action)</div>
                <div><span class="badge badge-info" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4);">{{ report.semantic_steps|length }} Ações Executadas</span></div>
            </div>
            <div style="padding: 1rem 0;">
                <p style="color: var(--text-muted); margin-bottom: 1rem;">
                    Passos semânticos declarativos interpretados e resolvidos em tempo de execução via Árvore de Acessibilidade e Visão Multimodal LMM.
                </p>
                <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                    {% for step in report.semantic_steps %}
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 8px; padding: 1rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap; gap: 0.5rem;">
                            <div>
                                <span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); margin-right: 0.5rem;">Passo {{ step.step_index or 'N/A' }}</span>
                                <strong style="font-size: 1.05rem; font-family: monospace; color: #38bdf8;">{{ step.action }}</strong>
                            </div>
                            <div style="display: flex; gap: 0.5rem; align-items: center;">
                                {% if step.strategy %}
                                <span class="badge badge-info">{{ step.strategy }}</span>
                                {% endif %}
                                {% if step.passed %}
                                <span class="badge badge-success">Aprovado</span>
                                {% else %}
                                <span class="badge badge-danger">Reprovado</span>
                                {% endif %}
                            </div>
                        </div>
                        <div style="font-size: 0.95rem; margin-bottom: 0.35rem;">
                            <span style="color: var(--text-muted);">Alvo Declarativo:</span>
                            <strong style="color: #f8fafc;">"{{ step.target }}"</strong>
                            {% if step.value %}
                            <span style="color: var(--text-muted); margin-left: 0.5rem;">Valor:</span>
                            <code style="color: #34d399; background: rgba(0,0,0,0.3); padding: 0.2rem 0.4rem; border-radius: 4px;">{{ step.value }}</code>
                            {% endif %}
                        </div>
                        {% if step.resolved_selector or step.coordinates %}
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.25rem;">
                            {% if step.resolved_selector %}
                            <span>Seletor Resolvido: <code style="color: #38bdf8;">{{ step.resolved_selector }}</code></span>
                            {% endif %}
                            {% if step.coordinates %}
                            <span style="margin-left: 0.5rem;">Coordenadas: <code style="color: #fbbf24;">({{ step.coordinates.x }}, {{ step.coordinates.y }})</code></span>
                            {% endif %}
                            {% if step.confidence %}
                            <span style="margin-left: 0.5rem;">Confiança: <span style="color: #34d399;">{{ "%.0f"|format(step.confidence * 100) }}%</span></span>
                            {% endif %}
                        </div>
                        {% endif %}
                        {% if step.reasoning %}
                        <div style="font-size: 0.85rem; background: rgba(0,0,0,0.25); border-left: 3px solid #a855f7; padding: 0.5rem 0.75rem; border-radius: 0 4px 4px 0; margin-top: 0.5rem; color: #cbd5e1;">
                            <strong>Justificativa Cognitiva:</strong> {{ step.reasoning }}
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        {% endif %}

        {% if report.console_logs or report.network_failures or report.performance_metrics %}
        <div class="checkpoint-card" style="border-left: 4px solid #06b6d4;">
            <div class="checkpoint-header">
                <div class="checkpoint-title">🖥️ Diagnósticos da Aplicação: Console Chromium & Performance (W3C)</div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    {% if report.total_console_errors > 0 %}
                        <span class="badge badge-danger">{{ report.total_console_errors }} Erro(s) JS</span>
                    {% endif %}
                    {% if report.total_console_warnings > 0 %}
                        <span class="badge badge-warning">{{ report.total_console_warnings }} Aviso(s) JS</span>
                    {% endif %}
                    {% if report.network_failures %}
                        <span class="badge badge-danger">{{ report.network_failures|length }} Falha(s) Rede</span>
                    {% endif %}
                </div>
            </div>

            {% if report.performance_metrics %}
            <div style="margin-top: 1rem;">
                <div style="font-weight: 600; font-size: 0.95rem; color: #38bdf8; margin-bottom: 0.6rem;">⚡ Métricas de Navegação e Carregamento (W3C Navigation Timing):</div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem;">
                    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; text-align: center;">
                        <div style="font-size: 1.3rem; font-weight: 700; color: #38bdf8;">{{ "%.0f"|format(report.performance_metrics.load_time_ms) }} ms</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Page Load Total</div>
                    </div>
                    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; text-align: center;">
                        <div style="font-size: 1.3rem; font-weight: 700; color: #34d399;">{{ "%.0f"|format(report.performance_metrics.ttfb_ms) }} ms</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Time to First Byte (TTFB)</div>
                    </div>
                    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; text-align: center;">
                        <div style="font-size: 1.3rem; font-weight: 700; color: #fbbf24;">{{ "%.0f"|format(report.performance_metrics.dom_interactive_ms) }} ms</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">DOM Interactive</div>
                    </div>
                    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; text-align: center;">
                        <div style="font-size: 1.3rem; font-weight: 700; color: #cbd5e1;">{{ "%.0f"|format(report.performance_metrics.dns_time_ms) }} ms</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">DNS Lookup</div>
                    </div>
                    <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; text-align: center;">
                        <div style="font-size: 1.3rem; font-weight: 700; color: #cbd5e1;">{{ "%.0f"|format(report.performance_metrics.tcp_time_ms) }} ms</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">TCP / SSL Connect</div>
                    </div>
                </div>
            </div>
            {% endif %}

            {% if report.network_failures %}
            <div style="margin-top: 1rem;">
                <div style="font-weight: 600; font-size: 0.95rem; color: #f87171; margin-bottom: 0.6rem;">🌐 Requisições de Rede com Falha (HTTP):</div>
                <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; text-align: left;">
                        <thead>
                            <tr style="background: rgba(239, 68, 68, 0.1); border-bottom: 1px solid var(--border);">
                                <th style="padding: 0.6rem 0.8rem;">Método</th>
                                <th style="padding: 0.6rem 0.8rem;">Status</th>
                                <th style="padding: 0.6rem 0.8rem;">URL</th>
                                <th style="padding: 0.6rem 0.8rem;">Erro / Diagnóstico</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for net in report.network_failures %}
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <td style="padding: 0.5rem 0.8rem;"><span class="badge badge-info" style="font-size: 0.7rem;">{{ net.method }}</span></td>
                                <td style="padding: 0.5rem 0.8rem;"><span class="badge badge-danger" style="font-size: 0.7rem;">{{ net.status or 'ERR' }}</span></td>
                                <td style="padding: 0.5rem 0.8rem; font-family: monospace; color: #94a3b8; word-break: break-all;">{{ net.url }}</td>
                                <td style="padding: 0.5rem 0.8rem; color: #f87171;">{{ net.error_text or 'Falha' }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endif %}

            {% if report.console_logs %}
            <div style="margin-top: 1.25rem;">
                <div style="font-weight: 600; font-size: 0.95rem; color: #fbbf24; margin-bottom: 0.6rem;">📜 Mensagens e Logs Capturados do Console (Chromium DevTools):</div>
                <div style="background: rgba(0,0,0,0.35); border: 1px solid var(--border); border-radius: 8px; max-height: 380px; overflow-y: auto; font-family: monospace; font-size: 0.82rem;">
                    {% for c_log in report.console_logs %}
                    <div style="padding: 0.45rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; gap: 0.75rem; align-items: flex-start; {% if c_log.type in ['error', 'critical'] %}background: rgba(239, 68, 68, 0.08); color: #fca5a5;{% elif c_log.type in ['warn', 'warning'] %}background: rgba(245, 158, 11, 0.08); color: #fde047;{% else %}color: #cbd5e1;{% endif %}">
                        <span style="font-weight: 700; text-transform: uppercase; font-size: 0.72rem; min-width: 65px;">[{{ c_log.type }}]</span>
                        <div style="flex: 1; word-break: break-word;">{{ c_log.text }}</div>
                        {% if c_log.location %}
                        <span style="font-size: 0.72rem; color: var(--text-muted); white-space: nowrap;">{{ c_log.location }}</span>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

        </div>
        {% endif %}

        {% set unique_viewports = [] %}
        {% for cp in report.checkpoints %}
            {% if cp.viewport and cp.viewport not in unique_viewports %}
                {% set _ = unique_viewports.append(cp.viewport) %}
            {% endif %}
        {% endfor %}

        {% if unique_viewports|length > 1 or (unique_viewports|length == 1 and unique_viewports[0]) %}
        <div class="viewport-filter-container" style="background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.5rem; margin-bottom: 2rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-size: 1.2rem;">📱</span>
                <strong style="font-size: 0.95rem;">Filtrar Checkpoints por Viewport / Resolução:</strong>
            </div>
            <div class="viewport-filters" style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                <button type="button" class="viewport-filter-btn active" data-filter="all" onclick="filterViewport('all')">
                    Todas as Resoluções ({{ report.checkpoints|length }})
                </button>
                {% for vp in unique_viewports %}
                <button type="button" class="viewport-filter-btn" data-filter="{{ vp }}" onclick="filterViewport('{{ vp }}')">
                    {% if 'mobile' in vp|lower %}📱{% elif 'tablet' in vp|lower %}📟{% else %}🖥️{% endif %} {{ vp }}
                </button>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% for cp in report.checkpoints %}
        <div class="checkpoint-card" data-viewport="{{ cp.viewport or 'default' }}">
            <div class="checkpoint-header">
                <div class="checkpoint-title">
                    📍 Checkpoint: {{ cp.name }}
                    {% if cp.viewport %}
                        <span class="badge badge-info" style="margin-left: 0.5rem; font-size: 0.8rem;">
                            {% if 'mobile' in cp.viewport|lower %}📱{% elif 'tablet' in cp.viewport|lower %}📟{% else %}🖥️{% endif %} {{ cp.viewport }}
                        </span>
                    {% endif %}
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                    {% if cp.visual_diff %}
                        {% if cp.visual_diff.has_diff %}
                            <span class="badge badge-danger" style="background: rgba(225, 29, 72, 0.2); color: #fb7185; border: 1px solid rgba(225, 29, 72, 0.5);">
                                ⚡ Regressão Visual: {{ "%.2f"|format(cp.visual_diff.diff_percentage) }}% diff
                            </span>
                        {% else %}
                            <span class="badge badge-success" style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4);">
                                👁️ Baseline Conforme ({{ "%.2f"|format(cp.visual_diff.diff_percentage) }}% diff)
                            </span>
                        {% endif %}
                    {% endif %}
                    {% if cp.status == 'ok' %}
                        <span class="badge badge-success">Conforme</span>
                    {% elif cp.status == 'problemas_encontrados' %}
                        <span class="badge badge-warning">{{ cp.issues|length }} Problemas</span>
                    {% else %}
                        <span class="badge badge-danger">Erro de Execução</span>
                    {% endif %}
                </div>
            </div>

            <div class="expected-box">
                <strong>Comportamento Esperado da Regra:</strong><br>
                {{ cp.expected_behavior }}
            </div>

            {% if cp.a11y_score is not none %}
            <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 8px; padding: 0.85rem 1.25rem; margin-bottom: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                    <span style="font-size: 1.4rem;">♿</span>
                    <div>
                        <div style="font-size: 0.95rem; font-weight: 600;">Auditoria Axe-Core (WCAG 2.2 AA)</div>
                        <div style="font-size: 0.8rem; color: var(--text-muted);">
                            {% if cp.a11y_violations %}
                                <span style="color: #f87171; font-weight: 600;">{{ cp.a11y_violations|length }} violação(ões) detectada(s)</span>
                            {% else %}
                                <span style="color: #34d399; font-weight: 600;">100% Conforme às diretrizes WCAG 2.2 AA</span>
                            {% endif %}
                        </div>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <div style="text-align: right;">
                        <span style="font-size: 1.3rem; font-weight: 700; color: {% if cp.a11y_score >= 90 %}#34d399{% elif cp.a11y_score >= 70 %}#fbbf24{% else %}#f87171{% endif %};">
                            {{ "%.1f"|format(cp.a11y_score) }}%
                        </span>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">A11y Score</div>
                    </div>
                </div>
            </div>
            {% endif %}

            <div class="checkpoint-body">
                <div class="screenshot-box">
                    {% if cp.visual_diff and cp.visual_diff.baseline_path %}
                    <div class="slider-wrapper">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.25rem;">
                            <div class="slider-view-tabs">
                                <button type="button" class="slider-tab-btn active" onclick="switchViewMode(this, 'slider')">
                                    🎚️ Slider Antes / Depois
                                </button>
                                {% if cp.visual_diff.diff_image_path %}
                                <button type="button" class="slider-tab-btn" onclick="switchViewMode(this, 'diff')">
                                    🎭 Máscara de Diff (Highlight)
                                </button>
                                {% endif %}
                                <button type="button" class="slider-tab-btn" onclick="switchViewMode(this, 'current')">
                                    📸 Captura Atual
                                </button>
                                <button type="button" class="slider-tab-btn" onclick="switchViewMode(this, 'baseline')">
                                    📌 Baseline Homologado
                                </button>
                            </div>
                            <div>
                                {% if cp.visual_diff.has_diff %}
                                    <span class="badge badge-danger" style="font-size: 0.75rem; background: rgba(225, 29, 72, 0.25); color: #fb7185; border: 1px solid rgba(225, 29, 72, 0.6);">
                                        Divergência: {{ "%.2f"|format(cp.visual_diff.diff_percentage) }}%
                                    </span>
                                {% else %}
                                    <span class="badge badge-success" style="font-size: 0.75rem;">
                                        Conforme: {{ "%.2f"|format(cp.visual_diff.diff_percentage) }}%
                                    </span>
                                {% endif %}
                            </div>
                        </div>

                        <!-- Visual Slider Split-View (Vanilla CSS / JS) -->
                        <div class="visual-slider-box" id="slider-box-{{ loop.index }}">
                            <span class="slider-floating-badge badge-before">Antes (Baseline)</span>
                            <span class="slider-floating-badge badge-after">Depois (Atual)</span>

                            <img src="{{ rel_url(cp.visual_diff.baseline_path) }}" class="slider-baseline-img" alt="Baseline {{ cp.name }}">

                            <div class="slider-current-wrap">
                                <img src="{{ rel_url(cp.screenshot_path) }}" class="slider-current-img" alt="Atual {{ cp.name }}">
                            </div>

                            <div class="slider-divider">
                                <div class="slider-handle-btn">↔</div>
                            </div>

                            <input type="range" min="0" max="100" value="50" class="slider-input-range" aria-label="Slider comparativo antes e depois" oninput="onSliderInput(this, 'slider-box-{{ loop.index }}')">
                        </div>

                        <!-- Painel Máscara Diff (Highlight #E11D48) -->
                        {% if cp.visual_diff.diff_image_path %}
                        <div class="diff-view-panel diff-panel-diff">
                            <a href="{{ rel_url(cp.visual_diff.diff_image_path) }}" target="_blank" title="Clique para ampliar máscara de diff">
                                <img src="{{ rel_url(cp.visual_diff.diff_image_path) }}" alt="Máscara de Diff {{ cp.name }}">
                            </a>
                            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.35rem;">
                                Pixels alterados destacados na cor de alto contraste <code>#E11D48</code>.
                            </div>
                        </div>
                        {% endif %}

                        <!-- Painel Atual -->
                        <div class="diff-view-panel diff-panel-current">
                            <a href="{{ rel_url(cp.screenshot_path) }}" target="_blank" title="Clique para ampliar captura atual">
                                <img src="{{ rel_url(cp.screenshot_path) }}" alt="Captura Atual {{ cp.name }}">
                            </a>
                        </div>

                        <!-- Painel Baseline -->
                        <div class="diff-view-panel diff-panel-baseline">
                            <a href="{{ rel_url(cp.visual_diff.baseline_path) }}" target="_blank" title="Clique para ampliar baseline homologado">
                                <img src="{{ rel_url(cp.visual_diff.baseline_path) }}" alt="Baseline Homologado {{ cp.name }}">
                            </a>
                        </div>
                    </div>
                    {% elif cp.screenshot_path %}
                        <a href="{{ rel_url(cp.screenshot_path) }}" target="_blank" title="Clique para ampliar em nova aba">
                            <img src="{{ rel_url(cp.screenshot_path) }}" alt="Screenshot {{ cp.name }}">
                        </a>
                    {% else %}
                        <p style="color: var(--text-muted); text-align: center; padding: 2rem;">Sem imagem registrada.</p>
                    {% endif %}
                </div>

                <div class="issues-list">
                    {% if cp.issues %}
                        {% for issue in cp.issues %}
                        <div class="issue-item {{ issue.severidade.value }}">
                            <div class="issue-top">
                                <div>
                                    <span class="badge badge-{{ 'danger' if issue.severidade.value in ['bloqueante', 'alta'] else 'warning' if issue.severidade.value == 'media' else 'info' }}">
                                        {{ issue.severidade.value }}
                                    </span>
                                    {% if issue.viewport %}
                                        <span class="badge badge-info" style="font-size: 0.75rem; margin-left: 0.25rem;">
                                            {% if 'mobile' in issue.viewport|lower %}📱{% elif 'tablet' in issue.viewport|lower %}📟{% else %}🖥️{% endif %} {{ issue.viewport }}
                                        </span>
                                    {% endif %}
                                    {% if issue.evaluator %}
                                        <span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); font-size: 0.75rem; margin-left: 0.25rem;">
                                            🤖 {{ issue.evaluator }}
                                        </span>
                                    {% endif %}
                                </div>
                                <span style="font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase;">
                                    🏷️ {{ issue.categoria.value }}
                                </span>
                            </div>
                            <div class="issue-desc">{{ issue.descricao }}</div>
                            {% if issue.elemento_alvo %}
                                <div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.3rem;">
                                    <strong>Elemento:</strong> <code>{{ issue.elemento_alvo }}</code>
                                </div>
                            {% endif %}
                            {% if issue.sugestao_correcao %}
                                <div class="issue-fix">
                                    💡 <strong>Correção Sugerida:</strong> {{ issue.sugestao_correcao }}
                                </div>
                            {% endif %}
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="no-issues">
                            🎉 Nenhuma inconformidade encontrada! Tela em plena conformidade visual e de regras.
                        </div>
                    {% endif %}
                </div>
            </div>

            {% if cp.a11y_violations %}
            <div style="margin-top: 1.5rem; background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem;">
                <div style="font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem; display: flex; align-items: center; justify-content: space-between;">
                    <span>♿ Detalhamento de Violações de Acessibilidade (Axe-Core)</span>
                    <span class="badge badge-warning">{{ cp.a11y_violations|length }} regra(s) violada(s)</span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                    {% for v in cp.a11y_violations %}
                    <div style="background: var(--surface); border: 1px solid var(--border); border-left: 4px solid {% if v.impact == 'critical' %}var(--danger){% elif v.impact == 'serious' %}#f97316{% elif v.impact == 'moderate' %}var(--warning){% else %}var(--info){% endif %}; border-radius: 6px; padding: 0.85rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; flex-wrap: wrap; gap: 0.5rem;">
                            <div>
                                <span class="badge badge-{% if v.impact in ['critical', 'serious'] %}danger{% elif v.impact == 'moderate' %}warning{% else %}info{% endif %}" style="font-size: 0.75rem;">
                                    {% if v.impact == 'critical' %}CRÍTICO{% elif v.impact == 'serious' %}GRAVE{% elif v.impact == 'moderate' %}MODERADO{% elif v.impact == 'minor' %}LEVE{% else %}{{ v.impact }}{% endif %}
                                </span>
                                <strong style="margin-left: 0.4rem; font-size: 0.9rem;">{{ v.id }}</strong>
                            </div>
                            {% if v.help_url %}
                            <a href="{{ v.help_url }}" target="_blank" style="font-size: 0.8rem; color: #38bdf8; text-decoration: none;" title="Ver especificação técnica WCAG / Deque">
                                📖 Especificação Deque/WCAG ↗
                            </a>
                            {% endif %}
                        </div>
                        <div style="font-size: 0.85rem; color: #cbd5e1; margin-bottom: 0.4rem;">
                            {{ v.help or v.description }}
                        </div>
                        {% if v.tags %}
                        <div style="display: flex; gap: 0.3rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
                            {% for tag in v.tags %}
                            <span style="font-size: 0.7rem; background: rgba(255,255,255,0.05); padding: 0.15rem 0.4rem; border-radius: 4px; color: var(--text-muted);">
                                #{{ tag }}
                            </span>
                            {% endfor %}
                        </div>
                        {% endif %}
                        {% if v.nodes %}
                        <div style="font-size: 0.8rem; background: rgba(0,0,0,0.3); border-radius: 4px; padding: 0.5rem;">
                            <div style="color: var(--text-muted); margin-bottom: 0.2rem;"><strong>Alvo CSS:</strong> <code>{{ v.nodes[0].target|join(' > ') }}</code></div>
                            {% if v.nodes[0].html %}
                            <div style="margin-bottom: 0.2rem; font-family: monospace; color: #94a3b8; overflow-x: auto; white-space: pre-wrap; max-height: 80px;">{{ v.nodes[0].html }}</div>
                            {% endif %}
                            {% if v.nodes[0].failure_summary %}
                            <div style="color: #fbbf24; font-size: 0.75rem; margin-top: 0.3rem;">💡 {{ v.nodes[0].failure_summary }}</div>
                            {% endif %}
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            {% if cp.css_audit and cp.css_audit.violations %}
            <div style="margin-top: 1.5rem; background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem;">
                <div style="font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem; display: flex; align-items: center; justify-content: space-between;">
                    <span>🎨 Auditoria Profunda de CSS (UXS-47) — Score: {{ "%.1f"|format(cp.css_audit.score) }}/100</span>
                    <span class="badge badge-info">{{ cp.css_audit.violations|length }} violação(ões)</span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                    {% for cv in cp.css_audit.violations %}
                    <div style="background: var(--surface); border: 1px solid var(--border); border-left: 4px solid {% if cv.severity.value == 'bloqueante' %}var(--danger){% elif cv.severity.value == 'alta' %}#f97316{% elif cv.severity.value == 'media' %}var(--warning){% else %}var(--info){% endif %}; border-radius: 6px; padding: 0.85rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; flex-wrap: wrap; gap: 0.5rem;">
                            <div>
                                <span class="badge badge-{% if cv.severity.value in ['bloqueante', 'alta'] %}danger{% elif cv.severity.value == 'media' %}warning{% else %}info{% endif %}" style="font-size: 0.75rem;">
                                    {{ cv.severity.value|upper }}
                                </span>
                                <strong style="margin-left: 0.4rem; font-size: 0.9rem;">{{ cv.rule_id }}</strong>
                                <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.3rem;">({{ cv.category.value }})</span>
                            </div>
                            <span style="font-size: 0.75rem; color: var(--text-muted);">Origem: <code>{{ cv.source }}</code></span>
                        </div>
                        <div style="font-size: 0.85rem; color: #cbd5e1; margin-bottom: 0.4rem;">
                            {{ cv.description }}
                        </div>
                        {% if cv.selector or cv.snippet %}
                        <div style="font-size: 0.8rem; background: rgba(0,0,0,0.3); border-radius: 4px; padding: 0.5rem; margin-bottom: 0.3rem;">
                            {% if cv.selector %}
                            <div style="color: var(--text-muted); margin-bottom: 0.2rem;"><strong>Seletor:</strong> <code>{{ cv.selector }}</code></div>
                            {% endif %}
                            {% if cv.snippet %}
                            <div style="font-family: monospace; color: #94a3b8; overflow-x: auto; white-space: pre-wrap;">{{ cv.snippet }}</div>
                            {% endif %}
                        </div>
                        {% endif %}
                        {% if cv.suggestion %}
                        <div style="color: #34d399; font-size: 0.8rem; background: rgba(16, 185, 129, 0.1); border-radius: 4px; padding: 0.4rem 0.6rem;">
                            💡 <strong>Sugestão:</strong> {{ cv.suggestion }}
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    <script>
        function onSliderInput(input, containerId) {
            const container = document.getElementById(containerId);
            if (container) {
                container.style.setProperty('--slider-pos', input.value + '%');
            }
        }

        function switchViewMode(btn, targetMode) {
            const parent = btn.closest('.screenshot-box');
            if (!parent) return;

            parent.querySelectorAll('.slider-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const sliderBox = parent.querySelector('.visual-slider-box');
            const diffBox = parent.querySelector('.diff-panel-diff');
            const currentBox = parent.querySelector('.diff-panel-current');
            const baselineBox = parent.querySelector('.diff-panel-baseline');

            if (sliderBox) sliderBox.style.display = targetMode === 'slider' ? 'block' : 'none';
            if (diffBox) diffBox.style.display = targetMode === 'diff' ? 'block' : 'none';
            if (currentBox) currentBox.style.display = targetMode === 'current' ? 'block' : 'none';
            if (baselineBox) baselineBox.style.display = targetMode === 'baseline' ? 'block' : 'none';
        }

        function filterViewport(viewport) {
            const buttons = document.querySelectorAll('.viewport-filter-btn');
            buttons.forEach(btn => {
                if (btn.getAttribute('data-filter') === viewport) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
            const cards = document.querySelectorAll('.checkpoint-card[data-viewport]');
            cards.forEach(card => {
                if (viewport === 'all' || card.getAttribute('data-viewport') === viewport) {
                    card.style.display = '';
                } else {
                    card.style.display = 'none';
                }
            });
        }
    </script>
</body>
</html>
"""


def get_logo_base64() -> str:
    """Busca o logo oficial do UXSentinel e converte para string base64 data-URI."""
    candidates = [
        Path(__file__).resolve().parent.parent / "assets" / "logo.png",
        Path(__file__).resolve().parent.parent.parent / "images" / "logo.png",
        Path.cwd() / "images" / "logo.png",
        Path(__file__).resolve().parent.parent / "assets" / "logo_completa.png",
        Path(__file__).resolve().parent.parent.parent / "images" / "logo_completa.png",
        Path.cwd() / "images" / "logo_completa.png",
    ]
    for p in candidates:
        if p.is_file():
            try:
                data = p.read_bytes()
                encoded = base64.b64encode(data).decode("ascii")
                return f"data:image/png;base64,{encoded}"
            except Exception:
                continue
    return ""


def build_html_report(
    report: TestReport,
    video_rel_path: str | None = None,
    gif_rel_path: str | None = None,
    output_dir: str | Path | None = None,
) -> str:
    """Renderiza a string HTML do dashboard com os dados do relatório."""
    out_p = Path(output_dir) if output_dir else None

    def rel_url(p: str | None) -> str:
        if not p:
            return ""
        if out_p:
            try:
                return str(Path(p).resolve().relative_to(out_p.resolve()))
            except Exception:
                try:
                    return str(Path(p).relative_to(out_p))
                except Exception:
                    pass
        return str(p)

    logo_data = get_logo_base64()
    template = Environment(autoescape=True).from_string(HTML_TEMPLATE)
    return template.render(
        report=report,
        logo_base64=logo_data,
        video_rel_path=video_rel_path,
        gif_rel_path=gif_rel_path,
        rel_url=rel_url,
    )


def save_html_report(report: TestReport, output_dir: str) -> Path:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / f"{report.scenario_id}_report.html"

    video_rel: str | None = None
    if report.video_path:
        vp = Path(report.video_path)
        try:
            video_rel = str(vp.relative_to(out_path))
        except ValueError:
            video_rel = str(vp)

    gif_rel: str | None = None
    if report.gif_path:
        gp = Path(report.gif_path)
        try:
            gif_rel = str(gp.relative_to(out_path))
        except ValueError:
            gif_rel = str(gp)

    rendered_html = build_html_report(
        report=report,
        video_rel_path=video_rel,
        gif_rel_path=gif_rel,
        output_dir=out_path,
    )
    report_file.write_text(rendered_html, encoding="utf-8")
    return report_file
