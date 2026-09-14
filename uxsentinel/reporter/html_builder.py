import base64
from pathlib import Path

from jinja2 import Template

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
            {% if report.healed_steps %}
            <div class="metric-card" style="color: #fbbf24;">
                <div class="metric-val">{{ report.healed_steps|length }}</div>
                <div class="metric-label">Auto-Curados (Self-Healing)</div>
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
                <div>
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

            <div class="checkpoint-body">
                <div class="screenshot-box">
                    {% if cp.screenshot_path %}
                        <a href="{{ cp.screenshot_path }}" target="_blank" title="Clique para ampliar em nova aba">
                            <img src="{{ cp.screenshot_path }}" alt="Screenshot {{ cp.name }}">
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
        </div>
        {% endfor %}
    </div>

    <script>
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

    logo_data = get_logo_base64()
    template = Template(HTML_TEMPLATE)
    rendered_html = template.render(
        report=report,
        logo_base64=logo_data,
        video_rel_path=video_rel,
        gif_rel_path=gif_rel,
    )
    report_file.write_text(rendered_html, encoding="utf-8")
    return report_file
