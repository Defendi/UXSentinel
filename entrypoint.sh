#!/bin/bash
set -e

echo "🚀 Iniciando ambiente visual Ubuntu Desktop para o UXSentinel..."

VNC_PORT="${VNC_PORT:-5901}"
NOVNC_PORT="${NOVNC_PORT:-6080}"

# Cria diretórios necessários (já preparados na imagem; ignora falha ao rodar sem privilégios)
mkdir -p /tmp/.X11-unix 2>/dev/null || true
chmod 1777 /tmp/.X11-unix 2>/dev/null || true

# Inicia o servidor X virtual (Xvfb)
Xvfb :1 -screen 0 ${VNC_RESOLUTION}x24 &
sleep 2

# Inicia o ambiente gráfico leve XFCE4
startxfce4 &
sleep 2

# Inicia o servidor x11vnc. Com VNC_PASSWORD definido exige autenticação;
# sem senha, o acesso depende de as portas estarem publicadas apenas em 127.0.0.1.
if [ -n "${VNC_PASSWORD:-}" ]; then
    mkdir -p "$HOME/.vnc"
    x11vnc -storepasswd "$VNC_PASSWORD" "$HOME/.vnc/passwd" >/dev/null 2>&1
    VNC_AUTH_ARGS="-rfbauth $HOME/.vnc/passwd"
    VNC_AUTH_LABEL="protegido por senha"
else
    VNC_AUTH_ARGS="-nopw"
    VNC_AUTH_LABEL="sem senha (publique as portas apenas em 127.0.0.1)"
fi

x11vnc -display :1 -forever -shared $VNC_AUTH_ARGS -rfbport "$VNC_PORT" &
sleep 1

# Inicia o noVNC (permite abrir o desktop diretamente no navegador)
websockify --web /usr/share/novnc "$NOVNC_PORT" "localhost:$VNC_PORT" &
sleep 1

echo "===================================================================="
echo "🖥️  Ubuntu Desktop pronto!"
echo "🌐 Acesse a tela no seu navegador em: http://localhost:${NOVNC_PORT}/vnc.html"
echo "🔌 Ou conecte seu cliente VNC local em: localhost:${VNC_PORT}"
echo "🔐 Acesso VNC: ${VNC_AUTH_LABEL}"
echo "🛡️  Para rodar o agente no terminal do container:"
echo "    docker exec -it uxsentinel_desktop uxsentinel --scenario scenarios/exemplo_web_geral.yaml"
echo "===================================================================="

# Se foi passado um comando customizado, executa-o; caso contrário, mantém o container vivo
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    tail -f /dev/null
fi
