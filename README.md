# BotInsta — Bot Instagram Intelligent

Bot Instagram conçu pour simuler un comportement humain naturel, avec des limites de sécurité strictes pour éviter les blocages.

---

## Structure du projet

```
botinsta/
├── main.py                  ← Point d'entrée
├── .env.example             ← Template de configuration
├── requirements.txt
│
├── config/                  ← Paramètres (chargés depuis .env)
├── core/                    ← Navigateur + anti-détection
├── actions/                 ← Login, feed, profil, follow, like, stories, reels
├── targeting/               ← Scraping et filtrage des cibles
├── safety/                  ← Limites journalières + détection d'anomalies
├── bot/                     ← Moteur principal
├── dashboard/               ← Interface web Flask
├── storage/                 ← Base de données SQLite
└── utils/                   ← Logger, simulation humaine, planificateur
```

---

## Installation

### 1. Prérequis
- Python 3.10+
- pip

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configurer le fichier .env

```bash
copy .env.example .env
```

Éditez `.env` avec vos identifiants :

```env
INSTAGRAM_USERNAME=votre_username
INSTAGRAM_PASSWORD=votre_mot_de_passe
TARGET_ACCOUNTS=compte_a_cibler1,compte_a_cibler2
HEADLESS=false
```

---

## Utilisation

### Démarrer le bot + dashboard

```bash
python main.py
```

Le dashboard est accessible sur **http://127.0.0.1:5000**

### Modes disponibles

```bash
python main.py                     # Bot + Dashboard (recommandé)
python main.py --mode bot          # Bot uniquement
python main.py --mode dashboard    # Dashboard uniquement
python main.py --headless          # Sans fenêtre de navigateur
```

---

## Configuration des limites de sécurité

Ces valeurs dans `.env` contrôlent ce que le bot fait par jour.  
**Ne pas dépasser les valeurs recommandées.**

| Variable | Défaut | Maximum recommandé |
|---|---|---|
| MAX_FOLLOWS_PER_DAY | 25 | 40 |
| MAX_LIKES_PER_DAY | 40 | 60 |
| MAX_PROFILE_VISITS_PER_DAY | 80 | 120 |
| MAX_STORIES_PER_DAY | 50 | 80 |
| MAX_REELS_PER_DAY | 30 | 50 |
| MIN_ACTION_DELAY | 4s | — |
| MAX_ACTION_DELAY | 12s | — |

---

## Dashboard

Accessible sur `http://127.0.0.1:5000` pendant l'exécution.

**Fonctionnalités :**
- Statistiques journalières en temps réel
- Journal de toutes les actions
- Liste des erreurs détectées
- Gestion des comptes cibles (ajout manuel)
- Bouton Pause / Reprendre

---

## Sécurité et recommandations

### Ce que le bot fait pour éviter la détection
- Délais variables et aléatoires entre chaque action
- Mouvements de souris simulés en courbe de Bézier
- Saisie au clavier avec délais entre chaque caractère
- Scripts JavaScript injectés pour masquer l'automatisation
- Rotation des User-Agents
- Pauses longues aléatoires (simulation de distraction)
- Arrêt automatique si captcha ou blocage détecté
- Persistance de session (cookies) pour éviter les reconnexions répétées

### Recommandations importantes
1. **Commencez doucement** : réduisez les limites de moitié les 2 premières semaines
2. **Utilisez toujours votre vrai compte** connecté à votre appareil habituel
3. **Même IP** : n'utilisez pas de VPN sauf si vous avez toujours utilisé ce VPN
4. **Proxy** : configurez `PROXY_URL` uniquement si nécessaire
5. **Horaires réalistes** : le bot s'active automatiquement aux heures définies dans `utils/scheduler.py`
6. **Surveillance** : vérifiez le dashboard régulièrement et les notifications Instagram

### Ajouter un proxy (optionnel)

Dans `.env` :
```env
PROXY_URL=http://user:password@proxy-host:port
```

---

## Personnalisation des plages horaires

Éditez `utils/scheduler.py` → `DEFAULT_ACTIVE_HOURS` :

```python
DEFAULT_ACTIVE_HOURS = [
    (7, 9),    # Matin
    (12, 14),  # Midi
    (18, 22),  # Soirée
]
```

---

## Ajouter des cibles manuellement

Via le dashboard ou directement en Python :

```python
from storage.database import add_target
add_target("username_cible", source="manual")
```

---

## Données

Toutes les données sont stockées localement dans `./data/` :
- `botinsta.db` — Base SQLite (actions, cibles, stats, erreurs)
- `sessions/` — Cookies de session Instagram
- `botinsta.log` — Logs détaillés

---

## Résolution de problèmes

| Problème | Solution |
|---|---|
| "Impossible de se connecter" | Vérifiez `.env`, essayez en mode non-headless |
| Captcha détecté | Connectez-vous manuellement une fois, puis relancez |
| Aucune cible trouvée | Ajoutez des `TARGET_ACCOUNTS` dans `.env` |
| Dashboard inaccessible | Vérifiez que le port 5000 n'est pas utilisé |
| Sélecteurs Instagram cassés | Instagram change son UI régulièrement, ouvrez une issue |
