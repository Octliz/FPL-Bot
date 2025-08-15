# file: fetch_data.py
# Flask API for FPL Assistant — works preseason and in-season.
# - Uses PUBLIC endpoints only (no login required)
# - Falls back to next/first GW if no current GW
# - Enriches picks with names, team short names, images, profile links
# - Generates unlimited ranked transfer suggestions within budget

from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, render_template, request

# --- Flask setup (Render-compatible) ---
app = Flask(__name__, template_folder="templates", static_folder="static")

# --- Constants ---
BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
PICKS_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/"
ENTRY_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/"  # for bank if needed
PLAYER_IMG = (
    "https://resources.premierleague.com/premierleague/photos/players/110x140/p{code}.png"
)

POSITION_MAP = {1: "Goalkeeper", 2: "Defender", 3: "Midfielder", 4: "Forward"}
POSITION_ORDER = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Forward": 3}

# --- Helpers ---

def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip().lower()
    s = re.sub(r"\s+", "-", s)
    return s


def get_bootstrap() -> Dict[str, Any]:
    r = requests.get(BOOTSTRAP_URL, timeout=20)
    r.raise_for_status()
    return r.json()


def current_or_next_gw(bootstrap: Dict[str, Any]) -> Optional[int]:
    # Prefer current
    for ev in bootstrap.get("events", []):
        if ev.get("is_current"):
            return ev.get("id")
    # Then next upcoming
    for ev in bootstrap.get("events", []):
        if ev.get("is_next"):
            return ev.get("id")
    # Preseason fallback → GW1
    first = bootstrap.get("events", [{}])[0]
    return first.get("id")


def build_indexes(bootstrap: Dict[str, Any]) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, str]]:
    teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
    players: Dict[int, Dict[str, Any]] = {}
    for p in bootstrap.get("elements", []):
        code_raw = str(p.get("code", ""))
        photo_raw = p.get("photo", "").split(".")[0]
        # Prefer code for image URL; fallback to photo id
        img_code = code_raw or photo_raw
        img_url = PLAYER_IMG.format(code=img_code)
        full_name = f"{p.get('first_name','')} {p.get('second_name','')}".strip()
        team_short = teams.get(p.get("team"), "UNK")
        pos_name = POSITION_MAP.get(p.get("element_type"), "Unknown")
        profile_slug = _slugify(full_name)
        # FPL player page uses the numeric code in URL path
        profile_url = f"https://fantasy.premierleague.com/players/{p.get('code')}/{profile_slug}"

        players[p["id"]] = {
            "id": p["id"],
            "code": p.get("code"),
            "name": full_name,
            "web_name": p.get("web_name"),
            "team": team_short,
            "position": pos_name,
            "position_sort": p.get("element_type", 99),
            "now_cost": p.get("now_cost", 0),  # tenths of £m
            "form": float(p.get("form") or 0.0),
            "points_per_game": float(p.get("points_per_game") or 0.0),
            "selected_by_percent": float((p.get("selected_by_percent") or 0).replace("%", "") or 0),
            "ep_next": float(p.get("ep_next") or 0.0),
            "status": p.get("status"),
            "chance_of_playing_next_round": p.get("chance_of_playing_next_round"),
            "image": img_url,
            "profile": profile_url,
        }
    return players, teams


def fetch_picks(team_id: str, gw: int) -> Dict[str, Any]:
    r = requests.get(PICKS_URL.format(team_id=team_id, gw=gw), timeout=20)
    r.raise_for_status()
    return r.json()


def estimate_budget_and_squad(picks_json: Dict[str, Any], players: Dict[int, Dict[str, Any]]) -> Tuple[int, List[Dict[str, Any]]]:
    # Bank in tenths of a million (e.g., 5 => £0.5m, 100 => £10.0m)
    entry_hist = picks_json.get("entry_history") or {}
    bank = int(entry_hist.get("bank") or 0)

    squad: List[Dict[str, Any]] = []
    for pick in picks_json.get("picks", []):
        el = pick["element"]
        p = players.get(el, {})
        # Use current market value as approximation for sell price (simple)
        sell_price = players.get(el, {}).get("now_cost", 0)
        squad.append({
            "element": el,
            "name": p.get("name", f"Unknown {el}"),
            "team": p.get("team", "UNK"),
            "position": p.get("position", "Unknown"),
            "position_sort": p.get("position_sort", 99),
            "now_cost": p.get("now_cost", 0),
            "sell_price": sell_price,
            "ep_next": p.get("ep_next", 0.0),
            "status": p.get("status"),
            "image": p.get("image"),
            "profile": p.get("profile"),
            "is_captain": pick.get("is_captain", False),
            "is_vice_captain": pick.get("is_vice_captain", False),
        })
    # Sort by position for readability
    squad.sort(key=lambda x: x["position_sort"])
    return bank, squad


def find_better_replacements(
    squad: List[Dict[str, Any]],
    players: Dict[int, Dict[str, Any]],
    bank: int,
) -> List[Dict[str, Any]]:
    """
    Generate transfer suggestions ranked by expected points delta.
    - Simple rule: for each player in squad, find alternatives same position
      with higher ep_next and playable status, affordable within (bank + sell_price).
    - Returns many suggestions (up to ~50), already sorted by gain desc.
    - Costs are in tenths of £m.
    """
    suggestions: List[Dict[str, Any]] = []

    # Pre-filter candidate pool by status and minimal EP
    pool = [p for p in players.values() if p["status"] in ("a", "d") and p["ep_next"] > 0]

    for cur in squad:
        cur_pos = cur["position"]
        cur_ep = float(cur.get("ep_next") or 0.0)
        budget = bank + int(cur.get("sell_price") or 0)

        # same-position candidates
        cands = [p for p in pool if p["position"] == cur_pos]
        for c in cands:
            price = int(c.get("now_cost") or 0)
            if price <= budget and c["ep_next"] > cur_ep + 0.1:  # require meaningful upgrade
                gain = round(c["ep_next"] - cur_ep, 2)
                cost_delta = price - int(cur.get("sell_price") or 0)
                suggestions.append({
                    "out": {
                        "name": cur["name"],
                        "team": cur["team"],
                        "position": cur_pos,
                        "now_cost": cur["now_cost"],
                        "ep_next": cur_ep,
                        "image": cur["image"],
                        "profile": cur["profile"],
                    },
                    "in": {
                        "id": c["id"],
                        "name": c["name"],
                        "team": c["team"],
                        "position": c["position"],
                        "now_cost": c["now_cost"],
                        "ep_next": round(c["ep_next"], 2),
                        "image": c["image"],
                        "profile": c["profile"],
                    },
                    "expected_points_gain": gain,
                    "cost_change": int(cost_delta),
                    "affordable": price <= budget,
                })

    # Rank by EP gain, then cheaper first, then higher in EP
    suggestions.sort(key=lambda s: (-s["expected_points_gain"], s["cost_change"]))

    # Deduplicate by identical (out.name -> in.name)
    seen = set()
    unique: List[Dict[str, Any]] = []
    for s in suggestions:
        key = (s["out"]["name"], s["in"]["name"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
            if len(unique) >= 50:  # safety cap
                break
    return unique


# --- Routes ---
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.get("/my_team_analysis")
def my_team_analysis():
    team_id = request.args.get("team_id")
    if not team_id:
        return jsonify({"error": "No team ID provided"}), 400

    try:
        bootstrap = get_bootstrap()
        players, teams = build_indexes(bootstrap)
        gw = current_or_next_gw(bootstrap)

        # Fetch picks for computed GW
        picks_json = fetch_picks(team_id, gw)

        # Build enriched squad + budget
        bank, squad = estimate_budget_and_squad(picks_json, players)

        # Suggestions (many, ranked). If preseason, still works because EP exists.
        suggestions = find_better_replacements(squad, players, bank)

        result = {
            "team_id": team_id,
            "gameweek": gw,
            "bank_tenths_m": bank,
            "bank_million": round(bank / 10.0, 1),
            "squad": squad,  # already enriched and sorted by position
            "transfer_suggestions": suggestions,
        }
        return jsonify(result)

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch data: {e}"}), 502
    except Exception as e:  # guard
        return jsonify({"error": f"Unexpected error: {e}"}), 500


if __name__ == "__main__":
    # Render sets PORT env var; default to 10000 locally
    port = int(os.environ.get("PORT", os.environ.get("RENDER_PORT", 10000)))
    app.run(host="0.0.0.0", port=port)
