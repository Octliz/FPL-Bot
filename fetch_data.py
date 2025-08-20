@app.route("/my_team_analysis")
def analyze_team(team_data, players, teams):
    """
    Analyze a team and suggest 2 alternative transfers per player,
    grouped by position (GK, Def, Mid, Fwd).
    """

    # Map position ids to names
    position_map = {
        1: "GK",
        2: "Def",
        3: "Mid",
        4: "Fwd"
    }

    # Build squad
    squad = []
    for p in team_data["picks"]:
        player = players[p["element"]]
        squad.append({
            "id": player["id"],
            "name": player["web_name"],
            "team": teams[player["team"]],
            "position": position_map[player["element_type"]],
            "now_cost": player["now_cost"] / 10,  # convert to millions
            "points_per_game": player["points_per_game"]
        })

    # Prepare grouped suggestions
    grouped_suggestions = {
        "GK": [],
        "Def": [],
        "Mid": [],
        "Fwd": []
    }

    # Suggest 2 best alternatives for each player
    for player in squad:
        # Find numeric key for their position
        pos_key = [k for k, v in position_map.items() if v == player["position"]][0]
        max_price = player["now_cost"] * 10  # convert back to integer cost units

        # Candidates: same position, cheaper or equal price, not the same player
        alternatives = [
            p for p in players.values()
            if p["element_type"] == pos_key and p["id"] != player["id"] and p["now_cost"] <= max_price
        ]

        # Sort by points per game, keep best 2
        alternatives = sorted(alternatives, key=lambda x: float(x["points_per_game"]), reverse=True)[:2]

        # Add suggestions
        for alt in alternatives:
            grouped_suggestions[player["position"]].append({
                "out": player["name"],
                "in": alt["web_name"],
                "team": teams[alt["team"]],
                "position": position_map[alt["element_type"]],
                "price": alt["now_cost"] / 10,
                "ppg": alt["points_per_game"]
            })

    return {
        "squad": squad,
        "suggestions": grouped_suggestions
    }

   except Exception as e:
        return jsonify({"error": str(e)}), 500
