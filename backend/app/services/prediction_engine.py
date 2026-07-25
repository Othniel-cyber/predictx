from math import exp, factorial
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.models.prediction import Prediction

DEFAULT_HOME_AVG = 1.50
DEFAULT_AWAY_AVG = 1.20
_stats_cache = {}


def get_team_stats_from_db(db: Session, team_id, team_name, match_date):
    cache_key = f"{team_id}"
    if cache_key in _stats_cache:
        return _stats_cache[cache_key]

    cutoff = match_date - timedelta(days=180) if match_date else datetime.utcnow() - timedelta(days=180)
    past_matches = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.date >= cutoff,
        Match.date < match_date if match_date else Match.date < datetime.utcnow(),
        ((Match.home_team_id == team_id) | (Match.away_team_id == team_id)),
    ).order_by(Match.date.desc()).limit(20).all()

    if not past_matches:
        result = (1.0, 1.0, 1.0, 1.0, 0)
        _stats_cache[cache_key] = result
        return result

    home_scored_w = home_conceded_w = home_weight = 0.0
    away_scored_w = away_conceded_w = away_weight = 0.0
    results = []

    for m in past_matches:
        days_ago = (datetime.utcnow() - m.date).days if m.date else 30
        w = 2 ** (-days_ago / 30)

        if m.home_team_id == team_id:
            home_scored_w += (m.home_score or 0) * w
            home_conceded_w += (m.away_score or 0) * w
            home_weight += w
            results.append(1 if (m.home_score or 0) > (m.away_score or 0) else (-1 if (m.home_score or 0) < (m.away_score or 0) else 0))
        else:
            away_scored_w += (m.away_score or 0) * w
            away_conceded_w += (m.home_score or 0) * w
            away_weight += w
            results.append(1 if (m.away_score or 0) > (m.home_score or 0) else (-1 if (m.away_score or 0) < (m.home_score or 0) else 0))

    avg_hs = home_scored_w / home_weight if home_weight > 0 else 1.0
    avg_hc = home_conceded_w / home_weight if home_weight > 0 else 1.0
    avg_as = away_scored_w / away_weight if away_weight > 0 else 1.0
    avg_ac = away_conceded_w / away_weight if away_weight > 0 else 1.0
    streak = sum(results[-6:]) if results else 0

    result = (avg_hs, avg_hc, avg_as, avg_ac, streak)
    _stats_cache[cache_key] = result
    return result


def estimate_expected_goals(db: Session, home_id, home_name, away_id, away_name, competition, date):
    h_hs, h_hc, h_as, h_ac, h_str = get_team_stats_from_db(db, home_id, home_name, date)
    a_hs, a_hc, a_as, a_ac, a_str = get_team_stats_from_db(db, away_id, away_name, date)

    home_attack = max(h_hs + h_as * 0.3, 0.5)
    home_defense = max(h_hc + h_ac * 0.3, 0.5)
    away_attack = max(a_as + a_hs * 0.3, 0.5)
    away_defense = max(a_hc + a_hc * 0.3, 0.5)

    home_lam = DEFAULT_HOME_AVG * (home_attack / away_defense)
    away_lam = DEFAULT_AWAY_AVG * (away_attack / home_defense)

    home_lam += max(min(h_str * 0.05, 0.3), -0.3)
    away_lam += max(min(a_str * 0.05, 0.3), -0.3)

    return max(min(home_lam, 4.0), 0.2), max(min(away_lam, 4.0), 0.2)


def dixon_coles_probs(home_lam, away_lam, rho=-0.08):
    def tau(x, y):
        if x == 0 and y == 0:
            return 1 - home_lam * away_lam * rho
        if x == 1 and y == 0:
            return 1 + away_lam * rho
        if x == 0 and y == 1:
            return 1 + home_lam * rho
        if x == 1 and y == 1:
            return 1 - rho
        return 1

    home_win = draw = away_win = over_25 = over_35 = over_45 = 0.0
    home_zero = away_zero = 0.0

    for i in range(11):
        pi = (home_lam ** i) * exp(-home_lam) / factorial(i)
        if i == 0:
            home_zero = pi
        for j in range(11):
            pj = (away_lam ** j) * exp(-away_lam) / factorial(j)
            if j == 0:
                away_zero = pj
            p = pi * pj * tau(i, j)
            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p
            t = i + j
            if t > 2.5:
                over_25 += p
            if t > 3.5:
                over_35 += p
            if t > 4.5:
                over_45 += p

    gg = 1 - (home_zero + away_zero - home_zero * away_zero)
    return {
        "home_expected_goals": round(home_lam, 4),
        "away_expected_goals": round(away_lam, 4),
        "prob_home": round(home_win, 4),
        "prob_draw": round(draw, 4),
        "prob_away": round(away_win, 4),
        "prob_over_25": round(over_25, 4),
        "prob_under_25": round(1 - over_25, 4),
        "prob_over_35": round(over_35, 4),
        "prob_under_35": round(1 - over_35, 4),
        "prob_over_45": round(over_45, 4),
        "prob_under_45": round(1 - over_45, 4),
        "prob_gg": round(gg, 4),
        "prob_ng": round(1 - gg, 4),
        "prob_dc_1x": round(home_win + draw, 4),
        "prob_dc_12": round(home_win + away_win, 4),
        "prob_dc_2x": round(away_win + draw, 4),
    }


def find_best_market(probs):
    return max([
        ("1X2 - Domicile", probs["prob_home"]),
        ("1X2 - Nul", probs["prob_draw"]),
        ("1X2 - Extérieur", probs["prob_away"]),
        ("DC 1X", probs["prob_dc_1x"]),
        ("DC 12", probs["prob_dc_12"]),
        ("DC 2X", probs["prob_dc_2x"]),
        ("Over 2.5", probs["prob_over_25"]),
        ("Under 2.5", probs["prob_under_25"]),
        ("GG", probs["prob_gg"]),
        ("NG", probs["prob_ng"]),
    ], key=lambda x: x[1])


_calibrated_thresholds = None


def load_calibrated_thresholds(db: Session):
    global _calibrated_thresholds
    try:
        from app.services.ml_engine import run_backtest, load_model
        model = load_model()
        if model is not None:
            df = run_backtest(db, model)
            if df is not None and len(df) > 0:
                thresholds = {}
                for conf in range(10, 0, -1):
                    subset = df[df["confidence"] == conf]
                    if len(subset) > 0:
                        thresholds[conf] = subset["correct"].mean()
                    elif thresholds:
                        thresholds[conf] = thresholds.get(conf + 1, 0.5)
                _calibrated_thresholds = thresholds
    except Exception:
        pass


def probability_to_confidence(prob):
    if prob >= 0.92:
        return 10
    if prob >= 0.88:
        return 9
    if prob >= 0.84:
        return 8
    if prob >= 0.79:
        return 7
    if prob >= 0.74:
        return 6
    if prob >= 0.69:
        return 5
    if prob >= 0.64:
        return 4
    if prob >= 0.58:
        return 3
    if prob >= 0.52:
        return 2
    return 1


def predict_match(db: Session, match_id):
    match = db.query(Match).filter_by(id=match_id).first()
    if not match:
        return None
    home_team = db.query(Team).filter_by(id=match.home_team_id).first()
    away_team = db.query(Team).filter_by(id=match.away_team_id).first()
    if not home_team or not away_team:
        return None

    hl, al = estimate_expected_goals(db, home_team.id, home_team.name, away_team.id, away_team.name, match.competition, match.date)
    poisson_probs = dixon_coles_probs(hl, al)

    ml_probs = None
    try:
        from app.services.ml_engine import predict_with_ml, load_model
        model = load_model()
        if model is not None:
            probs_ml = predict_with_ml(db, match_id)
            if probs_ml is not None and len(probs_ml) > 0:
                ml_probs = {
                    "prob_home": round(float(probs_ml[0][0]), 4),
                    "prob_draw": round(float(probs_ml[0][1]), 4),
                    "prob_away": round(float(probs_ml[0][2]), 4),
                }
    except Exception:
        pass

    if ml_probs:
        probs = poisson_probs.copy()
        blend = 0.6
        probs["prob_home"] = round(ml_probs["prob_home"] * blend + poisson_probs["prob_home"] * (1 - blend), 4)
        probs["prob_draw"] = round(ml_probs["prob_draw"] * blend + poisson_probs["prob_draw"] * (1 - blend), 4)
        probs["prob_away"] = round(ml_probs["prob_away"] * blend + poisson_probs["prob_away"] * (1 - blend), 4)
        probs["prob_dc_1x"] = round(probs["prob_home"] + probs["prob_draw"], 4)
        probs["prob_dc_12"] = round(probs["prob_home"] + probs["prob_away"], 4)
        probs["prob_dc_2x"] = round(probs["prob_draw"] + probs["prob_away"], 4)
    else:
        probs = poisson_probs

    market, prob = find_best_market(probs)
    conf = probability_to_confidence(prob)

    pred = db.query(Prediction).filter_by(match_id=match_id).first()
    if pred:
        for k, v in probs.items():
            setattr(pred, k, v)
        pred.best_market = market
        pred.best_prediction = market
        pred.best_probability = prob
        pred.confidence_score = conf
    else:
        pred = Prediction(match_id=match_id, best_market=market, best_prediction=market, best_probability=prob, confidence_score=conf, **probs)
        db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


def predict_all_upcoming_matches(db: Session):
    _stats_cache.clear()
    today = datetime.now().replace(hour=0, minute=0, second=0)
    limit_date = today + timedelta(days=2)
    matches = db.query(Match).filter(
        Match.status == "SCHEDULED",
        Match.date >= today,
        Match.date <= limit_date,
    ).all()
    try:
        load_calibrated_thresholds(db)
    except Exception:
        pass
    out = []
    for m in matches:
        p = predict_match(db, m.id)
        if p:
            out.append(p)
    return out