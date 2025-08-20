import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_TEAM_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/event/1/picks/"


# ----------------------------
# Helpers
# ----------------------------
def get_bootstrap_data():
    """Fetch players and teams from FPL bootstrap API."""
    resp = requests.get(FPL_BOOTSTRAP)
    resp.raise_for_status()
    data = resp.json()
    players = {p["id"]: p for p in data["elements"]}
    teams = {t["id"]: t for t in data["teams"]}
    return players, teams


def get_team_data(team_id):
    """Fetch a team by ID."""
    url = FPL_TEAM_URL.format(team_id=team_id)
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()


def analyze_team(team_data, players, teams):
    """Build squad details + suggest transfers."""
    picks = team_data.get("picks", [])
    squad = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    suggestions = []

    for pick in picks:
        player = players.get(pick["element"])
        if not player:
            continue

        pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
        pos = pos_map.get(player["element_type"], "UNK")

        squad[pos].append({
            "web_name": player["web_name"],
            "team": teams[player["team"]]["name"],
            "now_cost": player["now_cost"],
            "total_points": player["total_points"]
        })

        # --- Suggest replacements ---
        if player["total_points"] < 50:  # Basic heuristic
            # Find two alternatives with higher points in same position
            better_alternatives = sorted(
                [p for p in players.values() if p["element_type"] == player["element_type"]
                 and p["total_points"] > player["total_points"]],
                key=lambda x: x["total_points"],
                reverse=True
            )[:2]

            for alt in better_alternatives:
                suggestions.append({
                    "out": player["web_name"],
                    "in": alt["web_name"],
                    "in_team": teams[alt["team"]]["name"],
                    "points": alt["total_points"],
                    "cost": alt["now_cost"] / 10
                })

    return {
        "squad": squad,
        "suggested_transfers": suggestions
    }


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
