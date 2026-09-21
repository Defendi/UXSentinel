"""
Script JavaScript injetado no navegador para renderizar feedback visual ao vivo.
Gera um halo luminoso e efeito de ondulação (ripple) no ponto de clique.
"""

OVERLAY_INJECTION_SCRIPT = """
(function() {
    if (window.__uxsentinel_installed) return;
    window.__uxsentinel_installed = true;

    // Injeta estilos CSS para animação do cursor e ripples
    const style = document.createElement('style');
    style.id = '__uxsentinel_styles';
    style.innerHTML = `
        .__uxsentinel_highlight {
            outline: 3px solid #10b981 !important;
            outline-offset: 2px !important;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.6) !important;
            transition: all 0.2s ease-in-out !important;
        }
        .__uxsentinel_ripple {
            position: fixed;
            border-radius: 50%;
            background: rgba(16, 185, 129, 0.4);
            border: 2px solid #059669;
            transform: scale(0);
            animation: __uxsentinel_ripple_anim 0.6s ease-out;
            pointer-events: none;
            z-index: 9999999;
        }
        @keyframes __uxsentinel_ripple_anim {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
    `;
    const target = document.head || document.documentElement;
    if (target) {
        target.appendChild(style);
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            (document.head || document.documentElement).appendChild(style);
        });
    }

    window.__uxsentinel_show_click = function(x, y) {
        const ripple = document.createElement('div');
        ripple.className = '__uxsentinel_ripple';
        const size = 30;
        ripple.style.width = size + 'px';
        ripple.style.height = size + 'px';
        ripple.style.left = (x - size / 2) + 'px';
        ripple.style.top = (y - size / 2) + 'px';
        document.body.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
    };

    window.__uxsentinel_highlight_elem = function(el) {
        if (!el) return;
        el.classList.add('__uxsentinel_highlight');
        setTimeout(() => {
            el.classList.remove('__uxsentinel_highlight');
        }, 800);
    };
})();
"""
