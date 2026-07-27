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
    from app.services.data_collector import save_matches_to_db
    from app.services.prediction_engine import predict_all_upcoming_matches
    from app.services.coupon_service import generate_daily_coupon, update_coupon_results
    from app.firebase_db import init_firebase, get_db
    from datetime import datetime
    init_firebase()
    fb_db = get_db()
    now = datetime.now()
    expired = fb_db.collection("users").where("subscription_type", "!=", "none").get()
    expired_count = 0
    for u in expired:
        data = u.to_dict()
        expiry = data.get("subscription_expiry")
        if expiry and expiry < now:
            fb_db.collection("users").document(u.id).update({
                "subscription_type": "none",
                "subscription_expiry": None,
            })
            expired_count += 1
    db = SessionLocal()
    try:
        save_matches_to_db(db)
        update_coupon_results(db)
        predictions = predict_all_upcoming_matches(db)
        coupon = generate_daily_coupon(db)
        return {
            "message": "Mise à jour terminée",
            "predictions": len(predictions),
            "coupon": coupon.id if coupon else None,
            "coupon_status": coupon.status if coupon else None,
            "expired_subscriptions_revoked": expired_count,
        }
    finally:
        db.close()