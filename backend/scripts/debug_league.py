import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.api_client import get_matches_by_date

data = get_matches_by_date("20250115")
for l in data.get("leagues", []):
    for m in l.get("matches", []):
        print(f"\nMatch keys: {list(m.keys())}")
        print(f"statusId: {m.get('statusId')}")
        print(f"status: {m.get('status')}")
        print(f"home.score: {m.get('home', {}).get('score')}")
        print(f"away.score: {m.get('away', {}).get('score')}")
        print(f"finished: {m.get('finished')}")
        print(f"timeTS: {m.get('timeTS')}")
        break
    break