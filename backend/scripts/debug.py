import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from app.services.api_client import get_matches_by_date, get_team_data, get_league_matches

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.fotmob.com/",
}

print("=== Test new /api/data/ endpoints ===")
urls = [
    "https://www.fotmob.com/api/data/matches?date=20260725",
    "https://www.fotmob.com/api/data/allLeagues",
    "https://www.fotmob.com/api/data/leagues?id=47",
]
for url in urls:
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        print(f"[{resp.status_code}] {url[:70]}...")
        if resp.status_code == 200 and "matches" in url:
            data = resp.json()
            leagues = data.get("leagues", [])
            total = sum(len(l.get("matches", [])) for l in leagues)
            print(f"  -> {len(leagues)} leagues, {total} matches")
    except Exception as e:
        print(f"[ERR] {url[:70]}: {e}")

print("\n=== Test app functions ===")
try:
    data = get_matches_by_date("20260725")
    leagues = data.get("leagues", [])
    total = sum(len(l.get("matches", [])) for l in leagues)
    print(f"get_matches_by_date OK: {len(leagues)} leagues, {total} matches")
except Exception as e:
    print(f"get_matches_by_date ERR: {e}")