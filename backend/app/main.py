import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.config import ALLOWED_ORIGINS, API_UPDATE_KEY
from app.routers.coupon_router import router as coupon_router
from app.routers.web_router import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"DB init error: {e}")
    try:
        from app.firebase_db import init_firebase
        init_firebase()
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Firebase init skipped")
    yield


app = FastAPI(title="PredictX API", lifespan=lifespan)
origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(coupon_router)
app.include_router(web_router)


@app.get("/api")
def api_root():
    return {"message": "PredictX API - Pronostics football IA"}


@app.get("/api/update")
def update_data(key: str = ""):
    if API_UPDATE_KEY and key != API_UPDATE_KEY:
        raise HTTPException(status_code=403, detail="Clé API invalide")
    from app.database import SessionLocal
    from datetime import datetime
    import traceback

    expired_count = 0
    errors = []
    try:
        from app.firebase_db import init_firebase, get_db
        init_firebase()
        fb_db = get_db()
        now = datetime.now()
        expired = fb_db.collection("users").where("subscription_type", "!=", "none").get()
        for u in expired:
            data = u.to_dict()
            expiry = data.get("subscription_expiry")
            if expiry and expiry < now:
                fb_db.collection("users").document(u.id).update({
                    "subscription_type": "none",
                    "subscription_expiry": None,
                })
                expired_count += 1
    except Exception as e:
        errors.append(f"Firebase: {e}")

    db = SessionLocal()
    matches_count = 0
    predictions_count = 0
    coupon_info = None
    try:
        from app.services.data_collector import save_matches_to_db
        try:
            save_matches_to_db(db)
            matches_count = 0
        except Exception as e:
            errors.append(f"Data collection: {e}")

        from app.services.coupon_service import update_coupon_results
        try:
            update_coupon_results(db)
        except Exception as e:
            errors.append(f"Coupon update: {e}")

        from app.services.prediction_engine import predict_all_upcoming_matches
        try:
            predictions = predict_all_upcoming_matches(db)
            predictions_count = len(predictions)
        except Exception as e:
            errors.append(f"Predictions: {e}")

        from app.services.coupon_service import generate_daily_coupon
        try:
            coupon = generate_daily_coupon(db)
            coupon_info = {"id": coupon.id, "status": coupon.status} if coupon else None
        except Exception as e:
            errors.append(f"Coupon generation: {e}")

        return {
            "message": "Mise à jour terminée",
            "predictions": predictions_count,
            "coupon": coupon_info,
            "expired_subscriptions_revoked": expired_count,
            "errors": errors if errors else None,
        }
    finally:
        db.close()