from flask import Flask, jsonify, request, render_template, send_file, make_response
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

def extract_player_stats(data):
    players = data['elements']
    teams = {team['id']: team['name'] for team in data['teams']}
    positions = {pos['id']: pos['singular_name_short'] for pos in data['element_types']}

    elements_df = pd.DataFrame(players)
    stats_df = elements_df[[
        'id', 'first_name', 'second_name', 'web_name',
        'now_cost', 'form', 'total_points', 'minutes',
        'goals_scored', 'assists', 'clean_sheets',
        'selected_by_percent', 'transfers_in_event', 'transfers_out_event',
        'in_dreamteam', 'status', 'points_per_game', 'team', 'element_type'
    ]].copy()

    stats_df['now_cost'] = stats_df['now_cost'] / 10.0
    stats_df['name'] = stats_df['first_name'] + ' ' + stats_df['second_name']
    stats_df['team_name'] = stats_df['team'].map(teams)
    stats_df['position'] = stats_df['element_type'].map(positions)
    stats_df = stats_df[~stats_df['status'].isin(['i', 'd', 's', 'n'])]

    return stats_df.sort_values(by='form', ascending=False)

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
        same_position_pool = df[(df['position'] == my_team_df.loc[my_team_df['id'] == row['id'], 'position'].values[0]) & (~df['id'].isin(player_ids))]
        suggestion = same_position_pool.head(3)[['name', 'form', 'points_per_game']].to_dict(orient='records')
        replacements.append({"out": row['name'], "recommendations": suggestion})

    return jsonify({
        "team_summary": my_team_df.to_dict(orient="records"),
        "weakest_recommendations": replacements
    })

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

if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)

    scheduler = BackgroundScheduler()
    scheduler.add_job(clear_caches, 'interval', hours=24)
    scheduler.start()

    with open("templates/index.html", "w") as f:
        f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>FPL Assistant</title>
    <script src=\"https://code.jquery.com/jquery-3.6.0.min.js\"></script>
</head>
<body>
    <h1>FPL Login + My Team Analysis</h1>
    <form id=\"login-form\">
        <label>Username:</label>
        <input type=\"text\" name=\"username\" required>
        <label>Password:</label>
        <input type=\"password\" name=\"password\" required>
        <button type=\"submit\">Login</button>
    </form>
    <hr>
    <form id=\"my-team-form\">
        <label>Enter Team ID:</label>
        <input type=\"text\" id=\"team_id\" required>
        <button type=\"submit\">Analyze My Team</button>
    </form>
    <pre id=\"my-team-output\"></pre>
    <script>
        $('#login-form').submit(function(e) {
            e.preventDefault();
            $.post('/login', $(this).serialize(), function(res) {
                alert(res.message);
            }).fail(function(err) {
                alert("Login failed: " + err.responseJSON.error);
            });
        });

        $('#my-team-form').submit(function(e) {
            e.preventDefault();
            const teamId = $('#team_id').val();
            $.getJSON(`/my_team_analysis?team_id=${teamId}`, function(data) {
                $('#my-team-output').text(JSON.stringify(data, null, 2));
            });
        });
    </script>
</body>
</html>
""")
        port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

