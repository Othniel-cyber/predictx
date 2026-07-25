import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from datetime import datetime, timedelta
import joblib
import os

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.models.prediction import Prediction

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "model.pkl")


def compute_features_for_match(db: Session, match: Match, home_team: Team, away_team: Team):
    now = match.date or datetime.utcnow()
    cutoff = now - timedelta(days=365)

    home_matches = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.date.between(cutoff, now),
        ((Match.home_team_id == home_team.id) | (Match.away_team_id == away_team.id)),
    ).order_by(Match.date.desc()).limit(20).all()

    away_matches = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.date.between(cutoff, now),
        ((Match.home_team_id == away_team.id) | (Match.away_team_id == away_team.id)),
    ).order_by(Match.date.desc()).limit(20).all()

    h_goals_scored = []
    h_goals_conceded = []
    h_results = []
    h_home_scored = []
    h_home_conceded = []
    last_h_date = None

    for m in home_matches:
        hs = m.home_score or 0
        aws = m.away_score or 0
        if m.home_team_id == home_team.id:
            h_goals_scored.append(hs)
            h_goals_conceded.append(aws)
            h_home_scored.append(hs)
            h_home_conceded.append(aws)
            h_results.append(1 if hs > aws else (0 if hs == aws else -1))
        else:
            h_goals_scored.append(aws)
            h_goals_conceded.append(hs)
            h_results.append(1 if aws > hs else (0 if aws == hs else -1))
        if not last_h_date:
            last_h_date = m.date

    a_goals_scored = []
    a_goals_conceded = []
    a_results = []
    a_away_scored = []
    a_away_conceded = []
    last_a_date = None

    for m in away_matches:
        hs = m.home_score or 0
        aws = m.away_score or 0
        if m.away_team_id == away_team.id:
            a_goals_scored.append(aws)
            a_goals_conceded.append(hs)
            a_away_scored.append(aws)
            a_away_conceded.append(hs)
            a_results.append(1 if aws > hs else (0 if aws == hs else -1))
        else:
            a_goals_scored.append(hs)
            a_goals_conceded.append(aws)
            a_results.append(1 if hs > aws else (0 if hs == aws else -1))
        if not last_a_date:
            last_a_date = m.date

    h_gf = np.mean(h_goals_scored[-5:]) if len(h_goals_scored) >= 1 else 1.0
    h_ga = np.mean(h_goals_conceded[-5:]) if len(h_goals_conceded) >= 1 else 1.0
    h_home_gf = np.mean(h_home_scored[-5:]) if len(h_home_scored) >= 1 else h_gf
    h_home_ga = np.mean(h_home_conceded[-5:]) if len(h_home_conceded) >= 1 else h_ga
    h_streak = sum(h_results[-5:]) if len(h_results) >= 1 else 0

    a_gf = np.mean(a_goals_scored[-5:]) if len(a_goals_scored) >= 1 else 1.0
    a_ga = np.mean(a_goals_conceded[-5:]) if len(a_goals_conceded) >= 1 else 1.0
    a_away_gf = np.mean(a_away_scored[-5:]) if len(a_away_scored) >= 1 else a_gf
    a_away_ga = np.mean(a_away_conceded[-5:]) if len(a_away_conceded) >= 1 else a_ga
    a_streak = sum(a_results[-5:]) if len(a_results) >= 1 else 0

    h_rest = (now - last_h_date).days if last_h_date else 7 if now else 7
    a_rest = (now - last_a_date).days if last_a_date else 7 if now else 7

    h2h = db.query(Match).filter(
        Match.status == "FINISHED",
        ((Match.home_team_id == home_team.id) & (Match.away_team_id == away_team.id)) |
        ((Match.home_team_id == away_team.id) & (Match.away_team_id == home_team.id)),
    ).order_by(Match.date.desc()).limit(5).all()

    h2h_h_wins = 0
    h2h_draws = 0
    h2h_a_wins = 0
    for m in h2h:
        hs = m.home_score or 0
        aws = m.away_score or 0
        if m.home_team_id == home_team.id:
            if hs > aws:
                h2h_h_wins += 1
            elif hs == aws:
                h2h_draws += 1
            else:
                h2h_a_wins += 1
        else:
            if aws > hs:
                h2h_h_wins += 1
            elif aws == hs:
                h2h_draws += 1
            else:
                h2h_a_wins += 1

    return {
        "h_avg_gf": h_gf,
        "h_avg_ga": h_ga,
        "h_home_gf": h_home_gf,
        "h_home_ga": h_home_ga,
        "h_streak": h_streak,
        "h_rest_days": h_rest,
        "a_avg_gf": a_gf,
        "a_avg_ga": a_ga,
        "a_away_gf": a_away_gf,
        "a_away_ga": a_away_ga,
        "a_streak": a_streak,
        "a_rest_days": a_rest,
        "h2h_h_wins": h2h_h_wins,
        "h2h_draws": h2h_draws,
        "h2h_a_wins": h2h_a_wins,
        "h_attack_ratio": h_home_gf / max(a_away_ga, 0.5),
        "a_attack_ratio": a_away_gf / max(h_home_ga, 0.5),
    }


def build_training_dataset(db: Session, min_matches=500):
    matches = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.home_score != None,
        Match.away_score != None,
    ).order_by(Match.date.desc()).limit(5000).all()

    features = []
    labels = []
    count = 0

    for m in matches:
        ht = db.query(Team).filter_by(id=m.home_team_id).first()
        at = db.query(Team).filter_by(id=m.away_team_id).first()
        if not ht or not at:
            continue
        try:
            feats = compute_features_for_match(db, m, ht, at)
        except Exception:
            continue
        hs = m.home_score or 0
        aws = m.away_score or 0
        if hs > aws:
            label = 0
        elif hs == aws:
            label = 1
        else:
            label = 2
        features.append([
            feats["h_avg_gf"], feats["h_avg_ga"], feats["h_home_gf"], feats["h_home_ga"],
            feats["h_streak"], feats["h_rest_days"],
            feats["a_avg_gf"], feats["a_avg_ga"], feats["a_away_gf"], feats["a_away_ga"],
            feats["a_streak"], feats["a_rest_days"],
            feats["h2h_h_wins"], feats["h2h_draws"], feats["h2h_a_wins"],
            feats["h_attack_ratio"], feats["a_attack_ratio"],
        ])
        labels.append(label)
        count += 1
        if count >= min_matches:
            break

    return np.array(features), np.array(labels)


def train_model(X, y):
    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=15,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Précision du modèle: {acc:.4f} ({acc*100:.1f}%)")
    return model, acc, X_test, y_test, y_pred


def save_model(model):
    joblib.dump(model, MODEL_PATH)
    print(f"Modèle sauvegardé: {MODEL_PATH}")


def load_model():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    return None


def predict_with_ml(db: Session, match_id, rf_proba=None):
    match = db.query(Match).filter_by(id=match_id).first()
    if not match:
        return None
    ht = db.query(Team).filter_by(id=match.home_team_id).first()
    at = db.query(Team).filter_by(id=match.away_team_id).first()
    if not ht or not at:
        return None

    feats = compute_features_for_match(db, match, ht, at)
    X = np.array([[
        feats["h_avg_gf"], feats["h_avg_ga"], feats["h_home_gf"], feats["h_home_ga"],
        feats["h_streak"], feats["h_rest_days"],
        feats["a_avg_gf"], feats["a_avg_ga"], feats["a_away_gf"], feats["a_away_ga"],
        feats["a_streak"], feats["a_rest_days"],
        feats["h2h_h_wins"], feats["h2h_draws"], feats["h2h_a_wins"],
        feats["h_attack_ratio"], feats["a_attack_ratio"],
    ]])

    if rf_proba is None:
        model = load_model()
        if model is None:
            return None
        rf_proba = model.predict_proba(X)
    else:
        rf_proba = rf_proba

    return rf_proba


def ml_prediction_to_market(probas):
    h, d, a = probas[0][0], probas[0][1], probas[0][2]
    return {
        "prob_home": round(float(h), 4),
        "prob_draw": round(float(d), 4),
        "prob_away": round(float(a), 4),
        "prob_dc_1x": round(float(h + d), 4),
        "prob_dc_12": round(float(h + a), 4),
        "prob_dc_2x": round(float(d + a), 4),
    }


def run_backtest(db: Session, model=None, min_confidence=7):
    if model is None:
        model = load_model()
    if model is None:
        print("Aucun modèle trouvé")
        return

    matches = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.home_score != None,
        Match.away_score != None,
    ).order_by(Match.date.desc()).limit(1000).all()

    results = []
    for m in matches:
        ht = db.query(Team).filter_by(id=m.home_team_id).first()
        at = db.query(Team).filter_by(id=m.away_team_id).first()
        if not ht or not at:
            continue
        try:
            feats = compute_features_for_match(db, m, ht, at)
        except Exception:
            continue
        X = np.array([[
            feats["h_avg_gf"], feats["h_avg_ga"], feats["h_home_gf"], feats["h_home_ga"],
            feats["h_streak"], feats["h_rest_days"],
            feats["a_avg_gf"], feats["a_avg_ga"], feats["a_away_gf"], feats["a_away_ga"],
            feats["a_streak"], feats["a_rest_days"],
            feats["h2h_h_wins"], feats["h2h_draws"], feats["h2h_a_wins"],
            feats["h_attack_ratio"], feats["a_attack_ratio"],
        ]])
        proba = model.predict_proba(X)[0]
        best_prob = max(proba)
        confidence = _prob_to_conf(best_prob)
        hs = m.home_score or 0
        aws = m.away_score or 0
        if hs > aws:
            actual = 0
        elif hs == aws:
            actual = 1
        else:
            actual = 2
        predicted = np.argmax(proba)
        correct = predicted == actual
        results.append({"confidence": confidence, "correct": correct, "prob": best_prob, "actual": actual, "predicted": predicted})

    df = pd.DataFrame(results)
    for conf in range(1, 11):
        subset = df[df["confidence"] == conf]
        if len(subset) == 0:
            continue
        acc = subset["correct"].mean()
        print(f"Confiance {conf}/10: {len(subset)} matchs, précision: {acc*100:.1f}%")

    high = df[df["confidence"] >= 9]
    if len(high) > 0:
        print(f"\nNotes 9-10: {len(high)} matchs, précision: {high['correct'].mean()*100:.1f}%")

    med = df[df["confidence"].between(7, 8)]
    if len(med) > 0:
        print(f"Notes 7-8: {len(med)} matchs, précision: {med['correct'].mean()*100:.1f}%")

    return df


def _prob_to_conf(prob):
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