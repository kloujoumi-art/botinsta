#!/usr/bin/env bash
# =============================================================
#  Script de build pour Render.com (Linux Ubuntu)
#  Installe Python deps + Playwright Chromium + dépendances système
# =============================================================
set -e

echo "==> Installation des dépendances Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Installation de Playwright Chromium + dépendances système..."
playwright install --with-deps chromium

echo "==> Création des dossiers de données..."
mkdir -p /data/sessions || mkdir -p ./data/sessions

echo "==> Build terminé avec succès ✓"
