from flask import Flask, jsonify, request, render_template, make_response
import requests
import pandas as pd
from datetime import datetime
from functools import lru_cache
import os
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__, template_folder="templates", static_folder="static")

FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_API_URL = "https://fantasy.premierleague.com/api/fixtures/"
MY_TEAM_URL_TEMPLATE = "https://fantasy.premierleague.com/api/my-team/{team_id}/"
TRANSFER_URL_TEMPLATE = "https://fantasy.premierleague.com/api/transfers/"
LOGIN_URL = "https://users.premierleague.com/accounts/login/"

@lru_cache(maxsize=1)
def fetch_fpl_data():
    response = requests.get(FPL_API_URL)
    response.raise_for_status()
    return response.json()

@lru_cache(maxsize=1)
def fetch_fixtures():
    response = requests.get(FIXTURES_API_URL)
    response.raise_for_status()
    return response.json()

def clear_caches():
    fetch_fpl_data.cache_clear()
    fetch_fixtures.cache_clear()
    print("[Cache Cleared]", datetime.now())

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    session = requests.Session()
    payload = {
        "login": username,
        "password": password,
        "redirect_uri": "https://fantasy.premierleague.com/",
        "app": "plfpl-web"
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    response = session.post(LOGIN_URL, data=payload, headers=headers)

    if response.status_code == 200 and 'csrftoken' in session.cookies:
        resp = make_response(jsonify({"message": "Login successful"}))
        resp.set_cookie("session", session.cookies.get("pl_profile"))
        return resp
    else:
        return jsonify({"error": "Login failed"}), 401

@app.route("/my_team_analysis", methods=["GET"])
def my_team_analysis():
    team_id = request.args.get("team_id")
    if not team_id:
        return jsonify({"error": "Missing team_id parameter"}), 400

    cookies = request.cookies.get('session')
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        url = MY_TEAM_URL_TEMPLATE.format(team_id=team_id)
        response = requests.get(url, headers=headers, cookies={"session": cookies})
        response.raise_for_status()
        team_data = response.json()
    except Exception as e:
        return jsonify({"error": f"Failed to fetch team data: {str(e)}"}), 500

    player_ids = [pick['element'] for pick in team_data['picks']]
    all_data = fetch_fpl_data()
    df = extract_player_stats(all_data)
    my_team_df = df[df['id'].isin(player_ids)].copy()

    my_team_df['form'] = my_team_df['form'].astype(float)
    my_team_df['points_per_game'] = my_team_df['points_per_game'].astype(float)
    weak_players = my_team_df.nsmallest(3, ['form', 'points_per_game'])[['id', 'name', 'form', 'points_per_game']]

    replacements = []
    for _, row in weak_players.iterrows():
        same_position = my_team_df.loc[my_team_df['id'] == row['id'], 'position'].values[0]
        same_position_pool = df[(df['position'] == same_position) & (~df['id'].isin(player_ids))]
        suggestion = same_position_pool.head(3)[['name', 'form', 'points_per_game']].to_dict(orient='records')
        replacements.append({"out": row['name'], "recommendations": suggestion})

    return render_template("analysis.html", team=my_team_df.to_dict(orient="records"), replacements=replacements)

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

if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)

    scheduler = BackgroundScheduler()
    scheduler.add_job(clear_caches, 'interval', hours=24)
    scheduler.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
