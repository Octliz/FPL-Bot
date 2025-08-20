from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

# ----------------------------
# Helpers
# ----------------------------

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_TEAM_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/event/1/picks/"

def get_bootstrap_data():
    """Fetch global FPL bootstrap data: players + teams."""
    resp = requests.get(FPL_BOOTSTRAP_URL)
    resp.raise_for_status()
    data = resp.json()
    return data["elements"], data["teams"]

def get_team_data(team_id):
    """Fetch picks for given team ID (Gameweek 1 for now)."""
    url = FPL_TEAM_URL.format(team_id=team_id)
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def analyze_team(team_data, players, teams):
    """Analyze a team: strengths, weaknesses, and transfer suggestions."""
    player_lookup = {p["id"]: p for p in players}
    team_lookup = {t["id"]: t for t in teams}

    squad = []
    for pick in team_data["picks"]:
        p = player_lookup.get(pick["element"])
        if not p:
            continue
        squad.append({
            "id": p["id"],
            "name": f"{p['first_name']} {p['second_name']}",
            "position": p["element_type"],  # 1=GK, 2=DEF, 3=MID, 4=FWD
            "team": team_lookup[p["team"] - 1]["name"],
            "now_cost": p["now_cost"] / 10,
            "points_last_season": p.get("total_points", 0),
        })

    # Simple transfer suggestions:
    suggestions = []
    avg_points = sum(p["points_last_season"] for p in squad) / len(squad) if squad else 0

    for player in squad:
        if player["points_last_season"] < avg_points * 0.5:
            # Suggest 2 possible replacements from same position
            alts = [
                p for p in players
                if p["element_type"] == player["position"]
                and p["id"] != player["id"]
            ]
            # Pick top 2 by points
            alts_sorted = sorted(alts, key=lambda x: x.get("total_points", 0), reverse=True)[:2]
            replacements = [
                {
                    "id": alt["id"],
                    "name": f"{alt['first_name']} {alt['second_name']}",
                    "team": team_lookup[alt["team"] - 1]["name"],
                    "now_cost": alt["now_cost"] / 10,
                    "points_last_season": alt.get("total_points", 0),
                }
                for alt in alts_sorted
            ]
            suggestions.append({
                "out": player,
                "in": replacements
            })

    return {
        "squad": squad,
        "suggestions": suggestions
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
