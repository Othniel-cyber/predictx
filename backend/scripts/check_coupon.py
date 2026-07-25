import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import SessionLocal, engine, Base
from app.models.coupon import Coupon
from app.models.coupon_match import CouponMatch
from app.models.match import Match
from app.models.prediction import Prediction

Base.metadata.create_all(bind=engine)
db = SessionLocal()

coupon = db.query(Coupon).order_by(Coupon.date.desc()).first()
print(f"Coupon #{coupon.id} - {coupon.status} - {coupon.total_bets} matchs")
print(f"Date: {coupon.date}")

for cm in db.query(CouponMatch).filter_by(coupon_id=coupon.id).all():
    m = db.query(Match).filter_by(id=cm.match_id).first()
    p = db.query(Prediction).filter_by(id=cm.prediction_id).first()
    if m and p:
        print(f"  {m.home_team_name} vs {m.away_team_name} | {m.competition}")
        print(f"    Meilleur marché: {p.best_market} (prob: {p.best_probability}, confiance: {p.confidence_score}/10)")

db.close()