# Imagem oficial do Playwright com Python (Debian/Ubuntu LTS jammy)
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Evita que o Python gere arquivos .pyc e força logs em tempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências do sistema necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Garante a instalação do navegador Chromium no Playwright
RUN playwright install chromium

# Copia o código da aplicação
COPY . .

# Cria pasta de dados para o perfil do navegador e banco de dados SQLite
RUN mkdir -p data/browser_profile data/logs

# Expõe a porta do painel Web HTTP
EXPOSE 8088

# Comando padrão: inicia a API e o painel Web
CMD ["python", "main.py"]
