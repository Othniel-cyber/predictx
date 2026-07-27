import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth

_firebase_app = None
_db = None


def init_firebase():
    global _firebase_app, _db
    if _firebase_app:
        return
    from app.config import FIREBASE_KEY_PATH, FIREBASE_KEY_JSON

    if FIREBASE_KEY_JSON:
        cred = credentials.Certificate(json.loads(FIREBASE_KEY_JSON))
        _firebase_app = firebase_admin.initialize_app(cred)
        _db = firestore.client()
        return

    key_path = FIREBASE_KEY_PATH
    if not key_path:
        for f in os.listdir("."):
            if f.endswith(".json") and "firebase" in f.lower() and "adminsdk" in f.lower():
                key_path = f
                break
    if not key_path:
        raise FileNotFoundError("Aucun fichier de clé Firebase trouvé")
    cred = credentials.Certificate(key_path)
    _firebase_app = firebase_admin.initialize_app(cred)
    _db = firestore.client()


def get_db():
    global _db
    if not _db:
        init_firebase()
    return _db


def get_auth():
    return auth


def create_user(uid, name, email):
    db = get_db()
    doc_ref = db.collection("users").document(uid)
    doc_ref.set({
        "name": name,
        "email": email,
        "subscription_type": "none",
        "subscription_expiry": None,
        "created_at": firestore.SERVER_TIMESTAMP,
    })
    return doc_ref.get().to_dict()


def get_user(uid):
    db = get_db()
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def get_user_by_email(email):
    db = get_db()
    users = db.collection("users").where("email", "==", email).limit(1).get()
    for u in users:
        data = u.to_dict()
        data["id"] = u.id
        return data
    return None


def search_users(query_str):
    db = get_db()
    results = []
    users = db.collection("users").order_by("name").get()
    for u in users:
        data = u.to_dict()
        data["id"] = u.id
        if query_str.lower() in data.get("name", "").lower() or query_str.lower() in data.get("email", "").lower():
            results.append(data)
    return results


def get_all_users(limit=50):
    db = get_db()
    results = []
    users = db.collection("users").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).get()
    for u in users:
        data = u.to_dict()
        data["id"] = u.id
        results.append(data)
    return results


def update_subscription(uid, plan):
    db = get_db()
    from datetime import datetime, timedelta
    days = {"semaine": 7, "mois": 30, "annee": 365}
    expiry = datetime.now() + timedelta(days=days.get(plan, 7))
    db.collection("users").document(uid).update({
        "subscription_type": plan,
        "subscription_expiry": expiry,
    })


def remove_subscription(uid):
    db = get_db()
    db.collection("users").document(uid).update({
        "subscription_type": "none",
        "subscription_expiry": None,
    })