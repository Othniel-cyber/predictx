import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.firebase_db import init_firebase, get_db


def check_expirations():
    init_firebase()
    db = get_db()
    users = db.collection("users").where("subscription_type", "!=", "none").get()
    now = datetime.now()
    expired_count = 0

    for u in users:
        data = u.to_dict()
        expiry = data.get("subscription_expiry")
        if expiry and expiry < now:
            db.collection("users").document(u.id).update({
                "subscription_type": "none",
                "subscription_expiry": None,
            })
            expired_count += 1
            print(f"[{datetime.now()}] Expiré: {data.get('name')} ({data.get('email')})")

    print(f"[{datetime.now()}] Vérification terminée. {expired_count} abonnement(s) expiré(s) révoqué(s).")


if __name__ == "__main__":
    check_expirations()
