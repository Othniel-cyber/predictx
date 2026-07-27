from datetime import datetime

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.prediction import Prediction
from app.models.coupon import Coupon
from app.models.coupon_match import CouponMatch

MAX_COUPON_MATCHES = 11


def generate_daily_coupon(db: Session):
    today = datetime.now().replace(hour=0, minute=0, second=0)
    existing = db.query(Coupon).filter(Coupon.date >= today).first()
    if existing:
        return existing

    predictions = db.query(Prediction).join(Match).filter(
        Match.status == "SCHEDULED",
        Match.date >= today,
        Prediction.confidence_score >= 7,
        Prediction.best_market != None,
    ).order_by(Prediction.best_probability.desc()).all()

    if len(predictions) < MAX_COUPON_MATCHES:
        extra = db.query(Prediction).join(Match).filter(
            Match.status == "SCHEDULED",
            Match.date >= today,
            Prediction.confidence_score.between(5, 6),
            Prediction.best_market != None,
        ).order_by(Prediction.best_probability.desc()).all()
        predictions.extend(extra)

    if len(predictions) < MAX_COUPON_MATCHES:
        extra = db.query(Prediction).join(Match).filter(
            Match.status == "SCHEDULED",
            Match.date >= today,
            Prediction.confidence_score >= 3,
            Prediction.best_market != None,
        ).order_by(Prediction.best_probability.desc()).all()
        predictions.extend(extra)

    if not predictions:
        return None

    selected = []
    seen_leagues = {}

    for p in predictions:
        if len(selected) >= MAX_COUPON_MATCHES:
            break
        match = db.query(Match).filter_by(id=p.match_id).first()
        if not match:
            continue
        league = match.competition or ""
        seen_leagues[league] = seen_leagues.get(league, 0) + 1
        if seen_leagues[league] > 3:
            continue
        selected.append(p)

    if len(selected) < MAX_COUPON_MATCHES:
        for p in predictions:
            if len(selected) >= MAX_COUPON_MATCHES:
                break
            if p not in selected:
                selected.append(p)

    selected = selected[:MAX_COUPON_MATCHES]

    coupon = Coupon(
        date=datetime.now(),
        status="PENDING",
        total_bets=len(selected),
        won_bets=0,
        is_public=1,
    )
    db.add(coupon)
    db.commit()
    db.refresh(coupon)

    for p in selected:
        cm = CouponMatch(coupon_id=coupon.id, match_id=p.match_id, prediction_id=p.id, status="PENDING")
        db.add(cm)
    db.commit()
    db.refresh(coupon)
    return coupon


def update_coupon_results(db: Session):
    coupons = db.query(Coupon).filter(Coupon.status == "PENDING").all()
    for coupon in coupons:
        coupon_matches = db.query(CouponMatch).filter_by(coupon_id=coupon.id).all()
        if not coupon_matches:
            continue

        all_finished = True
        won_count = 0

        for cm in coupon_matches:
            if cm.status != "PENDING":
                if cm.status == "WON":
                    won_count += 1
                continue

            match = db.query(Match).filter_by(id=cm.match_id).first()
            prediction = db.query(Prediction).filter_by(id=cm.prediction_id).first()
            if not match or not prediction:
                cm.status = "CANCELLED"
                continue

            if match.status == "FINISHED" and match.home_score is not None and match.away_score is not None:
                cm.status = _check_result(prediction.best_market, match.home_score, match.away_score)
                if cm.status == "WON":
                    won_count += 1
            elif match.status in ("CANCELLED", "POSTPONED"):
                cm.status = "CANCELLED"
            else:
                all_finished = False

        coupon.won_bets = won_count
        coupon.total_bets = len(coupon_matches)

        if all_finished:
            coupon.status = "WON" if won_count == len(coupon_matches) else "LOST"

        db.commit()


def _check_result(market, hs, aw):
    if not market:
        return "PENDING"
    if market == "1X2 - Domicile":
        return "WON" if hs > aw else "LOST"
    if market == "1X2 - Nul":
        return "WON" if hs == aw else "LOST"
    if market == "1X2 - Extérieur":
        return "WON" if hs < aw else "LOST"
    if market == "DC 1X":
        return "WON" if hs >= aw else "LOST"
    if market == "DC 12":
        return "WON" if hs != aw else "LOST"
    if market == "DC 2X":
        return "WON" if hs <= aw else "LOST"
    if market == "Over 2.5":
        return "WON" if hs + aw > 2.5 else "LOST"
    if market == "Under 2.5":
        return "WON" if hs + aw < 2.5 else "LOST"
    if market == "Over 3.5":
        return "WON" if hs + aw > 3.5 else "LOST"
    if market == "Under 3.5":
        return "WON" if hs + aw < 3.5 else "LOST"
    if market == "Over 4.5":
        return "WON" if hs + aw > 4.5 else "LOST"
    if market == "Under 4.5":
        return "WON" if hs + aw < 4.5 else "LOST"
    if market == "GG":
        return "WON" if hs > 0 and aw > 0 else "LOST"
    if market == "NG":
        return "WON" if hs == 0 or aw == 0 else "LOST"
    return "PENDING"


def get_current_coupon(db: Session):
    return db.query(Coupon).order_by(Coupon.date.desc()).first()


def get_coupon_with_matches(db: Session, coupon_id: int):
    coupon = db.query(Coupon).filter_by(id=coupon_id).first()
    if not coupon:
        return None
    data = []
    for cm in db.query(CouponMatch).filter_by(coupon_id=coupon_id).all():
        match = db.query(Match).filter_by(id=cm.match_id).first()
        pred = db.query(Prediction).filter_by(id=cm.prediction_id).first()
        data.append({"match": match, "prediction": pred, "status": cm.status})
    return {"coupon": coupon, "matches": data}