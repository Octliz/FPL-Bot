import requests
from flask import Flask, render_template, request, jsonify
from lazyfpl import FPL

app = Flask(__name__)

# ----------------------------
# FPL API Helpers
# ----------------------------
FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_TEAM = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{event_id}/picks/"

def get_bootstrap_data():
    r = requests.get(FPL_BOOTSTRAP)
    r.raise_for_status()
    data = r.json()
    return data["elements"], data["teams"]

def get_team_data(team_id, event_id=1):
    r = requests.get(FPL_TEAM.format(team_id=team_id, event_id=event_id))
    r.raise_for_status()
    return r.json()

def analyze_team(team_data, players, teams):
    analysis = {"players": [], "suggestions": []}

    # Map player ID → data
    player_map = {p["id"]: p for p in players}
    team_map = {t["id"]: t["name"] for t in teams}

    # Collect each player
    for pick in team_data.get("picks", []):
        pid = pick["element"]
        pdata = player_map.get(pid)
        if not pdata:
            continue

        analysis["players"].append({
            "name": pdata["web_name"],
            "position": ["GK","DEF","MID","FWD"][pdata["element_type"]-1],
            "team": team_map.get(pdata["team"]),
            "points": pdata["total_points"],
            "now_cost": pdata["now_cost"]/10,
            "selected_by": pdata["selected_by_percent"]
        })

    # Add LazyFPL suggestions
    try:
        fpl = FPL()
        captaincy = fpl.get_captaincy()
        transfers = fpl.get_transfers()
        analysis["suggestions"].append({"captaincy": captaincy})
        analysis["suggestions"].append({"transfer_tips": transfers})
    except Exception as e:
        analysis["suggestions"].append({"lazyfpl_error": str(e)})

    return analysis

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
