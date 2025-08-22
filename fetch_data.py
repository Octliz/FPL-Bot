from flask import Flask, render_template, request, jsonify
import requests
from lazyfpl import FPL

app = Flask(__name__, template_folder="templates", static_folder="static")

# ----------------------------
# Helper Functions
# ----------------------------

def get_bootstrap_data():
    """Fetch general player + team data from FPL bootstrap."""
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    players = data["elements"]
    teams = data["teams"]
    return players, teams

def get_team_data(team_id):
    """Fetch a user's team data by ID."""
    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/event/1/picks/"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def analyze_team(team_data, players, teams):
    """Basic analysis of team (GK, DEF, MID, FWD split + suggestions)."""
    picks = team_data.get("picks", [])
    player_map = {p["id"]: p for p in players}
    team_map = {t["id"]: t["name"] for t in teams}

    analysis = {"GK": [], "DEF": [], "MID": [], "FWD": []}

    for pick in picks:
        pid = pick["element"]
        pdata = player_map.get(pid, {})
        position = pdata.get("element_type")  # 1 = GK, 2 = DEF, 3 = MID, 4 = FWD
        entry = {
            "name": pdata.get("web_name"),
            "team": team_map.get(pdata.get("team")),
            "points": pdata.get("total_points"),
            "selected_by": pdata.get("selected_by_percent"),
        }
        if position == 1:
            analysis["GK"].append(entry)
        elif position == 2:
            analysis["DEF"].append(entry)
        elif position == 3:
            analysis["MID"].append(entry)
        elif position == 4:
            analysis["FWD"].append(entry)

    return analysis

def get_lazyfpl_tips():
    """Fetch tips and suggested transfers from LazyFPL."""
    fpl = FPL()
    # Get top picks (LazyFPL API wraps FPL community data)
    try:
        top_picks = fpl.picks.top_picks()
        return top_picks
    except Exception as e:
        return {"error": f"LazyFPL failed: {str(e)}"}

# ----------------------------
# Routes
# ----------------------------

@app.route("/")
def home():
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

@app.route("/tips")
def tips():
    try:
        tips = get_lazyfpl_tips()
        return jsonify(tips)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
