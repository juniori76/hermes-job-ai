# Imagem oficial do Playwright com Python (Debian/Ubuntu LTS jammy)
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Evita que o Python gere arquivos .pyc e força logs em tempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
# EVITA QUE O APT/DEBCONF TRAVE PERGUNTANDO FUSO HORARIO (TZDATA INTERATIVO)
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/Sao_Paulo

WORKDIR /app

# Instala dependências do sistema com modo noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    xvfb \
    fluxbox \
    x11vnc \
    novnc \
    websockify \
    net-tools \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Garante a instalação do navegador Chromium no Playwright
RUN playwright install chromium

# Copia o código da aplicação
COPY . .

# Garante permissão de execução no script de inicialização
RUN chmod +x entrypoint.sh

# Cria pasta de dados para o perfil do navegador, banco de dados SQLite e screenshots
RUN mkdir -p data/browser_profile data/logs data/screenshots

# Expõe as portas: 8088 (Painel Web HTTP) e 6080 (noVNC Browser Visual)
EXPOSE 8088 6080

# Ponto de entrada que inicializa Xvfb + VNC + noVNC + FastAPI
CMD ["./entrypoint.sh"]
