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

@app.route("/my_team_analysis")
def my_team_analysis():
    team_id = request.args.get("team_id")
    if not team_id:
        return jsonify({"error": "No team ID provided"}), 400

    try:
        # Step 1: Get bootstrap data (players, teams, gameweek info)
        bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
        bootstrap_res = requests.get(bootstrap_url)
        bootstrap_res.raise_for_status()
        bootstrap_data = bootstrap_res.json()

        # Map team ID to short name
        team_map = {
            t["id"]: t["short_name"]
            for t in bootstrap_data["teams"]
        }

        # Map player element ID to "Name (TEAM)"
        player_map = {
            p["id"]: f"{p['first_name']} {p['second_name']} ({team_map.get(p['team'], 'UNK')})"
            for p in bootstrap_data["elements"]
        }

        # Step 2: Find current gameweek
        current_gw = next(
            (event["id"] for event in bootstrap_data["events"] if event["is_current"]),
            None
        )
        if not current_gw:
            return jsonify({"error": "Could not determine current gameweek"}), 500

        # Step 3: Fetch public picks for current gameweek
        picks_url = f"https://fantasy.premierleague.com/api/entry/{team_id}/event/{current_gw}/picks/"
        picks_res = requests.get(picks_url)
        picks_res.raise_for_status()
        picks_data = picks_res.json()

        # Step 4: Replace element IDs with player names + team short names
        for pick in picks_data.get("picks", []):
            element_id = pick["element"]
            pick["player_name"] = player_map.get(element_id, f"Unknown ({element_id})")

        return jsonify(picks_data)

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch team data: {e}"}), 500


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
