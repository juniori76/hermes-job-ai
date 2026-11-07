#!/bin/bash
set -e

echo "[Hermes] Iniciando serviços de display gráfico para noVNC..."

# Inicia servidor X virtual em :99
export DISPLAY=:99
Xvfb :99 -screen 0 1366x850x24 -ac &
sleep 1

# Inicia gerenciador de janelas leve
fluxbox &
sleep 1

# Inicia servidor x11vnc sem senha para acesso local/container
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -bg

# Inicia noVNC proxy na porta 6080 apontando para o VNC local porta 5900
websockify --web /usr/share/novnc/ 6080 localhost:5900 &

echo "[Hermes] Display virtual, VNC (5900) e noVNC (6080) ativos!"

# Executa o aplicativo principal Python (FastAPI + Scheduler)
exec python main.py
