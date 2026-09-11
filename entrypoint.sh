#!/bin/bash
set -e

echo "🚀 Iniciando ambiente visual Ubuntu Desktop para o UXSentinel..."

# Cria diretórios necessários
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# Inicia o servidor X virtual (Xvfb)
Xvfb :1 -screen 0 ${VNC_RESOLUTION}x24 &
sleep 2

# Inicia o ambiente gráfico leve XFCE4
startxfce4 &
sleep 2

# Inicia o servidor x11vnc sem senha para fácil acesso local
x11vnc -display :1 -forever -shared -nopw -rfbport 5901 &
sleep 1

# Inicia o noVNC (permitindo abrir o desktop diretamente no navegador em http://localhost:6080/vnc.html)
websockify --web /usr/share/novnc 6080 localhost:5901 &
sleep 1

echo "===================================================================="
echo "🖥️  Ubuntu Desktop pronto!"
echo "🌐 Acesse a tela no seu navegador em: http://localhost:6080/vnc.html"
echo "🔌 Ou conecte seu cliente VNC local em: localhost:5901"
echo "🛡️  Para rodar o agente no terminal do container:"
echo "    docker exec -it uxsentinel_desktop uxsentinel --scenario scenarios/exemplo_web_geral.yaml"
echo "===================================================================="

# Se foi passado um comando customizado, executa-o; caso contrário, mantém o container vivo
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    tail -f /dev/null
fi
