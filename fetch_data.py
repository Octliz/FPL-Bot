# /fpl_bot/fetch_data.py

# ... (existing imports and code unchanged above)

TRANSFER_URL_TEMPLATE = "https://fantasy.premierleague.com/api/transfers/"

# ... (existing routes)

@app.route("/transfer_plan", methods=["POST"])
def transfer_plan():
    try:
        data = request.get_json()
        team_id = data.get("team_id")
        out_player_id = data.get("out_player_id")
        in_player_id = data.get("in_player_id")

        if not all([team_id, out_player_id, in_player_id]):
            return jsonify({"error": "team_id, out_player_id, in_player_id required"}), 400

        all_data = fetch_fpl_data()
        df = extract_player_stats(all_data)

        out_player = df[df['id'] == int(out_player_id)].iloc[0]
        in_player = df[df['id'] == int(in_player_id)].iloc[0]

        cost_diff = in_player['now_cost'] - out_player['now_cost']

        return jsonify({
            "suggestion": {
                "replace": out_player['name'],
                "with": in_player['name'],
                "position": out_player['position'],
                "form_gain": round(in_player['form'] - out_player['form'], 2),
                "ppg_gain": round(in_player['points_per_game'] - out_player['points_per_game'], 2),
                "cost_change": round(cost_diff, 1)
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/execute_transfer", methods=["POST"])
def execute_transfer():
    try:
        data = request.get_json()
        out_id = data.get("out_player_id")
        in_id = data.get("in_player_id")
        team_id = data.get("team_id")

        if not all([team_id, out_id, in_id]):
            return jsonify({"error": "team_id, out_player_id, in_player_id required"}), 400

        cookies = request.cookies.get('session')
        headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
        payload = {
            "element_in": in_id,
            "element_out": out_id,
            "purchase_price": 0,
            "selling_price": 0,
            "entry": team_id,
            "event": None
        }

        response = requests.post(
            TRANSFER_URL_TEMPLATE,
            json=payload,
            headers=headers,
            cookies={"session": cookies}
        )

        if response.status_code == 200:
            return jsonify({"message": "Transfer executed successfully"})
        else:
            return jsonify({"error": "Transfer failed", "details": response.text}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
