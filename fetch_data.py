from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_TEAM_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/"

# --- Helper function to analyze team ---
def analyze_team(team_data, elements, element_types, teams):
    players = []

    for p in team_data["picks"]:
        player = next((x for x in elements if x["id"] == p["element"]), None)
        if not player:
            continue

        team = next((t for t in teams if t["id"] == player["team"]), None)

        # Flags (injury, suspension, etc.)
        flags = []
        if player.get("news"):
            flags.append(player["news"])

        players.append({
            "name": player["web_name"],
            "position": element_types[player["element_type"] - 1]["singular_name"],
            "team": team["name"] if team else "Unknown",
            "team_badge": f"https://resources.premierleague.com/premierleague/badges/t{player['team']}.png" if team else None,
            "photo": f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{player['photo'].replace('.jpg','')}.png",
            "form": player["form"],
            "ppg": player["points_per_game"],
            "flags": flags
        })

    return players


# --- Flask Routes ---
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/my_team_analysis", methods=["GET"])
def my_team_analysis():
    try:
        team_id = request.args.get("team_id")
        if not team_id:
            return jsonify({"error": "team_id is required"}), 400

        # Get bootstrap data
        bootstrap = requests.get(FPL_BOOTSTRAP).json()
        elements = bootstrap["elements"]
        element_types = bootstrap["element_types"]
        teams = bootstrap["teams"]

        # Assume Gameweek 1 (later can make this dynamic)
        gw = 1
        team_data = requests.get(FPL_TEAM_URL.format(team_id=team_id, gw=gw)).json()

        # Analyze
        players = analyze_team(team_data, elements, element_types, teams)

        return jsonify({"team_id": team_id, "players": players})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
