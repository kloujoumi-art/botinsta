# ============================================================
#  BotInsta — Image Docker pour Render.com
#  Python 3.11 + dépendances système Chromium installées en root
# ============================================================
FROM python:3.11-slim-bookworm

# Installer les dépendances système de Chromium avec les droits root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    fonts-liberation \
    libfontconfig1 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnss3 \
    libnspr4 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installer les packages Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer le navigateur Playwright (les deps système sont déjà là)
RUN playwright install chromium

# Copier le code de l'application
COPY . .

# Créer le dossier de données (remplacé par le disque Render en production)
RUN mkdir -p /data/sessions

# Le PORT est injecté par Render via l'env var PORT
EXPOSE 10000

CMD ["python", "main.py", "--mode", "both"]
