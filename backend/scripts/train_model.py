import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from app.database import SessionLocal, engine, Base
from app.models.match import Match
from app.services.historical_collector import collect_historical_matches
from app.services.ml_engine import build_training_dataset, train_model, save_model, run_backtest, load_model


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("=== Collecte des matchs historiques (120 jours) ===")
    count = collect_historical_matches(db, days_back=120)
    print(f"  {count} nouveaux matchs ajoutés")

    total = db.query(Match).filter(
        Match.status == "FINISHED",
        Match.home_score != None,
    ).count()
    print(f"  Total matchs terminés en BDD : {total}")

    if total < 100:
        print("  Pas assez de données ! Collecte de plus de jours...")
        extra = collect_historical_matches(db, days_back=365)
        total = db.query(Match).filter(
            Match.status == "FINISHED",
            Match.home_score != None,
        ).count()
        print(f"  {extra} ajoutés, total: {total}")

    print("\n=== Construction du dataset d'entraînement ===")
    X, y = build_training_dataset(db, min_matches=min(total, 5000))
    print(f"  {len(X)} échantillons")

    print("\n=== Entraînement du modèle Random Forest ===")
    model, acc, X_test, y_test, y_pred = train_model(X, y)
    save_model(model)

    print("\n=== Backtesting ===")
    df = run_backtest(db, model)
    if df is not None and len(df) > 0:
        high = df[df["confidence"] >= 9]
        if len(high) > 0:
            print(f"\n>> RÉSULTAT: Notes 9-10 → {high['correct'].mean()*100:.1f}% de précision")

    db.close()


if __name__ == "__main__":
    main()