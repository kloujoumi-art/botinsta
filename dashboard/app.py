"""
Dashboard Flask : visualisation des statistiques en temps réel.
Accessible sur http://127.0.0.1:5000 pendant l'exécution du bot.
"""
import os
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS

from storage.database import (
    get_today_stats,
    get_recent_actions,
    get_recent_errors,
    get_targets_summary,
    get_weekly_stats,
    add_target,
)
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)

app = Flask(__name__, template_folder="templates")
CORS(app)

# Référence au moteur du bot, injectée depuis main.py
_bot_engine = None


def set_bot_engine(engine) -> None:
    global _bot_engine
    _bot_engine = engine


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    settings = get_settings()
    today = get_today_stats()
    remaining = {
        "follows":        max(0, settings.max_follows_per_day         - today.get("follows", 0)),
        "likes":          max(0, settings.max_likes_per_day           - today.get("likes", 0)),
        "profile_visits": max(0, settings.max_profile_visits_per_day  - today.get("profile_visits", 0)),
        "stories":        max(0, settings.max_stories_per_day         - today.get("stories_viewed", 0)),
        "reels":          max(0, settings.max_reels_per_day           - today.get("reels_viewed", 0)),
    }
    limits = {
        "follows":        settings.max_follows_per_day,
        "likes":          settings.max_likes_per_day,
        "profile_visits": settings.max_profile_visits_per_day,
        "stories":        settings.max_stories_per_day,
        "reels":          settings.max_reels_per_day,
    }
    return jsonify({
        "today":        today,
        "remaining":    remaining,
        "limits":       limits,
        "bot_running":  _bot_engine.running       if _bot_engine else False,
        "bot_paused":   _bot_engine.paused        if _bot_engine else False,
        "bot_status":   _bot_engine.status        if _bot_engine else "stopped",
        "login_status": _bot_engine.login_status  if _bot_engine else "pending",
    })


@app.route("/api/actions")
def api_actions():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_recent_actions(limit))


@app.route("/api/errors")
def api_errors():
    limit = request.args.get("limit", 20, type=int)
    return jsonify(get_recent_errors(limit))


@app.route("/api/targets")
def api_targets():
    return jsonify(get_targets_summary())


@app.route("/api/weekly")
def api_weekly():
    return jsonify(get_weekly_stats())


@app.route("/health")
def health():
    """Health check endpoint pour Render."""
    return jsonify({"status": "ok", "bot": _bot_engine.status if _bot_engine else "stopped"})


@app.route("/api/screenshot")
def api_screenshot():
    """Sert le dernier screenshot de debug sauvegardé par le bot."""
    name = request.args.get("name", "login_page")
    path = f"/data/debug_{name}.png"
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    return jsonify({"error": f"Screenshot '{name}' introuvable"}), 404


@app.route("/api/screenshots")
def api_screenshots():
    """Liste tous les screenshots disponibles dans /data."""
    try:
        files = [
            f.replace("debug_", "").replace(".png", "")
            for f in os.listdir("/data")
            if f.startswith("debug_") and f.endswith(".png")
        ]
        return jsonify(sorted(files))
    except Exception:
        return jsonify([])


@app.route("/api/bot/pause", methods=["POST"])
def api_pause():
    if _bot_engine:
        _bot_engine.pause()
        return jsonify({"status": "paused"})
    return jsonify({"error": "Bot non démarré"}), 400


@app.route("/api/bot/resume", methods=["POST"])
def api_resume():
    if _bot_engine:
        _bot_engine.resume()
        return jsonify({"status": "running"})
    return jsonify({"error": "Bot non démarré"}), 400


@app.route("/api/targets/add", methods=["POST"])
def api_add_target():
    data = request.get_json() or {}
    username = data.get("username", "").strip().lstrip("@")
    if not username:
        return jsonify({"error": "Username invalide"}), 400
    add_target(username, source="manual_dashboard")
    logger.info(f"Cible ajoutée manuellement : @{username}")
    return jsonify({"status": "added", "username": username})


def run_dashboard(host: str = None, port: int = None) -> None:
    settings = get_settings()
    h = host or settings.dashboard_host
    p = port or settings.dashboard_port
    logger.info(f"Dashboard disponible → http://{h}:{p}")
    app.run(host=h, port=p, debug=False, use_reloader=False, threaded=True)
