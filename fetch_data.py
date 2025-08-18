import requests
from flask import Flask, render_template, request

app = Flask(__name__, template_folder="templates", static_folder="static")

FPL_BASE_URL = "https://fantasy.premierleague.com/api"

def get_bootstrap():
    """Fetch global FPL data (players, teams, fixtures)."""
    url = f"{FPL_BASE_URL}/bootstrap-static/"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def get_team(team_id):
    """Fetch picks for a given team ID."""
    url = f"{FPL_BASE_URL}/entry/{team_id}/event/1/picks/"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def analysis = analyze_team(team_data, players, teams):
    position_map = {
        1: "Goalkeeper",
        2: "Defender",
        3: "Midfielder",
        4: "Forward"
    }

    results = []
    for pick in team_data.get("picks", []):
        player = next((p for p in players if p["id"] == pick["element"]), None)
        team = next((t for t in teams if t["id"] == player["team"]), None) if player else None

        if not player or not team:
            continue

        entry = {
            "name": f"{player['first_name']} {player['second_name']}",
            "team": team["name"],
            "position": position_map.get(player["element_type"], "Unknown"),
            "price": player["now_cost"] / 10.0,
            "points": player["event_points"],
            "status": player["status"],
        }

        # Flags for injured, doubtful, suspended
        flags = []
        if player["status"] == "i":
            flags.append("Injured")
        elif player["status"] == "d":
            flags.append("Doubtful")
        elif player["status"] == "s":
            flags.append("Suspended")

        entry["flags"] = flags
        results.append(entry)

    return results

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/my_team_analysis", methods=["GET"])
def my_team_analysis():
    team_id = request.args.get("team_id")
    if not team_id:
        return {"error": "team_id is required"}, 400

    try:
        bootstrap = get_bootstrap()
        team_data = get_team(team_id)
        analysis, suggestions, itb = analyze_team(team_data, bootstrap)

        return {
            "team": analysis,
            "suggestions": suggestions,
            "budget_left": itb,
        }
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
