from math import exp, factorial
from datetime import datetime, timedelta
import numpy as np

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.models.prediction import Prediction

_stats_cache = {}
_league_avg_cache = None


def compute_league_averages(db: Session):
    global _league_avg_cache
    if _league_avg_cache is not None:
        return _league_avg_cache

    from sqlalchemy import func
    rows = db.query(
        Match.competition,
        func.avg(Match.home_score).label("avg_h"),
        func.avg(Match.away_score).label("avg_a"),
    ).filter(
        Match.status == "FINISHED",
        Match.home_score != None,
        Match.away_score != None,
    ).group_by(Match.competition).all()

    avgs = {}
    for r in rows:
        if r.competition:
            avgs[r.competition] = (float(r.avg_h) if r.avg_h else 1.50, float(r.avg_a) if r.avg_a else 1.20)

    _league_avg_cache = avgs
    return avgs


def get_team_stats_from_db(db: Session, team_id, match_date):
    cache_key = f"{team_id}"
    if cache_key in _stats_cache:
        return _stats_cache[cache_key]

    cutoff = match_date - timedelta(days=365) if match_date else datetime.utcnow() - timedelta(days=365)
    match_filter = Match.date < match_date if match_date else Match.date < datetime.utcnow()

    past_matches = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.date >= cutoff,
        match_filter,
        ((Match.home_team_id == team_id) | (Match.away_team_id == team_id)),
    ).order_by(Match.date.desc()).limit(30).all()

    if not past_matches:
        result = (1.0, 1.0, 1.0, 1.0, 0, 0, 0)
        _stats_cache[cache_key] = result
        return result

    home_scored = []
    home_conceded = []
    away_scored = []
    away_conceded = []
    results = []
    n_home = n_away = 0

    for m in past_matches:
        hs = m.home_score or 0
        aws = m.away_score or 0

        if m.home_team_id == team_id:
            home_scored.append(hs)
            home_conceded.append(aws)
            n_home += 1
        else:
            away_scored.append(aws)
            away_conceded.append(hs)
            n_away += 1

        if m.home_team_id == team_id:
            results.append(1 if hs > aws else (0 if hs == aws else -1))
        else:
            results.append(1 if aws > hs else (0 if aws == hs else -1))

    avg_hs = np.mean(home_scored[-10:]) if home_scored else 1.0
    avg_hc = np.mean(home_conceded[-10:]) if home_conceded else 1.0
    avg_as = np.mean(away_scored[-10:]) if away_scored else 1.0
    avg_ac = np.mean(away_conceded[-10:]) if away_conceded else 1.0

    recent = results[-6:] if len(results) >= 6 else results
    streak = sum(recent) if recent else 0

    home_games_pct = n_home / max(len(past_matches), 1)

    result = (avg_hs, avg_hc, avg_as, avg_ac, streak, max(n_home, 1), max(n_away, 1))
    _stats_cache[cache_key] = result
    return result


def estimate_expected_goals(db: Session, home_id, away_id, competition, date):
    h_hs, h_hc, h_as, h_ac, h_str, h_nh, h_na = get_team_stats_from_db(db, home_id, date)
    a_hs, a_hc, a_as, a_ac, a_str, a_nh, a_na = get_team_stats_from_db(db, away_id, date)

    league_avgs = compute_league_averages(db)
    league_h_avg, league_a_avg = league_avgs.get(competition, (1.50, 1.20))

    home_attack = h_hs / max(league_h_avg, 0.5)
    home_defense = h_hc / max(league_a_avg, 0.5)
    away_attack = a_as / max(league_a_avg, 0.5)
    away_defense = a_ac / max(league_h_avg, 0.5)

    hl = league_h_avg * home_attack * away_defense
    al = league_a_avg * away_attack * home_defense

    hl += h_str * 0.03
    al += a_str * 0.03

    return max(min(hl, 5.0), 0.2), max(min(al, 5.0), 0.2)


def dixon_coles_probs(home_lam, away_lam, rho=-0.085):
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

    max_goals = 15
    home_win = draw = away_win = 0.0
    over_25 = over_35 = over_45 = 0.0
    home_probs = []
    away_probs = []

    for g in range(max_goals + 1):
        home_probs.append((home_lam ** g) * exp(-home_lam) / factorial(g))
        away_probs.append((away_lam ** g) * exp(-away_lam) / factorial(g))

    home_zero = home_probs[0]
    away_zero = away_probs[0]

    for i in range(max_goals + 1):
        pi = home_probs[i]
        for j in range(max_goals + 1):
            pj = away_probs[j]
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


def find_implied_lambdas(hl_init, al_init, target_h, target_d, target_a, rho=-0.085):
    hl, al = float(hl_init), float(al_init)

    for _ in range(25):
        p = dixon_coles_probs(hl, al, rho)
        ph, pd, pa = p["prob_home"], p["prob_draw"], p["prob_away"]

        err_h = target_h - ph
        err_a = target_a - pa

        if abs(err_h) < 0.0005 and abs(err_a) < 0.0005:
            break

        eps = 0.02
        p2 = dixon_coles_probs(hl + eps, al, rho)
        grad_h_h = (p2["prob_home"] - ph) / eps
        grad_a_h = (p2["prob_away"] - pa) / eps

        p3 = dixon_coles_probs(hl, al + eps, rho)
        grad_h_a = (p3["prob_home"] - ph) / eps
        grad_a_a = (p3["prob_away"] - pa) / eps

        det = grad_h_h * grad_a_a - grad_h_a * grad_a_h
        if abs(det) > 1e-8:
            dhl = (err_h * grad_a_a - err_a * grad_h_a) / det
            dal = (err_a * grad_h_h - err_h * grad_a_h) / det
            hl += min(max(dhl, -0.5), 0.5)
            al += min(max(dal, -0.5), 0.5)
        else:
            if abs(grad_h_h) > 0.001:
                hl += min(max(err_h / grad_h_h, -0.3), 0.3)
            if abs(grad_a_a) > 0.001:
                al += min(max(err_a / grad_a_a, -0.3), 0.3)

        hl = max(0.1, min(6.0, hl))
        al = max(0.1, min(6.0, al))

    return hl, al


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
        ("Over 3.5", probs["prob_over_35"]),
        ("Under 3.5", probs["prob_under_35"]),
        ("Over 4.5", probs["prob_over_45"]),
        ("Under 4.5", probs["prob_under_45"]),
        ("GG", probs["prob_gg"]),
        ("NG", probs["prob_ng"]),
    ], key=lambda x: x[1])


def find_best_market_by_type(probs):
    markets_by_type = {
        "1X2": [("Domicile", probs["prob_home"]), ("Nul", probs["prob_draw"]), ("Extérieur", probs["prob_away"])],
        "Double Chance": [("1X", probs["prob_dc_1x"]), ("12", probs["prob_dc_12"]), ("2X", probs["prob_dc_2x"])],
        "Over/Under": [("Over 2.5", probs["prob_over_25"]), ("Under 2.5", probs["prob_under_25"]),
                       ("Over 3.5", probs["prob_over_35"]), ("Under 3.5", probs["prob_under_35"]),
                       ("Over 4.5", probs["prob_over_45"]), ("Under 4.5", probs["prob_under_45"])],
        "GG/NG": [("GG", probs["prob_gg"]), ("NG", probs["prob_ng"])],
    }
    result = {}
    for mtype, items in markets_by_type.items():
        result[mtype] = max(items, key=lambda x: x[1])
    return result


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
    if _calibrated_thresholds:
        for conf in range(10, 0, -1):
            thresh = _calibrated_thresholds.get(conf, 0.5)
            if prob >= thresh - 0.05:
                return conf if conf <= 10 else 10
        return 1

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

    hl_base, al_base = estimate_expected_goals(db, home_team.id, away_team.id, match.competition, match.date)
    poisson_probs = dixon_coles_probs(hl_base, al_base)

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
        blend_ml = 0.55
        blend_poisson = 0.45
        target_h = ml_probs["prob_home"] * blend_ml + poisson_probs["prob_home"] * blend_poisson
        target_d = ml_probs["prob_draw"] * blend_ml + poisson_probs["prob_draw"] * blend_poisson
        target_a = ml_probs["prob_away"] * blend_ml + poisson_probs["prob_away"] * blend_poisson

        s = target_h + target_d + target_a
        target_h, target_d, target_a = target_h / s, target_d / s, target_a / s

        hl_adj, al_adj = find_implied_lambdas(hl_base, al_base, target_h, target_d, target_a)
        probs = dixon_coles_probs(hl_adj, al_adj)
        probs["home_expected_goals"] = round(hl_adj, 4)
        probs["away_expected_goals"] = round(al_adj, 4)
    else:
        probs = poisson_probs

    market, prob = find_best_market(probs)
    conf = probability_to_confidence(prob)

    best_by_type = find_best_market_by_type(probs)

    pred = db.query(Prediction).filter_by(match_id=match_id).first()
    if pred:
        for k, v in probs.items():
            setattr(pred, k, v)
        pred.best_market = market
        pred.best_prediction = market
        pred.best_probability = prob
        pred.confidence_score = conf
    else:
        pred = Prediction(match_id=match_id, best_market=market, best_prediction=market,
                          best_probability=prob, confidence_score=conf, **probs)
        db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


def predict_all_upcoming_matches(db: Session):
    global _stats_cache, _league_avg_cache, _calibrated_thresholds
    _stats_cache.clear()
    _league_avg_cache = None
    _calibrated_thresholds = None

    today = datetime.now().replace(hour=0, minute=0, second=0)
    limit_date = today + timedelta(days=3)
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
