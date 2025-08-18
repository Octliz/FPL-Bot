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

def analyze_team(team_data, bootstrap):
    """Basic internal analysis + transfer suggestions."""
    players = {p["id"]: p for p in bootstrap["elements"]}
    teams = {t["id"]: t for t in bootstrap["teams"]}
    picks = team_data.get("picks", [])

    analysis = []
    suggestions = []

    budget = 100.0
    spent = 0

    for pick in picks:
        player = players[pick["element"]]
        team = teams[player["team"]]

        spent += player["now_cost"] / 10.0
        position_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

entry = {
    "name": f"{player['first_name']} {player['second_name']}",
    "team": team["name"],
    "position": position_map.get(player["element_type"], "Unknown"),
    "price": player["now_cost"] / 10.0,
    "points": player["event_points"],
    "status": player["status"],
}


        # Add flags
        flags = []
        if player["status"] != "a":
            flags.append("🚑 Injury/Unavailable")
        if player["chance_of_playing_next_round"] and player["chance_of_playing_next_round"] < 75:
            flags.append(f"⚠️ Only {player['chance_of_playing_next_round']}% chance of playing")
        if player["event_points"] < 2:
            flags.append("⬇️ Low recent performance")

        entry["flags"] = flags
        analysis.append(entry)

        # Suggest transfer: very naive for now
        if flags:
            better_options = [
                p for p in bootstrap["elements"]
                if p["element_type"] == player["element_type"]
                and p["now_cost"] <= player["now_cost"]
                and p["event_points"] > player["event_points"]
            ]
            if better_options:
                best = sorted(better_options, key=lambda x: x["event_points"], reverse=True)[0]
                suggestions.append({
                    "out": entry["name"],
                    "in": f"{best['first_name']} {best['second_name']}",
                    "gain": best["event_points"] - player["event_points"],
                })

    return analysis, suggestions, round(budget - spent, 1)

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
