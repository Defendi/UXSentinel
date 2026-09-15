# Dockerfile para UXSentinel em ambiente Ubuntu Desktop com interface gráfica (X11 / VNC / noVNC)
# Instalado diretamente a partir do índice oficial do PyPI
FROM ubuntu:24.04

LABEL maintainer="Equipe UXSentinel <contato@gotryx.com.br>"
LABEL description="Ubuntu Desktop com XFCE4, noVNC e Playwright para teste visual do UXSentinel via PyPI"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=pt_BR.UTF-8 \
    LANGUAGE=pt_BR:pt \
    LC_ALL=pt_BR.UTF-8 \
    DISPLAY=:1 \
    VNC_PORT=5901 \
    NOVNC_PORT=6080 \
    VNC_RESOLUTION=1440x900 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# Instalação do XFCE4, Xvfb, x11vnc, noVNC, Python 3.12 e dependências base
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    locales-all \
    xfce4 \
    xfce4-goodies \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    git \
    ca-certificates \
    dbus-x11 \
    xterm \
    && locale-gen pt_BR.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# Configuração do ambiente virtual Python
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Instalação do pacote UXSentinel diretamente do PyPI oficial e dos navegadores Playwright
RUN pip install --upgrade pip setuptools wheel && \
    pip install uxsentinel && \
    playwright install chromium --with-deps && \
    ln -sf /opt/venv/bin/uxsentinel /usr/local/bin/uxsentinel

# Script de entrada para inicializar Display virtual, XFCE4, VNC e noVNC
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# O agente roda como usuario sem privilegios; o UID 1000 do usuario 'ubuntu' ja existe
# na imagem base e casa com o UID tipico do host, preservando escrita nos volumes montados.
RUN mkdir -p /workspace /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix \
    && chown -R ubuntu:ubuntu /workspace /opt/venv \
    && chmod -R a+rX /opt/ms-playwright

WORKDIR /workspace

EXPOSE 6080 5901

USER ubuntu

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://localhost:${NOVNC_PORT}/" >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
