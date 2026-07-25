from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.coupon_service import get_current_coupon, get_coupon_with_matches, generate_daily_coupon

router = APIRouter(prefix="/coupon", tags=["coupon"])


@router.get("/")
def current_coupon(db: Session = Depends(get_db)):
    generate_daily_coupon(db)
    coupon = get_current_coupon(db)
    if not coupon:
        return {"coupon": None}
    data = get_coupon_with_matches(db, coupon.id)
    if not data:
        return {"coupon": None}

    matches_out = []
    for cm in data["matches"]:
        match = cm["match"]
        pred = cm["prediction"]
        matches_out.append({
            "id": match.id,
            "home_team": match.home_team_name,
            "away_team": match.away_team_name,
            "competition": match.competition,
            "date": str(match.date) if match.date else None,
            "status": cm["status"],
            "home_score": match.home_score,
            "away_score": match.away_score,
            "best_market": pred.best_market if pred else None,
            "confidence_score": pred.confidence_score if pred else None,
            "best_probability": pred.best_probability if pred else None,
        })

    return {
        "coupon_id": coupon.id,
        "date": str(coupon.date),
        "status": coupon.status,
        "total_bets": coupon.total_bets,
        "won_bets": coupon.won_bets,
        "matches": matches_out,
    }