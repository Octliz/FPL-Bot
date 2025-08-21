from flask import Flask, render_template, request, jsonify
import requests
import pandas as pd
import numpy as np
from lazyfpl import FPL

app = Flask(__name__)

# ----------------------------
# Helpers
# ----------------------------
def get_bootstrap_data():
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()
    return data["elements"], data["teams"]

def get_team_data(team_id):
    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/event/1/picks/"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def analyze_team(team_data, players, teams):
    # map player id -> player data
    player_map = {p["id"]: p for p in players}
    team_map = {t["id"]: t["name"] for t in teams}

    picks = team_data.get("picks", [])
    result = {"goalkeepers": [], "defenders": [], "midfielders": [], "forwards": []}

    for pick in picks:
        p = player_map.get(pick["element"])
        if not p:
            continue
        position = p["element_type"]
        name = p["web_name"]
        team_name = team_map[p["team"]]
        player_info = {
            "name": name,
            "team": team_name,
            "points": p["total_points"],
            "price": p["now_cost"] / 10,
        }
        if position == 1:
            result["goalkeepers"].append(player_info)
        elif position == 2:
            result["defenders"].append(player_info)
        elif position == 3:
            result["midfielders"].append(player_info)
        elif position == 4:
            result["forwards"].append(player_info)

    return result

def get_lazyfpl_tips():
    """Fetch tips from LazyFPL"""
    try:
        fpl = FPL()
        tips = fpl.tips()  # this returns a dict with captaincy, transfers, chips, etc.
        return tips
    except Exception as e:
        return {"error": f"Failed to fetch LazyFPL tips: {e}"}

# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/my_team_analysis")
def my_team_analysis():
    team_id = request.args.get("team_id")
    if not team_id:
        return jsonify({"error": "Missing team_id"}), 400

    try:
        players, teams = get_bootstrap_data()
        team_data = get_team_data(team_id)
        analysis = analyze_team(team_data, players, teams)
        tips = get_lazyfpl_tips()
        return jsonify({"analysis": analysis, "lazyfpl_tips": tips})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
