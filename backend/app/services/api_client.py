import requests

FOTMOB_BASE = "https://www.fotmob.com/api/data"


def fetch_json(url):
    resp = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.fotmob.com/",
    })
    resp.raise_for_status()
    return resp.json()


def get_matches_by_date(date_str):
    return fetch_json(f"{FOTMOB_BASE}/matches?date={date_str}")


def get_league_matches(league_id, season=None):
    url = f"{FOTMOB_BASE}/leagues?id={league_id}"
    if season:
        url += f"&season={season}"
    return fetch_json(url)


def get_team_data(team_id):
    return fetch_json(f"{FOTMOB_BASE}/teams?id={team_id}")


def get_match_details(match_id):
    return fetch_json(f"{FOTMOB_BASE}/matchDetails?id={match_id}")