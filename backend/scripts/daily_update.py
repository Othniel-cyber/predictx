import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal, engine, Base
from app.services.data_collector import save_matches_to_db
from app.services.prediction_engine import predict_all_upcoming_matches
from app.services.coupon_service import generate_daily_coupon, update_coupon_results


def daily_update():
    Base.metadata.create_all(bind=engine)
    print(f"[{datetime.now()}] Vérification des abonnements expirés...")
    try:
        from scripts.check_expirations import check_expirations
        check_expirations()
    except Exception as e:
        print(f"[{datetime.now()}] Erreur vérification expirations: {e}")
    db = SessionLocal()
    try:
        print(f"[{datetime.now()}] Collecte des matchs FotMob...")
        save_matches_to_db(db)
        print(f"[{datetime.now()}] Mise à jour des résultats de coupons...")
        update_coupon_results(db)
        print(f"[{datetime.now()}] Génération des pronostics...")
        predictions = predict_all_upcoming_matches(db)
        print(f"[{datetime.now()}] Génération du coupon du jour...")
        coupon = generate_daily_coupon(db)
        print(f"[{datetime.now()}] {len(predictions)} pronostics, coupon #{coupon.id if coupon else 'N/A'}")
    finally:
        db.close()


if __name__ == "__main__":
    daily_update()