from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

FPL_BASE = "https://fantasy.premierleague.com/api"

# ----------------------------
# Helpers
# ----------------------------
def get_bootstrap_data():
    url = f"{FPL_BASE}/bootstrap-static/"
    res = requests.get(url)
    res.raise_for_status()
    data = res.json()
    players = {p["id"]: p for p in data["elements"]}
    teams = {t["id"]: t["name"] for t in data["teams"]}
    return players, teams

def get_team_data(team_id):
    url = f"{FPL_BASE}/entry/{team_id}/event/1/picks/"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def player_summary(player, teams):
    """Return cleaned player info with image + profile link"""
    element = player["element"]
    return {
        "id": element,
        "name": f"{player['web_name'] if 'web_name' in player else ''}".strip()
                or f"{player.get('first_name', '')} {player.get('second_name', '')}".strip(),
        "team": teams.get(player["team"], "Unknown"),
        "position": player["element_type"],
        "now_cost": round(player["now_cost"] / 10, 1),
        "points_last_season": player.get("total_points", 0),
        "image": f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{player['code']}.png",
        "profile_url": f"https://fantasy.premierleague.com/player/{player['code']}"
    }

def analyze_team(team_data, players, teams):
    """Return squad + naive transfer suggestions"""
    squad = []
    for p in team_data["picks"]:
        pl = players[p["element"]]
        squad.append(player_summary(pl, teams))

    suggestions = []
    # Naive: suggest cheaper/better alternatives
    for p in squad:
        cheaper_better = [
            player_summary(pl, teams)
            for pl in players.values()
            if pl["element_type"] == p["position"]
            and pl["id"] != p["id"]
            and pl["now_cost"] <= p["now_cost"]
            and pl["total_points"] > p["points_last_season"]
        ]
        cheaper_better = sorted(cheaper_better, key=lambda x: -x["points_last_season"])[:2]
        if cheaper_better:
            suggestions.append({"out": p, "in": cheaper_better})

    return {"squad": squad, "suggestions": suggestions}

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
        result = analyze_team(team_data, players, teams)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
